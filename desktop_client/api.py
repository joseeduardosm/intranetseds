from __future__ import annotations

from typing import Any

import requests


class DesktopAPI:
    def __init__(self, base_url: str, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = requests.Session()
        self.timeout = 15

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def login(self, username: str, password: str) -> dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/api/desktop/auth/login/",
            json={"username": username, "password": password},
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        self.token = data["token"]
        return data

    def logout(self) -> None:
        if not self.token:
            return
        self.session.post(
            f"{self.base_url}/api/desktop/auth/logout/",
            headers=self._headers(),
            timeout=self.timeout,
        )
        self.token = ""

    def list_notifications(self, since_id: int) -> list[dict[str, Any]]:
        params = {"since_id": since_id} if since_id else {}
        response = self.session.get(
            f"{self.base_url}/api/desktop/notificacoes/",
            params=params,
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def mark_displayed(self, notification_id: int) -> None:
        self.session.post(
            f"{self.base_url}/api/desktop/notificacoes/{notification_id}/marcar-exibida/",
            headers=self._headers(),
            timeout=self.timeout,
        ).raise_for_status()

    def mark_read(self, notification_id: int) -> None:
        self.session.post(
            f"{self.base_url}/api/desktop/notificacoes/{notification_id}/marcar-lida/",
            headers=self._headers(),
            timeout=self.timeout,
        ).raise_for_status()

