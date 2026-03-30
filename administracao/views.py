"""
Camada de views do app `administracao`.

Este arquivo orquestra os fluxos HTTP administrativos:
- pagina de configuracoes e cards condicionados por permissao;
- configuracao/teste/sincronizacao de AD;
- CRUD de atalhos de servico;
- gestao de RF/changelog com persistencia em banco e arquivos markdown.

Integracao arquitetural:
- recebe dados validados por formularios (`forms.py`);
- persiste e consulta entidades do dominio (`models.py`) via ORM;
- renderiza templates HTML;
- conversa com servico LDAP externo para teste/sincronizacao.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import re
import subprocess
import tempfile
from html import escape
from zipfile import ZIP_DEFLATED, ZipFile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.http import FileResponse
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.models import Group
from django.core.mail.backends.smtp import EmailBackend
from django.urls import reverse_lazy
from django.shortcuts import redirect, render
from django.utils.safestring import mark_safe
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from django.views.generic import TemplateView

try:
    from ldap3 import Connection, Server, NONE
    from ldap3.core.exceptions import LDAPException
except Exception:  # pragma: no cover - ambiente sem ldap3
    Connection = None
    Server = None
    NONE = None
    LDAPException = Exception

from .forms import (
    ADConfigurationForm,
    AtalhoAdministracaoForm,
    AtalhoServicoForm,
    IdentidadeVisualConfigForm,
    MarkdownEditorForm,
    RFChangelogEntryForm,
    SMTPConfigurationForm,
)
from .models import (
    ADConfiguration,
    AtalhoAdministracao,
    AtalhoServico,
    IdentidadeVisualConfig,
    RFChangelogEntry,
    SMTPConfiguration,
)
from .navigation import (
    can_access_rh as navigation_can_access_rh,
    can_manage_configuracoes as navigation_can_manage_configuracoes,
    can_manage_news,
    can_manage_rfs as navigation_can_manage_rfs,
    can_manage_shortcuts,
)
from usuarios.permissions import PROFILE_DEFINITIONS, build_group_name, ensure_profiles


@dataclass
class Feedback:
    """
    DTO simples para mensagens de retorno em telas administrativas.

    Campos:
    - `level`: nivel semantico (ex.: success, error).
    - `message`: texto amigavel para o operador.
    """

    level: str
    message: str


SYSTEM_BACKUP_ROOT_FILES = (
    "manage.py",
    "requirements.txt",
    ".env",
)
SYSTEM_BACKUP_ROOT_DIRS = (
    "administracao",
    "auditoria",
    "contratos",
    "diario_bordo",
    "docs",
    "empresas",
    "folha_ponto",
    "intranet",
    "licitacoes",
    "lousa_digital",
    "media",
    "noticias",
    "prepostos",
    "ramais",
    "reserva_salas",
    "RFs",
    "sala_situacao",
    "scripts",
    "static",
    "templates",
    "usuarios",
)
SYSTEM_BACKUP_SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".idea",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "venv",
    ".venv",
    "backups",
    "staticfiles",
    "logs",
}
SYSTEM_BACKUP_SKIP_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".sqlite3",
    ".log",
}


def _format_inline_markdown(text: str) -> str:
    """
    Aplica formatacao inline basica em markdown seguro.

    Parametros:
    - `text`: trecho de texto em markdown simplificado.

    Retorno:
    - `str`: HTML escapado com suporte a `code` e `strong`.

    Regra de seguranca:
    - Escapa HTML antes das substituicoes para evitar XSS.
    """

    rendered = escape(text)
    rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
    rendered = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", rendered)
    return rendered


def _iter_system_backup_sources() -> list[Path]:
    """Lista caminhos locais elegíveis para o backup completo do sistema."""

    sources: list[Path] = []
    for relative_name in SYSTEM_BACKUP_ROOT_FILES:
        path = settings.BASE_DIR / relative_name
        if path.exists():
            sources.append(path)
    for relative_name in SYSTEM_BACKUP_ROOT_DIRS:
        path = settings.BASE_DIR / relative_name
        if path.exists():
            sources.append(path)
    return sources


def _should_include_backup_file(path: Path) -> bool:
    """Aplica exclusões para reduzir o pacote aos artefatos realmente úteis."""

    if any(part in SYSTEM_BACKUP_SKIP_DIR_NAMES for part in path.parts):
        return False
    if path.name.endswith("~"):
        return False
    return path.suffix.lower() not in SYSTEM_BACKUP_SKIP_SUFFIXES


def _iter_files_for_backup(path: Path):
    """Percorre arquivos a serem adicionados ao ZIP preservando caminhos relativos."""

    if path.is_file():
        if _should_include_backup_file(path):
            yield path
        return

    for root, dirnames, filenames in os.walk(path):
        dirnames[:] = [name for name in dirnames if name not in SYSTEM_BACKUP_SKIP_DIR_NAMES]
        root_path = Path(root)
        for filename in filenames:
            file_path = root_path / filename
            if _should_include_backup_file(file_path):
                yield file_path


def _build_mysqldump_command() -> list[str]:
    """Monta comando de dump SQL com credenciais do banco configurado no Django."""

    db_config = settings.DATABASES["default"]
    command = [
        "mysqldump",
        f"--host={db_config.get('HOST') or '127.0.0.1'}",
        f"--port={db_config.get('PORT') or '3306'}",
        f"--user={db_config.get('USER') or ''}",
        f"--password={db_config.get('PASSWORD') or ''}",
        "--default-character-set=utf8mb4",
        "--single-transaction",
        "--routines",
        "--triggers",
        "--databases",
        db_config.get("NAME") or "",
    ]
    return command


def _generate_database_sql_dump() -> bytes:
    """Gera dump SQL completo do banco atual usando `mysqldump`."""

    completed = subprocess.run(
        _build_mysqldump_command(),
        check=True,
        capture_output=True,
    )
    return completed.stdout


def _build_system_backup_response() -> FileResponse:
    """Monta ZIP de backup completo com código essencial e dump SQL instantâneo."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_name = settings.DATABASES["default"].get("NAME") or "database"
    sql_dump = _generate_database_sql_dump()

    archive_file = tempfile.TemporaryFile()
    with ZipFile(archive_file, mode="w", compression=ZIP_DEFLATED) as zip_file:
        zip_file.writestr(f"database/{db_name}_{timestamp}.sql", sql_dump)
        for source in _iter_system_backup_sources():
            for file_path in _iter_files_for_backup(source):
                archive_name = file_path.relative_to(settings.BASE_DIR).as_posix()
                zip_file.write(file_path, arcname=archive_name)

    archive_file.seek(0)
    response = FileResponse(
        archive_file,
        as_attachment=True,
        filename=f"backup_sistema_{timestamp}.zip",
        content_type="application/zip",
    )
    return response


def _split_table_row(line: str) -> list[str]:
    """
    Divide uma linha de tabela markdown em celulas.

    Parametros:
    - `line`: linha com separador `|`.

    Retorno:
    - `list[str]`: celulas normalizadas (trim de espacos).
    """

    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_table_separator(line: str) -> bool:
    """
    Detecta se a linha representa separador de cabecalho de tabela markdown.

    Parametros:
    - `line`: linha candidata.

    Retorno:
    - `bool`: True quando todos os segmentos contem apenas `-` e `:`.
    """

    parts = [part.strip() for part in line.strip().strip("|").split("|")]
    if not parts:
        return False
    return all(part and set(part) <= {":", "-"} for part in parts)


def _render_markdown_basic(markdown_text: str):
    """
    Renderiza um subconjunto controlado de markdown para HTML.

    Parametros:
    - `markdown_text`: conteudo markdown bruto.

    Retorno:
    - `SafeString`: HTML final seguro para renderizacao no template.

    Regras de negocio:
    - Suporta titulos H1-H3, listas simples, paragrafos e tabelas.
    - Fecha blocos de lista corretamente para manter HTML valido.
    """

    lines = markdown_text.splitlines()
    html_parts: list[str] = []
    in_list = False
    i = 0

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        if stripped.startswith("|") and i + 1 < len(lines) and _is_table_separator(lines[i + 1]):
            if in_list:
                html_parts.append("</ul>")
                in_list = False

            # Interpreta bloco de tabela completo (cabecalho + linhas).
            headers = _split_table_row(lines[i])
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_split_table_row(lines[i]))
                i += 1

            html_parts.append('<div class="table-wrapper"><table class="table table-fulltext"><thead><tr>')
            for header in headers:
                html_parts.append(f"<th>{_format_inline_markdown(header)}</th>")
            html_parts.append("</tr></thead><tbody>")
            for row in rows:
                html_parts.append("<tr>")
                for cell in row:
                    html_parts.append(f"<td>{_format_inline_markdown(cell)}</td>")
                html_parts.append("</tr>")
            html_parts.append("</tbody></table></div>")
            continue

        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            i += 1
            continue

        if stripped.startswith("- "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{_format_inline_markdown(stripped[2:])}</li>")
            i += 1
            continue

        if in_list:
            html_parts.append("</ul>")
            in_list = False

        heading_match = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            html_parts.append(f"<h{level}>{_format_inline_markdown(heading_match.group(2))}</h{level}>")
        else:
            html_parts.append(f"<p>{_format_inline_markdown(stripped)}</p>")
        i += 1

    if in_list:
        html_parts.append("</ul>")

    return mark_safe("".join(html_parts))


def _get_ad_configuration() -> ADConfiguration:
    """
    Recupera a configuracao AD existente ou instancia vazia.

    Retorno:
    - `ADConfiguration`: instancia persistida (primeira) ou objeto novo.

    Regra de negocio:
    - O sistema adota configuracao singleton (primeiro registro).
    """

    config = ADConfiguration.objects.first()
    if config is None:
        config = ADConfiguration()
    return config


def _get_visual_configuration() -> IdentidadeVisualConfig:
    """
    Recupera configuracao visual persistida ou instancia padrao em memoria.

    Retorno:
    - `IdentidadeVisualConfig`: primeiro registro do banco (singleton) ou novo.
    """

    config = IdentidadeVisualConfig.objects.first()
    if config is None:
        config = IdentidadeVisualConfig()
    return config


def _get_smtp_configuration() -> SMTPConfiguration:
    """Recupera configuração SMTP persistida ou instancia vazia."""

    config = SMTPConfiguration.objects.first()
    if config is None:
        config = SMTPConfiguration()
    return config


def _test_ldap_connection(config: ADConfiguration) -> Feedback:
    """
    Testa conectividade LDAP com credenciais informadas na tela.

    Parametros:
    - `config`: configuracao AD em memoria (persistida ou nao).

    Retorno:
    - `Feedback`: status de sucesso/erro para exibicao no frontend.

    Integracao externa:
    - Realiza bind no servidor LDAP usando conta de servico.
    """

    if Connection is None or Server is None:
        return Feedback(level="error", message="Biblioteca ldap3 nao encontrada.")
    server = Server(
        config.server_host,
        port=config.server_port,
        use_ssl=config.use_ssl,
        connect_timeout=5,
        get_info=NONE,
    )
    try:
        connection = Connection(
            server,
            user=config.bind_dn,
            password=config.bind_password,
            auto_bind=True,
        )
        connection.unbind()
        return Feedback(level="success", message="Conexao estabelecida com sucesso.")
    except (LDAPException, OSError):
        return Feedback(level="error", message="Falha ao conectar no servidor AD.")


def _test_smtp_connection(config: SMTPConfiguration) -> Feedback:
    """Testa conectividade/autenticação SMTP sem enviar e-mail."""

    connection = EmailBackend(
        host=config.host,
        port=config.port,
        username=config.username,
        password=config.password,
        use_tls=config.use_tls,
        use_ssl=config.use_ssl,
        timeout=config.timeout,
        fail_silently=False,
    )
    try:
        opened = connection.open()
        if opened:
            connection.close()
        return Feedback(level="success", message="Conexão SMTP estabelecida com sucesso.")
    except Exception:
        return Feedback(level="error", message="Falha ao conectar no servidor SMTP.")


def _assign_read_groups(user):
    """
    Garante baseline de grupos para usuarios sincronizados do AD.

    Parametros:
    - `user`: instancia de usuario local.

    Retorno:
    - Nao retorna valor; modifica associacoes M2M de grupos.
    """

    ensure_profiles()
    groups = []
    for app_label in PROFILE_DEFINITIONS.keys():
        group_name = build_group_name(app_label, "Leitura")
        group = Group.objects.filter(name=group_name).first()
        if group:
            groups.append(group)
    diario_edicao = Group.objects.filter(
        name=build_group_name("Diario de Bordo", "Edicao")
    ).first()
    if diario_edicao and diario_edicao not in groups:
        groups.append(diario_edicao)
    if groups:
        user.groups.add(*groups)


def _sync_ad_users(config: ADConfiguration) -> Feedback:
    """
    Sincroniza usuarios ativos do AD para a base local.

    Parametros:
    - `config`: credenciais e escopo de busca LDAP.

    Retorno:
    - `Feedback`: resumo operacional com contagem de criados/atualizados.

    Regras de negocio:
    - Ignora entradas sem `sAMAccountName`.
    - Mantem atualizacao incremental de nome/email.
    - Cria perfil minimo em `ramais` quando aplicavel.
    """

    if Connection is None or Server is None:
        return Feedback(level="error", message="Biblioteca ldap3 nao encontrada.")
    try:
        from ldap3 import SUBTREE
    except Exception:
        return Feedback(level="error", message="Biblioteca ldap3 nao encontrada.")

    server = Server(
        config.server_host,
        port=config.server_port,
        use_ssl=config.use_ssl,
        connect_timeout=10,
        get_info=NONE,
    )
    try:
        connection = Connection(
            server,
            user=config.bind_dn,
            password=config.bind_password,
            auto_bind=True,
        )
    except (LDAPException, OSError):
        return Feedback(level="error", message="Falha ao conectar no servidor AD.")

    created = 0
    updated = 0
    skipped = 0
    try:
        search_filter = (
            "(&"
            "(objectCategory=person)"
            "(objectClass=user)"
            "(!(objectClass=computer))"
            "(!(userAccountControl:1.2.840.113556.1.4.803:=2))"
            ")"
        )
        connection.search(
            search_base=config.base_dn,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=["sAMAccountName", "givenName", "sn", "displayName", "mail"],
        )
        # Consulta ORM subsequente espera entradas de usuarios humanos ativos.
        UserModel = get_user_model()
        try:
            from ramais.models import PessoaRamal
        except Exception:
            PessoaRamal = None
        for entry in connection.entries:
            username = str(entry.sAMAccountName) if entry.sAMAccountName else ""
            if not username:
                skipped += 1
                continue
            email_value = str(entry.mail) if entry.mail else ""
            first_name = str(entry.givenName) if entry.givenName else ""
            last_name = str(entry.sn) if entry.sn else ""
            if not first_name and not last_name and entry.displayName:
                display = str(entry.displayName)
                parts = display.split(" ", 1)
                first_name = parts[0]
                if len(parts) > 1:
                    last_name = parts[1]

            user, was_created = UserModel.objects.get_or_create(
                username=username,
                defaults={
                    "email": email_value,
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_active": True,
                },
            )
            if was_created:
                # Usuario de AD nao usa senha local.
                user.set_unusable_password()
                user.save()
                created += 1
            else:
                changes = []
                if email_value and user.email != email_value:
                    user.email = email_value
                    changes.append("email")
                if first_name and user.first_name != first_name:
                    user.first_name = first_name
                    changes.append("first_name")
                if last_name and user.last_name != last_name:
                    user.last_name = last_name
                    changes.append("last_name")
                if changes:
                    user.save(update_fields=changes)
                    updated += 1

            if PessoaRamal and not hasattr(user, "ramal_perfil"):
                # Integra com modulo de ramais para manter consistencia
                # de dados entre autenticacao e diretorio interno.
                PessoaRamal.objects.create(
                    usuario=user,
                    cargo="",
                    setor="",
                    ramal="",
                    email=user.email or "",
                )

            _assign_read_groups(user)

    finally:
        connection.unbind()

    return Feedback(
        level="success",
        message=f"Sincronizacao concluida. Criados: {created}. Atualizados: {updated}. Ignorados: {skipped}.",
    )


def _can_manage_configuracoes(user) -> bool:
    """
    Avalia acesso ao hub de configuracoes administrativas.

    Parametros:
    - `user`: usuario autenticado.

    Retorno:
    - `bool`: True quando perfil possui permissao administrativa elegivel.

    Regra de negocio:
    - Agrupa permissoes de diferentes modulos em um unico gate de acesso.
    """

    return navigation_can_manage_configuracoes(user)


def _can_access_rh(user) -> bool:
    """
    Avalia acesso a area de RH dentro de administracao.

    Parametros:
    - `user`: usuario autenticado.

    Retorno:
    - `bool`: True quando usuario possui alguma permissao de RH.
    """

    return navigation_can_access_rh(user)


def _can_manage_rfs(user) -> bool:
    """
    Determina se usuario pode gerir RF/changelog.

    Atualmente reutiliza mesma politica de acesso de configuracoes para
    simplificar administracao de perfis.
    """

    return navigation_can_manage_rfs(user)


class ConfiguracoesAccessMixin(UserPassesTestMixin):
    """Mixin de autorizacao para telas de configuracoes do modulo."""

    def test_func(self) -> bool:
        """
        Hook do `UserPassesTestMixin` para controle de acesso por request.

        Retorno:
        - `bool`: permissao calculada para o usuario atual.
        """

        return _can_manage_configuracoes(self.request.user)


class ConfiguracoesView(ConfiguracoesAccessMixin, TemplateView):
    """
    View do painel agregador de configuracoes.

    Fluxo HTTP:
    - GET renderiza cards condicionados por permissao do usuario.
    """

    template_name = "administracao/configuracoes.html"

    def get_context_data(self, **kwargs):
        """
        Monta contexto com flags de exibicao dos cards da tela.

        Parametros:
        - `**kwargs`: contexto base da `TemplateView`.

        Retorno:
        - `dict`: contexto enriquecido com booleans por funcionalidade.
        """

        context = super().get_context_data(**kwargs)
        user = self.request.user
        # Cada flag evita expor atalhos de areas sem permissao minima.
        context["show_card_noticias"] = (
            can_manage_news(user)
        )
        context["show_card_ad"] = user.is_superuser
        context["show_card_atalhos"] = can_manage_shortcuts(user)
        context["show_card_atalhos_administracao"] = can_manage_shortcuts(user)
        context["show_card_rh"] = (
            user.is_superuser
            or user.has_perm("folha_ponto.add_feriado")
            or user.has_perm("folha_ponto.change_feriado")
            or user.has_perm("folha_ponto.delete_feriado")
            or user.has_perm("folha_ponto.add_feriasservidor")
            or user.has_perm("folha_ponto.change_feriasservidor")
            or user.has_perm("folha_ponto.delete_feriasservidor")
            or user.has_perm("folha_ponto.change_configuracaorh")
        )
        context["show_card_rfs"] = _can_manage_rfs(user)
        context["show_card_identidade_visual"] = _can_manage_configuracoes(user)
        context["show_card_smtp"] = user.is_superuser
        context["show_card_backup_sistema"] = user.is_superuser
        return context


class SystemBackupDownloadView(UserPassesTestMixin, View):
    """Disponibiliza backup completo do sistema em ZIP sob demanda."""

    def test_func(self) -> bool:
        """Restringe backup completo a superusuários por conter código e dump total."""

        user = self.request.user
        return bool(user.is_authenticated and user.is_superuser)

    def get(self, request):
        """Gera arquivo ZIP com dump SQL atual e artefatos essenciais do projeto."""

        try:
            return _build_system_backup_response()
        except (subprocess.CalledProcessError, FileNotFoundError):
            messages.error(
                request,
                "Nao foi possivel gerar o backup completo. Verifique a disponibilidade do mysqldump no servidor.",
            )
        except Exception:
            messages.error(request, "Nao foi possivel gerar o backup completo do sistema.")
        return redirect("administracao_configuracoes")


class RHAccessMixin(UserPassesTestMixin):
    """Mixin de autorizacao para rotas de RH."""

    def test_func(self) -> bool:
        """Retorna elegibilidade do usuario para acessar funcionalidades de RH."""

        return _can_access_rh(self.request.user)


class RHView(RHAccessMixin, TemplateView):
    """View de pagina estatico-funcional para navegacao de recursos de RH."""

    template_name = "administracao/rh.html"


class ADConfigView(UserPassesTestMixin, View):
    """
    Controla configuracao operacional de Active Directory.

    Fluxo HTTP:
    - GET: exibe formulario com configuracao atual.
    - POST: salva configuracao, testa conexao ou sincroniza usuarios.
    """

    template_name = "administracao/ad_config_form.html"

    def test_func(self) -> bool:
        """
        Restringe acesso somente a superusuario.

        Retorno:
        - `bool`: permissao final.
        """

        user = self.request.user
        return bool(user.is_authenticated and user.is_superuser)

    def get(self, request):
        """
        Renderiza formulario de configuracao AD.

        Parametros:
        - `request`: requisicao HTTP.

        Retorno:
        - `HttpResponse`: pagina com formulario preenchido.
        """

        form = ADConfigurationForm(instance=_get_ad_configuration())
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        """
        Processa acoes da tela AD conforme botao acionado.

        Parametros:
        - `request`: POST com dados e acao (`save`, `test`, `sync`).

        Retorno:
        - `HttpResponse`: mesma tela com feedback operacional.
        """

        config = _get_ad_configuration()
        form = ADConfigurationForm(request.POST, instance=config)
        feedback = None
        if form.is_valid():
            # Cada branch representa um comando operacional explicito do usuario.
            if "save" in request.POST:
                form.save()
                feedback = Feedback(
                    level="success", message="Configuracao salva com sucesso."
                )
            elif "test" in request.POST:
                config = form.save(commit=False)
                feedback = _test_ldap_connection(config)
            elif "sync" in request.POST:
                config = form.save(commit=False)
                feedback = _sync_ad_users(config)
        else:
            feedback = Feedback(
                level="error", message="Corrija os erros do formulario."
            )
        context = {"form": form, "feedback": feedback}
        return render(request, self.template_name, context)


class SMTPConfigView(UserPassesTestMixin, View):
    """Controla configuração e teste de conexão SMTP."""

    template_name = "administracao/smtp_config_form.html"

    def test_func(self) -> bool:
        user = self.request.user
        return bool(user.is_authenticated and user.is_superuser)

    def get(self, request):
        form = SMTPConfigurationForm(instance=_get_smtp_configuration())
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        config = _get_smtp_configuration()
        form = SMTPConfigurationForm(request.POST, instance=config)
        feedback = None
        if form.is_valid():
            if "save" in request.POST:
                form.save()
                feedback = Feedback(level="success", message="Configuração SMTP salva com sucesso.")
            elif "test" in request.POST:
                config = form.save(commit=False)
                feedback = _test_smtp_connection(config)
        else:
            feedback = Feedback(level="error", message="Corrija os erros do formulário.")
        context = {"form": form, "feedback": feedback}
        return render(request, self.template_name, context)


class IdentidadeVisualConfigView(ConfiguracoesAccessMixin, View):
    """
    Permite editar as cores globais de identidade visual da interface.

    Fluxo HTTP:
    - GET: exibe valores atuais da configuracao.
    - POST: valida e persiste novos valores (hex/rgb).
    """

    template_name = "administracao/identidade_visual_form.html"

    def get(self, request):
        form = IdentidadeVisualConfigForm(instance=_get_visual_configuration())
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        config = _get_visual_configuration()
        form = IdentidadeVisualConfigForm(request.POST, instance=config)
        feedback = None
        if form.is_valid():
            form.save()
            feedback = Feedback(
                level="success",
                message="Identidade visual atualizada com sucesso.",
            )
        else:
            feedback = Feedback(
                level="error",
                message="Corrija os erros do formulario.",
            )
        return render(request, self.template_name, {"form": form, "feedback": feedback})


class AtalhoServicoAccessMixin(UserPassesTestMixin):
    """Mixin de autorizacao para CRUD de atalhos de servico."""

    def test_func(self) -> bool:
        """
        Autoriza acesso por perfil staff ou permissoes de objeto do app.

        Retorno:
        - `bool`: permissao para listar/criar/editar/excluir atalhos.
        """

        user = self.request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_staff
            or user.has_perm("administracao.view_atalhoservico")
            or user.has_perm("administracao.add_atalhoservico")
            or user.has_perm("administracao.change_atalhoservico")
            or user.has_perm("administracao.delete_atalhoservico")
        )


class AtalhoServicoListView(AtalhoServicoAccessMixin, ListView):
    """
    Lista atalhos persistidos.

    Consulta ORM implicita:
    - Recupera queryset de `AtalhoServico` para renderizar tabela/lista.
    """

    model = AtalhoServico
    template_name = "administracao/atalho_list.html"
    context_object_name = "atalhos"


class AtalhoServicoCreateView(AtalhoServicoAccessMixin, CreateView):
    """Fluxo HTTP de criacao de atalho com validacao via `AtalhoServicoForm`."""

    model = AtalhoServico
    form_class = AtalhoServicoForm
    template_name = "administracao/atalho_form.html"
    success_url = reverse_lazy("administracao_atalho_list")


class AtalhoServicoUpdateView(AtalhoServicoAccessMixin, UpdateView):
    """Fluxo HTTP de atualizacao de atalho existente."""

    model = AtalhoServico
    form_class = AtalhoServicoForm
    template_name = "administracao/atalho_form.html"
    success_url = reverse_lazy("administracao_atalho_list")


class AtalhoServicoDeleteView(AtalhoServicoAccessMixin, DeleteView):
    """Fluxo HTTP de exclusao confirmada de atalhos."""

    model = AtalhoServico
    template_name = "administracao/atalho_confirm_delete.html"
    success_url = reverse_lazy("administracao_atalho_list")


class AtalhoAdministracaoAccessMixin(UserPassesTestMixin):
    """Mixin de autorizacao para CRUD dos cards administrativos da home."""

    def test_func(self) -> bool:
        return can_manage_shortcuts(self.request.user)


class AtalhoAdministracaoListView(AtalhoAdministracaoAccessMixin, ListView):
    """Lista configuracoes dos cards fixos administrativos exibidos na home."""

    model = AtalhoAdministracao
    template_name = "administracao/atalho_administracao_list.html"
    context_object_name = "atalhos"

    def get_queryset(self):
        atalhos = list(AtalhoAdministracao.objects.all())
        atalhos.sort(key=lambda item: item.get_funcionalidade_display().casefold())
        return atalhos


class AtalhoAdministracaoCreateView(AtalhoAdministracaoAccessMixin, CreateView):
    """Cria configuracao de card administrativo da home."""

    model = AtalhoAdministracao
    form_class = AtalhoAdministracaoForm
    template_name = "administracao/atalho_administracao_form.html"
    success_url = reverse_lazy("administracao_atalho_administracao_list")

    def get_initial(self):
        initial = super().get_initial()
        funcionalidade = self.request.GET.get("funcionalidade", "").strip()
        if funcionalidade:
            initial["funcionalidade"] = funcionalidade
        return initial


class AtalhoAdministracaoUpdateView(AtalhoAdministracaoAccessMixin, UpdateView):
    """Atualiza configuracao de card administrativo existente."""

    model = AtalhoAdministracao
    form_class = AtalhoAdministracaoForm
    template_name = "administracao/atalho_administracao_form.html"
    success_url = reverse_lazy("administracao_atalho_administracao_list")


class AtalhoAdministracaoDeleteView(AtalhoAdministracaoAccessMixin, DeleteView):
    """Exclui configuracao de card administrativo."""

    model = AtalhoAdministracao
    template_name = "administracao/atalho_administracao_confirm_delete.html"
    success_url = reverse_lazy("administracao_atalho_administracao_list")


class RFChangelogAccessMixin(UserPassesTestMixin):
    """Mixin de autorizacao para area de RF/changelog."""

    def test_func(self) -> bool:
        """Retorna permissao de gestao de RF/changelog para o usuario corrente."""

        return _can_manage_rfs(self.request.user)


class RFChangelogView(RFChangelogAccessMixin, View):
    """
    View de gestao de historico funcional e documentos markdown.

    Responsabilidades:
    - manter arquivos `docs/CHANGELOG_RF.md` e `docs/RF_site.md`;
    - registrar entradas estruturadas em `RFChangelogEntry`;
    - renderizar visualizacao HTML basica do markdown.
    """

    template_name = "administracao/rf_changelog.html"

    def _paths(self):
        """
        Resolve caminhos fisicos dos arquivos markdown do modulo.

        Retorno:
        - `tuple[Path, Path]`: caminho do changelog e do RF.

        Regra de negocio:
        - Garante existencia da pasta `docs` para operacoes de escrita.
        """

        base = Path(settings.BASE_DIR) / "docs"
        base.mkdir(parents=True, exist_ok=True)
        return base / "CHANGELOG_RF.md", base / "RF_site.md"

    def _read_file(self, path: Path) -> str:
        """
        Le conteudo textual de arquivo markdown.

        Parametros:
        - `path`: caminho absoluto do arquivo.

        Retorno:
        - `str`: conteudo UTF-8 ou string vazia quando inexistente.
        """

        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _write_file(self, path: Path, content: str):
        """
        Persiste markdown normalizando quebra de linha final.

        Parametros:
        - `path`: destino de escrita.
        - `content`: texto markdown completo.
        """

        path.write_text(content.rstrip() + "\n", encoding="utf-8")

    def _append_changelog(self, path: Path, entry: RFChangelogEntry):
        """
        Acrescenta bloco formatado de uma entrada no arquivo de changelog.

        Parametros:
        - `path`: arquivo `CHANGELOG_RF.md`.
        - `entry`: objeto salvo em banco contendo metadados da mudanca.
        """

        atual = self._read_file(path).strip()
        autor = "Sistema"
        if entry.criado_por:
            autor = entry.criado_por.get_full_name() or entry.criado_por.username
        bloco = (
            f"\n## {entry.criado_em:%Y-%m-%d %H:%M} - {entry.titulo}\n"
            f"- Modulo: {entry.get_sistema_display()}\n"
            f"- Alteracao: {entry.descricao}\n"
            f"- Autor: {autor}\n"
        )
        if not atual:
            atual = "# Changelog de RFs\n"
        self._write_file(path, atual + bloco)

    def post(self, request):
        """
        Processa acoes da tela de RF/changelog.

        Parametros:
        - `request`: POST com `action` e dados de formulario.

        Retorno:
        - `HttpResponseRedirect`: redireciona para evitar reenvio de POST.

        Acoes suportadas:
        - `save_changelog`: sobrescreve markdown do changelog.
        - `save_rf`: sobrescreve markdown de RF.
        - `new_entry`: cria registro no banco e apenda no arquivo.
        """

        changelog_file, rf_file = self._paths()
        action = request.POST.get("action", "").strip()

        if action == "save_changelog":
            form = MarkdownEditorForm(request.POST)
            if form.is_valid():
                self._write_file(changelog_file, form.cleaned_data["conteudo"])
            return redirect("administracao_rfs")

        if action == "save_rf":
            form = MarkdownEditorForm(request.POST)
            if form.is_valid():
                self._write_file(rf_file, form.cleaned_data["conteudo"])
            return redirect("administracao_rfs")

        if action == "new_entry":
            form = RFChangelogEntryForm(request.POST)
            if form.is_valid():
                entry = form.save(commit=False)
                entry.criado_por = request.user
                entry.save()
                self._append_changelog(changelog_file, entry)
            return redirect("administracao_rfs")

        return redirect("administracao_rfs")

    def get(self, request):
        """
        Renderiza a tela principal de RF/changelog.

        Parametros:
        - `request`: requisicao HTTP GET.

        Retorno:
        - `HttpResponse`: pagina com formularios, HTML renderizado e historico.

        Consulta ORM relevante:
        - `RFChangelogEntry.objects.select_related("criado_por").all()[:30]`
          busca ultimas entradas com prefetch do autor para evitar N+1.
        """

        changelog_file, rf_file = self._paths()
        changelog_text = self._read_file(changelog_file)
        rf_text = self._read_file(rf_file)
        rf_html = _render_markdown_basic(rf_text) if rf_text else ""
        changelog_html = _render_markdown_basic(changelog_text) if changelog_text else ""
        entry_form = RFChangelogEntryForm()
        changelog_form = MarkdownEditorForm(initial={"conteudo": changelog_text})
        rf_form = MarkdownEditorForm(initial={"conteudo": rf_text})
        entries = RFChangelogEntry.objects.select_related("criado_por").all()[:30]
        return render(
            request,
            self.template_name,
            {
                "changelog_text": changelog_text,
                "changelog_html": changelog_html,
                "changelog_path": str(changelog_file.relative_to(settings.BASE_DIR)),
                "rf_text": rf_text,
                "rf_html": rf_html,
                "rf_path": str(rf_file.relative_to(settings.BASE_DIR)),
                "entry_form": entry_form,
                "entries": entries,
                "changelog_form": changelog_form,
                "rf_form": rf_form,
            },
        )
