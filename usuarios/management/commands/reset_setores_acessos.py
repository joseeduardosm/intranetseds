"""Reset operacional de acessos para o novo modelo de setores."""

from __future__ import annotations

from django.contrib.auth.models import Group, Permission, User
from django.core.management.base import BaseCommand
from django.db import transaction

from usuarios.models import SetorGrant, UserAccessState, UserGrant, UserSetorMembership
from usuarios.permissions import ADMIN_GROUP_NAME
from usuarios.signals import RESERVA_SALAS_DEFAULT_CODENAMES


class Command(BaseCommand):
    help = (
        "Limpa vínculos de acesso legados e novos (mantendo contas), preserva ADMIN opcionalmente "
        "e marca recadastro obrigatório no próximo login."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Aplica as alterações. Sem essa flag, executa apenas simulação.",
        )
        parser.add_argument(
            "--preserve-admin",
            action="store_true",
            default=False,
            help="Preserva vínculo e permissões do grupo ADMIN.",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options.get("apply"))
        preserve_admin = bool(options.get("preserve_admin"))

        users_qs = User.objects.all()
        total_users = users_qs.count()
        admin_group = Group.objects.filter(name=ADMIN_GROUP_NAME).first()

        self.stdout.write(self.style.WARNING("[RESET SETORES] Plano de execução"))
        self.stdout.write(f"- Usuários afetados: {total_users}")
        self.stdout.write(f"- Preserve ADMIN: {'sim' if preserve_admin else 'nao'}")
        self.stdout.write(f"- Modo: {'APLICAR' if apply_changes else 'SIMULACAO'}")

        if not apply_changes:
            self.stdout.write(
                self.style.SUCCESS(
                    "Simulação concluída. Execute com --apply para efetivar o reset operacional."
                )
            )
            return

        reserva_default_perms = list(
            Permission.objects.filter(
                content_type__app_label="reserva_salas",
                codename__in=RESERVA_SALAS_DEFAULT_CODENAMES,
            ).values_list("id", flat=True)
        )

        with transaction.atomic():
            UserSetorMembership.objects.all().delete()
            SetorGrant.objects.all().delete()
            UserGrant.objects.all().delete()

            for user in users_qs.iterator():
                keep_group_ids = set()
                if preserve_admin and admin_group and user.groups.filter(pk=admin_group.pk).exists():
                    keep_group_ids.add(admin_group.pk)
                if keep_group_ids:
                    user.groups.set(Group.objects.filter(pk__in=keep_group_ids))
                else:
                    user.groups.clear()

                if reserva_default_perms:
                    user.user_permissions.set(Permission.objects.filter(id__in=reserva_default_perms))
                else:
                    user.user_permissions.clear()

                state, _created = UserAccessState.objects.get_or_create(user=user)
                state.force_profile_update = True
                state.save(update_fields=["force_profile_update", "updated_at"])

        self.stdout.write(self.style.SUCCESS("Reset operacional aplicado com sucesso."))
