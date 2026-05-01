"""Views administrativas para leitura dos acessos agregados por pagina."""

from __future__ import annotations

import base64
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Sum
from django.http import Http404
from django.utils import timezone
from django.views.generic import TemplateView

from .models import DailyPageVisit


@dataclass
class PageSummary:
    title: str
    path: str
    visit_count: int
    average_per_day: Decimal
    detail_token: str


def _encode_page_token(path: str) -> str:
    return base64.urlsafe_b64encode(path.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_page_token(token: str) -> str:
    padding = "=" * (-len(token) % 4)
    try:
        return base64.urlsafe_b64decode(f"{token}{padding}".encode("ascii")).decode("utf-8")
    except Exception as exc:  # pragma: no cover - token inválido
        raise Http404("Pagina nao encontrada.") from exc


def _parse_date(value: str):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _normalize_period(request):
    today = timezone.localdate()
    default_start = today - timedelta(days=6)
    start = _parse_date(request.GET.get("data_inicio", "").strip()) or default_start
    end = _parse_date(request.GET.get("data_fim", "").strip()) or today
    if start > end:
        start, end = end, start
    return start, end


def _period_days(start, end) -> int:
    return ((end - start).days or 0) + 1


def _round_average(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class AdminOnlyMixin(UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        user = self.request.user
        return bool(user and user.is_authenticated and user.is_superuser)


class NavigationAnalyticsDashboardView(AdminOnlyMixin, TemplateView):
    template_name = "rastreamento_navegacao/dashboard.html"
    SORT_FIELDS = {"titulo", "caminho", "visitas", "media"}

    def _build_sort_link(self, field: str) -> str:
        query = self.request.GET.copy()
        current_sort = getattr(self, "_sort", "visitas")
        current_dir = getattr(self, "_dir", "desc")
        next_dir = "asc"
        if current_sort == field and current_dir == "asc":
            next_dir = "desc"
        query["sort"] = field
        query["dir"] = next_dir
        return query.urlencode()

    def _build_page_summaries(self, start, end):
        rows = DailyPageVisit.objects.filter(visited_on__range=(start, end)).order_by("path", "visited_on")
        period_days = Decimal(_period_days(start, end))
        grouped = {}

        for row in rows:
            entry = grouped.setdefault(
                row.path,
                {"title": row.title, "path": row.path, "visit_count": 0},
            )
            if row.title:
                entry["title"] = row.title
            entry["visit_count"] += row.visit_count

        summaries = []
        for path, data in grouped.items():
            average = _round_average(Decimal(data["visit_count"]) / period_days)
            summaries.append(
                PageSummary(
                    title=data["title"] or "Sem titulo",
                    path=path,
                    visit_count=data["visit_count"],
                    average_per_day=average,
                    detail_token=_encode_page_token(path),
                )
            )
        return summaries

    def _sort_page_summaries(self, summaries):
        sort = self.request.GET.get("sort", "visitas")
        direction = self.request.GET.get("dir", "desc")
        if sort not in self.SORT_FIELDS:
            sort = "visitas"
        if direction not in {"asc", "desc"}:
            direction = "desc"

        key_map = {
            "titulo": lambda item: item.title.casefold(),
            "caminho": lambda item: item.path.casefold(),
            "visitas": lambda item: item.visit_count,
            "media": lambda item: item.average_per_day,
        }
        summaries.sort(key=key_map[sort], reverse=direction == "desc")
        self._sort = sort
        self._dir = direction
        return summaries

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start, end = _normalize_period(self.request)
        series_rows = (
            DailyPageVisit.objects.filter(visited_on__range=(start, end))
            .values("visited_on")
            .annotate(total_visits=Sum("visit_count"))
            .order_by("visited_on")
        )
        totals_by_day = {row["visited_on"]: row["total_visits"] for row in series_rows}
        labels = []
        values = []
        cursor = start
        while cursor <= end:
            labels.append(cursor.strftime("%d/%m"))
            values.append(int(totals_by_day.get(cursor, 0) or 0))
            cursor += timedelta(days=1)

        summaries = self._sort_page_summaries(self._build_page_summaries(start, end))
        context.update(
            {
                "data_inicio": start.isoformat(),
                "data_fim": end.isoformat(),
                "total_dias": _period_days(start, end),
                "graph_labels_json": json.dumps(labels),
                "graph_values_json": json.dumps(values),
                "page_summaries": summaries,
                "sort": getattr(self, "_sort", "visitas"),
                "dir": getattr(self, "_dir", "desc"),
                "sort_links": {
                    "titulo": self._build_sort_link("titulo"),
                    "caminho": self._build_sort_link("caminho"),
                    "visitas": self._build_sort_link("visitas"),
                    "media": self._build_sort_link("media"),
                },
            }
        )
        return context


class NavigationAnalyticsDetailView(AdminOnlyMixin, TemplateView):
    template_name = "rastreamento_navegacao/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start, end = _normalize_period(self.request)
        page_path = _decode_page_token(self.kwargs["page_token"])
        rows = DailyPageVisit.objects.filter(path=page_path, visited_on__range=(start, end)).order_by("visited_on")
        if not rows.exists():
            raise Http404("Pagina nao encontrada para o periodo informado.")

        totals_by_day = defaultdict(int)
        latest_title = "Sem titulo"
        total_visits = 0
        for row in rows:
            totals_by_day[row.visited_on] += row.visit_count
            total_visits += row.visit_count
            if row.title:
                latest_title = row.title

        labels = []
        values = []
        cursor = start
        while cursor <= end:
            labels.append(cursor.strftime("%d/%m"))
            values.append(int(totals_by_day.get(cursor, 0)))
            cursor += timedelta(days=1)

        total_days = Decimal(_period_days(start, end))
        context.update(
            {
                "data_inicio": start.isoformat(),
                "data_fim": end.isoformat(),
                "page_title": latest_title,
                "page_path": page_path,
                "total_visits": total_visits,
                "average_per_day": _round_average(Decimal(total_visits) / total_days),
                "graph_labels_json": json.dumps(labels),
                "graph_values_json": json.dumps(values),
                "dashboard_query": f"data_inicio={start.isoformat()}&data_fim={end.isoformat()}",
            }
        )
        return context
