"""
Views do app `diario_bordo`.

Este módulo concentra os fluxos HTTP de blocos de trabalho e incrementos:
listagem, detalhe, relatórios, criação/edição/exclusão e marcação de ciência.
Integra-se com `forms.py`, `models.py` e templates para operação diária.
"""

import json
import re

from django.contrib.auth import authenticate
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.auth.decorators import permission_required
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Prefetch
from django.http import HttpResponseRedirect, JsonResponse, Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_GET
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import BlocoTrabalhoCreateForm, BlocoTrabalhoUpdateForm, IncrementoForm
from .models import (
    BlocoTrabalho,
    BlocoLeitura,
    DiarioMarcador,
    DiarioMarcadorVinculo,
    Incremento,
    IncrementoCiencia,
    escolher_cor_marcador,
    normalizar_nome_marcador,
)


KANBAN_COLUMNS = [
    ("A_FAZER", "À Fazer"),
    ("SOLICITO_TERCEIROS", "Solicitado à terceiros"),
    ("AGUARDANDO_RESPOSTA", "Aguardando resposta"),
    ("EM_ANDAMENTO", "Em andamento"),
    ("CONCLUIDO", "Concluído"),
]


def _valor_historico(valor):
    """Normaliza valores para exibição legível nos incrementos automáticos."""

    if valor is None:
        return "(vazio)"
    if isinstance(valor, str):
        valor = valor.strip()
        return valor or "(vazio)"
    if isinstance(valor, (list, tuple, set)):
        itens = [str(item).strip() for item in valor if str(item).strip()]
        return ", ".join(itens) if itens else "(vazio)"
    return str(valor).strip() or "(vazio)"


def _nomes_usuarios(usuarios):
    """Converte coleção de usuários em nomes determinísticos para comparação/log."""

    return sorted((usuario.get_full_name() or usuario.username).strip() for usuario in usuarios)


def _nomes_marcadores(marcadores):
    """Converte coleção de marcadores em nomes determinísticos para comparação/log."""

    return sorted((marcador.nome or "").strip() for marcador in marcadores if (marcador.nome or "").strip())


def _tem_marcador_urgente(bloco) -> bool:
    """Sinaliza se o bloco possui marcador local/efetivo 'URGENTE'."""

    for marcador in bloco.marcadores_efetivos:
        if (marcador.nome or "").strip().upper() == "URGENTE":
            return True
    return False


def _can_view_all(user) -> bool:
    """
    Determina se o usuário possui visão global de blocos.

    Retorno:
    - `bool`: True para superusuário.
    """

    return user.is_superuser


def _can_manage_blocos(user) -> bool:
    """Permissão operacional para alterar blocos no Diário."""

    return (
        user.is_authenticated
        and (
            user.is_superuser
            or user.has_perm("diario_bordo.add_blocotrabalho")
            or user.has_perm("diario_bordo.change_blocotrabalho")
        )
    )


def _filter_by_participante(queryset, user):
    """
    Aplica filtro de participação ao queryset.

    Parâmetros:
    - `queryset`: queryset de blocos.
    - `user`: usuário atual.

    Retorno:
    - queryset completo (superuser) ou restrito por participante.
    """

    if _can_view_all(user):
        return queryset
    return queryset.filter(participantes=user)


def _apply_status_filter(queryset, filtro_status):
    """Aplica filtro de status conforme valor recebido na querystring."""

    if filtro_status == "todos":
        return queryset
    if filtro_status in {"novos", "a_fazer"}:
        return queryset.filter(status=BlocoTrabalho.Status.A_FAZER)
    if filtro_status == "terceiros":
        return queryset.filter(status=BlocoTrabalho.Status.SOLICITO_TERCEIROS)
    if filtro_status == "aguardando":
        return queryset.filter(status=BlocoTrabalho.Status.AGUARDANDO_RESPOSTA)
    if filtro_status == "andamento":
        return queryset.filter(status=BlocoTrabalho.Status.EM_ANDAMENTO)
    if filtro_status == "concluidos":
        return queryset.filter(status=BlocoTrabalho.Status.CONCLUIDO)
    return queryset.filter(
        status__in=[
            BlocoTrabalho.Status.A_FAZER,
            BlocoTrabalho.Status.SOLICITO_TERCEIROS,
            BlocoTrabalho.Status.AGUARDANDO_RESPOSTA,
            BlocoTrabalho.Status.EM_ANDAMENTO,
        ]
    )


def _get_alerta_class(status, dias_desde):
    """Converte idade da atualização em classe visual de alerta."""

    if status in [
        BlocoTrabalho.Status.A_FAZER,
        BlocoTrabalho.Status.SOLICITO_TERCEIROS,
        BlocoTrabalho.Status.AGUARDANDO_RESPOSTA,
        BlocoTrabalho.Status.EM_ANDAMENTO,
    ]:
        if dias_desde >= 5:
            return "bloco-alerta-preto"
        if dias_desde == 4:
            return "bloco-alerta-roxo"
        if dias_desde == 3:
            return "bloco-alerta-vermelho"
        if dias_desde == 2:
            return "bloco-alerta-laranja"
        if dias_desde == 1:
            return "bloco-alerta-amarelo"
    return ""


def _dias_desde(dt):
    if not dt:
        return 0
    data_referencia = timezone.localtime(dt).date() if timezone.is_aware(dt) else dt.date()
    return max(0, (timezone.localdate() - data_referencia).days)


def _dias_humanizados(dias):
    if dias == 0:
        return "hoje"
    if dias == 1:
        return "1 dia atrás"
    return f"{dias} dias atrás"


def _mark_bloco_seen(user, bloco):
    """Atualiza cursor de leitura do usuário para o último incremento do bloco."""

    if not getattr(user, "is_authenticated", False):
        return
    ultimo_incremento = bloco.incrementos.order_by("-criado_em").first()
    if not ultimo_incremento:
        return
    try:
        BlocoLeitura.objects.update_or_create(
            usuario=user,
            bloco=bloco,
            defaults={"ultimo_incremento_visto_em": ultimo_incremento.criado_em},
        )
    except Exception:
        # Tabela ainda pode nao existir durante migração inicial.
        return


@require_POST
@permission_required("diario_bordo.add_incremento", raise_exception=True)
def incremento_ciente(request, pk):
    """
    Registra ciência do usuário em um incremento específico.

    Regras de negócio:
    - respeita permissões/escopo de participação;
    - cria ciência única por usuário via `get_or_create`;
    - redireciona para `next` segura ou detalhe do bloco.
    """

    queryset = Incremento.objects.select_related("bloco")
    if not _can_view_all(request.user):
        queryset = queryset.filter(bloco__participantes=request.user)
    incremento_base = get_object_or_404(queryset, pk=pk)
    bloco = incremento_base.bloco

    usuario_nome = request.user.get_full_name() or request.user.username
    IncrementoCiencia.objects.get_or_create(
        incremento=incremento_base,
        usuario=request.user,
        defaults={
            "texto": f"{usuario_nome} ciente do incremento",
        },
    )
    _mark_bloco_seen(request.user, bloco)

    next_url = (request.POST.get("next") or "").strip()
    if next_url.startswith("/"):
        return HttpResponseRedirect(next_url)
    return HttpResponseRedirect(bloco.get_absolute_url())


@permission_required("diario_bordo.change_blocotrabalho", raise_exception=True)
def bloco_status_api(request, pk):
    """Atualiza status do bloco via API (drag-and-drop)."""

    if request.method not in {"PATCH", "POST"}:
        return HttpResponseNotAllowed(["PATCH", "POST"])
    bloco_qs = _filter_by_participante(BlocoTrabalho.objects.all(), request.user)
    bloco = get_object_or_404(bloco_qs, pk=pk)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}
    novo_status = (payload.get("status") or "").strip()
    validos = {item[0] for item in KANBAN_COLUMNS}
    if novo_status not in validos:
        return JsonResponse({"detail": "Status inválido."}, status=400)
    status_anterior = bloco.status
    status_anterior_label = bloco.get_status_display()
    if status_anterior == novo_status:
        return JsonResponse({"ok": True, "status": bloco.status, "status_label": bloco.get_status_display()})
    bloco.status = novo_status
    bloco.atualizado_em = timezone.now()
    bloco.atualizado_por = request.user if request.user.is_authenticated else None
    bloco.save(update_fields=["status", "atualizado_em", "atualizado_por"])
    Incremento.objects.create(
        bloco=bloco,
        texto=f"Status alterado de {status_anterior_label} para {bloco.get_status_display()}",
        criado_por=request.user if request.user.is_authenticated else None,
    )
    return JsonResponse({"ok": True, "status": bloco.status, "status_label": bloco.get_status_display()})


@require_GET
@permission_required("diario_bordo.view_blocotrabalho", raise_exception=True)
def marcador_sugestoes_api(request):
    q = (request.GET.get("q") or "").strip()
    queryset = DiarioMarcador.objects.filter(ativo=True)
    if q:
        normalizado = normalizar_nome_marcador(q)
        queryset = queryset.filter(
            models.Q(nome__icontains=q) | models.Q(nome_normalizado__icontains=normalizado)
        )
    resultados = list(queryset.order_by("nome")[:30].values("id", "nome", "cor"))
    return JsonResponse({"results": resultados})


def marcador_criar_api(request):
    if not _can_manage_blocos(request.user):
        return JsonResponse({"detail": "Sem permissão."}, status=403)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}
    nome = re.sub(r"\s+", " ", (payload.get("nome") or "").strip())
    if not nome:
        return JsonResponse({"detail": "Informe o nome do marcador."}, status=400)
    nome_normalizado = normalizar_nome_marcador(nome)
    marcador = DiarioMarcador.objects.filter(nome_normalizado=nome_normalizado).first()
    if marcador is None:
        marcador = DiarioMarcador.objects.create(
            nome=nome,
            nome_normalizado=nome_normalizado,
            cor=escolher_cor_marcador(),
            ativo=True,
        )
    elif marcador.nome != nome:
        marcador.nome = nome
        marcador.save(update_fields=["nome", "nome_normalizado", "atualizado_em"])
    return JsonResponse({"id": marcador.id, "nome": marcador.nome, "cor": marcador.cor}, status=201)


def marcador_cor_api(request, pk):
    if not _can_manage_blocos(request.user):
        return JsonResponse({"detail": "Sem permissão."}, status=403)
    if request.method != "PATCH":
        return HttpResponseNotAllowed(["PATCH"])
    marcador = DiarioMarcador.objects.filter(pk=pk, ativo=True).first()
    if not marcador:
        raise Http404("Marcador não encontrado.")
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}
    cor = (payload.get("cor") or "").strip()
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", cor):
        return JsonResponse({"detail": "Cor inválida. Use #RRGGBB."}, status=400)
    marcador.cor = cor
    marcador.save(update_fields=["cor", "atualizado_em"])
    return JsonResponse({"id": marcador.id, "nome": marcador.nome, "cor": marcador.cor})


def marcador_excluir_api(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Autenticação obrigatória."}, status=403)
    if request.method != "DELETE":
        return HttpResponseNotAllowed(["DELETE"])
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Payload inválido."}, status=400)
    admin_username = (payload.get("admin_username") or "").strip()
    admin_password = payload.get("admin_password") or ""
    if not admin_username or not admin_password:
        return JsonResponse({"detail": "Informe usuário e senha de admin."}, status=400)

    # Aceita login por username e também por email do usuário admin.
    candidatos_login = [admin_username]
    if "@" in admin_username:
        User = get_user_model()
        usernames = list(
            User.objects.filter(email__iexact=admin_username).values_list("username", flat=True)
        )
        candidatos_login.extend([username for username in usernames if username])

    admin_user = None
    for login in candidatos_login:
        admin_user = authenticate(request, username=login, password=admin_password)
        if admin_user:
            break

    admin_autorizado = (
        bool(admin_user)
        and admin_user.is_active
        and (
            admin_user.is_superuser
            or admin_user.is_staff
            or admin_user.has_perm("diario_bordo.change_diariomarcador")
            or admin_user.has_perm("diario_bordo.delete_diariomarcador")
        )
    )
    if not admin_autorizado:
        return JsonResponse({"detail": "Credenciais administrativas inválidas."}, status=403)
    marcador = DiarioMarcador.objects.filter(pk=pk, ativo=True).first()
    if not marcador:
        raise Http404("Marcador não encontrado.")
    marcador.ativo = False
    marcador.save(update_fields=["ativo", "atualizado_em"])
    return JsonResponse({"ok": True})


@require_GET
@permission_required("diario_bordo.view_blocotrabalho", raise_exception=True)
def bloco_marcadores_api(request, pk):
    bloco_qs = _filter_by_participante(BlocoTrabalho.objects.prefetch_related("marcadores_vinculos__marcador"), request.user)
    bloco = get_object_or_404(bloco_qs, pk=pk)
    locais = [{"id": m.id, "nome": m.nome, "cor": m.cor} for m in bloco.marcadores_locais]
    return JsonResponse({"locais": locais, "efetivos": locais})


@require_POST
def bloco_marcador_vincular_api(request, pk):
    if not _can_manage_blocos(request.user):
        return JsonResponse({"detail": "Sem permissão."}, status=403)
    bloco_qs = _filter_by_participante(BlocoTrabalho.objects.all(), request.user)
    bloco = get_object_or_404(bloco_qs, pk=pk)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}
    marcador_id = payload.get("marcador_id")
    if not str(marcador_id).isdigit():
        return JsonResponse({"detail": "marcador_id inválido."}, status=400)
    marcador = DiarioMarcador.objects.filter(pk=int(marcador_id), ativo=True).first()
    if not marcador:
        return JsonResponse({"detail": "Marcador não encontrado."}, status=404)
    DiarioMarcadorVinculo.objects.get_or_create(bloco=bloco, marcador=marcador)
    return JsonResponse({"id": marcador.id, "nome": marcador.nome, "cor": marcador.cor}, status=201)


def bloco_marcador_desvincular_api(request, pk, marcador_id):
    if not _can_manage_blocos(request.user):
        return JsonResponse({"detail": "Sem permissão."}, status=403)
    if request.method != "DELETE":
        return HttpResponseNotAllowed(["DELETE"])
    bloco_qs = _filter_by_participante(BlocoTrabalho.objects.all(), request.user)
    bloco = get_object_or_404(bloco_qs, pk=pk)
    DiarioMarcadorVinculo.objects.filter(
        bloco=bloco,
        marcador_id=marcador_id,
    ).delete()
    return JsonResponse({"ok": True})




class BlocoTrabalhoListView(PermissionRequiredMixin, ListView):
    """Lista blocos de trabalho com filtros e indicadores de prioridade."""

    model = BlocoTrabalho
    template_name = "diario_bordo/bloco_list.html"
    context_object_name = "blocos"
    permission_required = "diario_bordo.view_blocotrabalho"

    def get_queryset(self):
        """
        Monta queryset da listagem com pré-carregamento e filtros de interface.
        """

        incrementos_ordenados = Incremento.objects.order_by("-criado_em")
        queryset = BlocoTrabalho.objects.prefetch_related(
            Prefetch("incrementos", queryset=incrementos_ordenados),
            "participantes",
            "marcadores_vinculos__marcador",
        )
        queryset = _filter_by_participante(queryset, self.request.user)
        filtro_status = self.request.GET.get("status", "ativos").strip()
        queryset = _apply_status_filter(queryset, filtro_status)
        termo = self.request.GET.get("q", "").strip()
        if termo:
            queryset = queryset.filter(
                models.Q(nome__icontains=termo)
                | models.Q(descricao__icontains=termo)
                | models.Q(status__icontains=termo)
            )
        return queryset

    def get_context_data(self, **kwargs):
        """Enriquecimento do contexto da listagem com métricas e links auxiliares."""
        context = super().get_context_data(**kwargs)
        blocos = []
        for bloco in context["blocos"]:
            ultimo_incremento = next(iter(bloco.incrementos.all()), None)
            ultimo_incremento_em = ultimo_incremento.criado_em if ultimo_incremento else None
            ultima_alteracao_em = bloco.atualizado_em or bloco.criado_em
            if ultimo_incremento_em and ultimo_incremento_em >= ultima_alteracao_em:
                bloco.ultima_atualizacao = ultimo_incremento_em
                bloco.ultimo_usuario = ultimo_incremento.criado_por
            else:
                bloco.ultima_atualizacao = ultima_alteracao_em
                bloco.ultimo_usuario = bloco.atualizado_por
            if bloco.ultimo_usuario:
                bloco.ultimo_usuario_nome = (
                    bloco.ultimo_usuario.get_full_name() or bloco.ultimo_usuario.username
                )
            else:
                bloco.ultimo_usuario_nome = None
            dias_desde = _dias_desde(bloco.ultima_atualizacao)
            bloco.classe_alerta = _get_alerta_class(bloco.status, dias_desde)
            bloco.dias_desde = dias_desde
            bloco.criado_dias = _dias_desde(bloco.criado_em)
            bloco.criado_humanizado = _dias_humanizados(bloco.criado_dias)
            bloco.atualizado_humanizado = _dias_humanizados(bloco.dias_desde)
            bloco.tem_marcador_urgente = _tem_marcador_urgente(bloco)
            blocos.append(bloco)
        blocos = sorted(
            blocos,
            key=lambda item: (
                0 if item.tem_marcador_urgente else 1,
                -item.dias_desde,
            ),
        )
        context["blocos"] = blocos
        context["filtro_status"] = self.request.GET.get("status", "ativos")
        detail_params = self.request.GET.copy()
        detail_querystring = detail_params.urlencode()
        context["detail_querystring"] = f"?{detail_querystring}" if detail_querystring else ""
        relatorio_params = self.request.GET.copy()
        relatorio_params.pop("view", None)
        relatorio_params_completo = relatorio_params.copy()
        relatorio_params_completo.pop("tipo", None)
        if relatorio_params_completo:
            context["relatorio_url"] = (
                f"{reverse('diario_bordo_relatorio')}?{relatorio_params_completo.urlencode()}"
            )
        else:
            context["relatorio_url"] = reverse("diario_bordo_relatorio")

        relatorio_params_executivo = relatorio_params.copy()
        relatorio_params_executivo["tipo"] = "executivo"
        context["relatorio_executivo_url"] = (
            f"{reverse('diario_bordo_relatorio')}?{relatorio_params_executivo.urlencode()}"
        )
        relatorio_params_daily = relatorio_params.copy()
        relatorio_params_daily["tipo"] = "daily"
        context["relatorio_daily_url"] = (
            f"{reverse('diario_bordo_relatorio')}?{relatorio_params_daily.urlencode()}"
        )
        context["blocos_em_andamento"] = _filter_by_participante(
            BlocoTrabalho.objects.all(), self.request.user
        ).filter(
            status__in=[
                BlocoTrabalho.Status.A_FAZER,
                BlocoTrabalho.Status.SOLICITO_TERCEIROS,
                BlocoTrabalho.Status.AGUARDANDO_RESPOSTA,
                BlocoTrabalho.Status.EM_ANDAMENTO,
            ]
        ).count()
        bloco_ids = [bloco.id for bloco in blocos]
        feed_items = []
        if bloco_ids:
            incrementos = (
                Incremento.objects.filter(bloco_id__in=bloco_ids)
                .select_related("bloco", "criado_por")
                .order_by("-criado_em")
            )
            for incremento in incrementos:
                usuario = incremento.criado_por
                if usuario:
                    usuario_nome = usuario.get_full_name() or usuario.username
                else:
                    usuario_nome = "Sistema"
                feed_items.append(
                    {
                        "bloco": incremento.bloco,
                        "titulo": incremento.bloco.nome,
                        "usuario": usuario_nome,
                        "criado_em": timezone.localtime(incremento.criado_em),
                        "texto": incremento.texto,
                    }
                )
        context["feed_atualizacoes"] = feed_items[:5]
        columns = []
        for status_key, status_label in KANBAN_COLUMNS:
            items = sorted(
                [item for item in blocos if item.status == status_key],
                key=lambda item: (
                    0 if item.tem_marcador_urgente else 1,
                    -item.dias_desde,
                ),
            )
            columns.append(
                {
                    "key": status_key,
                    "label": status_label,
                    "items": items,
                    "count": len(items),
                }
            )
        context["kanban_columns"] = columns
        context["kanban_status_json"] = json.dumps(
            [{"value": key, "label": label} for key, label in KANBAN_COLUMNS],
            ensure_ascii=False,
        )
        return context


class BlocoTrabalhoRelatorioView(PermissionRequiredMixin, ListView):
    """Lista de blocos orientada à impressão/exportação de relatórios."""

    model = BlocoTrabalho
    template_name = "diario_bordo/bloco_relatorio.html"
    context_object_name = "blocos"
    permission_required = "diario_bordo.view_blocotrabalho"

    def get_queryset(self):
        """Monta queryset do relatório com os mesmos filtros da listagem."""
        incrementos_ordenados = Incremento.objects.order_by("criado_em")
        queryset = BlocoTrabalho.objects.prefetch_related(
            Prefetch("incrementos", queryset=incrementos_ordenados),
            "participantes",
        )
        queryset = _filter_by_participante(queryset, self.request.user)
        filtro_status = self.request.GET.get("status", "ativos").strip()
        queryset = _apply_status_filter(queryset, filtro_status)
        termo = self.request.GET.get("q", "").strip()
        if termo:
            queryset = queryset.filter(
                models.Q(nome__icontains=termo)
                | models.Q(descricao__icontains=termo)
                | models.Q(status__icontains=termo)
            )
        return queryset

    def get_context_data(self, **kwargs):
        """Calcula dados derivados do relatório e aplica filtro de legenda."""
        context = super().get_context_data(**kwargs)
        legenda = self.request.GET.get("legenda", "").strip()
        tipo = self.request.GET.get("tipo", "").strip().lower()
        if tipo == "daily":
            self.template_name = "diario_bordo/bloco_relatorio_daily.html"
        context["relatorio_tipo"] = "executivo" if tipo == "executivo" else "completo"
        for bloco in context["blocos"]:
            ultimo_incremento = bloco.incrementos.all().last()
            ultimo_incremento_em = ultimo_incremento.criado_em if ultimo_incremento else None
            ultima_alteracao_em = bloco.atualizado_em or bloco.criado_em
            ultima_atualizacao = (
                ultimo_incremento_em
                if ultimo_incremento_em and ultimo_incremento_em >= ultima_alteracao_em
                else ultima_alteracao_em
            )
            bloco.dias_desde = _dias_desde(ultima_atualizacao)
            bloco.classe_alerta = _get_alerta_class(bloco.status, bloco.dias_desde)
            bloco.ultima_atualizacao = ultima_atualizacao
            bloco.ultimo_usuario = (
                ultimo_incremento.criado_por if ultimo_incremento else bloco.atualizado_por
            )
            bloco.ultimo_incremento = ultimo_incremento
            if bloco.ultimo_usuario:
                bloco.ultimo_usuario_nome = (
                    bloco.ultimo_usuario.get_full_name() or bloco.ultimo_usuario.username
                )
            else:
                bloco.ultimo_usuario_nome = None
        if legenda and legenda != "all":
            context["blocos"] = [
                bloco for bloco in context["blocos"] if bloco.classe_alerta == legenda
            ]
        return context


class BlocoTrabalhoDetailView(PermissionRequiredMixin, DetailView):
    """Exibe detalhe do bloco com incrementos paginados e navegação contextual."""

    model = BlocoTrabalho
    template_name = "diario_bordo/bloco_detail.html"
    context_object_name = "bloco"
    permission_required = "diario_bordo.view_blocotrabalho"

    def get_queryset(self):
        """Restringe detalhe a blocos permitidos ao usuário atual."""

        # Bloqueia acesso direto a blocos alheios.
        queryset = super().get_queryset().prefetch_related(
            "participantes",
            "marcadores_vinculos__marcador",
        )
        return _filter_by_participante(queryset, self.request.user)

    def get_context_data(self, **kwargs):
        """Monta detalhe com paginação, ordenação e navegação entre blocos filtrados."""
        context = super().get_context_data(**kwargs)
        ultimo_incremento_obj = self.object.incrementos.order_by("-criado_em").first()
        ultimo_incremento_em = ultimo_incremento_obj.criado_em if ultimo_incremento_obj else None
        ultima_alteracao_em = self.object.atualizado_em or self.object.criado_em
        self.object.ultima_atualizacao = (
            ultimo_incremento_em
            if ultimo_incremento_em and ultimo_incremento_em >= ultima_alteracao_em
            else ultima_alteracao_em
        )
        ordem_data = self.request.GET.get("data", "desc")
        if ordem_data == "asc":
            incrementos_qs = self.object.incrementos.order_by("criado_em")
        else:
            incrementos_qs = self.object.incrementos.order_by("-criado_em")
        incrementos_qs = incrementos_qs.prefetch_related("ciencias__usuario", "anexos")
        from django.core.paginator import Paginator
        page_number = self.request.GET.get("inc_page", "1")
        paginator = Paginator(incrementos_qs, 6)
        page_obj = paginator.get_page(page_number)
        context["incrementos"] = page_obj.object_list
        context["incrementos_page"] = page_obj
        context["incrementos_paginator"] = paginator
        context["ordem_data"] = ordem_data
        context["incremento_form"] = IncrementoForm()
        params = self.request.GET.copy()
        querystring = params.urlencode()
        query_suffix = f"?{querystring}" if querystring else ""
        context["filtro_querystring"] = query_suffix
        params_sem_pagina = self.request.GET.copy()
        params_sem_pagina.pop("inc_page", None)
        base_query = params_sem_pagina.urlencode()
        context["incrementos_page_base"] = f"?{base_query}&inc_page=" if base_query else "?inc_page="
        params_sem_data = self.request.GET.copy()
        params_sem_data.pop("data", None)
        params_desc = params_sem_data.copy()
        params_desc["data"] = "desc"
        params_asc = params_sem_data.copy()
        params_asc["data"] = "asc"
        context["ordem_desc_url"] = f"?{params_desc.urlencode()}"
        context["ordem_asc_url"] = f"?{params_asc.urlencode()}"
        if query_suffix:
            context["voltar_url"] = f"{reverse('diario_bordo_list')}{query_suffix}"
        else:
            context["voltar_url"] = reverse("diario_bordo_list")
        _mark_bloco_seen(self.request.user, self.object)

        incrementos_ordenados = Incremento.objects.order_by("-criado_em")
        blocos = BlocoTrabalho.objects.prefetch_related(
            Prefetch("incrementos", queryset=incrementos_ordenados),
            "participantes",
        )
        blocos = _filter_by_participante(blocos, self.request.user)
        filtro_status = self.request.GET.get("status", "ativos").strip()
        blocos = _apply_status_filter(blocos, filtro_status)
        termo = self.request.GET.get("q", "").strip()
        if termo:
            blocos = blocos.filter(
                models.Q(nome__icontains=termo)
                | models.Q(descricao__icontains=termo)
                | models.Q(status__icontains=termo)
            )
        blocos_list = list(blocos)
        for bloco in blocos_list:
            ultimo_incremento = next(iter(bloco.incrementos.all()), None)
            ultimo_incremento_em = ultimo_incremento.criado_em if ultimo_incremento else None
            ultima_alteracao_em = bloco.atualizado_em or bloco.criado_em
            ultima_atualizacao = (
                ultimo_incremento_em
                if ultimo_incremento_em and ultimo_incremento_em >= ultima_alteracao_em
                else ultima_alteracao_em
            )
            dias_desde = _dias_desde(ultima_atualizacao)
            bloco.dias_desde = dias_desde
            bloco.classe_alerta = _get_alerta_class(bloco.status, dias_desde)
        legenda = self.request.GET.get("legenda", "").strip()
        if legenda and legenda != "all":
            blocos_list = [bloco for bloco in blocos_list if bloco.classe_alerta == legenda]
        blocos_list = sorted(blocos_list, key=lambda item: item.dias_desde, reverse=True)
        bloco_anterior = None
        bloco_proximo = None
        for idx, bloco in enumerate(blocos_list):
            if bloco.pk == self.object.pk:
                if idx > 0:
                    bloco_anterior = blocos_list[idx - 1]
                if idx + 1 < len(blocos_list):
                    bloco_proximo = blocos_list[idx + 1]
                break
        context["bloco_anterior"] = bloco_anterior
        context["bloco_proximo"] = bloco_proximo
        return context


class BlocoTrabalhoRelatorioDetalheView(PermissionRequiredMixin, DetailView):
    """Detalhe de bloco em versão voltada para relatório."""

    model = BlocoTrabalho
    template_name = "diario_bordo/bloco_relatorio_detalhe.html"
    context_object_name = "bloco"
    permission_required = "diario_bordo.view_blocotrabalho"

    def get_queryset(self):
        """Restringe visualização de relatório ao escopo de acesso do usuário."""

        incrementos_ordenados = Incremento.objects.order_by("criado_em")
        queryset = BlocoTrabalho.objects.prefetch_related(
            Prefetch("incrementos", queryset=incrementos_ordenados),
            "participantes",
        )
        return _filter_by_participante(queryset, self.request.user)

    def get_context_data(self, **kwargs):
        """Calcula dias desde atualização para a exibição do relatório."""

        context = super().get_context_data(**kwargs)
        ultimo_incremento = self.object.incrementos.all().last()
        ultimo_incremento_em = ultimo_incremento.criado_em if ultimo_incremento else None
        ultima_alteracao_em = self.object.atualizado_em or self.object.criado_em
        ultima_atualizacao = (
            ultimo_incremento_em
            if ultimo_incremento_em and ultimo_incremento_em >= ultima_alteracao_em
            else ultima_alteracao_em
        )
        context["dias_desde"] = _dias_desde(ultima_atualizacao)
        _mark_bloco_seen(self.request.user, self.object)
        return context


class BlocoTrabalhoCreateView(PermissionRequiredMixin, CreateView):
    """Fluxo HTTP de criação de bloco com automações de histórico."""

    model = BlocoTrabalho
    form_class = BlocoTrabalhoCreateForm
    template_name = "diario_bordo/bloco_form.html"
    success_url = reverse_lazy("diario_bordo_list")
    permission_required = "diario_bordo.add_blocotrabalho"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["marcador_item_tipo"] = "bloco"
        context["marcador_sugestoes_url"] = reverse("diario_bordo_marcador_sugestoes_api")
        context["marcador_criar_url"] = reverse("diario_bordo_marcador_criar_api")
        context["marcador_cor_url_template"] = reverse("diario_bordo_marcador_cor_api", kwargs={"pk": 0})
        context["marcador_excluir_url_template"] = reverse("diario_bordo_marcador_excluir_api", kwargs={"pk": 0})
        context["marcador_item_url_template"] = reverse(
            "diario_bordo_bloco_marcadores_api",
            kwargs={"pk": 0},
        )
        context["marcador_item_id"] = ""
        return context

    def form_valid(self, form):
        """Persiste bloco e registra incrementos automáticos de criação e participantes."""
        if self.request.user.is_authenticated:
            form.instance.atualizado_por = self.request.user
        form.instance.atualizado_em = timezone.now()
        response = super().form_valid(form)
        # Criador vira participante do bloco.
        if self.request.user.is_authenticated:
            self.object.participantes.add(self.request.user)
        participantes_finais = set(self.object.participantes.all())
        participantes_adicionados = participantes_finais - set()
        # Incremento de inclusao de participantes (ignora criador automatico).
        for participante in participantes_adicionados:
            if (
                self.request.user.is_authenticated
                and participante.id == self.request.user.id
            ):
                continue
            nome = participante.get_full_name() or participante.username
            Incremento.objects.create(
                bloco=self.object,
                texto=f"{nome} inserido no bloco de trabalho",
                criado_por=self.request.user if self.request.user.is_authenticated else None,
            )
        Incremento.objects.create(
            bloco=self.object,
            texto=f"Criação do Bloco: {self.object.nome}",
            criado_por=self.request.user if self.request.user.is_authenticated else None,
        )
        _mark_bloco_seen(self.request.user, self.object)
        return response


class BlocoTrabalhoUpdateView(PermissionRequiredMixin, UpdateView):
    """Fluxo HTTP de atualização de bloco com trilha de participantes."""

    model = BlocoTrabalho
    form_class = BlocoTrabalhoUpdateForm
    template_name = "diario_bordo/bloco_form.html"
    permission_required = "diario_bordo.change_blocotrabalho"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["marcador_item_tipo"] = "bloco"
        context["marcador_sugestoes_url"] = reverse("diario_bordo_marcador_sugestoes_api")
        context["marcador_criar_url"] = reverse("diario_bordo_marcador_criar_api")
        context["marcador_cor_url_template"] = reverse("diario_bordo_marcador_cor_api", kwargs={"pk": 0})
        context["marcador_excluir_url_template"] = reverse("diario_bordo_marcador_excluir_api", kwargs={"pk": 0})
        context["marcador_item_url_template"] = reverse(
            "diario_bordo_bloco_marcadores_api",
            kwargs={"pk": 0},
        )
        context["marcador_item_id"] = self.object.pk
        return context

    def get_queryset(self):
        """Restringe edição a blocos permitidos ao usuário."""

        queryset = super().get_queryset()
        return _filter_by_participante(queryset, self.request.user)

    def form_valid(self, form):
        """Registra alterações do bloco como incrementos automáticos."""
        bloco_original = BlocoTrabalho.objects.get(pk=self.object.pk)
        alteracoes = []
        if "nome" in form.changed_data:
            alteracoes.append(
                f"Alterou nome de {_valor_historico(bloco_original.nome)} para {_valor_historico(form.cleaned_data.get('nome'))}"
            )
        if "descricao" in form.changed_data:
            alteracoes.append(
                "Alterou descricao de "
                f"{_valor_historico(bloco_original.descricao)} para {_valor_historico(form.cleaned_data.get('descricao'))}"
            )
        if "status" in form.changed_data:
            alteracoes.append(
                "Alterou status de "
                f"{_valor_historico(bloco_original.get_status_display())} "
                f"para {_valor_historico(form.instance.get_status_display())}"
            )

        participantes_anteriores = set(bloco_original.participantes.all())
        nomes_participantes_anteriores = _nomes_usuarios(participantes_anteriores)
        marcadores_anteriores = list(bloco_original.marcadores_locais)
        nomes_marcadores_anteriores = _nomes_marcadores(marcadores_anteriores)
        if self.request.user.is_authenticated:
            form.instance.atualizado_por = self.request.user
        form.instance.atualizado_em = timezone.now()
        response = super().form_valid(form)
        participantes_novos = set(self.object.participantes.all())
        nomes_participantes_novos = _nomes_usuarios(participantes_novos)
        if nomes_participantes_anteriores != nomes_participantes_novos:
            alteracoes.append(
                "Alterou participantes de "
                f"{_valor_historico(nomes_participantes_anteriores)} "
                f"para {_valor_historico(nomes_participantes_novos)}"
            )
        nomes_marcadores_novos = _nomes_marcadores(self.object.marcadores_locais)
        if nomes_marcadores_anteriores != nomes_marcadores_novos:
            alteracoes.append(
                "Alterou marcadores de "
                f"{_valor_historico(nomes_marcadores_anteriores)} "
                f"para {_valor_historico(nomes_marcadores_novos)}"
            )

        adicionados = participantes_novos - participantes_anteriores
        for participante in adicionados:
            nome = participante.get_full_name() or participante.username
            Incremento.objects.create(
                bloco=self.object,
                texto=f"{nome} inserido no bloco de trabalho",
                criado_por=self.request.user if self.request.user.is_authenticated else None,
            )
        for texto in alteracoes:
            Incremento.objects.create(
                bloco=self.object,
                texto=texto,
                criado_por=self.request.user if self.request.user.is_authenticated else None,
            )
        _mark_bloco_seen(self.request.user, self.object)
        return response

    def get_success_url(self):
        """Retorna URL de detalhe do bloco atualizado."""

        return self.object.get_absolute_url()


class BlocoTrabalhoDeleteView(PermissionRequiredMixin, DeleteView):
    """Fluxo HTTP de exclusão de bloco com filtro por participação."""

    model = BlocoTrabalho
    template_name = "diario_bordo/bloco_confirm_delete.html"
    success_url = reverse_lazy("diario_bordo_list")
    permission_required = "diario_bordo.delete_blocotrabalho"

    def get_queryset(self):
        """Restringe exclusão aos blocos permitidos ao usuário."""

        queryset = super().get_queryset()
        return _filter_by_participante(queryset, self.request.user)


class IncrementoCreateView(PermissionRequiredMixin, CreateView):
    """
    Fluxo HTTP de criação de incremento.

    Regra de negócio:
    - primeiro incremento de um bloco À Fazer altera status para Em andamento.
    """

    model = Incremento
    form_class = IncrementoForm
    template_name = "diario_bordo/incremento_form.html"
    permission_required = "diario_bordo.add_incremento"

    def _get_bloco(self):
        """Obtém bloco alvo validando permissão de participação."""

        # Garante permissao ao adicionar incremento.
        queryset = BlocoTrabalho.objects.all()
        queryset = _filter_by_participante(queryset, self.request.user)
        return queryset.get(pk=self.kwargs["pk"])

    def form_valid(self, form):
        """Define bloco/autor do incremento e aplica transição automática de status."""

        bloco = self._get_bloco()
        form.instance.bloco = bloco
        if self.request.user.is_authenticated:
            form.instance.criado_por = self.request.user
        if bloco.status == BlocoTrabalho.Status.A_FAZER:
            bloco.status = BlocoTrabalho.Status.EM_ANDAMENTO
            bloco.save(update_fields=["status"])
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        """Inclui bloco alvo no contexto do formulário de incremento."""

        context = super().get_context_data(**kwargs)
        context["bloco"] = self._get_bloco()
        return context

    def get_success_url(self):
        """Retorna detalhe do bloco após criar incremento."""

        return self.object.bloco.get_absolute_url()


class IncrementoUpdateView(PermissionRequiredMixin, UpdateView):
    """Fluxo HTTP de edição de incremento com restrição por participação."""

    model = Incremento
    form_class = IncrementoForm
    template_name = "diario_bordo/incremento_form.html"
    permission_required = "diario_bordo.change_incremento"

    def get_queryset(self):
        """Restringe edição de incremento ao escopo permitido ao usuário."""

        queryset = super().get_queryset().select_related("bloco")
        if _can_view_all(self.request.user):
            return queryset
        return queryset.filter(bloco__participantes=self.request.user)

    def get_context_data(self, **kwargs):
        """Expõe bloco relacionado no contexto da tela de edição."""

        context = super().get_context_data(**kwargs)
        context["bloco"] = self.object.bloco
        return context

    def get_success_url(self):
        """Retorna detalhe do bloco após edição do incremento."""

        return self.object.bloco.get_absolute_url()


class IncrementoDeleteView(PermissionRequiredMixin, DeleteView):
    """Fluxo HTTP de remoção de incremento com validação de acesso."""

    model = Incremento
    template_name = "diario_bordo/incremento_confirm_delete.html"
    permission_required = "diario_bordo.delete_incremento"

    def get_queryset(self):
        """Restringe exclusão de incremento ao escopo permitido ao usuário."""

        queryset = super().get_queryset().select_related("bloco")
        if _can_view_all(self.request.user):
            return queryset
        return queryset.filter(bloco__participantes=self.request.user)

    def get_success_url(self):
        """Retorna detalhe do bloco após exclusão do incremento."""

        return self.object.bloco.get_absolute_url()
