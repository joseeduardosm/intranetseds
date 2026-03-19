"""
Entidades persistentes do app `administracao`.

Este modulo define o contrato de dados usado pelas views e formularios
administrativos: configuracao de AD/LDAP, atalhos exibidos na interface
e historico de RF/changelog.
Tambem centraliza validacoes de dominio (ex.: formato de URL) antes da
persistencia no banco via ORM do Django.
"""

import re

from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models
from urllib.parse import urlparse


HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
RGB_COLOR_RE = re.compile(
    r"^rgb\(\s*"
    r"(?:25[0-5]|2[0-4]\d|1?\d?\d)\s*,\s*"
    r"(?:25[0-5]|2[0-4]\d|1?\d?\d)\s*,\s*"
    r"(?:25[0-5]|2[0-4]\d|1?\d?\d)\s*"
    r"\)$",
    re.IGNORECASE,
)


def validar_cor_css_hex_ou_rgb(value: str) -> None:
    """
    Valida entrada de cor no formato hexadecimal ou RGB.

    Formatos aceitos:
    - `#RGB` ou `#RRGGBB`
    - `rgb(0, 0, 0)` ate `rgb(255, 255, 255)`
    """

    normalized = (value or "").strip()
    if HEX_COLOR_RE.match(normalized) or RGB_COLOR_RE.match(normalized):
        return
    raise ValidationError(
        "Informe uma cor valida em hexadecimal (#A32B21) ou RGB (rgb(163, 43, 33))."
    )


def validar_url_destino_interna_ou_externa(value: str) -> None:
    """
    Valida o campo de URL de destino dos atalhos de servico.

    Parametros:
    - `value`: texto informado no formulario/model.

    Retorno:
    - Nao retorna valor; levanta `ValidationError` quando invalida.

    Regra de negocio:
    - O sistema exige URL absoluta com esquema HTTP/HTTPS para garantir
      navegacao consistente e evitar caminhos ambiguos/incompletos.
    """

    parsed = urlparse(value or "")
    if parsed.scheme not in {"http", "https"}:
        raise ValidationError("Informe uma URL valida com http:// ou https://.")
    if not parsed.netloc:
        raise ValidationError("Informe uma URL valida.")


class ADConfiguration(models.Model):
    """
    Representa os parametros de conexao com o Active Directory.

    Entidade de infraestrutura: armazena host/porta/credenciais de bind
    usados por fluxos de teste de conexao, autenticacao LDAP e sincronizacao
    de usuarios para a base local.
    """

    server_host = models.CharField(max_length=255)
    server_port = models.PositiveIntegerField(default=389)
    use_ssl = models.BooleanField(default=False)
    base_dn = models.CharField(max_length=255)
    bind_dn = models.CharField(max_length=255)
    bind_password = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Metadados de exibicao no admin e em telas administrativas."""

        verbose_name = "Configuracao de AD"
        verbose_name_plural = "Configuracoes de AD"

    def __str__(self) -> str:
        """
        Retorna representacao curta da configuracao para listagens.

        Retorno:
        - `str`: combinacao `host:porta`.
        """

        return f"{self.server_host}:{self.server_port}"


class SMTPConfiguration(models.Model):
    """Configuração singleton de servidor SMTP para envios transacionais."""

    host = models.CharField(max_length=255)
    port = models.PositiveIntegerField(default=587)
    use_tls = models.BooleanField(default=True)
    use_ssl = models.BooleanField(default=False)
    username = models.CharField(max_length=255, blank=True, default="")
    password = models.CharField(max_length=255, blank=True, default="")
    from_email = models.EmailField(max_length=255)
    timeout = models.PositiveIntegerField(default=10)
    ativo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuracao SMTP"
        verbose_name_plural = "Configuracoes SMTP"

    def __str__(self) -> str:
        return f"{self.host}:{self.port} ({'ativo' if self.ativo else 'inativo'})"


class AtalhoServico(models.Model):
    """
    Entidade de atalho funcional exibido na area administrativa.

    Cada registro representa um card/link com imagem e URL de destino.
    A flag `ativo` permite desabilitar atalho sem excluir historico.
    """

    titulo = models.CharField(max_length=120)
    imagem = models.ImageField(
        upload_to="atalhos/",
        validators=[FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg"])],
    )
    url_destino = models.CharField(
        max_length=500,
        validators=[validar_url_destino_interna_ou_externa],
    )
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Define ordenacao padrao e nomes de exibicao da entidade."""

        ordering = ["id"]
        verbose_name = "Atalho"
        verbose_name_plural = "Atalhos"

    def __str__(self) -> str:
        """
        Retorna o titulo do atalho em listagens e relacionamentos.

        Retorno:
        - `str`: titulo legivel para operadores.
        """

        return self.titulo


class RFChangelogEntry(models.Model):
    """
    Registro estruturado de alteracoes funcionais (RF/changelog).

    Entidade de auditoria funcional: guarda modulo afetado, titulo,
    descricao e autor para alimentar historico exibido em tela e
    arquivos markdown de documentacao interna.
    """

    SISTEMA_CHOICES = [
        ("GERAL", "Geral"),
        ("NOTICIAS", "Noticias"),
        ("RAMAIS", "Ramais"),
        ("DIARIO_BORDO", "Diario de Bordo"),
        ("CONTRATOS", "Contratos"),
        ("EMPRESAS_PREPOSTOS", "Empresas e Prepostos"),
        ("RESERVA_SALAS", "Reserva de Salas"),
        ("USUARIOS", "Usuarios"),
        ("AUDITORIA", "Auditoria"),
        ("ADMINISTRACAO", "Administracao"),
        ("FOLHA_PONTO", "Folha de Ponto"),
    ]

    sistema = models.CharField(max_length=40, choices=SISTEMA_CHOICES, default="GERAL")
    titulo = models.CharField(max_length=180)
    descricao = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rf_changelog_entries",
    )

    class Meta:
        """Ordenacao mais recente primeiro para leitura operacional."""

        ordering = ["-criado_em"]
        verbose_name = "RF/Changelog"
        verbose_name_plural = "RFs/Changelog"

    def __str__(self) -> str:
        """
        Exibe modulo + titulo para identificacao rapida da entrada.

        Retorno:
        - `str`: etiqueta amigavel da mudanca registrada.
        """

        return f"{self.get_sistema_display()} - {self.titulo}"


class IdentidadeVisualConfig(models.Model):
    """
    Configuracao visual global aplicada ao cabecalho e fundo do sistema.

    A aplicacao usa o primeiro registro como configuracao ativa (singleton
    operacional), permitindo ajuste simples sem versionamento de temas.
    """

    DEFAULT_NAVBAR_COLOR = "#1f2a44"
    DEFAULT_BACKGROUND_COLOR = "#f2f0ea"
    DEFAULT_BRAND_TEXT_COLOR = "#d94f04"

    navbar_color = models.CharField(
        max_length=32,
        default=DEFAULT_NAVBAR_COLOR,
        validators=[validar_cor_css_hex_ou_rgb],
    )
    background_color = models.CharField(
        max_length=32,
        default=DEFAULT_BACKGROUND_COLOR,
        validators=[validar_cor_css_hex_ou_rgb],
    )
    brand_text_color = models.CharField(
        max_length=32,
        default=DEFAULT_BRAND_TEXT_COLOR,
        validators=[validar_cor_css_hex_ou_rgb],
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Identidade visual"
        verbose_name_plural = "Identidade visual"

    def __str__(self) -> str:
        return "Identidade visual do site"
