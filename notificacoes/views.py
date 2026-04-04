from __future__ import annotations

import json

from django.contrib.auth import authenticate
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .auth import desktop_token_required
from .models import DesktopAPIToken, NotificacaoUsuario


def _json_body(request):
    try:
        raw = request.body.decode("utf-8") if request.body else "{}"
        return json.loads(raw or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _serialize_notificacao(item: NotificacaoUsuario) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "body_short": item.body_short,
        "target_url": item.target_url,
        "source_app": item.source_app,
        "event_type": item.event_type,
        "created_at": item.created_at.isoformat(),
        "read_at": item.read_at.isoformat() if item.read_at else None,
        "displayed_at": item.displayed_at.isoformat() if item.displayed_at else None,
    }


@csrf_exempt
@require_POST
def desktop_login(request):
    payload = _json_body(request)
    if payload is None:
        return JsonResponse({"detail": "Payload invalido."}, status=400)
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not username or not password:
        return JsonResponse({"detail": "Informe usuario e senha."}, status=400)

    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_active:
        return JsonResponse({"detail": "Credenciais invalidas."}, status=401)

    ttl_seconds = 60 * 60 * 24 * 30
    token, raw_token = DesktopAPIToken.issue_for_user(user, ttl_seconds=ttl_seconds)
    return JsonResponse(
        {
            "token": raw_token,
            "token_type": "Bearer",
            "expires_at": token.expires_at.isoformat(),
            "user": {
                "id": user.id,
                "username": user.username,
                "full_name": user.get_full_name().strip() or user.username,
                "email": user.email,
            },
        }
    )


@csrf_exempt
@require_POST
@desktop_token_required
def desktop_logout(request):
    token = request.desktop_token
    token.revoked_at = timezone.now()
    token.save(update_fields=["revoked_at"])
    return JsonResponse({"ok": True})


@require_GET
@desktop_token_required
def desktop_notificacoes_list(request):
    since_id_raw = (request.GET.get("since_id") or "").strip()
    queryset = NotificacaoUsuario.objects.filter(user=request.user).order_by("-id")
    if since_id_raw:
        try:
            since_id = int(since_id_raw)
        except ValueError:
            return JsonResponse({"detail": "since_id invalido."}, status=400)
        queryset = queryset.filter(id__gt=since_id)
    results = [_serialize_notificacao(item) for item in queryset[:100]]
    return JsonResponse({"results": results})


@csrf_exempt
@require_POST
@desktop_token_required
def desktop_notificacao_marcar_lida(request, pk: int):
    item = NotificacaoUsuario.objects.filter(pk=pk, user=request.user).first()
    if item is None:
        return JsonResponse({"detail": "Notificacao nao encontrada."}, status=404)
    if item.read_at is None:
        item.read_at = timezone.now()
        item.save(update_fields=["read_at"])
    return JsonResponse({"ok": True, "read_at": item.read_at.isoformat() if item.read_at else None})


@csrf_exempt
@require_POST
@desktop_token_required
def desktop_notificacao_marcar_exibida(request, pk: int):
    item = NotificacaoUsuario.objects.filter(pk=pk, user=request.user).first()
    if item is None:
        return JsonResponse({"detail": "Notificacao nao encontrada."}, status=404)
    if item.displayed_at is None:
        item.displayed_at = timezone.now()
        item.save(update_fields=["displayed_at"])
    return JsonResponse({"ok": True, "displayed_at": item.displayed_at.isoformat() if item.displayed_at else None})
