from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from monitoramento.models import (
    ConsultaDashboardMonitoramento,
    DashboardMonitoramento,
    GraficoDashboardMonitoramento,
    ProjetoMonitoramento,
)
from monitoramento.services import execute_monitoring_query
PARAM_DEFS = [
    {"name": "DataInicio", "type": "date", "label": "Data inicial"},
    {"name": "DataFim", "type": "date", "label": "Data final"},
    {
        "name": "Periodo",
        "type": "text",
        "label": "Registros por período",
        "default": "mes",
        "options": [
            {"value": "dia", "label": "Dias"},
            {"value": "semana", "label": "Semanas"},
            {"value": "mes", "label": "Mês"},
        ],
    },
]

PARAM_SAMPLE = {"DataInicio": "2025-10-01", "DataFim": "2026-03-31", "Periodo": "mes"}


@dataclass
class DashboardSpec:
    titulo: str
    descricao: str
    base_sql: str
    distinct_key: str = ""


def _sql_templates(base_sql: str, distinct_key: str = "") -> dict[str, str]:
    count_expr = f"COUNT(DISTINCT {distinct_key})" if distinct_key else "COUNT(*)"
    return {
        "base": base_sql,
        "kpi_total": f"""
WITH base AS (
{base_sql}
)
SELECT {count_expr} AS total_registros
FROM base
""".strip(),
        "kpi_mes": f"""
WITH base AS (
{base_sql}
)
SELECT {count_expr} AS total_registros_mes
FROM base
WHERE data_referencia >= DATEFROMPARTS(YEAR(@DataFim), MONTH(@DataFim), 1)
  AND data_referencia < DATEADD(DAY, 1, CAST(@DataFim AS DATE))
""".strip(),
        "kpi_media": f"""
WITH base AS (
{base_sql}
)
SELECT
    ISNULL(CAST(ROUND(AVG(CAST(mensal.total_registros AS DECIMAL(10, 2))), 1) AS DECIMAL(10, 1)), 0) AS media_registros_mes
FROM (
    SELECT
        YEAR(data_referencia) AS ano,
        MONTH(data_referencia) AS mes,
        {count_expr} AS total_registros
    FROM base
    WHERE data_referencia IS NOT NULL
    GROUP BY YEAR(data_referencia), MONTH(data_referencia)
) mensal
""".strip(),
        "linha_periodo": f"""
WITH base AS (
{base_sql}
),
periodizado AS (
    SELECT
        base.*,
        CASE
            WHEN LOWER(ISNULL(@Periodo, 'mes')) = 'dia' THEN
                CONVERT(VARCHAR(10), CAST(base.data_referencia AS DATE), 23)
            WHEN LOWER(ISNULL(@Periodo, 'mes')) = 'semana' THEN
                CONVERT(
                    VARCHAR(10),
                    DATEADD(
                        DAY,
                        -(DATEDIFF(DAY, 0, CAST(base.data_referencia AS DATE)) % 7),
                        CAST(base.data_referencia AS DATE)
                    ),
                    23
                )
            ELSE
                CONCAT(
                    YEAR(base.data_referencia),
                    '-',
                    RIGHT('0' + CAST(MONTH(base.data_referencia) AS VARCHAR(2)), 2)
                )
        END AS referencia
    FROM base
    WHERE base.data_referencia IS NOT NULL
)
SELECT
    referencia,
    {count_expr} AS total_registros
FROM periodizado
GROUP BY referencia
ORDER BY referencia
""".strip(),
        "barra_municipio": f"""
WITH base AS (
{base_sql}
)
SELECT TOP 12
    ROW_NUMBER() OVER (ORDER BY {count_expr} DESC, municipio) AS ordem,
    municipio,
    {count_expr} AS total_registros
FROM base
GROUP BY municipio
ORDER BY ordem
""".strip(),
        "tabela_agente": f"""
WITH base AS (
{base_sql}
)
SELECT TOP 15
    agente,
    {count_expr} AS total_registros
FROM base
GROUP BY agente
ORDER BY total_registros DESC, agente
""".strip(),
    }


def _dashboard_specs() -> list[DashboardSpec]:
    return [
        DashboardSpec(
            titulo="Painel SIGMA | Relatorio Demandas",
            descricao="Dashboard derivado de 'Relatorio PDF - Demandas'.",
            base_sql="""
SELECT
    p.cod_familiar_fam,
    p.pessoa_nome AS nome_pessoa,
    ISNULL(cid.cidade, 'Municipio nao informado') AS municipio,
    pb.politica_descricao AS politica_publica,
    md.modulo_descricao AS modulo,
    ind.indicacao_descricao AS indicacao,
    area.politica_area_descricao AS area,
    pp.data_cadastro AS data_referencia,
    ISNULL(ag.usuario_nome, 'Sem agente') AS agente
FROM tbl_pessoas_politicas pp
JOIN tbl_pessoas p ON p.pessoa_id = pp.pessoa_id
LEFT JOIN cadunico cad ON cad.cod_familiar_fam = p.cod_familiar_fam AND cad.cod_parentesco_rf_pessoa = 1
LEFT JOIN p_cidades cid ON cid.ibge = cad.COD_IBGE_FAM
LEFT JOIN tbl_politicas_beneficios pb ON pb.politica_beneficio_id = pp.politica_beneficio_id
LEFT JOIN tbl_modulos md ON md.modulo_id = pb.modulo_id
LEFT JOIN tbl_politicas_indicacoes ind ON ind.indicacao_id = pb.indicacao_id
LEFT JOIN tbl_politicas_areas area ON area.politica_area_id = pb.area_id
LEFT JOIN tbl_usuarios_sigma ag ON ag.usuario_id = pp.agente_id
WHERE p.pessoa_vinculo_id IS NULL
  AND pp.data_cadastro BETWEEN @DataInicio AND @DataFim
""".strip(),
        ),
        DashboardSpec(
            titulo="Painel SIGMA | Relatorio Municipais",
            descricao="Dashboard derivado de 'Relatorio PDF - Municipais'.",
            base_sql="""
SELECT
    p.cod_familiar_fam,
    p.pessoa_nome AS nome_pessoa,
    ISNULL(cid.cidade, 'Municipio nao informado') AS municipio,
    pb.politica_descricao AS politica_publica_municipal,
    sd.pessoa_politica_municipal_status_descricao AS descricao_status,
    st.status_atividade_descricao AS status,
    ppm.data_cadastro AS data_referencia,
    ISNULL(ag.usuario_nome, 'Sem agente') AS agente
FROM tbl_pessoas_politicas_municipais ppm
JOIN tbl_pessoas p ON p.pessoa_id = ppm.pessoa_id
LEFT JOIN cadunico cad ON cad.cod_familiar_fam = p.cod_familiar_fam AND cad.cod_parentesco_rf_pessoa = 1
LEFT JOIN p_cidades cid ON cid.ibge = cad.COD_IBGE_FAM
LEFT JOIN tbl_politicas_beneficios pb ON pb.politica_beneficio_id = ppm.politica_beneficio_id
LEFT JOIN tbl_pessoas_politicas_municipais_status_descricoes sd ON sd.pessoa_politica_municipal_id = ppm.pessoa_politica_municipal_id
LEFT JOIN tbl_status_atividades st ON st.status_atividade_id = sd.status_id
LEFT JOIN tbl_usuarios_sigma ag ON ag.usuario_id = ppm.agente_id
WHERE p.pessoa_vinculo_id IS NULL
  AND ppm.data_cadastro BETWEEN @DataInicio AND @DataFim
""".strip(),
        ),
        DashboardSpec(
            titulo="Painel SIGMA | Relatorio Estrategia",
            descricao="Dashboard derivado de 'Relatorio PDF - Estrategia'.",
            base_sql="""
SELECT
    p.cod_familiar_fam,
    p.pessoa_nome AS nome_pessoa,
    ISNULL(cid.cidade, 'Municipio nao informado') AS municipio,
    pb.politica_descricao AS politica_publica,
    area.politica_area_descricao AS area,
    po.pessoa_politica_objetivo_id AS id_objetivo,
    ISNULL(pob.objetivo_descricao, po.outro_objetivo) AS descricao_objetivo,
    po.data_cadastro AS data_cadastro_objetivo,
    obj_obs.pessoa_politica_objetivo_observacao_descricao AS observacoes_objetivo,
    ISNULL(ag_obj.usuario_nome, 'Sem agente') AS agente_objetivo,
    ISNULL(aob.acao_descricao, pa.outro_acao) AS acao,
    pa.data_cadastro AS data_registro_acao,
    st_acao.status_atividade_descricao AS status_acao,
    acao_obs.pessoa_politica_acao_observacao_descricao AS observacoes_acao,
    ISNULL(ag_acao.usuario_nome, 'Sem agente') AS agente_acao,
    ISNULL(atv.atividade_descricao, pat.outro_atividade) AS atividade,
    pat.data_cadastro AS data_registro_atividade,
    st_atv.status_atividade_descricao AS status_atividade,
    atv_obs.pessoa_politica_atividade_observacao_descricao AS observacoes_atividade,
    ISNULL(ag_atv.usuario_nome, 'Sem agente') AS agente_atividade,
    pdf.data_cadastro AS data_pactuacao_pdf,
    po.data_cadastro AS data_referencia,
    ISNULL(ag_obj.usuario_nome, 'Sem agente') AS agente
FROM tbl_pessoas_politicas_objetivos po
JOIN tbl_pessoas_politicas pp ON pp.pessoa_politica_id = po.pessoa_politica_id
JOIN tbl_pessoas p ON p.pessoa_id = pp.pessoa_id
LEFT JOIN cadunico cad ON cad.cod_familiar_fam = p.cod_familiar_fam AND cad.cod_parentesco_rf_pessoa = 1
LEFT JOIN p_cidades cid ON cid.ibge = cad.COD_IBGE_FAM
LEFT JOIN tbl_politicas_beneficios pb ON pb.politica_beneficio_id = pp.politica_beneficio_id
LEFT JOIN tbl_politicas_areas area ON area.politica_area_id = pb.area_id
LEFT JOIN tbl_politicas_objetivos pob ON pob.objetivo_id = po.objetivo_id
LEFT JOIN tbl_pessoas_politicas_objetivos_observacoes obj_obs ON obj_obs.pessoa_politica_objetivo_id = po.pessoa_politica_objetivo_id
LEFT JOIN tbl_pessoas_politicas_acoes pa ON pa.pessoa_politica_objetivo_id = po.pessoa_politica_objetivo_id
LEFT JOIN tbl_acoes_objetivos aob ON aob.acao_id = pa.acao_id
LEFT JOIN tbl_pessoas_politicas_acoes_status_descricoes acs ON acs.pessoa_politica_acao_id = pa.pessoa_politica_acao_id
LEFT JOIN tbl_status_atividades st_acao ON st_acao.status_atividade_id = ISNULL(acs.status_acao_id, pa.status)
LEFT JOIN tbl_pessoas_politicas_acoes_observacoes acao_obs ON acao_obs.pessoa_politica_acao_id = pa.pessoa_politica_acao_id
LEFT JOIN tbl_pessoas_politicas_atividades pat ON pat.pessoa_politica_acao_id = pa.pessoa_politica_acao_id
LEFT JOIN tbl_atividades_acoes atv ON atv.atividade_id = pat.atividade_id
LEFT JOIN tbl_pessoas_politicas_atividades_status_descricoes ats ON ats.pessoa_politica_atividade_id = pat.pessoa_politica_atividade_id
LEFT JOIN tbl_status_atividades st_atv ON st_atv.status_atividade_id = ISNULL(ats.status_atividade_id, pat.status)
LEFT JOIN tbl_pessoas_politicas_atividades_observacoes atv_obs ON atv_obs.pessoa_politica_atividade_id = pat.pessoa_politica_atividade_id
LEFT JOIN tbl_usuarios_sigma ag_obj ON ag_obj.usuario_id = po.agente_id
LEFT JOIN tbl_usuarios_sigma ag_acao ON ag_acao.usuario_id = pa.agente_id
LEFT JOIN tbl_usuarios_sigma ag_atv ON ag_atv.usuario_id = pat.agente_id
LEFT JOIN tbl_pessoas_pdf pdf ON pdf.cod_familiar_fam = p.cod_familiar_fam
WHERE p.pessoa_vinculo_id IS NULL
  AND po.data_cadastro BETWEEN @DataInicio AND @DataFim
""".strip(),
        ),
        DashboardSpec(
            titulo="Painel SIGMA | Relatorio Familias EBIA Grave",
            descricao="Dashboard derivado de 'Relatorio de Familias - EBIA Grave'.",
            base_sql="""
SELECT
    p.pessoa_nome AS nome_rf_sigma,
    p.pessoa_cpf AS cpf_rf_sigma,
    cad.nom_pessoa AS nome_rf_cadunico,
    cad.NUM_CPF_PESSOA AS cpf_rf_cadunico,
    p.data_aceite AS data_adesao,
    cad.ebia AS resultado_ebia,
    TRY_CAST(cad.total_pessoas AS INT) AS numero_pessoas_familia,
    CASE WHEN p.envio_arquivo = 1 THEN 'SIM' ELSE NULL END AS diagnostico_finalizado,
    TRY_CAST(cad.renda_media AS DECIMAL(12,2)) AS renda_per_capita,
    cad.NUM_CEP_LOGRADOURO_FAM AS cep,
    ISNULL(cid.cidade, 'Municipio nao informado') AS municipio,
    ISNULL(ag.usuario_nome, 'Sem agente') AS agente_superacao,
    p.data_aceite AS data_referencia,
    ISNULL(ag.usuario_nome, 'Sem agente') AS agente
FROM tbl_pessoas p
LEFT JOIN cadunico cad ON cad.cod_familiar_fam = p.cod_familiar_fam AND cad.cod_parentesco_rf_pessoa = 1
LEFT JOIN p_cidades cid ON cid.ibge = cad.COD_IBGE_FAM
LEFT JOIN tbl_agentes_familias af ON af.cod_familiar_fam = p.cod_familiar_fam
LEFT JOIN tbl_usuarios_sigma ag ON ag.usuario_id = af.agente_id
WHERE p.pessoa_vinculo_id IS NULL
  AND p.termo_aceite = 1
  AND p.data_aceite BETWEEN @DataInicio AND @DataFim
  AND ISNULL(cad.ebia, '') LIKE '%GRAVE%'
""".strip(),
        ),
        DashboardSpec(
            titulo="Painel SIGMA | Relatorio Completo",
            descricao="Dashboard derivado de 'Relatorio SIGMA - Completo'.",
            base_sql="""
SELECT
    p.cod_familiar_fam,
    p.pessoa_nome AS nome_rf_sigma,
    p.pessoa_cpf AS cpf_rf_sigma,
    cad.nom_pessoa AS nome_rf_cadunico,
    cad.NUM_CPF_PESSOA AS cpf_rf_cadunico,
    ISNULL(cid.cidade, 'Municipio nao informado') AS municipio,
    cad.NUM_CEP_LOGRADOURO_FAM AS cep,
    CASE WHEN af.agente_id IS NOT NULL THEN 'SIM' ELSE 'NAO' END AS tentativa_visita_1,
    'NAO' AS tentativa_visita_2,
    'NAO' AS tentativa_visita_3,
    ISNULL(ag.usuario_nome, 'Sem agente') AS agente_responsavel,
    CASE WHEN p.termo_aceite = 1 THEN 'SIM' ELSE 'NAO' END AS pre_diagnostico,
    CASE WHEN p.termo_aceite = 1 THEN 'SIM' ELSE 'NAO' END AS aceitou_termo,
    p.data_aceite AS data_aceite_termo,
    CASE WHEN p.termo_aceite = 0 THEN 'SIM' ELSE 'NAO' END AS recusou_termo,
    CASE WHEN af.motivo_recusa IS NOT NULL THEN 'SIM' ELSE 'NAO' END AS recusou_busca_ativa,
    af.motivo_recusa AS status_busca_ativa,
    af.observacao_recusa AS observacoes_busca_ativa,
    af.data_recusa AS data_status,
    CASE WHEN cad.ebia IS NOT NULL THEN 'Sim' ELSE NULL END AS recebe_bolsa_familia,
    'Sim' AS adulto_idade_ativa,
    'Nao' AS adultos_sem_condicao_trabalho,
    'Nao' AS adultos_situacao_rua,
    NULL AS trilha_protecao_social,
    cad.ebia AS status_ebia,
    CASE WHEN p.termo_aceite = 1 THEN 'SIM' ELSE NULL END AS diagnostico_iniciado,
    CASE WHEN p.envio_arquivo = 1 THEN 'SIM' ELSE NULL END AS diagnostico_finalizado,
    cad.data_atualizacao AS data_atualizacao_cadunico,
    pdf.data_cadastro AS data_criacao_pdf,
    pdf.data_cadastro AS data_pactuacao_pdf,
    pdf.data_cadastro AS data_atualizacao_pactuacao_pdf,
    p.data_cadastro AS data_referencia,
    ISNULL(ag.usuario_nome, 'Sem agente') AS agente
FROM tbl_pessoas p
LEFT JOIN cadunico cad ON cad.cod_familiar_fam = p.cod_familiar_fam AND cad.cod_parentesco_rf_pessoa = 1
LEFT JOIN p_cidades cid ON cid.ibge = cad.COD_IBGE_FAM
LEFT JOIN tbl_agentes_familias af ON af.cod_familiar_fam = p.cod_familiar_fam
LEFT JOIN tbl_usuarios_sigma ag ON ag.usuario_id = af.agente_id
LEFT JOIN tbl_pessoas_pdf pdf ON pdf.cod_familiar_fam = p.cod_familiar_fam
WHERE p.pessoa_vinculo_id IS NULL
  AND p.data_cadastro BETWEEN @DataInicio AND @DataFim
""".strip(),
        ),
        DashboardSpec(
            titulo="Painel SIGMA | Relatorio Diagnostico Resultado",
            descricao="Dashboard derivado de 'Diagnostico_Resultado'.",
            base_sql="""
SELECT
    p.cod_familiar_fam,
    p.pessoa_cpf AS cpf_pessoa,
    COALESCE(
        NULLIF(LTRIM(RTRIM(CONVERT(VARCHAR(32), p.pessoa_cpf))), ''),
        CONCAT('RF:', CONVERT(VARCHAR(32), p.cod_familiar_fam)),
        CONCAT('PESSOA:', CONVERT(VARCHAR(32), p.pessoa_id))
    ) AS pessoa_chave,
    p.pessoa_nome,
    ISNULL(par.parentesco, 'Nao informado') AS grau_parentesco,
    CASE p.sexo_id WHEN 1 THEN 'Masculino' WHEN 2 THEN 'Feminino' ELSE 'Nao informado' END AS sexo,
    ISNULL(cr.cor_raca, 'Nao informado') AS cor_raca,
    p.pessoa_data_nascimento AS data_nascimento,
    CONCAT(q.questao_sigla, ' ', q.questao_descricao) AS questao,
    ISNULL(qr.resposta_descricao, rp.descricao_respostas) AS resposta,
    ISNULL(cid.cidade, 'Municipio nao informado') AS municipio,
    rp.data_cadastro AS data_referencia,
    ISNULL(ag.usuario_nome, 'Sem agente') AS nome_agente,
    ISNULL(ag.usuario_nome, 'Sem agente') AS agente
FROM tbl_respostas_pessoas rp
JOIN tbl_pessoas p ON p.pessoa_id = rp.pessoa_id
LEFT JOIN p_parentescos par ON par.id = p.vinculo_rf_id
LEFT JOIN p_cor_racas cr ON cr.id = p.cor_raca_id
LEFT JOIN tbl_abas_questoes q ON q.questao_id = rp.questao_id
LEFT JOIN tbl_questoes_respostas qr ON qr.id_questao = rp.questao_id AND qr.id_resposta = rp.id_resposta
LEFT JOIN cadunico cad ON cad.cod_familiar_fam = p.cod_familiar_fam AND cad.cod_parentesco_rf_pessoa = 1
LEFT JOIN p_cidades cid ON cid.ibge = cad.COD_IBGE_FAM
LEFT JOIN tbl_agentes_familias af ON af.cod_familiar_fam = p.cod_familiar_fam
LEFT JOIN tbl_usuarios_sigma ag ON ag.usuario_id = ISNULL(rp.agente_id, af.agente_id)
WHERE rp.data_cadastro BETWEEN @DataInicio AND @DataFim
""".strip(),
            distinct_key="pessoa_chave",
        ),
    ]


class Command(BaseCommand):
    help = "Cria dashboards SIGMA (um por relatorio) no projeto de monitoramento."

    def add_arguments(self, parser):
        parser.add_argument("--project-id", type=int, default=1)
        parser.add_argument("--replace-existing", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        UserModel = get_user_model()
        project_id = options["project_id"]
        replace_existing = options["replace_existing"]
        projeto = ProjetoMonitoramento.objects.filter(pk=project_id).select_related("conexao").first()
        if not projeto:
            raise CommandError(f"Projeto {project_id} nao encontrado.")
        if not hasattr(projeto, "conexao"):
            raise CommandError("Projeto sem conexao de banco cadastrada.")

        user = UserModel.objects.order_by("id").first()
        if not user:
            raise CommandError("Nenhum usuario encontrado para autoria dos dashboards.")

        created = 0
        updated = 0

        for spec in _dashboard_specs():
            existing = DashboardMonitoramento.objects.filter(projeto=projeto, titulo=spec.titulo).first()
            if existing and not replace_existing:
                self.stdout.write(self.style.WARNING(f"[skip] Dashboard ja existe: {spec.titulo}"))
                continue
            if existing and replace_existing:
                existing.delete()
                updated += 1

            dashboard = DashboardMonitoramento.objects.create(
                projeto=projeto,
                titulo=spec.titulo,
                descricao=spec.descricao,
                criado_por=user,
            )
            sqls = _sql_templates(spec.base_sql, distinct_key=spec.distinct_key)

            query_defs = [
                ("Base | Dados completos do relatorio", sqls["base"]),
                ("KPI | Total de registros no periodo", sqls["kpi_total"]),
                ("KPI | Registros no mes de referencia", sqls["kpi_mes"]),
                ("KPI | Media mensal de registros", sqls["kpi_media"]),
                ("Linha | Registros por periodo", sqls["linha_periodo"]),
                ("Barra | Registros por municipio", sqls["barra_municipio"]),
                ("Tabela | Agentes com mais registros", sqls["tabela_agente"]),
            ]

            consultas: dict[str, ConsultaDashboardMonitoramento] = {}
            for nome, sql_texto in query_defs:
                preview = execute_monitoring_query(
                    projeto.conexao,
                    sql_texto,
                    PARAM_DEFS,
                    PARAM_SAMPLE,
                    limit=20,
                )
                consulta = ConsultaDashboardMonitoramento.objects.create(
                    dashboard=dashboard,
                    nome=nome,
                    sql_texto=sql_texto,
                    colunas_json=preview["columns"],
                    parametros_json=PARAM_DEFS,
                    ultima_validacao_em=timezone.now(),
                )
                consultas[nome] = consulta

            GraficoDashboardMonitoramento.objects.create(
                dashboard=dashboard,
                consulta=consultas["KPI | Total de registros no periodo"],
                titulo="Total de registros no periodo",
                tipo_grafico=GraficoDashboardMonitoramento.TIPO_TABELA,
                ordem=1,
                ativo=True,
            )
            GraficoDashboardMonitoramento.objects.create(
                dashboard=dashboard,
                consulta=consultas["KPI | Registros no mes de referencia"],
                titulo="Registros no mes de referencia",
                tipo_grafico=GraficoDashboardMonitoramento.TIPO_TABELA,
                ordem=2,
                ativo=True,
            )
            GraficoDashboardMonitoramento.objects.create(
                dashboard=dashboard,
                consulta=consultas["KPI | Media mensal de registros"],
                titulo="Media de registros por mes",
                tipo_grafico=GraficoDashboardMonitoramento.TIPO_TABELA,
                ordem=3,
                ativo=True,
            )
            GraficoDashboardMonitoramento.objects.create(
                dashboard=dashboard,
                consulta=consultas["Linha | Registros por periodo"],
                titulo="Registros por periodo",
                tipo_grafico=GraficoDashboardMonitoramento.TIPO_LINHA,
                campo_x="referencia",
                campo_y="total_registros",
                campo_data="referencia",
                campo_detalhe="data_referencia",
                ordem=4,
                ativo=True,
            )
            GraficoDashboardMonitoramento.objects.create(
                dashboard=dashboard,
                consulta=consultas["Barra | Registros por municipio"],
                titulo="Registros por municipio",
                tipo_grafico=GraficoDashboardMonitoramento.TIPO_BARRA,
                campo_x="municipio",
                campo_y="total_registros",
                campo_data="ordem",
                campo_detalhe="municipio",
                ordem=5,
                ativo=True,
            )
            GraficoDashboardMonitoramento.objects.create(
                dashboard=dashboard,
                consulta=consultas["Tabela | Agentes com mais registros"],
                titulo="Agentes com mais registros",
                tipo_grafico=GraficoDashboardMonitoramento.TIPO_TABELA,
                ordem=6,
                ativo=True,
            )

            created += 1
            self.stdout.write(self.style.SUCCESS(f"[ok] Dashboard criado: {dashboard.titulo} (id={dashboard.id})"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Finalizado. Criados={created} | Substituidos={updated} | Projeto={projeto.id}"
            )
        )
