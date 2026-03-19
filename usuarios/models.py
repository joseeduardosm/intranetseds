"""Modelos de autorização hierárquica para o app `usuarios`."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import models


class SetorNode(models.Model):
    """Representa um setor canônico com possível pai (árvore)."""

    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name="setor_node",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["group__name"]

    def __str__(self):
        return self.group.name

    def clean(self):
        super().clean()
        if not self.parent_id:
            return
        if self.parent_id == self.id:
            raise ValidationError({"parent": "Um setor não pode ser pai de si mesmo."})

        visited = set()
        cursor = self.parent
        while cursor:
            if cursor.id in visited:
                raise ValidationError({"parent": "Ciclo detectado na árvore de setores."})
            visited.add(cursor.id)
            if self.id and cursor.id == self.id:
                raise ValidationError({"parent": "Ciclo detectado na árvore de setores."})
            cursor = cursor.parent

    def get_ancestry(self):
        ancestry = []
        cursor = self
        visited = set()
        while cursor and cursor.id not in visited:
            ancestry.append(cursor)
            visited.add(cursor.id)
            cursor = cursor.parent
        return ancestry

    def get_path_labels(self):
        nodes = list(reversed(self.get_ancestry()))
        return [node.group.name for node in nodes if node and node.group_id]


class GrantEffect(models.TextChoices):
    ALLOW = "ALLOW", "Allow"
    DENY = "DENY", "Deny"


class SetorGrant(models.Model):
    setor = models.ForeignKey(SetorNode, on_delete=models.CASCADE, related_name="grants")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="setor_grants")
    effect = models.CharField(max_length=8, choices=GrantEffect.choices)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("setor", "permission")
        ordering = ["setor__group__name", "permission__content_type__app_label", "permission__codename"]


class UserGrant(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="grants")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="user_grants")
    effect = models.CharField(max_length=8, choices=GrantEffect.choices)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "permission")
        ordering = ["user__username", "permission__content_type__app_label", "permission__codename"]


class UserSetorMembership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="setor_memberships")
    setor = models.ForeignKey(SetorNode, on_delete=models.CASCADE, related_name="memberships")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "setor")
        ordering = ["user__username", "setor__group__name"]


class ResolutionSource(models.TextChoices):
    DIRECT_USER = "DIRECT_USER", "Direto do usuário"
    SETOR = "SETOR", "Setor"
    ANCESTRY_PATH = "ANCESTRY_PATH", "Herança de setor"


class PermissionResolutionAudit(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="permission_resolution_audits",
    )
    permission = models.ForeignKey(Permission, on_delete=models.SET_NULL, null=True, blank=True)
    permission_code = models.CharField(max_length=255)
    source = models.CharField(max_length=20, choices=ResolutionSource.choices)
    effect = models.CharField(max_length=8, choices=GrantEffect.choices)
    source_setor = models.ForeignKey(SetorNode, on_delete=models.SET_NULL, null=True, blank=True)
    ancestry_path = models.CharField(max_length=500, blank=True, default="")
    reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class UserAccessState(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="access_state",
    )
    force_profile_update = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
