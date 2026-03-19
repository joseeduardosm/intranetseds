"""
Regras de autorização e visibilidade do app `sala_situacao`.

Este módulo funciona como camada de política de acesso reutilizável entre views,
context processors e demais pontos da aplicação. A ideia é centralizar decisões
de segurança para evitar duplicação de lógica e inconsistências de permissão.

Integrações na arquitetura Django:
- autenticação/permissões nativas (`is_authenticated`, `has_perm`);
- grupos de usuários (`auth.Group`) vinculados ao monitoramento;
- tratamento de cenários de migração/bootstrap onde tabelas ainda não existem.
"""

from django.contrib.auth.models import Group
from django.db.utils import OperationalError, ProgrammingError

from usuarios.models import SetorNode, UserSetorMembership


def visible_group_ids_for_user(user):
    """
    Retorna os grupos visíveis ao usuário considerando sua árvore de setores.

    A visibilidade inclui:
    - grupos diretamente vinculados ao usuário;
    - grupos dos setores em que o usuário está lotado;
    - grupos de todos os setores descendentes desses setores.
    """

    if not user or not getattr(user, "is_authenticated", False):
        return set()

    try:
        group_ids = set(user.groups.values_list("id", flat=True))
        setor_ids = set(UserSetorMembership.objects.filter(user=user).values_list("setor_id", flat=True))
        if not setor_ids and group_ids:
            setor_ids = set(SetorNode.objects.filter(group_id__in=group_ids).values_list("id", flat=True))
        if not setor_ids:
            return group_ids

        nodes = list(SetorNode.objects.filter(ativo=True).values("id", "parent_id", "group_id"))
        children_by_parent = {}
        group_by_setor = {}
        for node in nodes:
            group_by_setor[node["id"]] = node["group_id"]
            children_by_parent.setdefault(node["parent_id"], []).append(node["id"])

        pending = list(setor_ids)
        visited = set()
        while pending:
            setor_id = pending.pop()
            if setor_id in visited:
                continue
            visited.add(setor_id)
            group_id = group_by_setor.get(setor_id)
            if group_id:
                group_ids.add(group_id)
            pending.extend(children_by_parent.get(setor_id, []))

        return group_ids
    except (OperationalError, ProgrammingError):
        return set(user.groups.values_list("id", flat=True))


def user_is_monitoring_group_member(user):
    """
    Verifica se o usuário participa de algum grupo habilitado para monitoramento.

    Parâmetros:
    - `user`: instância de usuário autenticável (ou `None`).

    Retorno:
    - `bool`: `True` quando existe ao menos um grupo relacionado a variáveis de
      monitoramento; `False` caso contrário.

    Regra de robustez:
    - Em erros de banco durante inicialização/migração, retorna `False` para não
      quebrar o carregamento global da aplicação.
    """

    if not user or not getattr(user, "is_authenticated", False):
        return False
    try:
        group_ids = visible_group_ids_for_user(user)
        if not group_ids:
            return False
        return Group.objects.filter(
            id__in=group_ids,
            variaveis_monitoramento_sala__isnull=False,
        ).exists()
    except (OperationalError, ProgrammingError):
        return False


def user_has_sala_situacao_access(user):
    """
    Decide se o usuário pode acessar qualquer funcionalidade do módulo.

    Parâmetros:
    - `user`: instância de usuário autenticável (ou `None`).

    Retorno:
    - `bool`: acesso liberado ou negado.

    Regras de negócio:
    - Superusuário e staff sempre têm acesso.
    - Usuário com permissões de leitura/edição/monitoramento do app tem acesso.
    - Usuário em grupo de monitoramento também recebe acesso, mesmo sem todas
      as permissões globais de CRUD.
    """

    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.is_staff:
        return True

    perms = (
        "sala_situacao.view_salasituacaopainel",
        "sala_situacao.view_indicadorestrategico",
        "sala_situacao.view_indicadortatico",
        "sala_situacao.view_processo",
        "sala_situacao.view_entrega",
        "sala_situacao.change_entrega",
        "sala_situacao.monitorar_entrega",
    )
    if any(user.has_perm(perm) for perm in perms):
        return True

    return user_is_monitoring_group_member(user)
