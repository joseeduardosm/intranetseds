"""Backend de autorização com herança de setores e precedência de deny."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied

from .models import (
    GrantEffect,
    PermissionResolutionAudit,
    ResolutionSource,
    SetorNode,
    UserGrant,
    UserSetorMembership,
)
from .permissions import ADMIN_GROUP_NAME


@dataclass
class ResolutionEntry:
    effect: str
    source: str
    setor: SetorNode | None = None
    ancestry_path: str = ""
    reason: str = ""


def ensure_setor_node_for_group(group: Group) -> SetorNode:
    node, _created = SetorNode.objects.get_or_create(group=group)
    return node


def ensure_setor_nodes_for_all_groups() -> None:
    for group in Group.objects.all().iterator():
        ensure_setor_node_for_group(group)


def _resolve_permission_obj(perm: str) -> Permission | None:
    if not perm or "." not in perm:
        return None
    app_label, codename = perm.split(".", 1)
    return Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()


def _membership_nodes(user) -> list[SetorNode]:
    memberships = list(
        UserSetorMembership.objects.filter(user=user)
        .select_related("setor", "setor__group", "setor__parent", "setor__parent__group")
    )
    nodes = [m.setor for m in memberships if m.setor_id]
    if nodes:
        return nodes

    # Compatibilidade: se ainda só existe vínculo em auth.Group, usa SetorNode correspondente.
    fallback = []
    groups = user.groups.exclude(name=ADMIN_GROUP_NAME)
    for group in groups:
        fallback.append(ensure_setor_node_for_group(group))
    return fallback


def _resolve_entries(user, permission: Permission) -> list[ResolutionEntry]:
    entries: list[ResolutionEntry] = []

    for grant in UserGrant.objects.filter(user=user, permission=permission):
        entries.append(
            ResolutionEntry(
                effect=grant.effect,
                source=ResolutionSource.DIRECT_USER,
                reason="Grant direto no usuario",
            )
        )

    seen = set()
    for setor in _membership_nodes(user):
        ancestry = setor.get_ancestry()
        for index, node in enumerate(ancestry):
            if not node:
                continue
            key = node.pk
            if key in seen:
                continue
            seen.add(key)
            grant = node.grants.filter(permission=permission).first()
            if not grant:
                continue
            if index == 0:
                source = ResolutionSource.SETOR
                ancestry_path = node.group.name
                reason = f"Grant no setor {node.group.name}"
            else:
                source = ResolutionSource.ANCESTRY_PATH
                path_labels = [entry.group.name for entry in reversed(ancestry[: index + 1]) if entry.group_id]
                ancestry_path = " -> ".join(path_labels)
                reason = f"Heranca via {ancestry_path}"
            entries.append(
                ResolutionEntry(
                    effect=grant.effect,
                    source=source,
                    setor=node,
                    ancestry_path=ancestry_path,
                    reason=reason,
                )
            )

    return entries


def _create_audit_rows(
    user,
    perm_code: str,
    entries: list[ResolutionEntry],
    final_effect: str,
    reason: str,
    permission: Permission | None = None,
) -> None:
    if not entries:
        PermissionResolutionAudit.objects.create(
            user=user,
            permission=permission,
            permission_code=perm_code,
            source=ResolutionSource.DIRECT_USER,
            effect=final_effect,
            reason=reason,
        )
        return

    for entry in entries:
        PermissionResolutionAudit.objects.create(
            user=user,
            permission=permission,
            permission_code=perm_code,
            source=entry.source,
            effect=final_effect,
            source_setor=entry.setor,
            ancestry_path=entry.ancestry_path,
            reason=entry.reason or reason,
        )


class SetorPermissionBackend(ModelBackend):
    """Calcula permissões efetivas com deny explícito e herança de setores."""

    def has_perm(self, user_obj, perm, obj=None):
        if not user_obj or not getattr(user_obj, "is_active", False):
            return False
        if obj is not None:
            return super().has_perm(user_obj, perm, obj=obj)

        if user_obj.is_superuser or user_obj.groups.filter(name=ADMIN_GROUP_NAME).exists():
            _create_audit_rows(
                user_obj,
                perm,
                [
                    ResolutionEntry(
                        effect=GrantEffect.ALLOW,
                        source=ResolutionSource.DIRECT_USER,
                        reason="Bypass administrativo (ADMIN/superuser)",
                    )
                ],
                final_effect=GrantEffect.ALLOW,
                reason="Bypass administrativo",
            )
            return True

        permission = _resolve_permission_obj(perm)
        if permission is None:
            _create_audit_rows(
                user_obj,
                perm,
                entries=[],
                final_effect=GrantEffect.DENY,
                reason="Permissao inexistente",
            )
            return False

        entries = _resolve_entries(user_obj, permission)
        deny_entries = [entry for entry in entries if entry.effect == GrantEffect.DENY]
        if deny_entries:
            _create_audit_rows(
                user_obj,
                perm,
                entries=deny_entries,
                final_effect=GrantEffect.DENY,
                reason="Negacao explicita encontrada",
                permission=permission,
            )
            raise PermissionDenied("Negacao explicita de permissao")

        allow_entries = [entry for entry in entries if entry.effect == GrantEffect.ALLOW]
        if allow_entries:
            _create_audit_rows(
                user_obj,
                perm,
                entries=allow_entries,
                final_effect=GrantEffect.ALLOW,
                reason="Permissao concedida por grant",
                permission=permission,
            )
            return True

        legacy_result = super().has_perm(user_obj, perm, obj=obj)
        _create_audit_rows(
            user_obj,
            perm,
            entries=[],
            final_effect=GrantEffect.ALLOW if legacy_result else GrantEffect.DENY,
            reason="Fallback de permissao legada (ModelBackend)",
            permission=permission,
        )
        return legacy_result
