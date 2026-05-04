from __future__ import annotations

import re
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db.utils import OperationalError, ProgrammingError
from sala_situacao.access import user_has_sala_situacao_access, user_is_monitoring_group_member


PROFILE_REVALIDATION_DAYS = 30
RAMAL_PROFILE_EXEMPT_USERNAMES = {"admin", "kaio"}


def _user_is_ramal_profile_exempt(user) -> bool:
    username = getattr(user, "username", "") or ""
    return username.lower() in RAMAL_PROFILE_EXEMPT_USERNAMES


def ramal_profile(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {
            "ramal_profile": None,
            "ramal_missing_fields": False,
            "ramal_requires_revalidation": False,
            "ramal_profile_requires_update": False,
            "ramal_profile_update_allowed": False,
            "ramal_update_reason": None,
        }

    if _user_is_ramal_profile_exempt(user):
        return {
            "ramal_profile": None,
            "ramal_missing_fields": False,
            "ramal_requires_revalidation": False,
            "ramal_profile_requires_update": False,
            "ramal_profile_update_allowed": False,
            "ramal_update_reason": None,
        }

    try:
        profile = user.ramal_perfil
    except Exception:
        profile = None
    try:
        from usuarios.models import UserAccessState

        force_profile_update = bool(
            UserAccessState.objects.filter(user=user, force_profile_update=True).exists()
        )
    except Exception:
        force_profile_update = False

    if not profile:
        return {
            "ramal_profile": None,
            "ramal_missing_fields": True,
            "ramal_requires_revalidation": False,
            "ramal_profile_requires_update": True,
            "ramal_profile_update_allowed": False,
            "ramal_update_reason": "missing",
        }

    missing = any(
        not getattr(profile, field)
        for field in ("ramal", "email", "setor", "cargo", "foto")
    )
    updated_at = getattr(profile, "atualizado_em", None)
    requires_revalidation = True
    if updated_at:
        requires_revalidation = (timezone.now() - updated_at) >= timedelta(days=PROFILE_REVALIDATION_DAYS)
    profile_requires_update = bool(missing or requires_revalidation or force_profile_update)

    resolver_match = getattr(request, "resolver_match", None)
    url_name = getattr(resolver_match, "url_name", "")
    url_pk = None
    if resolver_match:
        url_pk = str(getattr(resolver_match, "kwargs", {}).get("pk", ""))
    update_allowed = (
        bool(profile)
        and url_name == "ramais_update"
        and str(profile.pk) == url_pk
    )
    update_reason = None
    if missing:
        update_reason = "missing"
    elif force_profile_update:
        update_reason = "missing"
    elif requires_revalidation:
        update_reason = "revalidation"

    return {
        "ramal_profile": profile,
        "ramal_missing_fields": missing,
        "ramal_requires_revalidation": requires_revalidation,
        "ramal_profile_requires_update": profile_requires_update,
        "ramal_profile_update_allowed": update_allowed,
        "ramal_update_reason": update_reason,
    }


def diario_bordo_alert(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {
            "diario_bordo_alert": None,
            "diario_bordo_alert_bloco": None,
            "diario_bordo_alert_incrementos": [],
        }

    if not (user.is_superuser or user.has_perm("diario_bordo.view_blocotrabalho")):
        return {
            "diario_bordo_alert": None,
            "diario_bordo_alert_bloco": None,
            "diario_bordo_alert_incrementos": [],
        }

    try:
        from django.db import models
        from django.db.models import OuterRef, Subquery, DateTimeField
        from django.db.utils import OperationalError, ProgrammingError
        from diario_bordo.models import BlocoTrabalho, BlocoLeitura, Incremento
    except Exception:
        return {
            "diario_bordo_alert": None,
            "diario_bordo_alert_bloco": None,
            "diario_bordo_alert_incrementos": [],
        }

    try:
        blocos = BlocoTrabalho.objects.all()
    except (OperationalError, ProgrammingError):
        return {
            "diario_bordo_alert": None,
            "diario_bordo_alert_bloco": None,
            "diario_bordo_alert_incrementos": [],
        }
    if not user.is_superuser:
        blocos = blocos.filter(participantes=user)

    try:
        blocos = blocos.annotate(
            ultimo_incremento=models.Max("incrementos__criado_em")
        ).filter(ultimo_incremento__isnull=False)
    except (OperationalError, ProgrammingError):
        return {
            "diario_bordo_alert": None,
            "diario_bordo_alert_bloco": None,
            "diario_bordo_alert_incrementos": [],
        }

    if not blocos.exists():
        return {
            "diario_bordo_alert": None,
            "diario_bordo_alert_bloco": None,
            "diario_bordo_alert_incrementos": [],
        }

    visto_sub = BlocoLeitura.objects.filter(
        usuario=user, bloco=OuterRef("pk")
    ).values("ultimo_incremento_visto_em")[:1]

    blocos = blocos.annotate(
        ultimo_visto=Subquery(visto_sub, output_field=DateTimeField())
    )

    try:
        pendente = (
            blocos.filter(
                models.Q(ultimo_visto__isnull=True)
                | models.Q(ultimo_incremento__gt=models.F("ultimo_visto"))
            )
            .order_by("-ultimo_incremento")
            .first()
        )
    except (OperationalError, ProgrammingError):
        return {
            "diario_bordo_alert": None,
            "diario_bordo_alert_bloco": None,
            "diario_bordo_alert_incrementos": [],
        }

    if not pendente:
        return {
            "diario_bordo_alert": None,
            "diario_bordo_alert_bloco": None,
            "diario_bordo_alert_incrementos": [],
        }

    bloco_visto_sub = BlocoLeitura.objects.filter(
        usuario=user,
        bloco=OuterRef("bloco_id"),
    ).values("ultimo_incremento_visto_em")[:1]
    try:
        incrementos_pendentes = list(
            Incremento.objects.filter(bloco__in=blocos)
            .select_related("bloco", "criado_por")
            .prefetch_related("anexos")
            .annotate(
                ultimo_visto=Subquery(bloco_visto_sub, output_field=DateTimeField())
            )
            .filter(
                models.Q(ultimo_visto__isnull=True)
                | models.Q(criado_em__gt=models.F("ultimo_visto"))
            )
            .order_by("criado_em", "pk")
        )
    except (OperationalError, ProgrammingError):
        incrementos_pendentes = []

    return {
        "diario_bordo_alert": None,
        "diario_bordo_alert_bloco": None,
        "diario_bordo_alert_incrementos": incrementos_pendentes,
    }


def _nome_usuario_curto(usuario) -> str:
    if not usuario:
        return "Sistema"
    nome = (usuario.get_full_name() or usuario.username or "Sistema").strip()
    partes = [parte for parte in nome.split() if parte.strip()]
    if len(partes) >= 2:
        return f"{partes[0]} {partes[1]}"
    return partes[0] if partes else "Sistema"


def _link_anexo(anexo) -> dict[str, str] | None:
    arquivo = getattr(anexo, "arquivo", None)
    if not arquivo:
        return None
    try:
        url = arquivo.url
    except Exception:
        return None
    nome = getattr(anexo, "nome_exibicao", "") or getattr(anexo, "nome_original", "") or url.rsplit("/", 1)[-1]
    return {"url": url, "nome": nome}


def _juntar_resumo_atualizacao(*partes) -> str:
    itens = [(parte or "").strip() for parte in partes if (parte or "").strip()]
    return " - ".join(itens) if itens else "-"


def _item_notificacao_acompanhamento(notificacao):
    payload = notificacao.payload_json or {}
    historico = None
    titulo = notificacao.title
    meta = timezone.localtime(notificacao.created_at).strftime("%d/%m/%Y %H:%M")
    conteudo = notificacao.body_short
    anexos = []
    linhas_corpo = [linha.strip() for linha in (conteudo or "").splitlines() if linha.strip()]
    if linhas_corpo:
        responsavel_match = re.match(
            r"^(?P<nome>.+?),\s*(?P<data>\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})$",
            linhas_corpo[-1],
        )
        if responsavel_match:
            meta = f"{responsavel_match.group('data')} - {responsavel_match.group('nome').strip()}"
            conteudo = "\n".join(linhas_corpo[:-1]) or conteudo

    try:
        from acompanhamento_sistemas.models import (
            HistoricoEtapaProcessoRequisito,
            HistoricoEtapaSistema,
            HistoricoProcessoRequisito,
            HistoricoSistema,
        )
    except Exception:
        return None

    try:
        if payload.get("historico_sistema_id"):
            historico = (
                HistoricoSistema.objects.select_related("sistema", "criado_por")
                .prefetch_related("anexos")
                .get(pk=payload["historico_sistema_id"])
            )
            titulo = f"Sistema: {historico.sistema.nome}"
            conteudo = f"Nota: {(historico.descricao or '-').strip() or '-'}"
        elif payload.get("historico_id") and notificacao.event_type.startswith("processo_etapa_"):
            historico = (
                HistoricoEtapaProcessoRequisito.objects.select_related(
                    "etapa__processo__sistema",
                    "criado_por",
                )
                .prefetch_related("anexos")
                .get(pk=payload["historico_id"])
            )
            titulo = f"Sistema: {historico.etapa.processo.sistema.nome}"
            conteudo = "Processo: " + _juntar_resumo_atualizacao(
                historico.etapa.processo.titulo,
                historico.etapa.get_tipo_etapa_display(),
                historico.get_tipo_evento_display(),
                historico.descricao,
                f"Justificativa: {historico.justificativa}" if historico.justificativa else "",
            )
        elif payload.get("historico_id") and notificacao.event_type.startswith("processo_"):
            historico = (
                HistoricoProcessoRequisito.objects.select_related(
                    "processo__sistema",
                    "criado_por",
                )
                .prefetch_related("anexos")
                .get(pk=payload["historico_id"])
            )
            titulo = f"Sistema: {historico.processo.sistema.nome}"
            conteudo = "Processo: " + _juntar_resumo_atualizacao(
                historico.processo.titulo,
                historico.get_tipo_evento_display(),
                historico.descricao,
            )
        elif payload.get("historico_id"):
            historico = (
                HistoricoEtapaSistema.objects.select_related(
                    "etapa__entrega__sistema",
                    "criado_por",
                )
                .prefetch_related("anexos")
                .get(pk=payload["historico_id"])
            )
            titulo = f"Sistema: {historico.etapa.entrega.sistema.nome}"
            conteudo = "Processo: " + _juntar_resumo_atualizacao(
                historico.etapa.entrega.titulo,
                historico.etapa.get_tipo_etapa_display(),
                historico.get_tipo_evento_display(),
                historico.descricao,
                f"Justificativa: {historico.justificativa}" if historico.justificativa else "",
            )
    except Exception:
        historico = None

    if historico is not None:
        meta = (
            f"{timezone.localtime(historico.criado_em).strftime('%d/%m/%Y %H:%M')} - "
            f"{_nome_usuario_curto(historico.criado_por)}"
        )
        anexos = [
            item for item in (_link_anexo(anexo) for anexo in historico.anexos.all()) if item
        ]

    return {
        "id": notificacao.pk,
        "titulo": titulo,
        "meta": meta,
        "conteudo": conteudo,
        "target_url": notificacao.target_url,
        "anexos": anexos,
    }


def acompanhamento_sistemas_alert(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {"acompanhamento_sistemas_alert_notificacoes": []}

    try:
        from django.urls import reverse
        from notificacoes.models import NotificacaoUsuario
        from notificacoes.services import SOURCE_ACOMPANHAMENTO_SISTEMAS
    except Exception:
        return {"acompanhamento_sistemas_alert_notificacoes": []}

    try:
        inicio_modal = parse_datetime(
            getattr(settings, "ACOMPANHAMENTO_MODAL_NOTIFICATIONS_START_AT", "")
        )
        if inicio_modal and timezone.is_naive(inicio_modal):
            inicio_modal = timezone.make_aware(inicio_modal, timezone.get_current_timezone())
        notificacoes = NotificacaoUsuario.objects.filter(
            user=user,
            source_app=SOURCE_ACOMPANHAMENTO_SISTEMAS,
            read_at__isnull=True,
        )
        if inicio_modal:
            notificacoes = notificacoes.filter(created_at__gte=inicio_modal)
        notificacoes = notificacoes.order_by("created_at", "id")[:25]
        itens = []
        for notificacao in notificacoes:
            item = _item_notificacao_acompanhamento(notificacao)
            if not item:
                continue
            item["read_url"] = reverse(
                "acompanhamento_sistemas_notificacao_marcar_lida",
                kwargs={"pk": notificacao.pk},
            )
            itens.append(item)
    except (OperationalError, ProgrammingError):
        itens = []

    return {"acompanhamento_sistemas_alert_notificacoes": itens}


def sala_situacao_access(request):
    user = getattr(request, "user", None)
    authenticated = bool(user and getattr(user, "is_authenticated", False))
    return {
        "sala_situacao_access": authenticated or user_has_sala_situacao_access(user),
        "sala_situacao_monitoring_member": user_is_monitoring_group_member(user),
    }


def identidade_visual(request):
    default_navbar = "#1f2a44"
    default_background = "#f2f0ea"
    default_brand_text = "#d94f04"
    try:
        from administracao.models import IdentidadeVisualConfig
        config = IdentidadeVisualConfig.objects.first()
    except (OperationalError, ProgrammingError, Exception):
        config = None

    background_color = getattr(config, "background_color", "") or default_background
    return {
        "theme_navbar_color": (
            getattr(config, "navbar_color", "") or default_navbar
        ),
        "theme_background_color": background_color,
        "theme_brand_text_color": (
            getattr(config, "brand_text_color", "") or default_brand_text
        ),
        "theme_shortcuts_bg_color": background_color,
    }


def administracao_navigation(request):
    try:
        from administracao.navigation import get_administracao_menu_items
    except Exception:
        return {
            "administracao_menu_items": [],
            "administracao_menu_visible": False,
        }

    user = getattr(request, "user", None)
    items = get_administracao_menu_items(user)
    return {
        "administracao_menu_items": items,
        "administracao_menu_visible": bool(items),
    }
