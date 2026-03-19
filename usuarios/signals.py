"""
Sinais de domínio do app `usuarios`.

Este módulo automatiza regras transversais relacionadas ao ciclo de vida do
usuário e alterações de grupos:
- concessão de permissões padrão ao criar usuário;
- sincronização de flags administrativas (`is_staff` e `is_superuser`) com o
  pertencimento ao grupo ADMIN.

Integração na arquitetura Django:
- handlers conectados a `post_save(User)` e `m2m_changed(User.groups.through)`;
- importado em `apps.py` no método `ready()` para registrar receivers.
"""

from django.contrib.auth.models import Permission, User
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from .permissions import ADMIN_GROUP_NAME


# Conjunto mínimo de permissões concedidas automaticamente ao novo usuário
# para acesso inicial ao app de reserva de salas.
RESERVA_SALAS_DEFAULT_CODENAMES = (
    "view_sala",
    "view_reserva",
    "add_reserva",
)


def _grant_reserva_salas_access(user: User):
    """
    Concede permissões padrão de reserva de salas para usuário recém-criado.

    Consulta ORM:
    - filtra `auth.Permission` por app `reserva_salas` e codenames padrão.
    """
    perms = Permission.objects.filter(
        content_type__app_label="reserva_salas",
        codename__in=RESERVA_SALAS_DEFAULT_CODENAMES,
    )
    if perms:
        user.user_permissions.add(*perms)


def _sync_admin_flags(user: User):
    """
    Sincroniza `is_staff`/`is_superuser` com pertencimento ao grupo ADMIN.

    Regra de negócio:
    - usuário no grupo ADMIN deve refletir privilégios administrativos nativos.
    """
    is_admin_member = user.groups.filter(name=ADMIN_GROUP_NAME).exists()
    update_fields = []
    if user.is_superuser != is_admin_member:
        user.is_superuser = is_admin_member
        update_fields.append("is_superuser")
    if user.is_staff != is_admin_member:
        user.is_staff = is_admin_member
        update_fields.append("is_staff")
    if update_fields:
        user.save(update_fields=update_fields)


@receiver(m2m_changed, sender=User.groups.through)
def sync_admin_flags_on_group_change(sender, instance, action, **kwargs):
    """
    Reage a mudanças de associação usuário<->grupo para manter flags em sincronia.

    Fluxo tratado:
    - considera operações diretas e reversas (`reverse=True`), incluindo `clear`.
    - no `pre_clear` reverso, armazena IDs para processar corretamente no `post_clear`.
    """
    reverse = bool(kwargs.get("reverse"))
    pk_set = kwargs.get("pk_set") or set()

    if action == "pre_clear":
        if reverse:
            instance._admin_sync_user_ids = set(instance.user_set.values_list("id", flat=True))
        return

    if action not in {"post_add", "post_remove", "post_clear"}:
        return

    user_ids = set()
    if reverse:
        if pk_set:
            user_ids.update(pk_set)
        elif action == "post_clear":
            user_ids.update(getattr(instance, "_admin_sync_user_ids", set()))
            if hasattr(instance, "_admin_sync_user_ids"):
                delattr(instance, "_admin_sync_user_ids")
    else:
        if getattr(instance, "pk", None):
            user_ids.add(instance.pk)

    if not user_ids:
        return

    for user in User.objects.filter(pk__in=user_ids):
        _sync_admin_flags(user)


@receiver(post_save, sender=User)
def grant_reserva_salas_access_on_user_created(sender, instance, created, **kwargs):
    """
    Handler de criação de usuário para concessão de permissões default.

    Regra de negócio:
    - executa somente quando `created=True`.
    """
    if not created:
        return
    _grant_reserva_salas_access(instance)
