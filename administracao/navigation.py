"""
Definições compartilhadas da navegação administrativa.

Este módulo centraliza títulos, rotas e regras de visibilidade do dropdown
`Administracao` e dos cards fixos da home, garantindo consistência entre as
duas superfícies.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse

from .models import AtalhoAdministracao


def can_manage_news(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return (
        user.is_superuser
        or user.has_perm("noticias.add_noticia")
        or user.has_perm("noticias.change_noticia")
        or user.has_perm("noticias.delete_noticia")
    )


def can_manage_shortcuts(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return (
        user.is_superuser
        or user.has_perm("administracao.view_atalhoservico")
        or user.has_perm("administracao.add_atalhoservico")
        or user.has_perm("administracao.change_atalhoservico")
        or user.has_perm("administracao.delete_atalhoservico")
    )


def can_manage_configuracoes(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return (
        can_manage_news(user)
        or can_manage_shortcuts(user)
        or user.has_perm("folha_ponto.add_feriado")
        or user.has_perm("folha_ponto.change_feriado")
        or user.has_perm("folha_ponto.delete_feriado")
        or user.has_perm("folha_ponto.add_feriasservidor")
        or user.has_perm("folha_ponto.change_feriasservidor")
        or user.has_perm("folha_ponto.delete_feriasservidor")
        or user.has_perm("folha_ponto.change_configuracaorh")
    )


def can_access_rh(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return (
        user.is_superuser
        or user.has_perm("folha_ponto.view_feriado")
        or user.has_perm("folha_ponto.view_feriasservidor")
        or user.has_perm("folha_ponto.add_feriado")
        or user.has_perm("folha_ponto.change_feriado")
        or user.has_perm("folha_ponto.delete_feriado")
        or user.has_perm("folha_ponto.add_feriasservidor")
        or user.has_perm("folha_ponto.change_feriasservidor")
        or user.has_perm("folha_ponto.delete_feriasservidor")
        or user.has_perm("folha_ponto.change_configuracaorh")
    )


def can_manage_rfs(user) -> bool:
    return can_manage_configuracoes(user)


def can_access_monitoramento(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return (
        user.is_superuser
        or user.has_perm("monitoramento.view_projetomonitoramento")
        or user.has_perm("monitoramento.add_projetomonitoramento")
        or user.has_perm("monitoramento.change_projetomonitoramento")
    )


def can_access_contratos(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and user.has_perm("contratos.view_contrato"))


def can_access_diario_bordo(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and user.has_perm("diario_bordo.view_blocotrabalho"))


def can_access_licitacoes(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return (
        user.is_staff
        or user.has_perm("licitacoes.view_termoreferencia")
        or user.has_perm("licitacoes.add_termoreferencia")
        or user.has_perm("licitacoes.change_termoreferencia")
        or user.has_perm("licitacoes.delete_termoreferencia")
    )


def can_access_reserva_salas(user) -> bool:
    return bool(getattr(user, "is_authenticated", False))


def can_access_lousa_digital(user) -> bool:
    return bool(getattr(user, "is_authenticated", False))


def can_access_acompanhamento_sistemas(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    from acompanhamento_sistemas.models import InteressadoSistema

    return (
        user.is_superuser
        or user.has_perm("acompanhamento_sistemas.view_sistema")
        or user.has_perm("acompanhamento_sistemas.add_sistema")
        or user.has_perm("acompanhamento_sistemas.change_sistema")
        or InteressadoSistema.objects.filter(usuario=user).exists()
    )


def can_access_usuarios(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and user.is_staff)


def can_access_auditoria(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and user.is_superuser)


@dataclass(frozen=True)
class AdministracaoNavItemDefinition:
    funcionalidade: str
    titulo: str
    url_name: str
    visibility_check: callable


ADMINISTRACAO_NAV_ITEMS = [
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_ADMINISTRACAO,
        titulo="Administracao",
        url_name="administracao_configuracoes",
        visibility_check=can_manage_configuracoes,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_AUDITORIA,
        titulo="Auditoria",
        url_name="audit_log_list",
        visibility_check=can_access_auditoria,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_CONFIGURACOES,
        titulo="Configuracoes",
        url_name="administracao_configuracoes",
        visibility_check=can_manage_configuracoes,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_NOTICIAS,
        titulo="Noticias",
        url_name="noticia_list",
        visibility_check=can_manage_news,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_RAMAIS,
        titulo="Ramais",
        url_name="ramais_list",
        visibility_check=lambda user: True,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_MONITORAMENTO,
        titulo="Monitoramento",
        url_name="monitoramento_home",
        visibility_check=can_access_monitoramento,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_CONTRATOS,
        titulo="Contratos",
        url_name="contratos_list",
        visibility_check=can_access_contratos,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_EMPRESAS,
        titulo="Empresas",
        url_name="empresas_list",
        visibility_check=lambda user: True,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_PREPOSTOS,
        titulo="Prepostos",
        url_name="prepostos_list",
        visibility_check=lambda user: True,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_DIARIO_BORDO,
        titulo="Diario de Bordo",
        url_name="diario_bordo_list",
        visibility_check=can_access_diario_bordo,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_FOLHA_PONTO,
        titulo="Folha de Ponto",
        url_name="folha_ponto_home",
        visibility_check=lambda user: True,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_LICITACOES,
        titulo="Licitacoes",
        url_name="licitacoes_home",
        visibility_check=can_access_licitacoes,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_RESERVA_SALAS,
        titulo="Reserva de Salas",
        url_name="salas_list",
        visibility_check=can_access_reserva_salas,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_SALA_SITUACAO,
        titulo="Sala de Situacao",
        url_name="sala_situacao_home",
        visibility_check=lambda user: True,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_SALA_SITUACAO_OLD,
        titulo="Sala de Situacao (Legado)",
        url_name="sala_old_situacao_home",
        visibility_check=lambda user: True,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_LOUSA_DIGITAL,
        titulo="Lousa Digital",
        url_name="lousa_digital_list",
        visibility_check=can_access_lousa_digital,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_ACOMPANHAMENTO_SISTEMAS,
        titulo="Acompanhamento de Sistemas",
        url_name="acompanhamento_sistemas_list",
        visibility_check=can_access_acompanhamento_sistemas,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_RFS,
        titulo="RFs",
        url_name="administracao_rfs",
        visibility_check=can_manage_rfs,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_RH,
        titulo="RH",
        url_name="administracao_rh",
        visibility_check=can_access_rh,
    ),
    AdministracaoNavItemDefinition(
        funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_USUARIOS,
        titulo="Usuarios",
        url_name="usuarios_list",
        visibility_check=can_access_usuarios,
    ),
]


def get_administracao_menu_items(user) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in ADMINISTRACAO_NAV_ITEMS:
        if item.visibility_check(user):
            items.append(
                {
                    "funcionalidade": item.funcionalidade,
                    "titulo": item.titulo,
                    "url": reverse(item.url_name),
                }
            )
    return items


def get_administracao_home_items() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in ADMINISTRACAO_NAV_ITEMS:
        items.append(
            {
                "funcionalidade": item.funcionalidade,
                "titulo": item.titulo,
                "url": reverse(item.url_name),
            }
        )
    return items


def get_administracao_home_items_map() -> dict[str, dict[str, str]]:
    return {
        item["funcionalidade"]: item
        for item in get_administracao_home_items()
    }
