"""
Formularios Django do app `administracao`.

Este modulo conecta models e camada HTTP para entrada de dados validada.
As classes daqui sao consumidas por views para criar/editar configuracoes
de AD, atalhos de servico e entradas de changelog, alem de edicao de
conteudo markdown usado como documentacao interna.
"""

from django import forms

from .models import (
    ADConfiguration,
    AtalhoAdministracao,
    AtalhoServico,
    IdentidadeVisualConfig,
    RFChangelogEntry,
    SMTPConfiguration,
)


class ADConfigurationForm(forms.ModelForm):
    """
    Formulario de manutencao da configuracao de Active Directory.

    Papel na arquitetura:
    - Encapsula validacao de campos do model `ADConfiguration`.
    - Define labels/widgets para melhor usabilidade da tela de configuracao.
    """

    class Meta:
        """Mapeamento declarativo entre model e campos exibidos no formulario."""

        model = ADConfiguration
        fields = [
            "server_host",
            "server_port",
            "use_ssl",
            "base_dn",
            "bind_dn",
            "bind_password",
        ]
        widgets = {
            "bind_password": forms.PasswordInput(render_value=True),
        }
        labels = {
            "server_host": "Servidor",
            "server_port": "Porta",
            "use_ssl": "Usar SSL (LDAPS)",
            "base_dn": "Base DN",
            "bind_dn": "Usuario bind",
            "bind_password": "Senha bind",
        }


class AtalhoServicoForm(forms.ModelForm):
    """
    Formulario de cadastro/edicao de atalhos.

    Reaproveita validacoes do model `AtalhoServico` (arquivo e URL)
    e define labels para a interface administrativa.
    """

    class Meta:
        """Configura campos permitidos e rotulos para CRUD de atalhos."""

        model = AtalhoServico
        fields = ["titulo", "imagem", "url_destino", "ativo"]
        labels = {
            "titulo": "Titulo",
            "imagem": "Imagem (PNG, JPG ou JPEG)",
            "url_destino": "URL de destino",
            "ativo": "Ativo",
        }


class AtalhoAdministracaoForm(forms.ModelForm):
    """
    Formulario de cadastro/edicao de cards administrativos da home.

    A funcionalidade identifica o destino fixo do card; a imagem e o status
    permitem customizar sua apresentação sem alterar a navegação.
    """

    class Meta:
        model = AtalhoAdministracao
        fields = ["funcionalidade", "imagem", "ativo"]
        labels = {
            "funcionalidade": "Funcionalidade",
            "imagem": "Imagem (PNG, JPG ou JPEG)",
            "ativo": "Ativo",
        }


class SMTPConfigurationForm(forms.ModelForm):
    """Formulário de manutenção da configuração SMTP."""

    class Meta:
        model = SMTPConfiguration
        fields = [
            "host",
            "port",
            "use_tls",
            "use_ssl",
            "username",
            "password",
            "from_email",
            "timeout",
            "ativo",
        ]
        widgets = {
            "password": forms.PasswordInput(render_value=True),
        }
        labels = {
            "host": "Servidor SMTP",
            "port": "Porta",
            "use_tls": "Usar TLS (STARTTLS)",
            "use_ssl": "Usar SSL",
            "username": "Usuário",
            "password": "Senha",
            "from_email": "E-mail remetente",
            "timeout": "Timeout (segundos)",
            "ativo": "Ativo",
        }

    def clean(self):
        cleaned = super().clean()
        use_tls = cleaned.get("use_tls")
        use_ssl = cleaned.get("use_ssl")
        if use_tls and use_ssl:
            raise forms.ValidationError("Escolha TLS ou SSL. Não é permitido usar ambos ao mesmo tempo.")
        return cleaned


class RFChangelogEntryForm(forms.ModelForm):
    """
    Formulario para registrar nova entrada de RF/changelog.

    Usado na tela de historico para persistir uma mudanca funcional
    estruturada antes de refletir o conteudo em markdown.
    """

    class Meta:
        """Define campos de negocio e widget textual para descricao longa."""

        model = RFChangelogEntry
        fields = ["sistema", "titulo", "descricao"]
        labels = {
            "sistema": "Modulo",
            "titulo": "Titulo da alteracao",
            "descricao": "Descricao",
        }
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 4}),
        }


class MarkdownEditorForm(forms.Form):
    """
    Formulario simples para edicao manual de arquivos markdown.

    Campo:
    - `conteudo`: texto bruto do markdown persistido em disco.
    """

    conteudo = forms.CharField(widget=forms.Textarea(attrs={"rows": 18}))


class IdentidadeVisualConfigForm(forms.ModelForm):
    """
    Formulario de customizacao da identidade visual global do sistema.

    Aceita codigos CSS de cor em hexadecimal ou formato RGB.
    """

    class Meta:
        model = IdentidadeVisualConfig
        fields = ["navbar_color", "background_color", "brand_text_color"]
        labels = {
            "navbar_color": "Cor da barra de navegacao",
            "background_color": "Cor de fundo da pagina",
            "brand_text_color": "Cor do texto 'Sistema de Gestao Integrada'",
        }
        help_texts = {
            "navbar_color": "Use #A32B21 ou rgb(163, 43, 33).",
            "background_color": "Use #A32B21 ou rgb(163, 43, 33).",
            "brand_text_color": "Use #A32B21 ou rgb(163, 43, 33).",
        }
        widgets = {
            "navbar_color": forms.TextInput(attrs={"placeholder": "#1F2A44"}),
            "background_color": forms.TextInput(attrs={"placeholder": "rgb(242, 240, 234)"}),
            "brand_text_color": forms.TextInput(attrs={"placeholder": "#D94F04"}),
        }

    def clean(self):
        cleaned = super().clean()
        for field in ("navbar_color", "background_color", "brand_text_color"):
            value = cleaned.get(field)
            if isinstance(value, str):
                cleaned[field] = value.strip()
        return cleaned
