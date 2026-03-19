"""
Catálogo e utilitários de perfis/permissões do app `usuarios`.

Este módulo concentra a matriz de autorização por domínio funcional (apps do
projeto) e nível de acesso (Leitura, Edição e Administração), servindo como
fonte única para formulários e telas de gestão de usuários/grupos.

Integração na arquitetura Django:
- usa `auth.Permission` para mapear permissões reais do banco;
- é consumido por `forms.py` e `views.py` para atribuição de perfis;
- integra com `apps.py` (post_migrate) para garantir existência do grupo ADMIN.
"""

from django.apps import apps
from django.contrib.auth.models import Permission
from django.db.utils import OperationalError, ProgrammingError

# Matriz declarativa de perfis por domínio do sistema.
# - `models`: gera permissões a partir do modelo e ações.
# - `permissions`: usa codenames explícitos quando não há modelo diretamente.
PROFILE_DEFINITIONS = {
    "Ramais": {
        "models": ["ramais.PessoaRamal"],
        "levels": [
            ("Leitura", ["view"]),
            ("Edicao", ["view", "add", "change"]),
            ("Administracao", ["view", "add", "change", "delete"]),
        ],
    },
    "Organograma": {
        "permissions": {
            "Leitura": ["ramais.view_organograma"],
            "Edicao": ["ramais.view_organograma"],
            "Administracao": ["ramais.view_organograma"],
        },
        "levels": [
            ("Leitura", []),
            ("Edicao", []),
            ("Administracao", []),
        ],
    },
    "Contratos": {
        "models": ["contratos.Contrato"],
        "levels": [
            ("Leitura", ["view"]),
            ("Edicao", ["view", "add", "change"]),
            ("Administracao", ["view", "add", "change", "delete"]),
        ],
    },
    "Licitacoes": {
        "models": [
            "licitacoes.TermoReferencia",
            "licitacoes.SessaoTermo",
            "licitacoes.SubsessaoTermo",
            "licitacoes.ItemSessao",
            "licitacoes.TabelaItemLinha",
            "licitacoes.EtpTic",
        ],
        "levels": [
            ("Leitura", ["view"]),
            ("Edicao", ["view", "add", "change"]),
            ("Administracao", ["view", "add", "change", "delete"]),
        ],
    },
    "Reserva de Salas": {
        "models": ["reserva_salas.Sala", "reserva_salas.Reserva"],
        "levels": [
            ("Leitura", ["view"]),
            ("Edicao", ["view", "add", "change"]),
            ("Administracao", ["view", "add", "change", "delete"]),
        ],
    },
    "Empresas": {
        "models": ["empresas.Empresa"],
        "levels": [
            ("Leitura", ["view"]),
            ("Edicao", ["view", "add", "change"]),
            ("Administracao", ["view", "add", "change", "delete"]),
        ],
    },
    "Prepostos": {
        "models": ["prepostos.Preposto"],
        "levels": [
            ("Leitura", ["view"]),
            ("Edicao", ["view", "add", "change"]),
            ("Administracao", ["view", "add", "change", "delete"]),
        ],
    },
    "Diario de Bordo": {
        "models": ["diario_bordo.BlocoTrabalho", "diario_bordo.Incremento"],
        "levels": [
            ("Leitura", ["view"]),
            ("Edicao", ["view", "add", "change"]),
            ("Administracao", ["view", "add", "change", "delete"]),
        ],
    },
    "Noticias": {
        "models": ["noticias.Noticia"],
        "levels": [
            ("Leitura", ["view"]),
            ("Edicao", ["view", "add", "change"]),
            ("Administracao", ["view", "add", "change", "delete"]),
        ],
    },
    "Configuracoes": {
        "models": ["administracao.ADConfiguration"],
        "levels": [
            ("Leitura", ["view"]),
            ("Edicao", ["view", "add", "change"]),
            ("Administracao", ["view", "add", "change", "delete"]),
        ],
    },
    "Auditoria": {
        "models": ["auditoria.AuditLog"],
        "levels": [
            ("Leitura", ["view"]),
            ("Edicao", ["view"]),
            ("Administracao", ["view"]),
        ],
    },
    "Folha de Ponto": {
        "models": [
            "folha_ponto.Feriado",
            "folha_ponto.FeriasServidor",
            "folha_ponto.ConfiguracaoRH",
        ],
        "levels": [
            ("Leitura", ["view"]),
            ("Edicao", ["view", "add", "change"]),
            ("Administracao", ["view", "add", "change", "delete"]),
        ],
    },
    "Sala de Situacao": {
        "models": [
            "sala_situacao.SalaSituacaoPainel",
            "sala_situacao.IndicadorEstrategico",
            "sala_situacao.IndicadorTatico",
            "sala_situacao.Processo",
            "sala_situacao.Entrega",
            "sala_situacao.IndicadorVariavel",
            "sala_situacao.IndicadorVariavelCicloMonitoramento",
            "sala_situacao.IndicadorCicloMonitoramento",
            "sala_situacao.IndicadorCicloValor",
            "sala_situacao.IndicadorCicloHistorico",
        ],
        "levels": [
            ("Leitura", ["view"]),
            ("Edicao", ["view", "add", "change"]),
            ("Administracao", ["view", "add", "change", "delete"]),
        ],
    },
    "Monitoramento": {
        "models": [
            "monitoramento.ProjetoMonitoramento",
            "monitoramento.ConexaoBancoMonitoramento",
            "monitoramento.SnapshotEsquemaMonitoramento",
            "monitoramento.DashboardMonitoramento",
            "monitoramento.ConsultaDashboardMonitoramento",
            "monitoramento.GraficoDashboardMonitoramento",
        ],
        "levels": [
            ("Leitura", ["view"]),
            ("Edicao", ["view", "add", "change"]),
            ("Administracao", ["view", "add", "change", "delete"]),
        ],
    },
}

# Labels de apresentação na UI (matriz de perfis).
LABEL_MAP = {
    "Leitura": "Leitura",
    "Edicao": "Criar/Editar",
    "Administracao": "Excluir",
}

# Grupo reservado para administração total do sistema.
ADMIN_GROUP_NAME = "ADMIN"


def build_group_name(app_label: str, level: str) -> str:
    """
    Padroniza o nome de grupo de perfil.

    Parâmetros:
    - `app_label`: domínio funcional (ex.: "Contratos").
    - `level`: nível de acesso (Leitura/Edicao/Administracao).

    Retorno:
    - `str`: nome canônico no formato `<domínio> - <nível>`.
    """
    return f"{app_label} - {level}"


def get_profile_group_names():
    """
    Lista todos os nomes de grupo de perfil definidos na matriz.

    Retorno:
    - `list[str]` de nomes esperados para perfis de acesso.
    """
    names = []
    for app_label, config in PROFILE_DEFINITIONS.items():
        for level, _actions in config["levels"]:
            names.append(build_group_name(app_label, level))
    return names


def _get_permissions_for_models(model_labels, actions):
    """
    Resolve permissões pelo par modelo + ações.

    Parâmetros:
    - `model_labels`: lista `app.Model`.
    - `actions`: ações Django (`view`, `add`, `change`, `delete`).

    Consulta ORM:
    - Busca `auth.Permission` pelo `content_type.app_label` e `codename`.

    Retorno:
    - `list[Permission]` encontradas para o conjunto informado.
    """
    perms = []
    for model_label in model_labels:
        app_label, model_name = model_label.split(".")
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            # Ignora app/model não carregado, preservando resiliência em migrações.
            continue
        for action in actions:
            codename = f"{action}_{model._meta.model_name}"
            perm = Permission.objects.filter(
                content_type__app_label=app_label,
                codename=codename,
            ).first()
            if perm:
                perms.append(perm)
    return perms


def _get_permissions_from_codenames(codenames):
    """
    Resolve permissões diretamente por codenames completos (`app.codename`).

    Retorno:
    - `list[Permission]` encontradas.
    """
    perms = []
    for codename in codenames:
        app_label, code = codename.split(".", 1)
        perm = Permission.objects.filter(
            content_type__app_label=app_label,
            codename=code,
        ).first()
        if perm:
            perms.append(perm)
    return perms


def ensure_admin_group():
    """
    Garante a existência do grupo ADMIN no banco.

    Integração:
    - usado no `post_migrate` para bootstrap seguro de permissões base.
    """
    try:
        from django.contrib.auth.models import Group

        Group.objects.get_or_create(name=ADMIN_GROUP_NAME)
    except (OperationalError, ProgrammingError):
        # Evita quebra quando tabelas ainda não estão prontas.
        return


def ensure_profiles():
    """
    Mantido por compatibilidade histórica do módulo.

    Comportamento atual:
    - não cria grupos de perfil automaticamente;
    - apenas garante o grupo ADMIN.
    """
    try:
        ensure_admin_group()
    except (OperationalError, ProgrammingError):
        # Evita falhas quando o banco ainda nao esta pronto (ex.: migrate).
        return


def build_profile_matrix():
    """
    Gera estrutura de matriz (app x nível) usada nas telas de formulário.

    Retorno:
    - `list[dict]`: linhas com `label` e células por nível/perfil.
    """
    matrix = []
    for app_label, config in PROFILE_DEFINITIONS.items():
        row = {
            "label": app_label,
            "levels": [],
        }
        for level, _actions in config["levels"]:
            row["levels"].append(
                {
                    "level": level,
                    "label": LABEL_MAP.get(level, level),
                    "group": build_group_name(app_label, level),
                }
            )
        matrix.append(row)
    return matrix


def get_profile_permission_ids_map():
    """
    Calcula IDs de permissões exigidas para cada perfil de acesso.

    Consulta ORM:
    - obtém permissões por modelos ou codenames explícitos da matriz.

    Retorno:
    - `dict[str, set[int]]`: nome de perfil -> conjunto de ids de permissão.
    """
    permission_map = {}
    for app_label, config in PROFILE_DEFINITIONS.items():
        for level, actions in config["levels"]:
            profile_group_name = build_group_name(app_label, level)
            if "permissions" in config:
                permissions = _get_permissions_from_codenames(
                    config["permissions"].get(level, [])
                )
            else:
                permissions = _get_permissions_for_models(config["models"], actions)
            permission_map[profile_group_name] = {perm.id for perm in permissions}
    return permission_map
