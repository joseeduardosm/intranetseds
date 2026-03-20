"""
Serviços do app `monitoramento`.
"""

from __future__ import annotations

import base64
import ctypes
import importlib.util
import json
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Random import get_random_bytes
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import ConexaoBancoMonitoramento, GraficoDashboardMonitoramento


PARAMETER_RE = re.compile(r"(?<!@)@([A-Za-z_][A-Za-z0-9_]*)")
FORBIDDEN_SQL_RE = re.compile(
    r"\b(DECLARE|USE|GO|ALTER|DROP|INSERT|UPDATE|DELETE|EXEC|EXECUTE|MERGE|TRUNCATE|CREATE)\b",
    re.IGNORECASE,
)


class MonitoramentoError(Exception):
    """Erro de domínio do app de monitoramento."""


def _runtime_odbc_dir() -> Path:
    return Path(settings.BASE_DIR) / ".runtime" / "odbc"


def _configure_local_sqlserver_odbc() -> None:
    unixodbc_dir = Path.home() / ".local" / "opt" / "unixodbc"
    freetds_dir = Path.home() / ".local" / "opt" / "freetds"
    libodbc = unixodbc_dir / "lib" / "libodbc.so.2"
    libodbcinst = unixodbc_dir / "lib" / "libodbcinst.so.2"
    freetds_driver = freetds_dir / "lib" / "libtdsodbc.so"
    freetds_conf = freetds_dir / "etc" / "freetds.conf"
    if not (libodbc.exists() and libodbcinst.exists() and freetds_driver.exists() and freetds_conf.exists()):
        return

    runtime_dir = _runtime_odbc_dir()
    runtime_dir.mkdir(parents=True, exist_ok=True)

    odbcinst_ini = runtime_dir / "odbcinst.ini"
    odbcinst_ini.write_text(
        "\n".join(
            [
                "[ODBC Driver 17 for SQL Server]",
                "Description=FreeTDS ODBC driver local para SQL Server",
                f"Driver={freetds_driver}",
                "UsageCount=1",
                "",
            ]
        ),
        encoding="utf-8",
    )

    os.environ["ODBCSYSINI"] = str(runtime_dir)
    os.environ["ODBCINSTINI"] = "odbcinst.ini"
    os.environ["FREETDSCONF"] = str(freetds_conf)

    # Precarrega o driver manager local para permitir importar pyodbc sem dependencia global.
    ctypes.CDLL(str(libodbcinst), mode=ctypes.RTLD_GLOBAL)
    ctypes.CDLL(str(libodbc), mode=ctypes.RTLD_GLOBAL)


def _get_secret_key_bytes() -> bytes:
    raw_key = getattr(settings, "MONITORAMENTO_SECRET_KEY", "") or settings.SECRET_KEY
    return SHA256.new(raw_key.encode("utf-8")).digest()


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    cipher = AES.new(_get_secret_key_bytes(), AES.MODE_EAX)
    ciphertext, tag = cipher.encrypt_and_digest(value.encode("utf-8"))
    payload = cipher.nonce + tag + ciphertext
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    payload = base64.urlsafe_b64decode(value.encode("ascii"))
    nonce = payload[:16]
    tag = payload[16:32]
    ciphertext = payload[32:]
    cipher = AES.new(_get_secret_key_bytes(), AES.MODE_EAX, nonce=nonce)
    return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")


def validate_read_only_sql(sql_text: str) -> None:
    normalized = (sql_text or "").strip()
    if not normalized:
        raise ValidationError("Informe um SQL para a consulta.")
    normalized_no_semicolon = normalized[:-1].strip() if normalized.endswith(";") else normalized
    if ";" in normalized_no_semicolon:
        raise ValidationError("Use apenas uma consulta por vez.")
    if not re.match(r"^(SELECT|WITH)\b", normalized, re.IGNORECASE):
        raise ValidationError("A consulta deve iniciar com SELECT ou WITH.")
    forbidden = FORBIDDEN_SQL_RE.search(normalized)
    if forbidden:
        raise ValidationError(
            f"Comando não permitido na consulta: {forbidden.group(1).upper()}."
        )


def extract_sql_parameters(sql_text: str) -> list[str]:
    names = []
    seen = set()
    for match in PARAMETER_RE.finditer(sql_text or ""):
        name = match.group(1)
        if name not in seen:
            names.append(name)
            seen.add(name)
    return names


def convert_parameter_value(param_type: str, raw_value: str):
    value = (raw_value or "").strip()
    if value == "":
        return None
    if param_type == "date":
        return datetime.strptime(value, "%Y-%m-%d").date()
    if param_type == "datetime":
        return datetime.fromisoformat(value)
    if param_type == "integer":
        return int(value)
    if param_type == "decimal":
        return Decimal(value)
    return value


def _compile_sql(sql_text: str, param_definitions: list[dict], param_values: dict, tipo_banco: str):
    placeholder = "%s" if tipo_banco == ConexaoBancoMonitoramento.TIPO_MYSQL else "?"
    values = []
    type_map = {item["name"]: item.get("type") or "text" for item in param_definitions}

    def repl(match):
        name = match.group(1)
        values.append(convert_parameter_value(type_map.get(name, "text"), param_values.get(name, "")))
        return placeholder

    compiled = PARAMETER_RE.sub(repl, sql_text)
    return compiled, values


def _require_module(module_name: str):
    if importlib.util.find_spec(module_name) is None:
        raise MonitoramentoError(f"Dependência ausente no ambiente: {module_name}.")


def open_external_connection(config: ConexaoBancoMonitoramento):
    password = decrypt_secret(config.senha_criptografada)
    if config.tipo_banco == ConexaoBancoMonitoramento.TIPO_MYSQL:
        _require_module("MySQLdb")
        import MySQLdb

        return MySQLdb.connect(
            host=config.host,
            port=int(config.porta),
            user=config.usuario,
            passwd=password,
            db=config.database,
            charset="utf8mb4",
            connect_timeout=10,
        )
    if config.tipo_banco == ConexaoBancoMonitoramento.TIPO_SQLSERVER:
        _require_module("pyodbc")
        _configure_local_sqlserver_odbc()
        import pyodbc

        explicit_driver = os.environ.get("MONITORAMENTO_SQLSERVER_ODBC_DRIVER", "").strip()
        preferred_drivers = [
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "FreeTDS",
        ]
        if explicit_driver:
            preferred_drivers.insert(0, explicit_driver)

        available_drivers = list(pyodbc.drivers())
        candidates = []
        for driver in preferred_drivers + available_drivers:
            if driver and driver not in candidates:
                candidates.append(driver)

        last_error = None
        for driver in candidates:
            connection_string = (
                f"DRIVER={{{driver}}};"
                f"SERVER={config.host},{config.porta};"
                f"DATABASE={config.database};"
                f"UID={config.usuario};PWD={password};"
                "TrustServerCertificate=yes;"
            )
            try:
                return pyodbc.connect(connection_string, timeout=10)
            except Exception as exc:
                last_error = exc
                continue
        raise MonitoramentoError(
            "Não foi possível conectar ao SQL Server com os drivers ODBC disponíveis. "
            f"Drivers testados: {', '.join(candidates) or 'nenhum'}. "
            f"Último erro: {last_error}"
        )
    raise MonitoramentoError("Tipo de banco não suportado.")


def test_external_connection(config: ConexaoBancoMonitoramento) -> None:
    connection = open_external_connection(config)
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
    finally:
        connection.close()


def introspect_database_schema(config: ConexaoBancoMonitoramento) -> dict:
    connection = open_external_connection(config)
    try:
        cursor = connection.cursor()
        if config.tipo_banco == ConexaoBancoMonitoramento.TIPO_MYSQL:
            cursor.execute(
                """
                SELECT table_name, column_name, data_type, column_key
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY table_name, ordinal_position
                """,
                [config.database],
            )
            columns_rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT table_name, column_name, referenced_table_name, referenced_column_name
                FROM information_schema.key_column_usage
                WHERE table_schema = %s
                  AND referenced_table_name IS NOT NULL
                ORDER BY table_name, column_name
                """,
                [config.database],
            )
            relation_rows = cursor.fetchall()
        else:
            cursor.execute(
                """
                SELECT
                    c.TABLE_NAME,
                    c.COLUMN_NAME,
                    c.DATA_TYPE,
                    CASE WHEN tc.CONSTRAINT_TYPE = 'PRIMARY KEY' THEN 'PRI' ELSE '' END
                FROM INFORMATION_SCHEMA.COLUMNS c
                LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                  ON c.TABLE_SCHEMA = kcu.TABLE_SCHEMA
                 AND c.TABLE_NAME = kcu.TABLE_NAME
                 AND c.COLUMN_NAME = kcu.COLUMN_NAME
                LEFT JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                  ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                 AND kcu.TABLE_SCHEMA = tc.TABLE_SCHEMA
                WHERE c.TABLE_CATALOG = ?
                ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
                """,
                [config.database],
            )
            columns_rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT
                    fk.TABLE_NAME,
                    cu.COLUMN_NAME,
                    pk.TABLE_NAME,
                    pt.COLUMN_NAME
                FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
                JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS fk
                  ON rc.CONSTRAINT_NAME = fk.CONSTRAINT_NAME
                JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS pk
                  ON rc.UNIQUE_CONSTRAINT_NAME = pk.CONSTRAINT_NAME
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE cu
                  ON rc.CONSTRAINT_NAME = cu.CONSTRAINT_NAME
                JOIN (
                    SELECT i1.TABLE_NAME, i2.COLUMN_NAME, i1.CONSTRAINT_NAME
                    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS i1
                    JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE i2
                      ON i1.CONSTRAINT_NAME = i2.CONSTRAINT_NAME
                    WHERE i1.CONSTRAINT_TYPE = 'PRIMARY KEY'
                ) pt
                  ON pt.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME
                WHERE fk.TABLE_CATALOG = ?
                ORDER BY fk.TABLE_NAME, cu.COLUMN_NAME
                """,
                [config.database],
            )
            relation_rows = cursor.fetchall()

        table_map = defaultdict(lambda: {"name": "", "columns": [], "relations": []})
        for table_name, column_name, data_type, key_type in columns_rows:
            table_map[table_name]["name"] = table_name
            table_map[table_name]["columns"].append(
                {
                    "name": column_name,
                    "type": data_type,
                    "is_primary_key": key_type == "PRI",
                }
            )
        relations = []
        for table_name, column_name, ref_table, ref_column in relation_rows:
            relation = {
                "from_table": table_name,
                "from_column": column_name,
                "to_table": ref_table,
                "to_column": ref_column,
            }
            relations.append(relation)
            table_map[table_name]["relations"].append(relation)

        tables = list(table_map.values())
        return {
            "tables": tables,
            "relations": relations,
            "generated_at": timezone.localtime(timezone.now()).isoformat(),
        }
    finally:
        connection.close()


def execute_monitoring_query(config, sql_text, param_definitions, param_values, limit=None):
    validate_read_only_sql(sql_text)
    compiled_sql, values = _compile_sql(sql_text, param_definitions, param_values, config.tipo_banco)

    connection = open_external_connection(config)
    try:
        cursor = connection.cursor()
        cursor.execute(compiled_sql, values)
        columns = [column[0] for column in cursor.description or []]
        fetched_rows = cursor.fetchmany(int(limit)) if limit else cursor.fetchall()
        rows = [dict(zip(columns, row)) for row in fetched_rows]
        return {"columns": columns, "rows": rows}
    finally:
        connection.close()


def build_plotly_payload(grafico, rows):
    title = grafico.titulo or grafico.get_tipo_grafico_display()
    x_field = grafico.campo_x
    y_field = grafico.campo_y
    serie_field = grafico.campo_serie
    chart_type = grafico.tipo_grafico

    if chart_type == GraficoDashboardMonitoramento.TIPO_TABELA:
        return {
            "kind": "table",
            "title": title,
            "columns": list(rows[0].keys()) if rows else [],
            "rows": rows,
        }

    if serie_field:
        grouped = defaultdict(list)
        for row in rows:
            grouped[row.get(serie_field)].append(row)
        traces = []
        for serie_name, serie_rows in grouped.items():
            sort_field = grafico.campo_data or (
                x_field if chart_type in {GraficoDashboardMonitoramento.TIPO_LINHA, GraficoDashboardMonitoramento.TIPO_AREA}
                else None
            )
            trace = _build_trace(
                chart_type,
                serie_rows,
                x_field,
                y_field,
                serie_name,
                sort_field,
            )
            traces.append(trace)
    else:
        sort_field = grafico.campo_data or (
            x_field if chart_type in {GraficoDashboardMonitoramento.TIPO_LINHA, GraficoDashboardMonitoramento.TIPO_AREA}
            else None
        )
        traces = [_build_trace(chart_type, rows, x_field, y_field, None, sort_field)]

    return {
        "kind": "plotly",
        "title": title,
        "traces": traces,
        "layout": _build_layout(chart_type, grafico),
        "config": {
            "responsive": True,
            "displaylogo": False,
            "toImageButtonOptions": {"format": "jpeg", "filename": "monitoramento", "scale": 2},
        },
    }


def _parse_trace_sort_value(value):
    if value in (None, ""):
        return (3, "")
    if isinstance(value, (int, float, Decimal)):
        return (0, value)
    if isinstance(value, datetime):
        return (0, value)

    text = str(value).strip()
    if re.match(r"^\d{4}-\d{2}$", text):
        try:
            return (0, datetime.strptime(text, "%Y-%m"))
        except ValueError:
            pass
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        try:
            return (0, datetime.strptime(text, "%Y-%m-%d"))
        except ValueError:
            pass
    if re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", text):
        try:
            return (0, datetime.fromisoformat(text.replace(" ", "T")))
        except ValueError:
            pass
    try:
        return (1, Decimal(text))
    except (InvalidOperation, ValueError):
        return (2, text)


def _sorted_trace_rows(rows, sort_field):
    if not sort_field:
        return rows
    return sorted(rows, key=lambda row: _parse_trace_sort_value(row.get(sort_field)))


def _build_trace(chart_type, rows, x_field, y_field, serie_name, sort_field=None):
    if chart_type in {
        GraficoDashboardMonitoramento.TIPO_LINHA,
        GraficoDashboardMonitoramento.TIPO_AREA,
        GraficoDashboardMonitoramento.TIPO_BARRA,
        GraficoDashboardMonitoramento.TIPO_BARRA_HORIZONTAL,
        GraficoDashboardMonitoramento.TIPO_DISPERSAO,
    }:
        rows = _sorted_trace_rows(rows, sort_field)
    if chart_type == GraficoDashboardMonitoramento.TIPO_LINHA:
        return {
            "type": "scatter",
            "mode": "lines+markers",
            "name": serie_name or "",
            "x": [row.get(x_field) for row in rows],
            "y": [row.get(y_field) for row in rows],
            "line": {"color": "#1f2a44", "width": 3, "shape": "spline"},
            "marker": {"size": 8, "color": "#d94f04", "line": {"color": "#ffffff", "width": 1.5}},
            "hovertemplate": "%{x}<br>%{y}<extra></extra>",
        }
    if chart_type == GraficoDashboardMonitoramento.TIPO_AREA:
        return {
            "type": "scatter",
            "mode": "lines",
            "fill": "tozeroy",
            "name": serie_name or "",
            "x": [row.get(x_field) for row in rows],
            "y": [row.get(y_field) for row in rows],
            "line": {"color": "#d94f04", "width": 3, "shape": "spline"},
            "fillcolor": "rgba(217, 79, 4, 0.18)",
            "hovertemplate": "%{x}<br>%{y}<extra></extra>",
        }
    if chart_type == GraficoDashboardMonitoramento.TIPO_BARRA:
        return {
            "type": "bar",
            "name": serie_name or "",
            "x": [row.get(x_field) for row in rows],
            "y": [row.get(y_field) for row in rows],
            "marker": {"color": "#1f2a44"},
            "hovertemplate": "%{x}<br>%{y}<extra></extra>",
        }
    if chart_type == GraficoDashboardMonitoramento.TIPO_BARRA_HORIZONTAL:
        return {
            "type": "bar",
            "orientation": "h",
            "name": serie_name or "",
            "x": [row.get(y_field) for row in rows],
            "y": [row.get(x_field) for row in rows],
            "marker": {"color": "#0f766e"},
            "hovertemplate": "%{y}<br>%{x}<extra></extra>",
        }
    if chart_type == GraficoDashboardMonitoramento.TIPO_DISPERSAO:
        return {
            "type": "scatter",
            "mode": "markers",
            "name": serie_name or "",
            "x": [row.get(x_field) for row in rows],
            "y": [row.get(y_field) for row in rows],
        }
    if chart_type == GraficoDashboardMonitoramento.TIPO_PIZZA:
        return {
            "type": "pie",
            "name": serie_name or "",
            "labels": [row.get(x_field) for row in rows],
            "values": [row.get(y_field) for row in rows],
            "hole": 0.35,
            "marker": {"colors": ["#1f2a44", "#d94f04", "#0f766e", "#f59e0b", "#475569", "#94a3b8"]},
        }
    return {
        "type": "bar",
        "name": serie_name or "",
        "x": [row.get(x_field) for row in rows],
        "y": [row.get(y_field) for row in rows],
    }


def _build_layout(chart_type, grafico):
    if chart_type == GraficoDashboardMonitoramento.TIPO_PIZZA:
        return {
            "margin": {"l": 16, "r": 16, "t": 20, "b": 20},
            "paper_bgcolor": "#ffffff",
            "plot_bgcolor": "#ffffff",
        }
    if chart_type == GraficoDashboardMonitoramento.TIPO_BARRA_HORIZONTAL:
        return {
            "margin": {"l": 140, "r": 20, "t": 20, "b": 40},
            "xaxis": {"title": grafico.campo_y or "Valor"},
            "yaxis": {"automargin": True},
            "paper_bgcolor": "#ffffff",
            "plot_bgcolor": "#ffffff",
        }
    return {
        "margin": {"l": 48, "r": 20, "t": 20, "b": 40},
        "xaxis": {"title": grafico.campo_x or "Eixo X", "gridcolor": "rgba(31, 42, 68, 0.08)"},
        "yaxis": {"title": grafico.campo_y or "Eixo Y", "rangemode": "tozero", "gridcolor": "rgba(31, 42, 68, 0.08)"},
        "paper_bgcolor": "#ffffff",
        "plot_bgcolor": "#ffffff",
    }


def filter_rows_for_click(
    grafico,
    rows,
    clicked_x="",
    clicked_y="",
    clicked_series="",
    clicked_label="",
):
    def _parse_date_like(value):
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        text = (str(value or "")).strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text.replace(" ", "T"))
        except ValueError:
            return None

    def _matches_clicked(row_value, clicked_value):
        clicked = (str(clicked_value or "")).strip()
        if not clicked:
            return True
        parsed = _parse_date_like(row_value)
        if clicked.startswith("WEEK_START:"):
            if not parsed:
                return False
            week_start = clicked.replace("WEEK_START:", "", 1)
            try:
                clicked_start = datetime.strptime(week_start, "%Y-%m-%d").date()
            except ValueError:
                return False
            row_date = parsed.date()
            row_week_start = row_date - timedelta(days=row_date.weekday())
            return row_week_start == clicked_start
        if parsed:
            if re.match(r"^\d{4}-\d{2}$", clicked):
                return parsed.strftime("%Y-%m") == clicked
            if re.match(r"^\d{4}-\d{2}-\d{2}$", clicked):
                return parsed.strftime("%Y-%m-%d") == clicked
            if re.match(r"^\d{2}/\d{2}/\d{4}$", clicked):
                return parsed.strftime("%d/%m/%Y") == clicked
        return str(row_value or "") == clicked

    chart_type = grafico.tipo_grafico
    filtered = rows
    if chart_type == GraficoDashboardMonitoramento.TIPO_PIZZA:
        if clicked_label:
            filtered = [row for row in filtered if _matches_clicked(row.get(grafico.campo_x, ""), clicked_label)]
    elif chart_type == GraficoDashboardMonitoramento.TIPO_BARRA_HORIZONTAL:
        if clicked_y:
            filtered = [row for row in filtered if _matches_clicked(row.get(grafico.campo_x, ""), clicked_y)]
    else:
        if clicked_x:
            filtered = [row for row in filtered if _matches_clicked(row.get(grafico.campo_x, ""), clicked_x)]
    if grafico.campo_serie and clicked_series:
        filtered = [row for row in filtered if _matches_clicked(row.get(grafico.campo_serie, ""), clicked_series)]
    if (
        grafico.campo_detalhe
        and clicked_y
        and not clicked_x
        and chart_type not in {
        GraficoDashboardMonitoramento.TIPO_PIZZA,
        GraficoDashboardMonitoramento.TIPO_BARRA_HORIZONTAL,
        }
    ):
        filtered = [
            row
            for row in filtered
            if _matches_clicked(row.get(grafico.campo_detalhe, row.get(grafico.campo_y, "")), clicked_y)
        ]
    return filtered


def export_rows_to_xlsx(filename_base: str, rows: list[dict]) -> tuple[bytes, str]:
    try:
        from openpyxl import Workbook
    except ModuleNotFoundError as exc:
        raise MonitoramentoError("openpyxl não está instalado no ambiente.") from exc

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Dados"
    headers = list(rows[0].keys()) if rows else ["Sem resultados"]
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(header, "") for header in headers])
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", filename_base).strip("-") or "monitoramento"
    return output.getvalue(), f"{safe_name}.xlsx"


def serialize_schema_for_graph(schema_payload: dict) -> dict:
    tables = schema_payload.get("tables") or []
    relations = schema_payload.get("relations") or []
    nodes = []
    edges = []
    for index, table in enumerate(tables):
        nodes.append(
            {
                "id": table["name"],
                "label": table["name"],
                "x": (index % 4) * 1.8,
                "y": -(index // 4) * 1.4,
                "columns": table.get("columns", []),
            }
        )
    for relation in relations:
        edges.append(
            {
                "source": relation["from_table"],
                "target": relation["to_table"],
                "label": f"{relation['from_column']} -> {relation['to_column']}",
            }
        )
    return {"nodes": nodes, "edges": edges}
