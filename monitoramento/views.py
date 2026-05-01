"""
Views do app `monitoramento`.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import PermissionRequiredMixin, UserPassesTestMixin
from django.db import OperationalError, ProgrammingError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, TemplateView, View

from .forms import (
    ConexaoBancoMonitoramentoForm,
    ConsultaDashboardForm,
    DashboardMonitoramentoForm,
    GraficoDashboardForm,
    ProjetoMonitoramentoForm,
    build_parameter_definitions,
    build_runtime_parameter_values,
)
from .models import (
    ConexaoBancoMonitoramento,
    ConsultaDashboardMonitoramento,
    DashboardMonitoramento,
    GraficoDashboardMonitoramento,
    ProjetoMonitoramento,
    SnapshotEsquemaMonitoramento,
)
from .services import (
    MonitoramentoError,
    build_plotly_payload,
    decrypt_secret,
    encrypt_secret,
    execute_monitoring_query,
    export_rows_to_xlsx,
    filter_rows_for_click,
    introspect_database_schema,
    serialize_schema_for_graph,
    test_external_connection,
)


User = get_user_model()


PERIODO_PARAM_DEFAULT = {
    "name": "Periodo",
    "type": "text",
    "label": "Registros por período",
    "default": "mes",
    "options": [
        {"value": "dia", "label": "Dias"},
        {"value": "semana", "label": "Semanas"},
        {"value": "mes", "label": "Mês"},
    ],
}


def _can_access_monitoramento(user) -> bool:
    """
    Determina acesso ao app de monitoramento com base nas permissoes do modulo.
    """

    if not user.is_authenticated:
        return False
    return user.is_superuser or any(
        user.has_perm(perm_name)
        for perm_name in (
            "monitoramento.view_projetomonitoramento",
            "monitoramento.add_projetomonitoramento",
            "monitoramento.change_projetomonitoramento",
            "monitoramento.delete_projetomonitoramento",
            "monitoramento.view_dashboardmonitoramento",
            "monitoramento.add_dashboardmonitoramento",
            "monitoramento.change_dashboardmonitoramento",
            "monitoramento.delete_dashboardmonitoramento",
        )
    )


class MonitoramentoAccessMixin(UserPassesTestMixin):
    def test_func(self):
        return _can_access_monitoramento(self.request.user)


class MonitoramentoHomeView(MonitoramentoAccessMixin, ListView):
    model = ProjetoMonitoramento
    template_name = "monitoramento/home.html"
    context_object_name = "projetos"
    schema_indisponivel = False

    def get_queryset(self):
        try:
            # Materializa a consulta aqui para evitar falha tardia durante a renderizacao do template.
            return list(ProjetoMonitoramento.objects.select_related("criado_por").all())
        except (ProgrammingError, OperationalError):
            self.schema_indisponivel = True
            return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["schema_indisponivel"] = self.schema_indisponivel
        if self.schema_indisponivel:
            messages.warning(
                self.request,
                "As tabelas de monitoramento ainda nao foram criadas neste ambiente. "
                "Aplique as migracoes do app para liberar esta area.",
            )
        return context


class ProjetoMonitoramentoCreateView(PermissionRequiredMixin, CreateView):
    model = ProjetoMonitoramento
    form_class = ProjetoMonitoramentoForm
    template_name = "monitoramento/projeto_form.html"
    permission_required = "monitoramento.add_projetomonitoramento"

    def form_valid(self, form):
        form.instance.criado_por = self.request.user
        messages.success(self.request, "Projeto de monitoramento criado com sucesso.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("monitoramento_projeto_detail", kwargs={"pk": self.object.pk})


class ProjetoMonitoramentoDetailView(MonitoramentoAccessMixin, DetailView):
    model = ProjetoMonitoramento
    template_name = "monitoramento/projeto_detail.html"
    context_object_name = "projeto"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        projeto = self.object
        context["has_conexao"] = hasattr(projeto, "conexao")
        context["has_esquema"] = projeto.snapshots_esquema.exists()
        context["dashboard_count"] = projeto.dashboards.count()
        return context


class ConexaoMonitoramentoUpdateView(PermissionRequiredMixin, View):
    template_name = "monitoramento/conexao_form.html"
    permission_required = "monitoramento.change_conexaobancomonitoramento"

    def get(self, request, pk):
        projeto = get_object_or_404(ProjetoMonitoramento, pk=pk)
        conexao = getattr(projeto, "conexao", None)
        initial = {}
        if conexao:
            initial["senha"] = decrypt_secret(conexao.senha_criptografada)
        form = ConexaoBancoMonitoramentoForm(instance=conexao, initial=initial)
        return self._render(request, projeto, form)

    def post(self, request, pk):
        projeto = get_object_or_404(ProjetoMonitoramento, pk=pk)
        conexao = getattr(projeto, "conexao", None)
        form = ConexaoBancoMonitoramentoForm(request.POST, instance=conexao)
        if form.is_valid():
            draft = form.save(commit=False)
            draft.projeto = projeto
            if form.cleaned_data.get("senha"):
                draft.senha_criptografada = encrypt_secret(form.cleaned_data["senha"])
            elif conexao:
                draft.senha_criptografada = conexao.senha_criptografada
            if "testar" in request.POST:
                try:
                    test_external_connection(draft)
                except Exception as exc:
                    draft.status_ultima_conexao = "erro"
                    draft.ultimo_teste_em = timezone.now()
                    draft.save()
                    messages.error(request, f"Falha ao testar a conexão: {exc}")
                else:
                    draft.status_ultima_conexao = "ok"
                    draft.ultimo_teste_em = timezone.now()
                    draft.save()
                    messages.success(request, "Conexão testada com sucesso.")
                return self._render(request, projeto, form)

            draft.save()
            messages.success(request, "Conexão salva com sucesso.")
            return redirect("monitoramento_projeto_detail", pk=projeto.pk)
        return self._render(request, projeto, form)

    def _render(self, request, projeto, form):
        from django.shortcuts import render

        return render(
            request,
            self.template_name,
            {"projeto": projeto, "form": form},
        )


class EsquemaMonitoramentoView(MonitoramentoAccessMixin, TemplateView):
    template_name = "monitoramento/esquema.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        projeto = get_object_or_404(ProjetoMonitoramento, pk=self.kwargs["pk"])
        context["projeto"] = projeto
        snapshot = projeto.snapshots_esquema.order_by("-gerado_em").first()
        if self.request.GET.get("refresh") == "1":
            if not hasattr(projeto, "conexao"):
                messages.error(self.request, "Cadastre uma conexão antes de verificar o esquema.")
            else:
                try:
                    payload = introspect_database_schema(projeto.conexao)
                except Exception as exc:
                    messages.error(self.request, f"Não foi possível gerar o esquema: {exc}")
                else:
                    snapshot = SnapshotEsquemaMonitoramento.objects.create(
                        projeto=projeto,
                        estrutura_json=payload,
                    )
                    messages.success(self.request, "Esquema atualizado com sucesso.")
        context["snapshot"] = snapshot
        context["schema_graph"] = serialize_schema_for_graph(snapshot.estrutura_json) if snapshot else {"nodes": [], "edges": []}
        return context


class DashboardProjetoListView(MonitoramentoAccessMixin, ListView):
    model = DashboardMonitoramento
    template_name = "monitoramento/dashboard_list.html"
    context_object_name = "dashboards"

    def get_queryset(self):
        self.projeto = get_object_or_404(ProjetoMonitoramento, pk=self.kwargs["pk"])
        return self.projeto.dashboards.select_related("criado_por").all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["projeto"] = self.projeto
        return context


class DashboardMonitoramentoCreateView(PermissionRequiredMixin, TemplateView):
    permission_required = "monitoramento.add_dashboardmonitoramento"
    template_name = "monitoramento/dashboard_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        projeto = get_object_or_404(ProjetoMonitoramento, pk=self.kwargs["pk"])
        context.setdefault("dashboard_form", DashboardMonitoramentoForm())
        context.setdefault("consulta_form", ConsultaDashboardForm())
        context.setdefault("grafico_form", GraficoDashboardForm())
        context["projeto"] = projeto
        context.setdefault("parameter_names", [])
        context.setdefault("preview", None)
        context.setdefault("parameter_definitions", [])
        return context

    def post(self, request, pk):
        projeto = get_object_or_404(ProjetoMonitoramento, pk=pk)
        if not hasattr(projeto, "conexao"):
            messages.error(request, "Cadastre uma conexão antes de criar um dashboard.")
            return redirect("monitoramento_conexao", pk=projeto.pk)

        dashboard_form = DashboardMonitoramentoForm(request.POST)
        consulta_form = ConsultaDashboardForm(request.POST)
        grafico_form = GraficoDashboardForm(request.POST)
        parameter_names = []
        parameter_definitions = []
        preview = None

        if consulta_form.is_valid():
            parameter_names = consulta_form.get_extracted_parameters()
            parameter_definitions = build_parameter_definitions(request.POST, parameter_names)

        if "preview" in request.POST and dashboard_form.is_valid() and consulta_form.is_valid() and grafico_form.is_valid():
            try:
                result = execute_monitoring_query(
                    projeto.conexao,
                    consulta_form.cleaned_data["sql_texto"],
                    parameter_definitions,
                    build_runtime_parameter_values(request.POST, parameter_definitions),
                    limit=100,
                )
                grafico_stub = type("GraficoStub", (), {
                    "titulo": grafico_form.cleaned_data.get("titulo") or consulta_form.cleaned_data["nome"],
                    "tipo_grafico": grafico_form.cleaned_data["tipo_grafico"],
                    "campo_x": grafico_form.cleaned_data.get("campo_x") or "",
                    "campo_y": grafico_form.cleaned_data.get("campo_y") or "",
                    "campo_serie": grafico_form.cleaned_data.get("campo_serie") or "",
                    "campo_data": grafico_form.cleaned_data.get("campo_data") or "",
                    "campo_detalhe": grafico_form.cleaned_data.get("campo_detalhe") or "",
                    "get_tipo_grafico_display": lambda self=None: "Prévia",
                })()
                preview = {
                    "result": result,
                    "chart": build_plotly_payload(grafico_stub, result["rows"]),
                }
            except Exception as exc:
                messages.error(request, f"Não foi possível gerar a prévia: {exc}")

        if "save" in request.POST and dashboard_form.is_valid() and consulta_form.is_valid() and grafico_form.is_valid():
            try:
                result = execute_monitoring_query(
                    projeto.conexao,
                    consulta_form.cleaned_data["sql_texto"],
                    parameter_definitions,
                    build_runtime_parameter_values(request.POST, parameter_definitions),
                    limit=20,
                )
            except Exception as exc:
                messages.error(request, f"A consulta não pôde ser validada: {exc}")
            else:
                dashboard = dashboard_form.save(commit=False)
                dashboard.projeto = projeto
                dashboard.criado_por = request.user
                dashboard.save()
                consulta = ConsultaDashboardMonitoramento.objects.create(
                    dashboard=dashboard,
                    nome=consulta_form.cleaned_data["nome"],
                    sql_texto=consulta_form.cleaned_data["sql_texto"],
                    colunas_json=result["columns"],
                    parametros_json=parameter_definitions,
                    ultima_validacao_em=timezone.now(),
                )
                GraficoDashboardMonitoramento.objects.create(
                    dashboard=dashboard,
                    consulta=consulta,
                    titulo=grafico_form.cleaned_data.get("titulo") or dashboard.titulo,
                    tipo_grafico=grafico_form.cleaned_data["tipo_grafico"],
                    campo_x=grafico_form.cleaned_data.get("campo_x") or "",
                    campo_y=grafico_form.cleaned_data.get("campo_y") or "",
                    campo_serie=grafico_form.cleaned_data.get("campo_serie") or "",
                    campo_data=grafico_form.cleaned_data.get("campo_data") or "",
                    campo_detalhe=grafico_form.cleaned_data.get("campo_detalhe") or "",
                    ordem=1,
                )
                messages.success(request, "Dashboard criado com sucesso.")
                return redirect("monitoramento_dashboard_detail", pk=dashboard.pk)

        return self.render_to_response(
            self.get_context_data(
                projeto=projeto,
                dashboard_form=dashboard_form,
                consulta_form=consulta_form,
                grafico_form=grafico_form,
                parameter_names=parameter_names,
                parameter_definitions=parameter_definitions,
                preview=preview,
            )
        )


class DashboardMonitoramentoUpdateView(PermissionRequiredMixin, TemplateView):
    permission_required = "monitoramento.change_dashboardmonitoramento"
    template_name = "monitoramento/dashboard_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dashboard = get_object_or_404(
            DashboardMonitoramento.objects.select_related("projeto").prefetch_related("consultas", "graficos"),
            pk=self.kwargs["pk"],
        )
        consulta = dashboard.consultas.order_by("id").first()
        grafico = dashboard.graficos.order_by("ordem", "id").first()
        context.setdefault("dashboard", dashboard)
        context.setdefault("projeto", dashboard.projeto)
        context.setdefault("dashboard_form", DashboardMonitoramentoForm(instance=dashboard))
        context.setdefault(
            "consulta_form",
            ConsultaDashboardForm(
                initial={
                    "nome": consulta.nome if consulta else "",
                    "sql_texto": consulta.sql_texto if consulta else "",
                }
            ),
        )
        context.setdefault(
            "grafico_form",
            GraficoDashboardForm(
                initial={
                    "titulo": grafico.titulo if grafico else "",
                    "tipo_grafico": grafico.tipo_grafico if grafico else "",
                    "campo_x": grafico.campo_x if grafico else "",
                    "campo_y": grafico.campo_y if grafico else "",
                    "campo_serie": grafico.campo_serie if grafico else "",
                    "campo_data": grafico.campo_data if grafico else "",
                    "campo_detalhe": grafico.campo_detalhe if grafico else "",
                }
            ),
        )
        context.setdefault("parameter_names", [])
        context.setdefault("parameter_definitions", consulta.parametros_json if consulta else [])
        context.setdefault("preview", None)
        context["is_edit_mode"] = True
        return context

    def post(self, request, pk):
        dashboard = get_object_or_404(
            DashboardMonitoramento.objects.select_related("projeto").prefetch_related("consultas", "graficos"),
            pk=pk,
        )
        projeto = dashboard.projeto
        consulta = dashboard.consultas.order_by("id").first()
        grafico = dashboard.graficos.order_by("ordem", "id").first()

        dashboard_form = DashboardMonitoramentoForm(request.POST, instance=dashboard)
        consulta_form = ConsultaDashboardForm(request.POST)
        grafico_form = GraficoDashboardForm(request.POST)
        parameter_names = []
        parameter_definitions = []
        preview = None

        if consulta_form.is_valid():
            parameter_names = consulta_form.get_extracted_parameters()
            parameter_definitions = build_parameter_definitions(request.POST, parameter_names)

        if "preview" in request.POST and dashboard_form.is_valid() and consulta_form.is_valid() and grafico_form.is_valid():
            try:
                result = execute_monitoring_query(
                    projeto.conexao,
                    consulta_form.cleaned_data["sql_texto"],
                    parameter_definitions,
                    build_runtime_parameter_values(request.POST, parameter_definitions),
                    limit=100,
                )
                grafico_stub = type("GraficoStub", (), {
                    "titulo": grafico_form.cleaned_data.get("titulo") or consulta_form.cleaned_data["nome"],
                    "tipo_grafico": grafico_form.cleaned_data["tipo_grafico"],
                    "campo_x": grafico_form.cleaned_data.get("campo_x") or "",
                    "campo_y": grafico_form.cleaned_data.get("campo_y") or "",
                    "campo_serie": grafico_form.cleaned_data.get("campo_serie") or "",
                    "campo_data": grafico_form.cleaned_data.get("campo_data") or "",
                    "campo_detalhe": grafico_form.cleaned_data.get("campo_detalhe") or "",
                    "get_tipo_grafico_display": lambda self=None: "Prévia",
                })()
                preview = {
                    "result": result,
                    "chart": build_plotly_payload(grafico_stub, result["rows"]),
                }
            except Exception as exc:
                messages.error(request, f"Não foi possível gerar a prévia: {exc}")

        if "save" in request.POST and dashboard_form.is_valid() and consulta_form.is_valid() and grafico_form.is_valid():
            try:
                result = execute_monitoring_query(
                    projeto.conexao,
                    consulta_form.cleaned_data["sql_texto"],
                    parameter_definitions,
                    build_runtime_parameter_values(request.POST, parameter_definitions),
                    limit=20,
                )
            except Exception as exc:
                messages.error(request, f"A consulta não pôde ser validada: {exc}")
            else:
                dashboard = dashboard_form.save()
                if consulta is None:
                    consulta = ConsultaDashboardMonitoramento(dashboard=dashboard)
                consulta.nome = consulta_form.cleaned_data["nome"]
                consulta.sql_texto = consulta_form.cleaned_data["sql_texto"]
                consulta.colunas_json = result["columns"]
                consulta.parametros_json = parameter_definitions
                consulta.ultima_validacao_em = timezone.now()
                consulta.save()

                if grafico is None:
                    grafico = GraficoDashboardMonitoramento(dashboard=dashboard, ordem=1, ativo=True)
                grafico.consulta = consulta
                grafico.titulo = grafico_form.cleaned_data.get("titulo") or dashboard.titulo
                grafico.tipo_grafico = grafico_form.cleaned_data["tipo_grafico"]
                grafico.campo_x = grafico_form.cleaned_data.get("campo_x") or ""
                grafico.campo_y = grafico_form.cleaned_data.get("campo_y") or ""
                grafico.campo_serie = grafico_form.cleaned_data.get("campo_serie") or ""
                grafico.campo_data = grafico_form.cleaned_data.get("campo_data") or ""
                grafico.campo_detalhe = grafico_form.cleaned_data.get("campo_detalhe") or ""
                grafico.save()

                messages.success(request, "Dashboard atualizado com sucesso.")
                return redirect("monitoramento_dashboard_detail", pk=dashboard.pk)

        return self.render_to_response(
            self.get_context_data(
                dashboard=dashboard,
                projeto=projeto,
                dashboard_form=dashboard_form,
                consulta_form=consulta_form,
                grafico_form=grafico_form,
                parameter_names=parameter_names,
                parameter_definitions=parameter_definitions,
                preview=preview,
            )
        )


class DashboardMonitoramentoDetailView(MonitoramentoAccessMixin, DetailView):
    model = DashboardMonitoramento
    template_name = "monitoramento/dashboard_detail.html"
    context_object_name = "dashboard"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dashboard = self.object
        projeto = dashboard.projeto
        graficos_payload = []
        metric_cards = []
        params_state = {}
        graficos_ativos = list(dashboard.graficos.select_related("consulta").filter(ativo=True))
        should_enable_periodo = any(_is_temporal_chart(grafico) for grafico in graficos_ativos)
        for grafico in graficos_ativos:
            param_definitions = _normalize_parameter_definitions(
                grafico.consulta.parametros_json or [],
                grafico.consulta.sql_texto,
                include_periodo=should_enable_periodo,
            )
            params_state = build_runtime_parameter_values(self.request.GET, param_definitions)
            month_reference_label = _build_month_reference_label(params_state)
            display_title = _build_display_title(
                grafico.titulo or grafico.get_tipo_grafico_display(),
                month_reference_label,
            )
            try:
                has_required = any((params_state.get(item["name"]) or "") == "" for item in param_definitions)
                if param_definitions and has_required:
                    result = {"columns": grafico.consulta.colunas_json or [], "rows": []}
                    warning = "Informe os parâmetros para carregar o dashboard."
                else:
                    result = execute_monitoring_query(
                        projeto.conexao,
                        grafico.consulta.sql_texto,
                        param_definitions,
                        params_state,
                    )
                    warning = ""
            except Exception as exc:
                result = {"columns": grafico.consulta.colunas_json or [], "rows": []}
                warning = str(exc)
            payload = build_plotly_payload(grafico, result["rows"])
            item_payload = {
                "obj": grafico,
                "consulta": grafico.consulta,
                "payload": payload,
                "table_columns": result["columns"],
                "table_rows": result["rows"],
                "warning": warning,
                "display_title": display_title,
                "subtitle": _build_chart_subtitle(grafico, param_definitions),
                "created_label": _format_created_label(dashboard),
                "updated_label": timezone.localtime(dashboard.atualizado_em).strftime("%d/%m/%Y às %H:%M:%S"),
            }
            if (
                payload.get("kind") == "table"
                and len(result["columns"]) == 1
                and len(result["rows"]) == 1
            ):
                metric_cards.append(
                    {
                        **item_payload,
                        "metric_value": result["rows"][0].get(result["columns"][0], ""),
                        "metric_column": result["columns"][0],
                    }
                )
            else:
                graficos_payload.append(item_payload)
        dashboard_parameter_definitions = []
        if dashboard.consultas.exists():
            dashboard_parameter_definitions = _normalize_parameter_definitions(
                dashboard.consultas.first().parametros_json or [],
                dashboard.consultas.first().sql_texto,
                include_periodo=should_enable_periodo,
            )
        context["metric_cards"] = metric_cards
        context["graficos_payload"] = graficos_payload
        context["parameter_definitions"] = dashboard_parameter_definitions
        context["parameter_values"] = params_state
        return context


class DashboardMonitoramentoDeleteView(PermissionRequiredMixin, View):
    permission_required = "monitoramento.delete_dashboardmonitoramento"
    def post(self, request, pk):
        dashboard = get_object_or_404(
            DashboardMonitoramento.objects.select_related("projeto"),
            pk=pk,
        )
        projeto_pk = dashboard.projeto_id
        dashboard.delete()
        messages.success(request, "Dashboard excluído com sucesso.")
        return redirect("monitoramento_dashboard_list", pk=projeto_pk)


def _format_created_label(dashboard):
    author = dashboard.criado_por.get_full_name() if dashboard.criado_por and dashboard.criado_por.get_full_name() else getattr(dashboard.criado_por, "username", "Sistema")
    return f"Criado por {author} em {timezone.localtime(dashboard.criado_em).strftime('%d/%m/%Y')}"


def _build_month_reference_label(parameter_values: dict) -> str:
    raw_date_end = (parameter_values.get("DataFim") or "").strip()
    if not raw_date_end:
        return ""

    parsed_date = None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%d/%m/%Y"):
        try:
            parsed_date = datetime.strptime(raw_date_end, fmt)
            break
        except ValueError:
            continue
    if parsed_date is None:
        return ""

    month_labels = {
        1: "janeiro",
        2: "fevereiro",
        3: "março",
        4: "abril",
        5: "maio",
        6: "junho",
        7: "julho",
        8: "agosto",
        9: "setembro",
        10: "outubro",
        11: "novembro",
        12: "dezembro",
    }
    return f"{month_labels.get(parsed_date.month, '')}/{parsed_date.year}"


def _build_display_title(title: str, month_reference_label: str) -> str:
    normalized_title = title or ""
    if "XXXX (mes)" in normalized_title:
        if month_reference_label:
            return normalized_title.replace("XXXX (mes)", month_reference_label)
        return normalized_title.replace(" - XXXX (mes)", "").replace("XXXX (mes)", "")
    return normalized_title


def _consulta_uses_periodo_parameter(sql_text: str) -> bool:
    return "@periodo" in (sql_text or "").lower()


def _is_temporal_chart(grafico) -> bool:
    return (grafico.campo_x or "").strip().lower() == "referencia" or _consulta_uses_periodo_parameter(grafico.consulta.sql_texto)


def _normalize_parameter_definitions(param_definitions: list[dict], sql_text: str = "", include_periodo: bool = False) -> list[dict]:
    normalized = [dict(item) for item in (param_definitions or []) if isinstance(item, dict)]
    has_periodo = any((item.get("name") or "").strip().lower() == "periodo" for item in normalized)
    if (include_periodo or _consulta_uses_periodo_parameter(sql_text)) and not has_periodo:
        normalized.append(dict(PERIODO_PARAM_DEFAULT))
    return normalized


def _build_chart_subtitle(grafico, param_definitions: list[dict] | None = None) -> str:
    if not _is_temporal_chart(grafico):
        return ""
    if not any((item.get("name") or "").strip().lower() == "periodo" for item in (param_definitions or [])):
        return ""
    temporal_field = (grafico.campo_detalhe or grafico.campo_data or grafico.campo_x or "").strip()
    if not temporal_field:
        return ""
    return f"Variável de tempo: {temporal_field}"


def exportar_grafico_monitoramento(request, pk):
    grafico = get_object_or_404(
        GraficoDashboardMonitoramento.objects.select_related("dashboard__projeto", "consulta"),
        pk=pk,
    )
    parameter_definitions = _normalize_parameter_definitions(
        grafico.consulta.parametros_json or [],
        grafico.consulta.sql_texto,
        include_periodo=_is_temporal_chart(grafico),
    )
    parameter_values = build_runtime_parameter_values(request.GET, parameter_definitions)
    result = execute_monitoring_query(
        grafico.dashboard.projeto.conexao,
        grafico.consulta.sql_texto,
        parameter_definitions,
        parameter_values,
    )
    clicked_x = request.GET.get("clicked_x", "")
    clicked_y = request.GET.get("clicked_y", "")
    clicked_series = request.GET.get("clicked_series", "")
    clicked_label = request.GET.get("clicked_label", "")
    periodo = (request.GET.get("Periodo") or "mes").strip().lower()

    if grafico.campo_x == "referencia" and clicked_x:
        if periodo == "mes":
            # Em series mensais, o Plotly pode enviar x como data completa (ex.: 2026-03-01T00:00:00.000Z).
            # Normalizamos para AAAA-MM para casar com o filtro por mes no relatorio base.
            month_match = re.search(r"(\d{4})-(\d{2})", str(clicked_x))
            if month_match:
                clicked_x = f"{month_match.group(1)}-{month_match.group(2)}"
        elif periodo == "semana":
            week_start_match = re.search(r"(\d{4}-\d{2}-\d{2})", str(clicked_x))
            if week_start_match:
                clicked_x = f"WEEK_START:{week_start_match.group(1)}"
        else:
            day_match = re.search(r"(\d{4}-\d{2}-\d{2})", str(clicked_x))
            if day_match:
                clicked_x = day_match.group(1)

    base_consulta = grafico.dashboard.consultas.filter(nome__istartswith="Base |").order_by("id").first()
    use_base_export = (
        base_consulta is not None
        and grafico.tipo_grafico in {
            GraficoDashboardMonitoramento.TIPO_LINHA,
            GraficoDashboardMonitoramento.TIPO_BARRA,
            GraficoDashboardMonitoramento.TIPO_BARRA_HORIZONTAL,
            GraficoDashboardMonitoramento.TIPO_AREA,
        }
    )

    if use_base_export:
        base_parameter_definitions = _normalize_parameter_definitions(
            base_consulta.parametros_json or [],
            base_consulta.sql_texto,
            include_periodo=_is_temporal_chart(grafico),
        )
        base_parameter_values = build_runtime_parameter_values(request.GET, base_parameter_definitions)
        base_result = execute_monitoring_query(
            grafico.dashboard.projeto.conexao,
            base_consulta.sql_texto,
            base_parameter_definitions,
            base_parameter_values,
        )
        export_stub = type(
            "ExportGraficoStub",
            (),
            {
                "tipo_grafico": grafico.tipo_grafico,
                "campo_x": grafico.campo_detalhe or grafico.campo_x,
                "campo_y": grafico.campo_y,
                "campo_serie": grafico.campo_serie,
                "campo_detalhe": "",
            },
        )()
        filtered_rows = filter_rows_for_click(
            export_stub,
            base_result["rows"],
            clicked_x=clicked_x,
            clicked_y=clicked_y,
            clicked_series=clicked_series,
            clicked_label=clicked_label,
        )
    else:
        filtered_rows = filter_rows_for_click(
            grafico,
            result["rows"],
            clicked_x=clicked_x,
            clicked_y=clicked_y,
            clicked_series=clicked_series,
            clicked_label=clicked_label,
        )
    content, filename = export_rows_to_xlsx(
        f"{grafico.dashboard.titulo}-{grafico.titulo or grafico.get_tipo_grafico_display()}",
        filtered_rows,
    )
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
