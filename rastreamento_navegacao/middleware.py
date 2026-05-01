"""Middleware de captura agregada de navegacao HTML."""

from __future__ import annotations

import re
from datetime import date

from django.db import IntegrityError, OperationalError, ProgrammingError
from django.db.models import F
from django.http import HttpRequest, HttpResponse
from django.utils.html import strip_tags

from .models import DailyPageVisit

TITLE_PATTERNS = (
    re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<h2[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL),
)
EXCLUDED_PREFIXES = (
    "/static/",
    "/media/",
    "/admin/",
    "/api/",
    "/administracao/configuracoes/rastreamento-navegacao/",
)
EXCLUDED_PATHS = {
    "/favicon.ico",
    "/login/",
    "/logout/",
}


def _clean_title(raw_title: str) -> str:
    cleaned = strip_tags(raw_title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:255]


def _fallback_title(request: HttpRequest) -> str:
    resolver_match = getattr(request, "resolver_match", None)
    if resolver_match:
        candidate = resolver_match.url_name or resolver_match.view_name or ""
        if candidate:
            return candidate.replace("_", " ").replace("-", " ").strip().title()
    path = (request.path or "/").strip("/")
    if not path:
        return "Home"
    return path.split("/")[-1].replace("-", " ").replace("_", " ").strip().title()


def _extract_title(response: HttpResponse, request: HttpRequest) -> str:
    content = getattr(response, "content", b"")
    if isinstance(content, bytes):
        decoded = content.decode(getattr(response, "charset", "utf-8"), errors="ignore")
    else:
        decoded = str(content)
    snippet = decoded[:20000]
    for pattern in TITLE_PATTERNS:
        match = pattern.search(snippet)
        if match:
            title = _clean_title(match.group(1))
            if title:
                return title
    return _fallback_title(request)


def _should_track_request(request: HttpRequest, response: HttpResponse) -> bool:
    if request.method != "GET":
        return False
    if response.status_code < 200 or response.status_code >= 400:
        return False
    if any(request.path.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return False
    if request.path in EXCLUDED_PATHS:
        return False
    content_type = (response.get("Content-Type") or "").lower()
    return "text/html" in content_type


def _persist_visit(request: HttpRequest, response: HttpResponse) -> None:
    today = date.today()
    path = request.path or "/"
    title = _extract_title(response, request)
    try:
        obj, created = DailyPageVisit.objects.get_or_create(
            visited_on=today,
            path=path,
            defaults={"title": title, "visit_count": 1},
        )
        if created:
            return
        DailyPageVisit.objects.filter(pk=obj.pk).update(
            visit_count=F("visit_count") + 1,
            title=title or obj.title,
        )
    except IntegrityError:
        DailyPageVisit.objects.filter(visited_on=today, path=path).update(
            visit_count=F("visit_count") + 1,
            title=title,
        )
    except (OperationalError, ProgrammingError):
        # Durante bootstrap/migrate a tabela ainda pode não existir.
        return


class PageVisitTrackingMiddleware:
    """Registra visitas HTML em agregados diários por caminho."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)

        if not _should_track_request(request, response):
            return response

        if hasattr(response, "add_post_render_callback"):
            response.add_post_render_callback(lambda rendered: _persist_visit(request, rendered))
            return response

        _persist_visit(request, response)
        return response
