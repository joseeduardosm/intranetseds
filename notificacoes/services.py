from __future__ import annotations

from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import NotificacaoUsuario


User = get_user_model()


SOURCE_ACOMPANHAMENTO_SISTEMAS = "acompanhamento_sistemas"


def _desktop_base_url() -> str:
    explicit = getattr(settings, "DESKTOP_CLIENT_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    trusted = getattr(settings, "CSRF_TRUSTED_ORIGINS", [])
    if trusted:
        return trusted[0].rstrip("/")
    hosts = getattr(settings, "ALLOWED_HOSTS", [])
    host = next((item for item in hosts if item not in {"localhost", "127.0.0.1", "*"}), "127.0.0.1")
    return f"http://{host}"


def absolutize_target_url(target_url: str) -> str:
    normalized = (target_url or "").strip()
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return urljoin(f"{_desktop_base_url()}/", normalized.lstrip("/"))


def emitir_notificacao(
    *,
    users,
    source_app: str,
    event_type: str,
    title: str,
    body_short: str,
    target_url: str,
    dedupe_key: str = "",
    payload_json: dict | None = None,
    dedupe_window_seconds: int | None = None,
):
    payload_json = payload_json or {}
    dedupe_window_seconds = (
        dedupe_window_seconds
        if dedupe_window_seconds is not None
        else getattr(settings, "DESKTOP_NOTIFICATION_DEDUPE_WINDOW_SECONDS", 300)
    )
    absolute_target_url = absolutize_target_url(target_url)
    now = timezone.now()
    cutoff = now - timezone.timedelta(seconds=dedupe_window_seconds)

    queryset = users if hasattr(users, "filter") else User.objects.filter(pk__in=[item.pk for item in users])
    queryset = queryset.filter(is_active=True).distinct()
    notificacoes = []
    for user in queryset:
        if dedupe_key:
            duplicada = NotificacaoUsuario.objects.filter(
                user=user,
                dedupe_key=dedupe_key,
                created_at__gte=cutoff,
            ).exists()
            if duplicada:
                continue
        notificacoes.append(
            NotificacaoUsuario(
                user=user,
                source_app=source_app,
                event_type=event_type,
                title=title.strip()[:160],
                body_short=body_short.strip()[:500],
                target_url=absolute_target_url,
                dedupe_key=(dedupe_key or "").strip()[:255],
                payload_json=payload_json,
            )
        )
    if notificacoes:
        NotificacaoUsuario.objects.bulk_create(notificacoes)
    return notificacoes

