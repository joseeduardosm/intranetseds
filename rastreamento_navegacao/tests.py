from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import DailyPageVisit


class NavigationAnalyticsAccessTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.admin = self.user_model.objects.create_superuser(
            username="admin_nav",
            email="admin@example.com",
            password="senha-forte-123",
        )
        self.common_user = self.user_model.objects.create_user(
            username="usuario_nav",
            password="senha-forte-123",
        )

    def test_dashboard_requires_superuser(self):
        self.client.force_login(self.common_user)
        response = self.client.get(reverse("rastreamento_navegacao_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_dashboard_lists_aggregated_visits(self):
        DailyPageVisit.objects.create(
            visited_on=date(2026, 4, 1),
            title="Home",
            path="/",
            visit_count=5,
        )
        DailyPageVisit.objects.create(
            visited_on=date(2026, 4, 2),
            title="Home",
            path="/",
            visit_count=3,
        )
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("rastreamento_navegacao_dashboard"),
            {"data_inicio": "2026-04-01", "data_fim": "2026-04-07"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Home")
        self.assertContains(response, "/")
        self.assertContains(response, "8")


class NavigationTrackingMiddlewareTests(TestCase):
    def test_html_request_creates_daily_aggregate(self):
        self.client.get("/")
        self.assertTrue(DailyPageVisit.objects.filter(path="/").exists())
