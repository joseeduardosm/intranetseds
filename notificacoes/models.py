from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone


User = get_user_model()


class NotificacaoUsuario(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notificacoes_desktop",
    )
    source_app = models.CharField(max_length=50)
    event_type = models.CharField(max_length=60)
    title = models.CharField(max_length=160)
    body_short = models.CharField(max_length=500)
    target_url = models.CharField(max_length=500)
    dedupe_key = models.CharField(max_length=255, blank=True, default="")
    payload_json = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    displayed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["user", "id"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["user", "read_at"]),
            models.Index(fields=["user", "displayed_at"]),
            models.Index(fields=["user", "dedupe_key", "created_at"]),
        ]
        verbose_name = "Notificacao de usuario"
        verbose_name_plural = "Notificacoes de usuario"

    def __str__(self) -> str:
        return f"{self.user} - {self.title}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None


class DesktopAPIToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="desktop_api_tokens",
    )
    token_prefix = models.CharField(max_length=12, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "Token da API desktop"
        verbose_name_plural = "Tokens da API desktop"

    def __str__(self) -> str:
        return f"{self.user} - {self.token_prefix}"

    @classmethod
    def _hash_token(cls, raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @classmethod
    def issue_for_user(cls, user: User, *, ttl_seconds: int) -> tuple["DesktopAPIToken", str]:
        raw_token = secrets.token_urlsafe(32)
        token = cls.objects.create(
            user=user,
            token_prefix=raw_token[:12],
            token_hash=cls._hash_token(raw_token),
            expires_at=timezone.now() + timedelta(seconds=ttl_seconds),
        )
        return token, raw_token

    @classmethod
    def from_raw_token(cls, raw_token: str) -> "DesktopAPIToken | None":
        normalized = (raw_token or "").strip()
        if not normalized:
            return None
        token_hash = cls._hash_token(normalized)
        return (
            cls.objects.select_related("user")
            .filter(
                token_hash=token_hash,
                revoked_at__isnull=True,
                expires_at__gt=timezone.now(),
                user__is_active=True,
            )
            .first()
        )
