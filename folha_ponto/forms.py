"""
Formulários do app `folha_ponto`.

Este módulo compõe a camada de entrada/validação para as views de RH:
- normaliza dados enviados pelos templates;
- aplica regras de tipos e widgets HTML;
- encaminha dados válidos para os modelos (`Feriado`, `FeriasServidor`, `ConfiguracaoRH`).
"""

from django import forms

from .models import ConfiguracaoRH, Feriado, FeriasServidor


class FeriadoForm(forms.ModelForm):
    """Formulário de cadastro/edição de feriados.

    Problema resolvido:
    - Capturar data e descrição em formato consistente para alimentar o calendário mensal.
    """

    class Meta:
        """Configuração de campos visíveis, rótulos e widget de data HTML5."""

        model = Feriado
        fields = ["data", "descricao"]
        labels = {
            "data": "Data",
            "descricao": "Descricao",
        }
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}),
        }


class FeriasServidorForm(forms.ModelForm):
    """Formulário de lançamento de férias por servidor.

    Problema resolvido:
    - Permitir ao RH registrar período de afastamento e observações em interface única.
    """

    class Meta:
        """Mapeamento dos campos de férias com widgets de data para início/fim."""

        model = FeriasServidor
        fields = ["servidor", "data_inicio", "data_fim", "observacao"]
        labels = {
            "servidor": "Servidor",
            "data_inicio": "Data inicio",
            "data_fim": "Data fim",
            "observacao": "Observacao",
        }
        widgets = {
            "data_inicio": forms.DateInput(attrs={"type": "date"}),
            "data_fim": forms.DateInput(attrs={"type": "date"}),
        }


class ConfiguracaoRHForm(forms.ModelForm):
    """Formulário de manutenção da configuração institucional de RH.

    Problema resolvido:
    - Atualizar o arquivo de brasão usado na impressão da folha ponto.
    """

    class Meta:
        """Expõe somente o campo de brasão para evitar edição indevida de metadados."""

        model = ConfiguracaoRH
        fields = ["brasao"]
        labels = {"brasao": "Brasao do Estado"}
