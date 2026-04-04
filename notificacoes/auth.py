from __future__ import annotations

from functools import wraps
from typing import Callable

from django.http import JsonResponse
from django.utils import timezone

from .models import DesktopAPIToken


def _bearer_token(request) -> str:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return ""
    return header[7:].strip()


def desktop_token_required(view_func: Callable):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        raw_token = _bearer_token(request)
        token = DesktopAPIToken.from_raw_token(raw_token)
        if token is None:
            return JsonResponse({"detail": "Autenticacao invalida."}, status=401)
        token.last_used_at = timezone.now()
        token.save(update_fields=["last_used_at"])
        request.desktop_token = token
        request.user = token.user
        return view_func(request, *args, **kwargs)

    return _wrapped

