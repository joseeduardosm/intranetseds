from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from django.db.utils import OperationalError, ProgrammingError
from sala_situacao.access import user_has_sala_situacao_access, user_is_monitoring_group_member


PROFILE_REVALIDATION_DAYS = 30
RAMAL_PROFILE_EXEMPT_USERNAMES = {"admin"}


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
        return {"diario_bordo_alert": None, "diario_bordo_alert_bloco": None}

    if not (user.is_superuser or user.has_perm("diario_bordo.view_blocotrabalho")):
        return {"diario_bordo_alert": None, "diario_bordo_alert_bloco": None}

    try:
        from django.db import models
        from django.db.models import OuterRef, Subquery, DateTimeField
        from django.db.utils import OperationalError, ProgrammingError
        from diario_bordo.models import BlocoTrabalho, BlocoLeitura
    except Exception:
        return {"diario_bordo_alert": None, "diario_bordo_alert_bloco": None}

    try:
        blocos = BlocoTrabalho.objects.all()
    except (OperationalError, ProgrammingError):
        return {"diario_bordo_alert": None, "diario_bordo_alert_bloco": None}
    if not user.is_superuser:
        blocos = blocos.filter(participantes=user)

    try:
        blocos = blocos.annotate(
            ultimo_incremento=models.Max("incrementos__criado_em")
        ).filter(ultimo_incremento__isnull=False)
    except (OperationalError, ProgrammingError):
        return {"diario_bordo_alert": None, "diario_bordo_alert_bloco": None}

    if not blocos.exists():
        return {"diario_bordo_alert": None, "diario_bordo_alert_bloco": None}

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
        return {"diario_bordo_alert": None, "diario_bordo_alert_bloco": None}

    if not pendente:
        return {"diario_bordo_alert": None, "diario_bordo_alert_bloco": None}

    try:
        ultimo_inc = (
            pendente.incrementos.order_by("-criado_em")
            .select_related("criado_por")
            .first()
        )
    except Exception:
        ultimo_inc = None

    usuario_nome = "alguem"
    data_texto = "agora"
    if ultimo_inc:
        if ultimo_inc.criado_por:
            usuario_nome = (
                ultimo_inc.criado_por.get_full_name()
                or ultimo_inc.criado_por.username
            )
        data_texto = ultimo_inc.criado_em.strftime("%d/%m/%Y %H:%M")

    return {
        "diario_bordo_alert": (
            f"{pendente.nome} - recebeu uma atualizacao de {usuario_nome} em {data_texto}"
        ),
        "diario_bordo_alert_bloco": pendente,
    }


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
