from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.models import OuterRef, Prefetch, Q, Subquery
from django.db.models.functions import Coalesce, Greatest
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from auditoria.models import AuditLog
from usuarios.utils import usuarios_visiveis

from .forms import (
    EntregaSistemaForm,
    EtapaProcessoRequisitoAtualizacaoForm,
    EtapaSistemaAtualizacaoForm,
    GerarNovoSistemaAPartirProcessosForm,
    GerarProcessoTransformacaoForm,
    InteressadoSistemaForm,
    NotaSistemaForm,
    NotaEtapaSistemaForm,
    ProcessoRequisitoForm,
    SistemaFiltroForm,
    SistemaForm,
)
from .models import (
    HistoricoSistema,
    ProcessoRequisito,
    EntregaSistema,
    EtapaProcessoRequisito,
    EtapaSistema,
    HistoricoProcessoRequisito,
    HistoricoEtapaSistema,
    HistoricoEtapaProcessoRequisito,
    InteressadoSistema,
    InteressadoSistemaManual,
    Sistema,
)
from .services import (
    adicionar_nota_etapa,
    adicionar_nota_sistema,
    atualizar_etapa_com_historico,
    atualizar_etapa_processo_requisito,
    atualizar_processo_requisito,
    entrega_pode_ser_publicada,
    etapa_pode_alterar_status_em_rascunho,
    criar_entrega_com_etapas,
    criar_processo_requisito,
    excluir_entrega_sistema,
    excluir_sistema,
    excluir_processo_requisito,
    gerar_ciclo_a_partir_processo,
    gerar_novo_sistema_a_partir_processos,
    publicar_entrega,
    sistema_pode_gerar_novo_sistema,
)


User = get_user_model()


def _historico_sistema_disponivel() -> bool:
    tabela = HistoricoSistema._meta.db_table
    cache = getattr(_historico_sistema_disponivel, "_cache", None)
    if cache is None:
        cache = set(connection.introspection.table_names())
        _historico_sistema_disponivel._cache = cache
    return tabela in cache


def _usuario_tem_acesso_global_acompanhamento(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return (
        user.is_superuser
        or user.has_perm("acompanhamento_sistemas.view_sistema")
        or user.has_perm("acompanhamento_sistemas.add_sistema")
        or user.has_perm("acompanhamento_sistemas.change_sistema")
        or user.has_perm("acompanhamento_sistemas.delete_sistema")
        or user.has_perm("acompanhamento_sistemas.view_entregasistema")
        or user.has_perm("acompanhamento_sistemas.change_entregasistema")
        or user.has_perm("acompanhamento_sistemas.view_etapasistema")
        or user.has_perm("acompanhamento_sistemas.change_etapasistema")
    )


def _usuario_tem_acesso_como_interessado(user) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and InteressadoSistema.objects.filter(usuario=user).exists()
    )


def _usuario_eh_interessado_do_sistema(user, sistema) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and sistema.interessados.filter(usuario=user).exists()
    )


def _usuario_tem_acesso_leitura_acompanhamento(user) -> bool:
    return _usuario_tem_acesso_global_acompanhamento(user) or _usuario_tem_acesso_como_interessado(user)


def _filtrar_sistemas_visiveis_para_usuario(queryset, user):
    if _usuario_tem_acesso_global_acompanhamento(user):
        return queryset
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    return queryset.filter(interessados__usuario=user).distinct()


def _filtrar_entregas_visiveis_para_usuario(queryset, user):
    if _usuario_tem_acesso_global_acompanhamento(user):
        return queryset
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    return queryset.filter(sistema__interessados__usuario=user).distinct()


def _filtrar_etapas_visiveis_para_usuario(queryset, user):
    if _usuario_tem_acesso_global_acompanhamento(user):
        return queryset
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    return queryset.filter(entrega__sistema__interessados__usuario=user).distinct()


def _usuario_pode_editar_sistema(user, sistema) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and (
            user.has_perm("acompanhamento_sistemas.change_sistema")
            or _usuario_eh_interessado_do_sistema(user, sistema)
        )
    )


def _usuario_pode_editar_entrega(user, entrega) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and (
            user.has_perm("acompanhamento_sistemas.change_entregasistema")
            or _usuario_eh_interessado_do_sistema(user, entrega.sistema)
        )
    )


def _usuario_pode_editar_etapa(user, etapa) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and (
            user.has_perm("acompanhamento_sistemas.change_etapasistema")
            or _usuario_eh_interessado_do_sistema(user, etapa.entrega.sistema)
        )
    )


def _usuario_pode_criar_ciclo(user, sistema) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and (
            user.has_perm("acompanhamento_sistemas.add_entregasistema")
            or _usuario_eh_interessado_do_sistema(user, sistema)
        )
    )


def _usuario_pode_gerir_processos(user, sistema) -> bool:
    return _usuario_pode_editar_sistema(user, sistema)


def _usuario_pode_gerir_interessados(user, sistema) -> bool:
    return _usuario_pode_editar_sistema(user, sistema)


def _usuario_pode_excluir_sistema(user, sistema) -> bool:
    return bool(getattr(user, "is_authenticated", False) and sistema.criado_por_id == user.id)


def _usuario_pode_excluir_entrega(user, entrega) -> bool:
    return bool(getattr(user, "is_authenticated", False) and entrega.criado_por_id == user.id)


def _usuario_pode_excluir_processo(user, processo) -> bool:
    return bool(getattr(user, "is_authenticated", False) and processo.criado_por_id == user.id)


def _registrar_auditoria_view(objeto, *, usuario, acao, changes=None):
    AuditLog.objects.create(
        user=usuario if getattr(usuario, "is_authenticated", False) else None,
        action=acao,
        content_type=ContentType.objects.get_for_model(objeto.__class__),
        object_id=str(objeto.pk),
        object_repr=str(objeto),
        changes=changes or {},
    )


def _enfileirar_erros_formulario(request, form):
    for _, erros in form.errors.items():
        for erro in erros:
            messages.error(request, erro)


def _eh_historico_avanco_automatico(historico) -> bool:
    return (
        getattr(historico, "tipo_evento", "") == HistoricoEtapaSistema.TipoEvento.STATUS
        and (getattr(historico, "justificativa", "") or "").strip()
        == "Avanço automático para a próxima etapa após conclusão da etapa anterior."
    )


def _timeline_sistema(sistema):
    itens = []
    if _historico_sistema_disponivel():
        historicos_sistema = (
            sistema.historicos_sistema.select_related("criado_por")
            .prefetch_related("anexos")
            .order_by("-criado_em", "-id")
        )
        for historico in historicos_sistema:
            historico.eh_criacao_entrega = False
            historico.timeline_titulo = f"Sistema {historico.sistema.nome}: Nota"
            itens.append(historico)

    for entrega in sistema.entregas.all():
        itens.append(
            SimpleNamespace(
                entrega=entrega,
                etapa=None,
                tipo_evento=HistoricoEtapaSistema.TipoEvento.CRIACAO,
                criado_em=entrega.criado_em,
                criado_por=entrega.criado_por,
                descricao=f"Ciclo {entrega.titulo} criado.",
                justificativa="",
                anexos=[],
                eh_criacao_entrega=True,
                timeline_titulo=f"Ciclo {entrega.titulo}: Criacao",
                get_tipo_evento_display=lambda: "Criacao",
            )
        )

    entrega_map = {str(entrega.pk): entrega for entrega in sistema.entregas.all()}
    audit_logs_entrega = AuditLog.objects.filter(
        content_type=ContentType.objects.get_for_model(EntregaSistema),
        object_id__in=list(entrega_map.keys()),
        action=AuditLog.Action.UPDATE,
    ).select_related("user")
    for audit in audit_logs_entrega:
        changes = audit.changes if isinstance(audit.changes, dict) else {}
        if not any(campo in changes for campo in ("titulo", "descricao")):
            continue
        entrega = entrega_map.get(str(audit.object_id))
        if entrega is None:
            continue
        titulo_anterior, titulo_novo = _valor_anterior_novo_change(changes.get("titulo"), fallback=entrega.titulo)
        _, descricao_nova = _valor_anterior_novo_change(changes.get("descricao"), fallback=entrega.descricao)
        descricao = _descricao_evento_edicao_ciclo(
            titulo_anterior=titulo_anterior,
            titulo_novo=titulo_novo,
            descricao_nova=descricao_nova,
        )
        itens.append(
            SimpleNamespace(
                entrega=entrega,
                etapa=None,
                tipo_evento="EDICAO",
                criado_em=audit.timestamp,
                criado_por=audit.user,
                descricao=descricao,
                justificativa="",
                anexos=[],
                eh_criacao_entrega=False,
                timeline_titulo=f"Ciclo {titulo_novo}: Edicao",
                get_tipo_evento_display=lambda: "Edicao",
            )
        )

    historicos = (
        HistoricoEtapaSistema.objects.filter(etapa__entrega__sistema=sistema)
        .exclude(tipo_evento=HistoricoEtapaSistema.TipoEvento.CRIACAO)
        .select_related("etapa", "etapa__entrega", "criado_por")
        .prefetch_related("anexos")
    )
    for historico in historicos:
        if _eh_historico_avanco_automatico(historico):
            continue
        historico.eh_criacao_entrega = False
        historico.timeline_titulo = f"Ciclo {historico.etapa.entrega.titulo}: {historico.etapa.get_tipo_etapa_display()}"
        itens.append(historico)

    historicos_processo = (
        HistoricoProcessoRequisito.objects.filter(processo__sistema=sistema)
        .select_related("processo", "criado_por")
        .prefetch_related("anexos")
    )
    for historico in historicos_processo:
        historico.eh_criacao_entrega = False
        historico.timeline_titulo = f"Processo {historico.processo.titulo}"
        itens.append(historico)

    historicos_etapa_processo = (
        HistoricoEtapaProcessoRequisito.objects.filter(etapa__processo__sistema=sistema)
        .exclude(tipo_evento=HistoricoEtapaProcessoRequisito.TipoEvento.CRIACAO)
        .select_related("etapa", "etapa__processo", "criado_por")
        .prefetch_related("anexos")
    )
    for historico in historicos_etapa_processo:
        historico.eh_criacao_entrega = False
        historico.timeline_titulo = (
            f"Processo {historico.etapa.processo.titulo}: {historico.etapa.get_tipo_etapa_display()}"
        )
        itens.append(historico)

    return sorted(itens, key=lambda item: (item.criado_em, getattr(item, "id", 0)), reverse=True)


def _valor_anterior_novo_change(valor, *, fallback=""):
    if isinstance(valor, (list, tuple)):
        if len(valor) >= 2:
            return valor[0] or "", valor[1] or ""
        if len(valor) == 1:
            return "", valor[0] or ""
    if isinstance(valor, str):
        return "", valor
    return "", fallback or ""


def _descricao_evento_edicao_ciclo(*, titulo_anterior="", titulo_novo="", descricao_nova=""):
    partes = []
    if titulo_anterior and titulo_novo and titulo_anterior != titulo_novo:
        partes.append(f'Ciclo renomeado de "{titulo_anterior}" para "{titulo_novo}".')
    else:
        partes.append(f'Ciclo {titulo_novo or titulo_anterior} atualizado.')
    if descricao_nova:
        partes.append(f"Descrição atualizada: {descricao_nova}")
    return " ".join(partes)


def _timeline_processo(processo):
    itens = []
    for historico in processo.historicos.select_related("criado_por").prefetch_related("anexos").order_by("-criado_em", "-id"):
        historico.timeline_titulo = f"Processo {processo.titulo}"
        itens.append(historico)
    for historico in (
        HistoricoEtapaProcessoRequisito.objects.filter(etapa__processo=processo)
        .exclude(tipo_evento=HistoricoEtapaProcessoRequisito.TipoEvento.CRIACAO)
        .select_related("etapa", "criado_por")
        .prefetch_related("anexos")
        .order_by("-criado_em", "-id")
    ):
        historico.timeline_titulo = f"{processo.titulo}: {historico.etapa.get_tipo_etapa_display()}"
        itens.append(historico)
    return sorted(itens, key=lambda item: (item.criado_em, getattr(item, "id", 0)), reverse=True)


def _timeline_etapa_processo(etapa):
    historicos = list(
        etapa.historicos.select_related("criado_por").prefetch_related("anexos").order_by("-criado_em", "-id")
    )
    for historico in historicos:
        historico.timeline_titulo = f"{etapa.processo.titulo}: {etapa.get_tipo_etapa_display()}"
    return historicos


def _timeline_etapa(etapa):
    historicos = []
    for historico in etapa.historicos.select_related("criado_por").prefetch_related("anexos").order_by("-criado_em", "-id"):
        if _eh_historico_avanco_automatico(historico):
            continue
        historicos.append(historico)
    for historico in historicos:
        historico.timeline_titulo = f"{etapa.entrega.titulo_com_numeracao}: {etapa.get_tipo_etapa_display()}"

    if etapa.tipo_etapa == EtapaSistema.TipoEtapa.HOMOLOGACAO_REQUISITOS:
        historicos_requisitos = (
            HistoricoEtapaSistema.objects.filter(
                etapa__entrega=etapa.entrega,
                etapa__tipo_etapa=EtapaSistema.TipoEtapa.REQUISITOS,
            )
            .exclude(anexos__isnull=True)
            .select_related("etapa", "criado_por")
            .prefetch_related("anexos")
            .distinct()
            .order_by("-criado_em", "-id")
        )
        for historico_requisitos in historicos_requisitos:
            prefixo_status = ""
            if etapa.status == EtapaSistema.Status.EM_ANDAMENTO:
                prefixo_status = f"{etapa.get_tipo_etapa_display()} em Andamento. "
            historicos.append(
                SimpleNamespace(
                    id=f"requisitos-{historico_requisitos.pk}",
                    etapa=etapa,
                    tipo_evento=HistoricoEtapaSistema.TipoEvento.ANEXO,
                    criado_em=historico_requisitos.criado_em,
                    criado_por=historico_requisitos.criado_por,
                    descricao=f"{prefixo_status}Documento de requisitos disponibilizado para a etapa de Homologacao de Requisitos.",
                    justificativa=historico_requisitos.justificativa,
                    anexos=historico_requisitos.anexos,
                    timeline_titulo=f"{etapa.entrega.titulo_com_numeracao}: Requisitos",
                    get_tipo_evento_display=lambda: "Anexo",
                )
            )

    proxima_etapa = (
        etapa.entrega.etapas.filter(ordem__gt=etapa.ordem)
        .order_by("ordem", "id")
        .first()
    )
    if proxima_etapa is not None and proxima_etapa.eh_homologacao:
        historicos_reprovacao = (
            proxima_etapa.historicos.filter(status_novo=EtapaSistema.Status.REPROVADO)
            .select_related("criado_por")
            .prefetch_related("anexos")
            .order_by("-criado_em", "-id")
        )
        for historico_reprovacao in historicos_reprovacao:
            historicos.append(
                SimpleNamespace(
                    id=f"reprovacao-{historico_reprovacao.pk}",
                    etapa=etapa,
                    tipo_evento=HistoricoEtapaSistema.TipoEvento.STATUS,
                    criado_em=historico_reprovacao.criado_em,
                    criado_por=historico_reprovacao.criado_por,
                    descricao="Homologação reprovada. Esta etapa retornou para tratamento.",
                    justificativa=historico_reprovacao.justificativa,
                    anexos=historico_reprovacao.anexos,
                    timeline_titulo=f"{etapa.entrega.titulo_com_numeracao}: {proxima_etapa.get_tipo_etapa_display()}",
                    get_tipo_evento_display=lambda: "Status",
                )
            )
        historicos_aprovacao = (
            proxima_etapa.historicos.filter(status_novo=EtapaSistema.Status.APROVADO)
            .select_related("criado_por")
            .prefetch_related("anexos")
            .order_by("-criado_em", "-id")
        )
        for historico_aprovacao in historicos_aprovacao:
            historicos.append(
                SimpleNamespace(
                    id=f"aprovacao-{historico_aprovacao.pk}",
                    etapa=etapa,
                    tipo_evento=HistoricoEtapaSistema.TipoEvento.STATUS,
                    criado_em=historico_aprovacao.criado_em,
                    criado_por=historico_aprovacao.criado_por,
                    descricao="Homologação aprovada. Esta etapa foi validada e o fluxo avançou.",
                    justificativa=historico_aprovacao.justificativa,
                    anexos=historico_aprovacao.anexos,
                    timeline_titulo=f"{etapa.entrega.titulo_com_numeracao}: {proxima_etapa.get_tipo_etapa_display()}",
                    get_tipo_evento_display=lambda: "Status",
                )
            )

    return sorted(historicos, key=lambda item: (item.criado_em, getattr(item, "id", 0)), reverse=True)


def _paginar_itens(request, itens, *, query_param="pagina_timeline", por_pagina=6):
    paginator = Paginator(itens, por_pagina)
    pagina = request.GET.get(query_param) or 1
    return paginator.get_page(pagina)


class AcompanhamentoReadAccessMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not _usuario_tem_acesso_leitura_acompanhamento(request.user):
            raise Http404
        return super().dispatch(request, *args, **kwargs)


class MockProcessosView(AcompanhamentoReadAccessMixin, View):
    arquivos = {
        "index": "acompanhamento_sistemas_processos_mock_index.html",
        "mock-01": "acompanhamento_sistemas_processos_mock_01.html",
        "mock-02": "acompanhamento_sistemas_processos_mock_02.html",
        "mock-03": "acompanhamento_sistemas_processos_mock_03.html",
        "acompanhamento_sistemas_processos_mock_index.html": "acompanhamento_sistemas_processos_mock_index.html",
        "acompanhamento_sistemas_processos_mock_01.html": "acompanhamento_sistemas_processos_mock_01.html",
        "acompanhamento_sistemas_processos_mock_02.html": "acompanhamento_sistemas_processos_mock_02.html",
        "acompanhamento_sistemas_processos_mock_03.html": "acompanhamento_sistemas_processos_mock_03.html",
    }

    def get(self, request, slug="index", *args, **kwargs):
        nome_arquivo = self.arquivos.get(slug)
        if not nome_arquivo:
            raise Http404

        caminho = Path(__file__).resolve().parent.parent / "docs" / nome_arquivo
        if not caminho.exists():
            raise Http404

        return HttpResponse(caminho.read_text(encoding="utf-8"))


class SistemaListView(AcompanhamentoReadAccessMixin, ListView):
    model = Sistema
    template_name = "acompanhamento_sistemas/list.html"
    context_object_name = "sistemas"

    def get_queryset(self):
        ultimo_historico = HistoricoEtapaSistema.objects.filter(
            etapa__entrega__sistema=OuterRef("pk")
        ).order_by("-criado_em", "-id")
        queryset = Sistema.objects.select_related("criado_por", "atualizado_por").prefetch_related(
            Prefetch(
                "entregas__etapas",
                queryset=EtapaSistema.objects.order_by("ordem", "id"),
            )
        )
        if _historico_sistema_disponivel():
            ultimo_historico_sistema = HistoricoSistema.objects.filter(
                sistema=OuterRef("pk")
            ).order_by("-criado_em", "-id")
            queryset = queryset.prefetch_related(
                "historicos_sistema__criado_por",
                "historicos_sistema__anexos",
            ).annotate(
                ultimo_historico_etapa_em=Subquery(ultimo_historico.values("criado_em")[:1]),
                ultimo_historico_etapa_usuario_id=Subquery(ultimo_historico.values("criado_por_id")[:1]),
                ultimo_historico_sistema_em=Subquery(ultimo_historico_sistema.values("criado_em")[:1]),
                ultimo_historico_sistema_usuario_id=Subquery(ultimo_historico_sistema.values("criado_por_id")[:1]),
            ).annotate(
                ultimo_historico_em=Greatest(
                    Coalesce("ultimo_historico_etapa_em", "criado_em"),
                    Coalesce("ultimo_historico_sistema_em", "criado_em"),
                ),
            )
        else:
            queryset = queryset.annotate(
                ultimo_historico_etapa_em=Subquery(ultimo_historico.values("criado_em")[:1]),
                ultimo_historico_etapa_usuario_id=Subquery(ultimo_historico.values("criado_por_id")[:1]),
                ultimo_historico_em=Coalesce(Subquery(ultimo_historico.values("criado_em")[:1]), "criado_em"),
            )
        queryset = _filtrar_sistemas_visiveis_para_usuario(queryset.distinct(), self.request.user)
        q = (self.request.GET.get("q") or "").strip()
        etapa = (self.request.GET.get("etapa") or "").strip()
        status = (self.request.GET.get("status") or "").strip()
        responsavel = (self.request.GET.get("responsavel") or "").strip()
        if q:
            queryset = queryset.filter(Q(nome__icontains=q) | Q(descricao__icontains=q))
        if etapa:
            queryset = queryset.filter(entregas__etapas__tipo_etapa=etapa)
        if status:
            queryset = queryset.filter(entregas__etapas__status=status)
        if responsavel and responsavel.isdigit():
            filtro_responsavel = Q(ultimo_historico_etapa_usuario_id=int(responsavel))
            if _historico_sistema_disponivel():
                filtro_responsavel |= Q(ultimo_historico_sistema_usuario_id=int(responsavel))
            queryset = queryset.filter(filtro_responsavel)
        return queryset.order_by("nome").distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        responsaveis = usuarios_visiveis(User.objects.filter(
            pk__in=HistoricoEtapaSistema.objects.exclude(criado_por__isnull=True).values_list("criado_por_id", flat=True)
        )).order_by("first_name", "username")
        sistemas = list(context["sistemas"])
        context["filtro_form"] = SistemaFiltroForm(self.request.GET or None, responsaveis=responsaveis)
        context["pode_editar_sistema"] = self.request.user.has_perm("acompanhamento_sistemas.change_sistema")
        context["dashboard"] = {
            "total": len(sistemas),
            "com_atraso": sum(
                1
                for sistema in sistemas
                if any(
                    etapa.prazo_marcador and etapa.prazo_marcador["classe"] == "atrasado"
                    for entrega in sistema.entregas.all()
                    for etapa in entrega.etapas.all()
                )
            ),
            "com_atencao": sum(
                1
                for sistema in sistemas
                if any(
                    etapa.prazo_marcador and etapa.prazo_marcador["classe"] == "atencao"
                    for entrega in sistema.entregas.all()
                    for etapa in entrega.etapas.all()
                )
            ),
            "com_retomada": sum(
                1
                for sistema in sistemas
                if any(
                    etapa.marcadores_historicos
                    for entrega in sistema.entregas.all()
                    for etapa in entrega.etapas.all()
                )
            ),
            "aguardando_homologacao": sum(
                1
                for sistema in sistemas
                if any(
                    etapa.eh_homologacao and etapa.status_exibicao in {"Em andamento", "Reprovado"}
                    for entrega in sistema.entregas.all()
                    for etapa in entrega.etapas.all()
                )
            ),
        }
        return context


class SistemaCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = ("acompanhamento_sistemas.add_sistema",)
    model = Sistema
    form_class = SistemaForm
    template_name = "acompanhamento_sistemas/form.html"

    def form_valid(self, form):
        form.instance.criado_por = self.request.user
        form.instance.atualizado_por = self.request.user
        response = super().form_valid(form)
        _registrar_auditoria_view(self.object, usuario=self.request.user, acao=AuditLog.Action.CREATE, changes={"nome": self.object.nome})
        messages.success(self.request, "Sistema criado com sucesso. Agora você já pode lançar as entregas.")
        return response


class SistemaUpdateView(LoginRequiredMixin, UpdateView):
    model = Sistema
    form_class = SistemaForm
    template_name = "acompanhamento_sistemas/form.html"

    def get_queryset(self):
        return _filtrar_sistemas_visiveis_para_usuario(Sistema.objects.all(), self.request.user)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not _usuario_pode_editar_sistema(request.user, self.object):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.atualizado_por = self.request.user
        _registrar_auditoria_view(
            self.object,
            usuario=self.request.user,
            acao=AuditLog.Action.UPDATE,
            changes={"nome": form.cleaned_data.get("nome"), "descricao": form.cleaned_data.get("descricao")},
        )
        messages.success(self.request, "Sistema atualizado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pode_excluir_sistema"] = _usuario_pode_excluir_sistema(self.request.user, self.object)
        return context


class SistemaDeleteView(LoginRequiredMixin, DeleteView):
    model = Sistema
    template_name = "acompanhamento_sistemas/confirm_delete.html"

    def get_queryset(self):
        return _filtrar_sistemas_visiveis_para_usuario(Sistema.objects.all(), self.request.user)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not _usuario_pode_excluir_sistema(request.user, self.object):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        messages.success(self.request, "Sistema excluído com sucesso.")
        return reverse("acompanhamento_sistemas_list")

    def form_valid(self, form):
        success_url = self.get_success_url()
        excluir_sistema(self.object, usuario=self.request.user)
        return HttpResponseRedirect(success_url)


class SistemaDetailView(AcompanhamentoReadAccessMixin, DetailView):
    model = Sistema
    template_name = "acompanhamento_sistemas/detail.html"
    context_object_name = "sistema"

    def get_queryset(self):
        queryset = Sistema.objects.prefetch_related(
            "interessados__usuario",
            "interessados_manuais",
            Prefetch("entregas", queryset=EntregaSistema.objects.prefetch_related("etapas").order_by("ordem", "id")),
            Prefetch(
                "processos_requisito",
                queryset=ProcessoRequisito.objects.prefetch_related("etapas").order_by("ordem", "id"),
            ),
        )
        return _filtrar_sistemas_visiveis_para_usuario(queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sistema = self.object
        context["entrega_form"] = kwargs.get("entrega_form") or EntregaSistemaForm()
        context["processo_form"] = kwargs.get("processo_form") or ProcessoRequisitoForm()
        context["processo_edicao"] = kwargs.get("processo_edicao")
        context["transformacao_form"] = kwargs.get("transformacao_form") or GerarProcessoTransformacaoForm()
        context["novo_sistema_form"] = kwargs.get("novo_sistema_form") or GerarNovoSistemaAPartirProcessosForm()
        context["processo_transformacao"] = kwargs.get("processo_transformacao")
        context["interessado_form"] = kwargs.get("interessado_form") or InteressadoSistemaForm(sistema=sistema)
        context["nota_sistema_form"] = kwargs.get("nota_sistema_form") or NotaSistemaForm()
        historicos_page = _paginar_itens(self.request, _timeline_sistema(sistema))
        context["historicos"] = historicos_page.object_list
        context["historicos_page"] = historicos_page
        context["timeline_query_param"] = "pagina_timeline"
        context["abrir_modal_ciclo"] = kwargs.get("abrir_modal_ciclo", False)
        context["abrir_modal_processo"] = kwargs.get("abrir_modal_processo", False)
        context["abrir_modal_transformacao"] = kwargs.get("abrir_modal_transformacao", False)
        context["abrir_modal_interessado"] = kwargs.get("abrir_modal_interessado", False)
        context["abrir_modal_nota_sistema"] = kwargs.get("abrir_modal_nota_sistema", False)
        context["historico_sistema_disponivel"] = _historico_sistema_disponivel()
        context["pode_editar_sistema"] = _usuario_pode_editar_sistema(self.request.user, sistema)
        context["pode_criar_entrega"] = _usuario_pode_criar_ciclo(self.request.user, sistema)
        context["pode_gerir_processos"] = _usuario_pode_gerir_processos(self.request.user, sistema)
        context["todos_processos_finalizados"] = sistema_pode_gerar_novo_sistema(sistema)
        context["pode_excluir_sistema"] = _usuario_pode_excluir_sistema(self.request.user, sistema)
        return context


class SistemaHistoricoView(AcompanhamentoReadAccessMixin, DetailView):
    model = Sistema
    template_name = "acompanhamento_sistemas/entrega_historico.html"
    context_object_name = "sistema"

    def get_queryset(self):
        queryset = Sistema.objects.prefetch_related(
            "interessados__usuario",
            "interessados_manuais",
            Prefetch("entregas", queryset=EntregaSistema.objects.order_by("ordem", "id")),
            Prefetch("processos_requisito", queryset=ProcessoRequisito.objects.order_by("ordem", "id")),
        )
        return _filtrar_sistemas_visiveis_para_usuario(queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        historicos_page = _paginar_itens(self.request, _timeline_sistema(self.object))
        context["historicos"] = historicos_page.object_list
        context["historicos_page"] = historicos_page
        context["timeline_query_param"] = "pagina_timeline"
        context["entrega"] = None
        return context


class ProcessoRequisitoCreateView(LoginRequiredMixin, View):

    def dispatch(self, request, *args, **kwargs):
        sistema = get_object_or_404(_filtrar_sistemas_visiveis_para_usuario(Sistema.objects.all(), request.user), pk=kwargs["pk"])
        if not _usuario_pode_gerir_processos(request.user, sistema):
            raise Http404
        self.sistema = sistema
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        form = ProcessoRequisitoForm(request.POST)
        if form.is_valid():
            criar_processo_requisito(
                self.sistema,
                usuario=request.user,
                titulo=form.cleaned_data["titulo"],
                descricao=form.cleaned_data["descricao"],
            )
            messages.success(request, "Processo de requisitos criado com sucesso.")
            return redirect("acompanhamento_sistemas_detail", pk=self.sistema.pk)
        messages.error(request, "Não foi possível criar o processo de requisitos.")
        _enfileirar_erros_formulario(request, form)
        view = SistemaDetailView()
        view.setup(request, pk=pk)
        view.object = self.sistema
        return view.render_to_response(view.get_context_data(processo_form=form, abrir_modal_processo=True))


class ProcessoRequisitoUpdateView(LoginRequiredMixin, View):

    def dispatch(self, request, *args, **kwargs):
        processo = get_object_or_404(
            ProcessoRequisito.objects.select_related("sistema").prefetch_related("etapas"),
            pk=kwargs["pk"],
        )
        sistema = get_object_or_404(_filtrar_sistemas_visiveis_para_usuario(Sistema.objects.all(), request.user), pk=processo.sistema_id)
        if not _usuario_pode_gerir_processos(request.user, sistema):
            raise Http404
        self.processo = processo
        self.sistema = sistema
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        form = ProcessoRequisitoForm(request.POST)
        if form.is_valid():
            atualizar_processo_requisito(
                self.processo,
                usuario=request.user,
                titulo=form.cleaned_data["titulo"],
                descricao=form.cleaned_data["descricao"],
            )
            messages.success(request, "Processo de requisitos atualizado com sucesso.")
            return redirect("acompanhamento_sistemas_detail", pk=self.sistema.pk)
        messages.error(request, "Não foi possível atualizar o processo de requisitos.")
        _enfileirar_erros_formulario(request, form)
        view = SistemaDetailView()
        view.setup(request, pk=self.sistema.pk)
        view.object = self.sistema
        return view.render_to_response(
            view.get_context_data(
                processo_form=form,
                processo_edicao=self.processo,
                abrir_modal_processo=True,
            )
        )


class ProcessoRequisitoDeleteView(LoginRequiredMixin, View):

    def dispatch(self, request, *args, **kwargs):
        processo = get_object_or_404(ProcessoRequisito.objects.select_related("sistema"), pk=kwargs["pk"])
        sistema = get_object_or_404(_filtrar_sistemas_visiveis_para_usuario(Sistema.objects.all(), request.user), pk=processo.sistema_id)
        if not _usuario_pode_excluir_processo(request.user, processo):
            raise Http404
        self.processo = processo
        self.sistema = sistema
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        excluir_processo_requisito(self.processo, usuario=request.user)
        messages.success(request, "Processo de requisitos excluído com sucesso.")
        return redirect("acompanhamento_sistemas_detail", pk=self.sistema.pk)


class ProcessoRequisitoDetailView(AcompanhamentoReadAccessMixin, DetailView):
    model = ProcessoRequisito
    template_name = "acompanhamento_sistemas/processo_detail.html"
    context_object_name = "processo"

    def get_queryset(self):
        queryset = ProcessoRequisito.objects.select_related("sistema").prefetch_related(
            "etapas",
            "historicos__criado_por",
            "historicos__anexos",
            "etapas__historicos__criado_por",
            "etapas__historicos__anexos",
        )
        return queryset.filter(sistema__in=_filtrar_sistemas_visiveis_para_usuario(Sistema.objects.all(), self.request.user))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        historicos_page = _paginar_itens(self.request, _timeline_processo(self.object))
        context["historicos"] = historicos_page.object_list
        context["historicos_page"] = historicos_page
        context["timeline_query_param"] = "pagina_timeline"
        context["pode_gerir_processos"] = _usuario_pode_gerir_processos(self.request.user, self.object.sistema)
        return context


class ProcessoRequisitoEtapaDetailView(AcompanhamentoReadAccessMixin, DetailView):
    model = EtapaProcessoRequisito
    template_name = "acompanhamento_sistemas/processo_etapa_detail.html"
    context_object_name = "etapa"

    def get_queryset(self):
        queryset = EtapaProcessoRequisito.objects.select_related(
            "processo",
            "processo__sistema",
            "criado_por",
            "atualizado_por",
        ).prefetch_related(
            "historicos__criado_por",
            "historicos__anexos",
            "processo__historicos__criado_por",
            "processo__historicos__anexos",
        )
        return queryset.filter(
            processo__sistema__in=_filtrar_sistemas_visiveis_para_usuario(Sistema.objects.all(), self.request.user)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        historicos_page = _paginar_itens(self.request, _timeline_etapa_processo(self.object))
        context["historicos"] = historicos_page.object_list
        context["historicos_page"] = historicos_page
        context["timeline_query_param"] = "pagina_timeline"
        context["etapa_form"] = kwargs.get("etapa_form") or EtapaProcessoRequisitoAtualizacaoForm(instance=self.object)
        context["abrir_modal_status"] = kwargs.get("abrir_modal_status", False)
        context["pode_gerir_processos"] = _usuario_pode_gerir_processos(self.request.user, self.object.processo.sistema)
        return context


class ProcessoRequisitoEtapaUpdateView(LoginRequiredMixin, View):

    def dispatch(self, request, *args, **kwargs):
        etapa = get_object_or_404(
            EtapaProcessoRequisito.objects.select_related("processo__sistema"),
            pk=kwargs["pk"],
        )
        if not _usuario_pode_gerir_processos(request.user, etapa.processo.sistema):
            raise Http404
        self.etapa = etapa
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        form = EtapaProcessoRequisitoAtualizacaoForm(request.POST, request.FILES, instance=self.etapa)
        if form.is_valid():
            try:
                etapa_atual = EtapaProcessoRequisito.objects.get(pk=self.etapa.pk)
                atualizar_etapa_processo_requisito(
                    etapa_atual,
                    novo_status=form.cleaned_data["status"],
                    justificativa=form.cleaned_data["justificativa_status"],
                    anexos=form.cleaned_data.get("anexos"),
                    usuario=request.user,
                    request=request,
                )
            except ValidationError as exc:
                messages.error(request, "Não foi possível atualizar a etapa do processo.")
                for mensagem in exc.messages:
                    form.add_error(None, mensagem)
            else:
                messages.success(request, "Etapa do processo atualizada com sucesso.")
                return redirect("acompanhamento_sistemas_processo_etapa_detail", pk=etapa_atual.pk)
        else:
            messages.error(request, "Não foi possível atualizar a etapa do processo.")
            _enfileirar_erros_formulario(request, form)
        view = ProcessoRequisitoEtapaDetailView()
        view.setup(request, pk=pk)
        view.object = self.etapa
        return view.render_to_response(view.get_context_data(etapa_form=form, abrir_modal_status=True))


class ProcessoRequisitoTransformarView(LoginRequiredMixin, View):

    def dispatch(self, request, *args, **kwargs):
        processo = get_object_or_404(ProcessoRequisito.objects.select_related("sistema").prefetch_related("etapas"), pk=kwargs["pk"])
        sistema = get_object_or_404(_filtrar_sistemas_visiveis_para_usuario(Sistema.objects.all(), request.user), pk=processo.sistema_id)
        if not _usuario_pode_gerir_processos(request.user, sistema):
            raise Http404
        self.processo = processo
        self.sistema = sistema
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        acao = request.POST.get("acao", "").strip()
        if acao == "ciclo":
            try:
                gerar_ciclo_a_partir_processo(self.processo, usuario=request.user, request=request)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
            else:
                messages.success(request, "Ciclo gerado a partir do processo de requisitos.")
            return redirect("acompanhamento_sistemas_detail", pk=self.sistema.pk)

        if acao == "sistema":
            form = GerarNovoSistemaAPartirProcessosForm(request.POST)
            if form.is_valid():
                try:
                    novo_sistema = gerar_novo_sistema_a_partir_processos(
                        self.sistema,
                        usuario=request.user,
                        nome=form.cleaned_data["nome"],
                        descricao=form.cleaned_data["descricao"],
                        url_homologacao=form.cleaned_data.get("url_homologacao") or "",
                        url_producao=form.cleaned_data.get("url_producao") or "",
                        request=request,
                    )
                except ValidationError as exc:
                    messages.error(request, exc.messages[0])
                else:
                    messages.success(request, "Novo sistema gerado a partir dos processos finalizados.")
                    return redirect("acompanhamento_sistemas_detail", pk=novo_sistema.pk)
            else:
                _enfileirar_erros_formulario(request, form)
            view = SistemaDetailView()
            view.setup(request, pk=self.sistema.pk)
            view.object = self.sistema
            return view.render_to_response(
                view.get_context_data(
                    abrir_modal_transformacao=True,
                    processo_transformacao=self.processo,
                    novo_sistema_form=form,
                )
            )

        messages.error(request, "Selecione uma ação válida para a transformação do processo.")
        return redirect("acompanhamento_sistemas_detail", pk=self.sistema.pk)


class EntregaSistemaCreateView(LoginRequiredMixin, View):

    def dispatch(self, request, *args, **kwargs):
        sistema = get_object_or_404(_filtrar_sistemas_visiveis_para_usuario(Sistema.objects.all(), request.user), pk=kwargs["pk"])
        if not _usuario_pode_criar_ciclo(request.user, sistema):
            raise Http404
        self.sistema = sistema
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        sistema = self.sistema
        form = EntregaSistemaForm(request.POST)
        if form.is_valid():
            criar_entrega_com_etapas(
                sistema,
                usuario=request.user,
                titulo=form.cleaned_data["titulo"],
                descricao=form.cleaned_data["descricao"],
            )
            messages.success(request, "Novo ciclo criado com as 5 etapas obrigatórias.")
            return redirect("acompanhamento_sistemas_detail", pk=sistema.pk)
        messages.error(request, "Não foi possível criar o ciclo.")
        _enfileirar_erros_formulario(request, form)
        view = SistemaDetailView()
        view.setup(request, pk=pk)
        view.object = sistema
        return view.render_to_response(view.get_context_data(entrega_form=form, abrir_modal_ciclo=True))

class EntregaSistemaDetailView(AcompanhamentoReadAccessMixin, DetailView):
    model = EntregaSistema
    template_name = "acompanhamento_sistemas/entrega_detail.html"
    context_object_name = "entrega"

    def get_queryset(self):
        queryset = EntregaSistema.objects.select_related(
            "sistema",
            "criado_por",
            "atualizado_por",
        ).prefetch_related(
            Prefetch(
                "etapas",
                queryset=EtapaSistema.objects.order_by("ordem", "id").prefetch_related("historicos"),
            )
        )
        return _filtrar_entregas_visiveis_para_usuario(queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pode_publicar_ciclo"] = (
            _usuario_pode_editar_entrega(self.request.user, self.object)
            and self.object.status == EntregaSistema.Status.RASCUNHO
            and entrega_pode_ser_publicada(self.object)
        )
        context["pode_editar_sistema"] = _usuario_pode_editar_sistema(self.request.user, self.object.sistema)
        context["pode_excluir_ciclo"] = _usuario_pode_excluir_entrega(self.request.user, self.object)
        return context


class EntregaSistemaHistoricoView(AcompanhamentoReadAccessMixin, DetailView):
    model = EntregaSistema
    template_name = "acompanhamento_sistemas/entrega_historico.html"
    context_object_name = "entrega"

    def get_queryset(self):
        queryset = EntregaSistema.objects.select_related(
            "sistema",
            "criado_por",
            "atualizado_por",
        ).prefetch_related(
            "sistema__interessados__usuario",
            "sistema__interessados_manuais",
            Prefetch("sistema__entregas", queryset=EntregaSistema.objects.order_by("ordem", "id")),
            Prefetch("sistema__processos_requisito", queryset=ProcessoRequisito.objects.order_by("ordem", "id")),
        )
        return _filtrar_entregas_visiveis_para_usuario(queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sistema = self.object.sistema
        historicos_page = _paginar_itens(self.request, _timeline_sistema(sistema))
        context["sistema"] = sistema
        context["historicos"] = historicos_page.object_list
        context["historicos_page"] = historicos_page
        context["timeline_query_param"] = "pagina_timeline"
        return context


class EntregaSistemaUpdateView(LoginRequiredMixin, UpdateView):
    model = EntregaSistema
    form_class = EntregaSistemaForm
    template_name = "acompanhamento_sistemas/form.html"

    def get_queryset(self):
        return _filtrar_entregas_visiveis_para_usuario(EntregaSistema.objects.select_related("sistema"), self.request.user)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not _usuario_pode_editar_entrega(request.user, self.object):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.atualizado_por = self.request.user
        entrega_original = EntregaSistema.objects.get(pk=self.object.pk)
        titulo_anterior = entrega_original.titulo
        descricao_anterior = entrega_original.descricao
        _registrar_auditoria_view(
            self.object,
            usuario=self.request.user,
            acao=AuditLog.Action.UPDATE,
            changes={
                "titulo": [titulo_anterior, form.cleaned_data.get("titulo")],
                "descricao": [descricao_anterior, form.cleaned_data.get("descricao")],
            },
        )
        messages.success(self.request, "Ciclo atualizado com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["modo_ciclo"] = True
        context["pode_excluir_ciclo"] = _usuario_pode_excluir_entrega(self.request.user, self.object)
        return context


class EntregaSistemaDeleteView(LoginRequiredMixin, DeleteView):
    model = EntregaSistema
    template_name = "acompanhamento_sistemas/confirm_delete.html"

    def get_queryset(self):
        return _filtrar_entregas_visiveis_para_usuario(EntregaSistema.objects.select_related("sistema"), self.request.user)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not _usuario_pode_excluir_entrega(request.user, self.object):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["modo_ciclo"] = True
        return context

    def get_success_url(self):
        sistema_pk = self.object.sistema.pk
        messages.success(self.request, "Ciclo excluído com sucesso.")
        return reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema_pk})

    def form_valid(self, form):
        success_url = self.get_success_url()
        excluir_entrega_sistema(self.object, usuario=self.request.user)
        return HttpResponseRedirect(success_url)


class EntregaSistemaPublishView(LoginRequiredMixin, View):

    def dispatch(self, request, *args, **kwargs):
        entrega = get_object_or_404(_filtrar_entregas_visiveis_para_usuario(EntregaSistema.objects.select_related("sistema"), request.user), pk=kwargs["pk"])
        if not _usuario_pode_editar_entrega(request.user, entrega):
            raise Http404
        self.entrega = entrega
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        entrega = EntregaSistema.objects.prefetch_related("etapas").get(pk=self.entrega.pk)
        try:
            publicar_entrega(entrega, usuario=request.user, request=request)
        except ValidationError as exc:
            for mensagem in exc.messages:
                messages.error(request, mensagem)
        else:
            messages.success(request, "Ciclo publicado com sucesso.")
        return redirect("acompanhamento_sistemas_entrega_detail", pk=entrega.pk)

class EtapaSistemaCalendarioView(AcompanhamentoReadAccessMixin, View):

    def get(self, request):
        try:
            ano = int(request.GET.get("ano", "0"))
            mes = int(request.GET.get("mes", "0"))
        except (TypeError, ValueError):
            return JsonResponse({"results": []})

        if ano <= 0 or mes < 1 or mes > 12:
            return JsonResponse({"results": []})

        etapas = (
            EtapaSistema.objects.filter(data_etapa__year=ano, data_etapa__month=mes)
            .select_related("entrega", "entrega__sistema")
            .order_by("data_etapa", "entrega__sistema__nome", "entrega__ordem", "ordem", "id")
        )
        etapas = _filtrar_etapas_visiveis_para_usuario(etapas, request.user)

        results = [
            {
                "id": etapa.pk,
                "data": etapa.data_etapa.isoformat(),
                "sistema": etapa.entrega.sistema.nome,
                "ciclo": etapa.entrega.titulo_com_numeracao,
                "etapa": etapa.get_tipo_etapa_display(),
                "status": etapa.status,
                "status_label": etapa.get_status_display(),
                "url": reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa.pk}),
            }
            for etapa in etapas
        ]
        return JsonResponse({"results": results})


class EtapaSistemaDetailView(AcompanhamentoReadAccessMixin, DetailView):
    model = EtapaSistema
    template_name = "acompanhamento_sistemas/etapa_detail.html"
    context_object_name = "etapa"

    def get_queryset(self):
        queryset = EtapaSistema.objects.select_related(
            "entrega",
            "entrega__sistema",
            "criado_por",
            "atualizado_por",
        ).prefetch_related(
            "historicos__criado_por",
            "historicos__anexos",
            "entrega__etapas__historicos",
            "entrega__sistema__interessados__usuario",
            "entrega__sistema__interessados_manuais",
        )
        return _filtrar_etapas_visiveis_para_usuario(queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        etapa = self.object
        sistema = etapa.entrega.sistema
        ciclo_publicado = etapa.entrega.status == EntregaSistema.Status.PUBLICADO
        pode_editar_etapa = _usuario_pode_editar_etapa(self.request.user, etapa)
        historicos_page = _paginar_itens(self.request, _timeline_etapa(etapa))
        context["historicos"] = historicos_page.object_list
        context["historicos_page"] = historicos_page
        context["timeline_query_param"] = "pagina_timeline"
        context["etapas_calendario_api_url"] = reverse("acompanhamento_sistemas_etapa_calendario")
        context["etapa_form"] = kwargs.get("etapa_form") or EtapaSistemaAtualizacaoForm(instance=etapa)
        context["nota_form"] = kwargs.get("nota_form") or NotaEtapaSistemaForm()
        context["abrir_modal_nota"] = kwargs.get("abrir_modal_nota", False)
        context["interessado_form"] = kwargs.get("interessado_form") or InteressadoSistemaForm(sistema=sistema)
        context["pode_editar_etapa"] = pode_editar_etapa
        context["ciclo_publicado"] = ciclo_publicado
        context["pode_alterar_status_etapa"] = pode_editar_etapa and (
            ciclo_publicado or etapa_pode_alterar_status_em_rascunho(etapa)
        )
        context["pode_lancar_nota_etapa"] = pode_editar_etapa and ciclo_publicado
        context["pode_editar_sistema"] = _usuario_pode_editar_sistema(self.request.user, sistema)
        return context


class EtapaSistemaUpdateView(LoginRequiredMixin, View):

    def dispatch(self, request, *args, **kwargs):
        etapa = get_object_or_404(_filtrar_etapas_visiveis_para_usuario(EtapaSistema.objects.select_related("entrega__sistema"), request.user), pk=kwargs["pk"])
        if not _usuario_pode_editar_etapa(request.user, etapa):
            raise Http404
        self.etapa = etapa
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        etapa = self.etapa
        form = EtapaSistemaAtualizacaoForm(request.POST, request.FILES, instance=etapa)
        if form.is_valid():
            etapa_atual = EtapaSistema.objects.get(pk=etapa.pk)
            try:
                atualizar_etapa_com_historico(
                    etapa_atual,
                    nova_data=form.cleaned_data.get("data_etapa"),
                    novo_status=form.cleaned_data["status"],
                    justificativa=form.cleaned_data.get("justificativa_status"),
                    texto_nota=form.cleaned_data.get("texto_nota"),
                    anexos=form.cleaned_data.get("anexos"),
                    usuario=request.user,
                    request=request,
                )
            except ValidationError as exc:
                messages.error(request, "Não foi possível atualizar a etapa.")
                for mensagem in exc.messages:
                    form.add_error(None, mensagem)
                    messages.error(request, mensagem)
                view = EtapaSistemaDetailView()
                view.setup(request, pk=pk)
                view.object = etapa
                return view.render_to_response(view.get_context_data(etapa_form=form))
            messages.success(request, "Etapa atualizada com sucesso.")
            return redirect("acompanhamento_sistemas_etapa_detail", pk=etapa_atual.pk)
        messages.error(request, "Não foi possível atualizar a etapa.")
        _enfileirar_erros_formulario(request, form)
        view = EtapaSistemaDetailView()
        view.setup(request, pk=pk)
        view.object = etapa
        return view.render_to_response(view.get_context_data(etapa_form=form))

class EtapaSistemaNotaView(LoginRequiredMixin, View):

    def dispatch(self, request, *args, **kwargs):
        etapa = get_object_or_404(_filtrar_etapas_visiveis_para_usuario(EtapaSistema.objects.select_related("entrega__sistema"), request.user), pk=kwargs["pk"])
        if not _usuario_pode_editar_etapa(request.user, etapa):
            raise Http404
        self.etapa = etapa
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        etapa = self.etapa
        form = NotaEtapaSistemaForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                adicionar_nota_etapa(
                    etapa,
                    texto=form.cleaned_data.get("texto_nota"),
                    anexos=form.cleaned_data.get("anexos"),
                    usuario=request.user,
                    request=request,
                )
            except ValidationError as exc:
                messages.error(request, "Não foi possível registrar a anotação.")
                for mensagem in exc.messages:
                    form.add_error(None, mensagem)
                    messages.error(request, mensagem)
                view = EtapaSistemaDetailView()
                view.setup(request, pk=pk)
                view.object = etapa
                return view.render_to_response(view.get_context_data(nota_form=form, abrir_modal_nota=True))
            messages.success(request, "Anotação registrada com sucesso.")
            return redirect("acompanhamento_sistemas_etapa_detail", pk=etapa.pk)
        messages.error(request, "Não foi possível registrar a anotação.")
        _enfileirar_erros_formulario(request, form)
        view = EtapaSistemaDetailView()
        view.setup(request, pk=pk)
        view.object = etapa
        return view.render_to_response(view.get_context_data(nota_form=form, abrir_modal_nota=True))

class InteressadoSistemaCreateView(LoginRequiredMixin, View):

    def dispatch(self, request, *args, **kwargs):
        sistema = get_object_or_404(_filtrar_sistemas_visiveis_para_usuario(Sistema.objects.all(), request.user), pk=kwargs["pk"])
        if not _usuario_pode_gerir_interessados(request.user, sistema):
            raise Http404
        self.sistema = sistema
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        sistema = self.sistema
        form = InteressadoSistemaForm(request.POST, sistema=sistema)
        if form.is_valid():
            interessado = form.save(sistema, request.user)
            _registrar_auditoria_view(
                interessado,
                usuario=request.user,
                acao=AuditLog.Action.CREATE,
                changes={"tipo_interessado": interessado.tipo_interessado},
            )
            messages.success(request, "Interessado vinculado ao sistema.")
        else:
            messages.error(request, "Não foi possível adicionar o interessado.")
            _enfileirar_erros_formulario(request, form)
            view = SistemaDetailView()
            view.setup(request, pk=pk)
            view.object = sistema
            return view.render_to_response(
                view.get_context_data(interessado_form=form, abrir_modal_interessado=True)
            )
        proxima_url = request.POST.get("next") or reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema.pk})
        return HttpResponseRedirect(proxima_url)

class SistemaNotaView(LoginRequiredMixin, View):

    def dispatch(self, request, *args, **kwargs):
        sistema = get_object_or_404(_filtrar_sistemas_visiveis_para_usuario(Sistema.objects.all(), request.user), pk=kwargs["pk"])
        if not _usuario_pode_editar_sistema(request.user, sistema):
            raise Http404
        self.sistema = sistema
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        sistema = self.sistema
        if not _historico_sistema_disponivel():
            messages.error(request, "A anotação do sistema estará disponível após aplicar a migration pendente do módulo.")
            return redirect("acompanhamento_sistemas_detail", pk=sistema.pk)
        form = NotaSistemaForm(request.POST, request.FILES)
        if form.is_valid():
            adicionar_nota_sistema(
                sistema,
                texto=form.cleaned_data.get("texto_nota"),
                anexos=form.cleaned_data.get("anexos"),
                usuario=request.user,
                request=request,
            )
            messages.success(request, "Anotação do sistema registrada com sucesso.")
            return redirect("acompanhamento_sistemas_detail", pk=sistema.pk)
        messages.error(request, "Não foi possível registrar a anotação do sistema.")
        _enfileirar_erros_formulario(request, form)
        view = SistemaDetailView()
        view.setup(request, pk=pk)
        view.object = sistema
        return view.render_to_response(view.get_context_data(nota_sistema_form=form, abrir_modal_nota_sistema=True))

class InteressadoSistemaDeleteView(LoginRequiredMixin, View):

    def dispatch(self, request, *args, **kwargs):
        sistema = get_object_or_404(_filtrar_sistemas_visiveis_para_usuario(Sistema.objects.all(), request.user), pk=kwargs["pk"])
        if not _usuario_pode_gerir_interessados(request.user, sistema):
            raise Http404
        self.sistema = sistema
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk, interessado_pk):
        sistema = self.sistema
        interessado = InteressadoSistema.objects.filter(pk=interessado_pk, sistema=sistema).first()
        if interessado is not None:
            _registrar_auditoria_view(interessado, usuario=request.user, acao=AuditLog.Action.DELETE, changes={"tipo_interessado": interessado.tipo_interessado})
            interessado.delete()
            messages.success(request, "Interessado removido.")
            return redirect(request.POST.get("next") or reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema.pk}))
        interessado_manual = get_object_or_404(InteressadoSistemaManual, pk=interessado_pk, sistema=sistema)
        _registrar_auditoria_view(interessado_manual, usuario=request.user, acao=AuditLog.Action.DELETE, changes={"tipo_interessado": interessado_manual.tipo_interessado})
        interessado_manual.delete()
        messages.success(request, "Interessado removido.")
        return redirect(request.POST.get("next") or reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema.pk}))
