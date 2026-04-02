from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction
from django.db.models import F, Min, Q
from django.http import HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from auditoria.models import AuditLog
from sala_situacao.forms import NotaItemForm
from sala_situacao.models import NotaItem, nota_item_anexo_storage_ready
from usuarios.models import SetorNode

from .access import (
    filter_visible_processos_for_user,
    filter_visible_entregas_for_user,
    user_can_monitor_entrega,
    user_can_delete_processo,
    user_can_manage_entrega,
    user_can_manage_indicador,
    user_can_manage_processo,
    user_can_write_item,
    user_is_v2_admin,
    writable_group_ids_for_user,
)
from .forms import EntregaForm, EntregaMonitoramentoForm, IndicadorForm, ProcessoForm
from .models import Entrega, Indicador, Processo, MarcadorVinculoAutomaticoGrupoItem


def _user_has_any_perm(user, perms):
    return any(user.has_perm(perm) for perm in perms)


def _creator_group_ids(user):
    if not user or not getattr(user, "is_authenticated", False):
        return []
    return list(user.groups.values_list("id", flat=True))


def _variaveis_queryset_para_detalhe(indicador):
    return (
        indicador.variaveis.only(
            "id",
            "indicador_id",
            "nome",
            "periodicidade_monitoramento",
            "ordem",
        )
        .prefetch_related("grupos_monitoramento", "ciclos_monitoramento")
        .all()
    )


def _ultimos_monitoramentos_variaveis_para_detalhe(indicador):
    variaveis = list(
        indicador.variaveis.prefetch_related("grupos_monitoramento").order_by("ordem", "nome")
    )
    entregas = list(
        Entrega.objects.filter(
            variavel_monitoramento__indicador=indicador,
            monitorado_em__isnull=False,
        )
        .select_related("variavel_monitoramento", "monitorado_por__ramal_perfil")
        .order_by("variavel_monitoramento__ordem", "variavel_monitoramento__nome", "-monitorado_em", "-id")
    )
    ultimo_por_variavel = {}
    for entrega in entregas:
        variavel_id = entrega.variavel_monitoramento_id
        if variavel_id and variavel_id not in ultimo_por_variavel:
            ultimo_por_variavel[variavel_id] = entrega

    itens = []
    for variavel in variaveis:
        entrega = ultimo_por_variavel.get(variavel.id)
        usuario = getattr(entrega, "monitorado_por", None) if entrega else None
        ramal_perfil = getattr(usuario, "ramal_perfil", None) if usuario else None
        itens.append(
            {
                "variavel": variavel,
                "entrega": entrega,
                "usuario": usuario,
                "ramal_perfil": ramal_perfil,
            }
        )
    return itens


def _resolver_cascata_indicador(indicador):
    processos = Processo.objects.filter(indicadores=indicador).distinct().order_by("nome")
    processos_ids = list(processos.values_list("id", flat=True))

    entregas = Entrega.objects.filter(
        Q(processos__in=processos_ids)
        | Q(variavel_monitoramento__indicador=indicador)
        | Q(ciclo_monitoramento__variavel__indicador=indicador)
    ).distinct()
    return {
        "processos": processos,
        "entregas": entregas,
    }


def _limpar_registros_genericos_item(model_class, object_ids):
    if not object_ids:
        return
    content_type = ContentType.objects.get_for_model(model_class)
    NotaItem.objects.filter(content_type=content_type, object_id__in=object_ids).delete()
    AuditLog.objects.filter(content_type=content_type, object_id__in=[str(item_id) for item_id in object_ids]).delete()
    MarcadorVinculoAutomaticoGrupoItem.objects.filter(
        content_type=content_type,
        object_id__in=object_ids,
    ).delete()


def _limpar_dependencias_indicador_por_sql(indicador_id):
    entrega_table = connection.ops.quote_name("sala_situacao_v2_entrega")
    variavel_table = connection.ops.quote_name("sala_situacao_v2_indicadorvariavel")
    variavel_grupos_table = connection.ops.quote_name("sala_situacao_v2_indicadorvariavel_grupos_monitoramento")
    ciclo_table = connection.ops.quote_name("sala_situacao_v2_indicadorvariavelciclomonitoramento")
    valor_table = connection.ops.quote_name("sala_situacao_v2_indicadorciclovalor")

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {entrega_table}
            SET ciclo_monitoramento_id = NULL
            WHERE ciclo_monitoramento_id IN (
                SELECT id FROM {ciclo_table}
                WHERE variavel_id IN (
                    SELECT id FROM {variavel_table} WHERE indicador_id = %s
                )
            )
            """,
            [indicador_id],
        )
        cursor.execute(
            f"""
            UPDATE {entrega_table}
            SET variavel_monitoramento_id = NULL
            WHERE variavel_monitoramento_id IN (
                SELECT id FROM {variavel_table} WHERE indicador_id = %s
            )
            """,
            [indicador_id],
        )
        cursor.execute(
            f"""
            DELETE FROM {valor_table}
            WHERE variavel_id IN (
                SELECT id FROM {variavel_table} WHERE indicador_id = %s
            )
            """,
            [indicador_id],
        )
        cursor.execute(
            f"""
            DELETE FROM {variavel_grupos_table}
            WHERE indicadorvariavel_id IN (
                SELECT id FROM {variavel_table} WHERE indicador_id = %s
            )
            """,
            [indicador_id],
        )
        cursor.execute(
            f"DELETE FROM {ciclo_table} WHERE variavel_id IN (SELECT id FROM {variavel_table} WHERE indicador_id = %s)",
            [indicador_id],
        )
        cursor.execute(f"DELETE FROM {variavel_table} WHERE indicador_id = %s", [indicador_id])


def _deletar_indicador_por_sql(indicador_id):
    indicador_table = connection.ops.quote_name("sala_situacao_v2_indicador")
    grupos_resp_table = connection.ops.quote_name("sala_situacao_v2_indicador_grupos_responsaveis")
    grupos_criadores_table = connection.ops.quote_name("sala_situacao_v2_indicador_grupos_criadores")
    processo_indicadores_table = connection.ops.quote_name("sala_situacao_v2_processo_indicadores")

    with connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {grupos_resp_table} WHERE indicador_id = %s", [indicador_id])
        cursor.execute(f"DELETE FROM {grupos_criadores_table} WHERE indicador_id = %s", [indicador_id])
        cursor.execute(f"DELETE FROM {processo_indicadores_table} WHERE indicador_id = %s", [indicador_id])
        cursor.execute(f"DELETE FROM {indicador_table} WHERE id = %s", [indicador_id])


def _adicionar_contexto_calendario_formulario(context):
    context["entregas_calendario_api_url"] = reverse("sala_entrega_calendario_api")
    return context


def _opcoes_grupos_monitoramento_variaveis():
    return [
        {"id": grupo.id, "nome": grupo.name}
        for grupo in Group.objects.filter(
            id__in=SetorNode.objects.filter(ativo=True).values_list("group_id", flat=True)
        ).exclude(name__iexact="admin").order_by("name")
    ]


class AuditHistoryContextMixin:
    audit_limit = 15
    FIELD_LABEL_MAP = {
        "grupos_responsaveis": "Grupos responsáveis",
        "grupos_criadores": "Grupos criadores",
        "indicadores": "Indicadores",
        "processos": "Processos",
        "evolucao_manual": "Evolução manual",
        "data_entrega_estipulada": "Data de entrega estipulada",
        "valor_atual": "Valor calculado",
    }

    def _is_recalculo_indicador_matematico_log(self, log):
        changes = log.changes if isinstance(log.changes, dict) else {}
        if not changes or log.action != AuditLog.Action.UPDATE:
            return False
        if not isinstance(getattr(self, "object", None), Indicador):
            return False
        if not self.object.eh_indicador_matematico:
            return False
        campos = set(changes.keys())
        return "valor_atual" in campos and campos.issubset({"valor_atual", "atualizado_em"})

    def _format_log_value(self, field_name, value):
        if value is None or value == "":
            return "-"
        if isinstance(value, bool):
            return "Sim" if value else "Não"
        if field_name == "evolucao_manual":
            try:
                return f"{float(value):.0f}%"
            except Exception:
                return f"{value}%"
        if field_name == "valor_atual":
            try:
                numero = f"{float(value):.4f}".rstrip("0").rstrip(".")
                return numero or "0"
            except Exception:
                return str(value)
        if isinstance(value, list):
            return ", ".join(str(item) for item in value) if value else "-"
        if isinstance(value, str):
            dt = parse_datetime(value)
            if dt is not None:
                if timezone.is_aware(dt):
                    dt = timezone.localtime(dt)
                return dt.strftime("%d/%m/%Y %H:%M:%S")
            d = parse_date(value)
            if d is not None:
                return d.strftime("%d/%m/%Y")
        return str(value)

    def _field_label(self, field_name):
        if field_name in self.FIELD_LABEL_MAP:
            return self.FIELD_LABEL_MAP[field_name]
        try:
            field = self.object._meta.get_field(field_name)
            return str(field.verbose_name).capitalize()
        except Exception:
            return (field_name or "").replace("_", " ").capitalize()

    def _resolve_related_names(self, field_name, related_pks):
        if not related_pks:
            return []
        try:
            field = self.object._meta.get_field(field_name)
            related_model = field.related_model
            objs = related_model.objects.filter(pk__in=related_pks)
            by_pk = {obj.pk: str(obj) for obj in objs}
            return [f"{by_pk.get(pk, f'#{pk}')} (#{pk})" for pk in related_pks]
        except Exception:
            return [f"#{pk}" for pk in related_pks]

    def _build_log_details(self, log):
        changes = log.changes if isinstance(log.changes, dict) else {}
        if not changes:
            return []

        if self._is_recalculo_indicador_matematico_log(log):
            delta = changes.get("valor_atual") or {}
            old_value = delta.get("from", delta.get("old"))
            new_value = delta.get("to", delta.get("new"))
            return [
                (
                    "Valor calculado: "
                    f"{self._format_log_value('valor_atual', old_value)} "
                    f"-> {self._format_log_value('valor_atual', new_value)}"
                )
            ]

        if log.action in {AuditLog.Action.M2M_ADD, AuditLog.Action.M2M_REMOVE, AuditLog.Action.M2M_CLEAR}:
            field_name = changes.get("field") or "relacionamento"
            related_model = (changes.get("related_model") or "").strip().lower()
            if field_name == "m2m" and related_model == "auth.group":
                field_name = "grupos_responsaveis"
            label = self._field_label(field_name)
            if log.action == AuditLog.Action.M2M_CLEAR:
                return [f"{label}: todos os vínculos foram removidos."]
            related_items = changes.get("related_items") or []
            related_names = [item.get("repr") or f"#{item.get('id')}" for item in related_items if isinstance(item, dict)]
            if not related_names:
                related_pks = [int(pk) for pk in (changes.get("related_pks") or [])]
                related_names = self._resolve_related_names(field_name, related_pks)
            if related_names:
                if field_name == "grupos_responsaveis":
                    prefix = "Adicionado" if log.action == AuditLog.Action.M2M_ADD else "Excluído"
                    sufixo = "grupo" if len(related_names) == 1 else "grupos"
                    return [f"{label}: {prefix} {', '.join(related_names)} ({sufixo})."]
                prefix = "adicionados" if log.action == AuditLog.Action.M2M_ADD else "removidos"
                return [f"{label}: {prefix} {', '.join(related_names)}."]
            return [f"{label}: relacionamento atualizado."]

        details = []
        for field_name, delta in changes.items():
            if not isinstance(delta, dict):
                continue
            if field_name == "atualizado_em":
                continue
            old_value = delta.get("from", delta.get("old"))
            new_value = delta.get("to", delta.get("new"))
            if old_value is None and new_value is None:
                continue
            label = self._field_label(field_name)
            details.append(
                f"{label}: {self._format_log_value(field_name, old_value)} → {self._format_log_value(field_name, new_value)}"
            )
        return details

    def _build_log_summary(self, log):
        if self._is_recalculo_indicador_matematico_log(log):
            return "Recalculou o indicador matemático com base nos monitoramentos."
        return log.acao_resumo

    def _get_audit_logs(self):
        content_type = ContentType.objects.get_for_model(self.object.__class__)
        return (
            AuditLog.objects.select_related("user")
            .filter(content_type=content_type, object_id=str(self.object.pk))
            .order_by("-timestamp")[: self.audit_limit]
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        logs = list(self._get_audit_logs())
        context["historico_alteracoes"] = logs
        context["historico_alteracoes_formatado"] = [
            {"registro": log, "resumo": self._build_log_summary(log), "detalhes": self._build_log_details(log)}
            for log in logs
        ]
        context["ultima_alteracao_usuario"] = next((log.user for log in logs if log.user), None)
        return context


class ItemNotesContextMixin:
    nota_form_class = NotaItemForm
    notas_limit = 30

    def _get_notas(self):
        content_type = ContentType.objects.get_for_model(self.object.__class__)
        queryset = NotaItem.objects.select_related("criado_por")
        if nota_item_anexo_storage_ready():
            queryset = queryset.prefetch_related("anexos")
        return queryset.filter(content_type=content_type, object_id=self.object.pk).order_by("-criado_em")[
            : self.notas_limit
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["nota_form"] = kwargs.get("nota_form") or self.nota_form_class()
        context["nota_anexos_disponiveis"] = nota_item_anexo_storage_ready()
        context["notas_item"] = list(self._get_notas())
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        nota_form = self.nota_form_class(request.POST, request.FILES)
        if nota_form.is_valid():
            try:
                with transaction.atomic():
                    content_type = ContentType.objects.get_for_model(self.object.__class__)
                    nota = NotaItem.objects.create(
                        content_type=content_type,
                        object_id=self.object.pk,
                        texto=nota_form.cleaned_data["texto"].strip(),
                        criado_por=request.user if request.user.is_authenticated else None,
                    )
                    nota_form.save_anexos(nota, request.FILES.getlist("anexos"))
            except OSError:
                nota_form.add_error("anexos", "Nao foi possivel salvar o arquivo enviado. Verifique as permissoes da pasta de upload.")
            else:
                messages.success(request, "Nota adicionada com sucesso.")
                return HttpResponseRedirect(request.path)
        messages.error(request, "Não foi possível salvar a nota. Verifique o conteúdo informado.")
        context = self.get_context_data(nota_form=nota_form)
        return self.render_to_response(context)


class WriteAccessObjectMixin:
    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        return response

    def get_writable_group_ids(self):
        return writable_group_ids_for_user(self.request.user)

    def has_object_write_access(self, obj):
        return user_can_write_item(self.request.user, obj)

    def ensure_object_write_access(self, obj):
        if self.has_object_write_access(obj):
            return None
        return HttpResponseForbidden("Sem permissao de escrita para este item.")


class SalaSituacaoV2HomeView(LoginRequiredMixin, TemplateView):
    template_name = "sala_situacao_v2/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["indicadores"] = Indicador.objects.order_by("nome")
        context["processos"] = Processo.objects.order_by("nome")[:12]
        context["entregas"] = Entrega.objects.order_by("nome")[:12]
        return context


class IndicadorListView(LoginRequiredMixin, ListView):
    model = Indicador
    context_object_name = "indicadores"
    template_name = "sala_situacao_v2/indicador_list.html"

    def get_queryset(self):
        return Indicador.objects.order_by("nome")


class IndicadorDetailView(LoginRequiredMixin, ItemNotesContextMixin, AuditHistoryContextMixin, DetailView):
    model = Indicador
    context_object_name = "indicador"
    template_name = "sala_situacao_v2/indicador_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_manage = user_can_manage_indicador(self.request.user, self.object)
        context["can_edit"] = can_manage
        context["can_delete"] = can_manage
        context["processos"] = self.object.processos.order_by("nome")
        context["variaveis"] = _variaveis_queryset_para_detalhe(self.object)
        context["ultimos_monitoramentos_variaveis"] = _ultimos_monitoramentos_variaveis_para_detalhe(self.object)
        return context


class IndicadorCreateView(LoginRequiredMixin, PermissionRequiredMixin, WriteAccessObjectMixin, CreateView):
    permission_required = ("sala_situacao_v2.add_indicador",)
    model = Indicador
    form_class = IndicadorForm
    template_name = "sala_situacao_v2/form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["writable_group_ids"] = self.get_writable_group_ids()
        return kwargs

    def has_permission(self):
        return _user_has_any_perm(
            self.request.user,
            ("sala_situacao_v2.add_indicador", "sala_situacao.add_indicadorestrategico"),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["titulo"] = "Novo indicador"
        context["cancel_url"] = reverse("sala_indicador_estrategico_list")
        form = context.get("form")
        if form is not None:
            context["variaveis_group_options"] = _opcoes_grupos_monitoramento_variaveis()
        return _adicionar_contexto_calendario_formulario(context)

    def form_valid(self, form):
        if self.request.user.is_authenticated and not form.instance.criado_por_id:
            form.instance.criado_por = self.request.user
        response = super().form_valid(form)
        if self.object and not self.object.grupos_criadores.exists():
            self.object.grupos_criadores.set(_creator_group_ids(self.request.user))
        messages.success(self.request, "Indicador criado com sucesso.")
        return response

    def get_success_url(self):
        return reverse("sala_indicador_estrategico_detail", kwargs={"pk": self.object.pk})


class IndicadorUpdateView(LoginRequiredMixin, PermissionRequiredMixin, WriteAccessObjectMixin, UpdateView):
    permission_required = ("sala_situacao_v2.change_indicador",)
    model = Indicador
    form_class = IndicadorForm
    template_name = "sala_situacao_v2/form.html"

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not user_can_manage_indicador(request.user, self.object):
            return HttpResponseForbidden("Sem permissao para editar este indicador.")
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self):
        return user_can_manage_indicador(self.request.user, self.get_object())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["titulo"] = "Editar indicador"
        context["cancel_url"] = reverse("sala_indicador_estrategico_detail", kwargs={"pk": self.object.pk})
        form = context.get("form")
        if form is not None:
            context["variaveis_group_options"] = _opcoes_grupos_monitoramento_variaveis()
        return _adicionar_contexto_calendario_formulario(context)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["writable_group_ids"] = self.get_writable_group_ids()
        return kwargs

    def get_success_url(self):
        messages.success(self.request, "Indicador atualizado com sucesso.")
        return reverse("sala_indicador_estrategico_detail", kwargs={"pk": self.object.pk})


class IndicadorDeleteView(LoginRequiredMixin, PermissionRequiredMixin, WriteAccessObjectMixin, DeleteView):
    permission_required = ("sala_situacao_v2.delete_indicador",)
    model = Indicador
    template_name = "sala_situacao_v2/confirm_delete.html"
    success_url = reverse_lazy("sala_indicador_estrategico_list")

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not user_can_manage_indicador(request.user, self.object):
            return HttpResponseForbidden("Sem permissao para excluir este indicador.")
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self):
        return user_can_manage_indicador(self.request.user, self.get_object())

    def form_valid(self, form):
        self.object = self.get_object()
        cascata = _resolver_cascata_indicador(self.object)
        entregas_ids = list(cascata["entregas"].values_list("id", flat=True))
        processos_ids = list(cascata["processos"].values_list("id", flat=True))

        with transaction.atomic():
            if entregas_ids:
                _limpar_registros_genericos_item(Entrega, entregas_ids)
                Entrega.objects.filter(id__in=entregas_ids).delete()
            if processos_ids:
                _limpar_registros_genericos_item(Processo, processos_ids)
                Processo.objects.filter(id__in=processos_ids).delete()
            _limpar_dependencias_indicador_por_sql(self.object.pk)
            _limpar_registros_genericos_item(Indicador, [self.object.pk])
            _deletar_indicador_por_sql(self.object.pk)

        messages.success(self.request, "Indicador e cadeia relacionada excluidos com sucesso.")
        return HttpResponseRedirect(self.get_success_url())


class ProcessoListView(LoginRequiredMixin, ListView):
    model = Processo
    context_object_name = "processos"
    template_name = "sala_situacao_v2/processo_list.html"

    def get_queryset(self):
        queryset = Processo.objects.prefetch_related("indicadores").order_by("nome")
        return filter_visible_processos_for_user(queryset, self.request.user)


class ProcessoDetailView(LoginRequiredMixin, ItemNotesContextMixin, AuditHistoryContextMixin, DetailView):
    model = Processo
    context_object_name = "processo"
    template_name = "sala_situacao_v2/processo_detail.html"

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related("indicadores", "entregas")
        return filter_visible_processos_for_user(queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_manage_by_creator_group = user_can_manage_processo(self.request.user, self.object)
        context["can_edit"] = can_manage_by_creator_group
        context["can_delete"] = can_manage_by_creator_group
        entregas = list(
            filter_visible_entregas_for_user(
                self.object.entregas.all(),
                self.request.user,
            ).order_by(
                F("data_entrega_estipulada").asc(nulls_last=True),
                "nome",
                "id",
            )
        )
        for entrega in entregas:
            entrega.rotulo_numero_processo_atual = entrega.rotulo_numeracao_no_processo(self.object)
        context["entregas"] = entregas
        return context


class ProcessoCreateView(LoginRequiredMixin, PermissionRequiredMixin, WriteAccessObjectMixin, CreateView):
    permission_required = ("sala_situacao_v2.add_processo",)
    model = Processo
    form_class = ProcessoForm
    template_name = "sala_situacao_v2/form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["writable_group_ids"] = self.get_writable_group_ids()
        return kwargs

    def has_permission(self):
        return _user_has_any_perm(self.request.user, ("sala_situacao_v2.add_processo", "sala_situacao.add_processo"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["titulo"] = "Novo processo"
        context["cancel_url"] = reverse("sala_processo_list")
        indicadores = Indicador.objects.prefetch_related("grupos_responsaveis").order_by("nome")
        context["indicadores_grupos_map_json"] = {
            str(indicador.id): list(indicador.grupos_responsaveis.values_list("id", flat=True))
            for indicador in indicadores
        }
        context["indicadores_prazo_map_json"] = {
            str(indicador.id): (
                indicador.data_entrega_estipulada.isoformat() if indicador.data_entrega_estipulada else ""
            )
            for indicador in indicadores
        }
        return _adicionar_contexto_calendario_formulario(context)

    def get_success_url(self):
        messages.success(self.request, "Processo criado com sucesso.")
        return reverse("sala_processo_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        if self.request.user.is_authenticated and not form.instance.criado_por_id:
            form.instance.criado_por = self.request.user
        response = super().form_valid(form)
        if self.object and not self.object.grupos_criadores.exists():
            self.object.grupos_criadores.set(_creator_group_ids(self.request.user))
        return response


class ProcessoUpdateView(LoginRequiredMixin, PermissionRequiredMixin, WriteAccessObjectMixin, UpdateView):
    permission_required = ("sala_situacao_v2.change_processo",)
    model = Processo
    form_class = ProcessoForm
    template_name = "sala_situacao_v2/form.html"

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not user_can_manage_processo(request.user, self.object):
            return HttpResponseForbidden("Sem permissao para editar este processo.")
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self):
        return user_can_manage_processo(self.request.user, self.get_object())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["titulo"] = "Editar processo"
        context["cancel_url"] = reverse("sala_processo_detail", kwargs={"pk": self.object.pk})
        indicadores = Indicador.objects.prefetch_related("grupos_responsaveis").order_by("nome")
        context["indicadores_grupos_map_json"] = {
            str(indicador.id): list(indicador.grupos_responsaveis.values_list("id", flat=True))
            for indicador in indicadores
        }
        context["indicadores_prazo_map_json"] = {
            str(indicador.id): (
                indicador.data_entrega_estipulada.isoformat() if indicador.data_entrega_estipulada else ""
            )
            for indicador in indicadores
        }
        return _adicionar_contexto_calendario_formulario(context)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["writable_group_ids"] = self.get_writable_group_ids()
        return kwargs

    def get_success_url(self):
        messages.success(self.request, "Processo atualizado com sucesso.")
        return reverse("sala_processo_detail", kwargs={"pk": self.object.pk})


class ProcessoDeleteView(LoginRequiredMixin, PermissionRequiredMixin, WriteAccessObjectMixin, DeleteView):
    permission_required = ("sala_situacao_v2.delete_processo",)
    model = Processo
    template_name = "sala_situacao_v2/confirm_delete.html"
    success_url = reverse_lazy("sala_processo_list")

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not user_can_delete_processo(request.user, self.object):
            return HttpResponseForbidden("Sem permissao para excluir este processo.")
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self):
        return user_can_delete_processo(self.request.user, self.get_object())


class EntregaListView(LoginRequiredMixin, ListView):
    model = Entrega
    context_object_name = "entregas"
    template_name = "sala_situacao_v2/entrega_list.html"

    SORT_FIELDS = {
        "nome": "nome",
        "processo": "processo_nome_sort",
        "prazo": "data_entrega_estipulada",
        "periodo_inicio": "periodo_inicio",
        "periodo_fim": "periodo_fim",
        "progresso": "evolucao_manual",
        "atualizacao": "atualizado_em",
    }

    def _sort_param(self):
        valor = (self.request.GET.get("sort") or "prazo").strip().lower()
        return valor if valor in self.SORT_FIELDS else "prazo"

    def _dir_param(self):
        valor = (self.request.GET.get("dir") or "asc").strip().lower()
        return "desc" if valor == "desc" else "asc"

    def _order_expression(self, field_name, direction):
        if direction == "desc":
            return F(field_name).desc(nulls_last=True)
        return F(field_name).asc(nulls_last=True)

    def get_queryset(self):
        queryset = (
            Entrega.objects.prefetch_related("processos")
            .annotate(processo_nome_sort=Min("processos__nome"))
        )
        return filter_visible_entregas_for_user(queryset, self.request.user)
        
    def _ordered_queryset(self, queryset):
        sort_key = self._sort_param()
        direction = self._dir_param()
        sort_field = self.SORT_FIELDS[sort_key]
        return queryset.order_by(
            self._order_expression(sort_field, direction),
            F("nome").asc(nulls_last=True),
            "id",
        )

    def get_context_data(self, **kwargs):
        queryset = self._ordered_queryset(self.get_queryset())
        context = super().get_context_data(object_list=queryset, **kwargs)
        current_sort = self._sort_param()
        current_dir = self._dir_param()

        def _sort_url(column):
            params = self.request.GET.copy()
            params["sort"] = column
            if current_sort == column and current_dir == "asc":
                params["dir"] = "desc"
            else:
                params["dir"] = "asc"
            return f"?{params.urlencode()}"

        for entrega in context["entregas"]:
            entrega.resumo_numeracao_processos = [
                f'{item["processo"].nome}: {item["rotulo"]}'
                for item in entrega.numeracao_processos
            ]
        context["entregas_calendario_api_url"] = reverse("sala_entrega_calendario_api")
        context["current_sort"] = current_sort
        context["current_dir"] = current_dir
        context["current_dir_symbol"] = "↓" if current_dir == "desc" else "↑"
        context["sort_urls"] = {
            "nome": _sort_url("nome"),
            "processo": _sort_url("processo"),
            "prazo": _sort_url("prazo"),
            "periodo_inicio": _sort_url("periodo_inicio"),
            "periodo_fim": _sort_url("periodo_fim"),
            "progresso": _sort_url("progresso"),
            "atualizacao": _sort_url("atualizacao"),
        }
        return context


@login_required
@require_GET
def entrega_calendario_api(request):
    hoje = timezone.localdate()
    ano_raw = (request.GET.get("ano") or "").strip()
    mes_raw = (request.GET.get("mes") or "").strip()
    ano = int(ano_raw) if ano_raw.isdigit() else hoje.year
    mes = int(mes_raw) if mes_raw.isdigit() else hoje.month
    if mes < 1 or mes > 12:
        return JsonResponse({"detail": "Mês inválido."}, status=400)

    inicio = hoje.replace(year=ano, month=mes, day=1)
    if mes == 12:
        proximo_mes = inicio.replace(year=ano + 1, month=1, day=1)
    else:
        proximo_mes = inicio.replace(month=mes + 1, day=1)
    fim = proximo_mes - timedelta(days=1)

    entregas = (
        Entrega.objects.filter(data_entrega_estipulada__gte=inicio, data_entrega_estipulada__lte=fim)
        .select_related("ciclo_monitoramento", "variavel_monitoramento")
        .prefetch_related("processos")
        .order_by("data_entrega_estipulada", "nome", "id")
    )
    entregas = filter_visible_entregas_for_user(entregas, request.user)
    resultados = []
    for entrega in entregas:
        entregue = entrega.progresso_percentual >= 100
        resultados.append(
            {
                "id": entrega.pk,
                "data": entrega.data_entrega_estipulada.isoformat(),
                "periodo_inicio": entrega.periodo_inicio.isoformat() if entrega.periodo_inicio else None,
                "periodo_fim": entrega.periodo_fim.isoformat() if entrega.periodo_fim else None,
                "nome": entrega.nome,
                "descricao": (entrega.descricao or "").strip() or "Sem descrição.",
                "processos": [processo.nome for processo in entrega.processos.all()],
                "entregue": entregue,
                "status_label": "Entregue" if entregue else "Não entregue",
                "url": reverse("sala_entrega_detail", kwargs={"pk": entrega.pk}),
            }
        )

    return JsonResponse({"ano": ano, "mes": mes, "results": resultados})


class EntregaDetailView(LoginRequiredMixin, ItemNotesContextMixin, AuditHistoryContextMixin, DetailView):
    model = Entrega
    context_object_name = "entrega"
    template_name = "sala_situacao_v2/entrega_detail.html"

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related("processos__indicadores")
        return filter_visible_entregas_for_user(queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_manage = user_can_manage_entrega(self.request.user, self.object)
        can_monitor = user_can_monitor_entrega(self.request.user, self.object)
        context["can_edit"] = can_manage
        context["can_delete"] = can_manage
        context["numeracao_processos"] = self.object.numeracao_processos
        context["pode_monitorar"] = can_monitor and self.object.eh_entrega_monitoravel
        context["monitoramento_somente"] = context["pode_monitorar"] and not can_manage
        if context["pode_monitorar"]:
            context["monitoramento_form"] = kwargs.get("monitoramento_form") or EntregaMonitoramentoForm(
                instance=self.object,
                usuario=self.request.user,
            )
        context["nota_monitoramento_valor"] = kwargs.get("nota_monitoramento_valor", "")
        context["nota_monitoramento_error"] = kwargs.get("nota_monitoramento_error", "")
        context["abrir_modal_nota_monitoramento"] = kwargs.get("abrir_modal_nota_monitoramento", False)
        return context


class EntregaCreateView(LoginRequiredMixin, PermissionRequiredMixin, WriteAccessObjectMixin, CreateView):
    permission_required = ("sala_situacao_v2.add_entrega",)
    model = Entrega
    form_class = EntregaForm
    template_name = "sala_situacao_v2/form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["writable_group_ids"] = self.get_writable_group_ids()
        return kwargs

    def has_permission(self):
        return _user_has_any_perm(self.request.user, ("sala_situacao_v2.add_entrega", "sala_situacao.add_entrega"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["titulo"] = "Nova entrega"
        context["cancel_url"] = reverse("sala_entrega_list")
        form = context.get("form")
        if form is not None:
            ordered_field_names = [
                "nome",
                "descricao",
                "processos",
                "grupos_responsaveis",
                "data_entrega_estipulada",
                "evolucao_manual",
            ]
            context["ordered_form_fields"] = [
                form[name] for name in ordered_field_names if name in form.fields
            ]
        processos = Processo.objects.prefetch_related("grupos_responsaveis").order_by("nome")
        context["processos_grupos_map_json"] = {
            str(processo.id): list(processo.grupos_responsaveis.values_list("id", flat=True))
            for processo in processos
        }
        context["processos_prazo_map_json"] = {
            str(processo.id): (
                processo.data_entrega_estipulada.isoformat() if processo.data_entrega_estipulada else ""
            )
            for processo in processos
        }
        return _adicionar_contexto_calendario_formulario(context)

    def get_success_url(self):
        messages.success(self.request, "Entrega criada com sucesso.")
        return reverse("sala_entrega_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        if self.request.user.is_authenticated and not form.instance.criado_por_id:
            form.instance.criado_por = self.request.user
        response = super().form_valid(form)
        if self.object and not self.object.grupos_criadores.exists():
            self.object.grupos_criadores.set(_creator_group_ids(self.request.user))
        return response


class EntregaUpdateView(LoginRequiredMixin, PermissionRequiredMixin, WriteAccessObjectMixin, UpdateView):
    permission_required = ("sala_situacao_v2.change_entrega",)
    model = Entrega
    form_class = EntregaForm
    template_name = "sala_situacao_v2/form.html"

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not user_can_manage_entrega(request.user, self.object):
            return HttpResponseForbidden("Sem permissao para editar esta entrega.")
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self):
        return user_can_manage_entrega(self.request.user, self.get_object())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["titulo"] = "Editar entrega"
        context["cancel_url"] = reverse("sala_entrega_detail", kwargs={"pk": self.object.pk})
        form = context.get("form")
        if form is not None:
            ordered_field_names = [
                "nome",
                "descricao",
                "processos",
                "grupos_responsaveis",
                "data_entrega_estipulada",
                "evolucao_manual",
            ]
            context["ordered_form_fields"] = [
                form[name] for name in ordered_field_names if name in form.fields
            ]
        processos = Processo.objects.prefetch_related("grupos_responsaveis").order_by("nome")
        context["processos_grupos_map_json"] = {
            str(processo.id): list(processo.grupos_responsaveis.values_list("id", flat=True))
            for processo in processos
        }
        context["processos_prazo_map_json"] = {
            str(processo.id): (
                processo.data_entrega_estipulada.isoformat() if processo.data_entrega_estipulada else ""
            )
            for processo in processos
        }
        return _adicionar_contexto_calendario_formulario(context)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["writable_group_ids"] = self.get_writable_group_ids()
        return kwargs

    def get_success_url(self):
        messages.success(self.request, "Entrega atualizada com sucesso.")
        return reverse("sala_entrega_detail", kwargs={"pk": self.object.pk})


class EntregaDeleteView(LoginRequiredMixin, PermissionRequiredMixin, WriteAccessObjectMixin, DeleteView):
    permission_required = ("sala_situacao_v2.delete_entrega",)
    model = Entrega
    template_name = "sala_situacao_v2/confirm_delete.html"
    success_url = reverse_lazy("sala_entrega_list")

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not user_can_manage_entrega(request.user, self.object):
            return HttpResponseForbidden("Sem permissao para excluir esta entrega.")
        return super().dispatch(request, *args, **kwargs)

    def has_permission(self):
        return user_can_manage_entrega(self.request.user, self.get_object())


class EntregaMonitorarView(LoginRequiredMixin, View):
    template_name = "sala_situacao_v2/entrega_detail.html"

    def _render_detail_com_erros(self, request, entrega, monitoramento_form, nota_texto="", nota_error=""):
        detail_view = EntregaDetailView()
        detail_view.setup(request, pk=entrega.pk)
        detail_view.object = entrega
        context = detail_view.get_context_data(
            object=entrega,
            monitoramento_form=monitoramento_form,
            nota_monitoramento_valor=nota_texto,
            nota_monitoramento_error=nota_error,
            abrir_modal_nota_monitoramento=True,
        )
        return detail_view.render_to_response(context)

    def post(self, request, pk):
        entrega = get_object_or_404(Entrega, pk=pk)
        if not user_can_monitor_entrega(request.user, entrega):
            return HttpResponseForbidden("Sem permissao para monitorar esta entrega.")

        nota_texto = (request.POST.get("nota_monitoramento") or "").strip()
        form = EntregaMonitoramentoForm(request.POST, request.FILES, instance=entrega, usuario=request.user)
        nota_error = ""
        if not nota_texto:
            nota_error = "A nota a equipe e obrigatoria para concluir o monitoramento."

        if form.is_valid() and not nota_error:
            with transaction.atomic():
                form.save()
                NotaItem.objects.create(
                    content_type=ContentType.objects.get_for_model(Entrega),
                    object_id=entrega.pk,
                    texto=nota_texto,
                    criado_por=request.user if request.user.is_authenticated else None,
                )
            messages.success(request, "Monitoramento registrado com nota para a equipe.")
            return HttpResponseRedirect(reverse("sala_entrega_detail", kwargs={"pk": entrega.pk}))

        messages.error(request, "Falha ao registrar monitoramento. Revise os dados e a nota da equipe.")
        return self._render_detail_com_erros(
            request,
            entrega,
            form,
            nota_texto=nota_texto,
            nota_error=nota_error,
        )
