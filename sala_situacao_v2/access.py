from django.contrib.auth.models import Group
from django.db.models import Q

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


def _user_is_direct_creator(user, item):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(item, "criado_por_id", None) == user.id
    )


def _user_in_creator_groups(user, creator_group_ids):
    if not creator_group_ids:
        return False
    return bool(set(creator_group_ids).intersection(writable_group_ids_for_user(user)))


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
    if _user_is_direct_creator(user, processo):
        return True
    creator_group_ids = set(processo.grupos_criadores.values_list("id", flat=True))
    if _user_in_creator_groups(user, creator_group_ids):
        return True
    if (
        not getattr(processo, "criado_por_id", None)
        and not creator_group_ids
        and user_can_write_item(user, processo)
        and not any(indicador.eh_indicador_matematico for indicador in processo.indicadores.all())
    ):
        return True
    for indicador in processo.indicadores.all():
        if indicador.eh_indicador_matematico and user_can_manage_indicador(user, indicador):
            return True
    return False


def user_can_delete_processo(user, processo):
    return user_can_manage_processo(user, processo)


def user_can_manage_indicador(user, indicador):
    if user_is_v2_admin(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if _user_is_direct_creator(user, indicador):
        return True
    creator_group_ids = set(indicador.grupos_criadores.values_list("id", flat=True))
    if not getattr(indicador, "criado_por_id", None) and not creator_group_ids and user_can_write_item(user, indicador):
        return True
    return _user_in_creator_groups(user, creator_group_ids)


def user_can_manage_entrega(user, entrega):
    if user_is_v2_admin(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if _user_is_direct_creator(user, entrega):
        return True
    creator_group_ids = set(entrega.grupos_criadores.values_list("id", flat=True))
    if _user_in_creator_groups(user, creator_group_ids):
        return True
    if (
        not getattr(entrega, "criado_por_id", None)
        and not creator_group_ids
        and user_can_write_item(user, entrega)
        and not entrega.eh_entrega_monitoramento
    ):
        return True
    for processo in entrega.processos.all():
        if user_can_manage_processo(user, processo):
            return True
    variavel = getattr(entrega, "variavel_monitoramento", None)
    if variavel and getattr(variavel, "indicador", None):
        if user_can_manage_indicador(user, variavel.indicador):
            return True
    return False


def user_can_monitor_entrega(user, entrega):
    if user_can_manage_entrega(user, entrega):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    variavel = getattr(entrega, "variavel_monitoramento", None)
    if not variavel:
        return False
    grupos_monitoramento_ids = set(variavel.grupos_monitoramento.values_list("id", flat=True))
    return _user_in_creator_groups(user, grupos_monitoramento_ids)


def filter_visible_entregas_for_user(queryset, user):
    if user_is_v2_admin(user):
        return queryset
    if not user or not getattr(user, "is_authenticated", False):
        return queryset.none()

    writable_group_ids = writable_group_ids_for_user(user)
    filtros = (
        Q(criado_por_id=user.id)
        | Q(grupos_criadores__id__in=writable_group_ids)
        | Q(grupos_responsaveis__id__in=writable_group_ids)
        | Q(processos__criado_por_id=user.id)
        | Q(processos__grupos_criadores__id__in=writable_group_ids)
        | Q(processos__grupos_responsaveis__id__in=writable_group_ids)
        | Q(processos__indicadores__criado_por_id=user.id)
        | Q(processos__indicadores__grupos_criadores__id__in=writable_group_ids)
        | Q(processos__indicadores__grupos_responsaveis__id__in=writable_group_ids)
        | Q(variavel_monitoramento__indicador__criado_por_id=user.id)
        | Q(variavel_monitoramento__indicador__grupos_criadores__id__in=writable_group_ids)
        | Q(variavel_monitoramento__grupos_monitoramento__id__in=writable_group_ids)
    )
    return queryset.filter(filtros).distinct()


def filter_visible_processos_for_user(queryset, user):
    if user_is_v2_admin(user):
        return queryset
    if not user or not getattr(user, "is_authenticated", False):
        return queryset.none()

    writable_group_ids = writable_group_ids_for_user(user)
    filtros = (
        Q(criado_por_id=user.id)
        | Q(grupos_criadores__id__in=writable_group_ids)
        | Q(grupos_responsaveis__id__in=writable_group_ids)
        | Q(indicadores__criado_por_id=user.id)
        | Q(indicadores__grupos_criadores__id__in=writable_group_ids)
        | Q(indicadores__grupos_responsaveis__id__in=writable_group_ids)
        | Q(entregas__criado_por_id=user.id)
        | Q(entregas__grupos_criadores__id__in=writable_group_ids)
        | Q(entregas__grupos_responsaveis__id__in=writable_group_ids)
        | Q(entregas__variavel_monitoramento__indicador__criado_por_id=user.id)
        | Q(entregas__variavel_monitoramento__indicador__grupos_criadores__id__in=writable_group_ids)
        | Q(entregas__variavel_monitoramento__grupos_monitoramento__id__in=writable_group_ids)
    )
    return queryset.filter(filtros).distinct()
