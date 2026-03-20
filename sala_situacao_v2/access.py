from django.contrib.auth.models import Group

from sala_situacao.access import visible_group_ids_for_user
from usuarios.permissions import ADMIN_GROUP_NAME


def user_has_sala_situacao_v2_access(user):
    return bool(user and getattr(user, "is_authenticated", False))


def user_is_v2_admin(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name=ADMIN_GROUP_NAME).exists()


def writable_group_ids_for_user(user):
    if user_is_v2_admin(user):
        return set(Group.objects.values_list("id", flat=True))
    return set(visible_group_ids_for_user(user))


def user_can_write_item(user, item):
    if user_is_v2_admin(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not hasattr(item, "grupos_responsaveis"):
        return False
    item_group_ids = set(item.grupos_responsaveis.values_list("id", flat=True))
    if not item_group_ids:
        return False
    return bool(item_group_ids.intersection(writable_group_ids_for_user(user)))


def user_can_manage_processo(user, processo):
    if user_is_v2_admin(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    creator_group_ids = set(processo.grupos_criadores.values_list("id", flat=True))
    if not creator_group_ids:
        return False
    return bool(creator_group_ids.intersection(writable_group_ids_for_user(user)))


def user_can_delete_processo(user, processo):
    return user_can_manage_processo(user, processo)


def user_can_manage_indicador(user, indicador):
    if user_is_v2_admin(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    creator_group_ids = set(indicador.grupos_criadores.values_list("id", flat=True))
    if not creator_group_ids:
        return False
    return bool(creator_group_ids.intersection(writable_group_ids_for_user(user)))


def user_can_manage_entrega(user, entrega):
    if user_is_v2_admin(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    creator_group_ids = set(entrega.grupos_criadores.values_list("id", flat=True))
    if not creator_group_ids:
        return False
    return bool(creator_group_ids.intersection(writable_group_ids_for_user(user)))
