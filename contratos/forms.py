"""
Formulários do app `contratos`.

Este módulo adapta o model `Contrato` para entrada validada na camada HTTP,
incluindo parsing de datas em formatos locais e regras de preenchimento
automático de `data_fim` quando a vigência é informada.
"""

from django import forms

from .models import Contrato, add_months


class ContratoForm(forms.ModelForm):
    """
    Formulário principal de criação/edição de contratos.

    Papel na arquitetura:
    - encapsular validações de entrada;
    - definir widgets/estilo para templates do app.
    """

    data_inicial = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"class": "form-control", "type": "date"},
        ),
    )
    data_fim = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={"class": "form-control", "type": "date"},
        ),
    )

    class Meta:
        """Mapeamento declarativo entre campos de formulário e model."""

        model = Contrato
        fields = [
            "nro_sei",
            "link_processo",
            "nro_contrato",
            "empresa",
            "objeto",
            "status",
            "valor_total",
            "valor_mensal",
            "data_inicial",
            "vigencia_meses",
            "data_fim",
            "prorrogacao_maxima_meses",
        ]
        widgets = {
            "nro_sei": forms.TextInput(attrs={"class": "form-control"}),
            "link_processo": forms.URLInput(attrs={"class": "form-control"}),
            "nro_contrato": forms.TextInput(attrs={"class": "form-control"}),
            "empresa": forms.Select(attrs={"class": "form-select"}),
            "objeto": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "valor_total": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "valor_mensal": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "vigencia_meses": forms.Select(attrs={"class": "form-select"}),
            "prorrogacao_maxima_meses": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        """
        Aplica regra de negócio para cálculo de `data_fim`.

        Retorno:
        - `dict`: `cleaned_data` enriquecido para persistência.
        """

        cleaned_data = super().clean()
        data_inicial = cleaned_data.get("data_inicial")
        vigencia = cleaned_data.get("vigencia_meses")
        data_fim = cleaned_data.get("data_fim")
        # Quando usuário informa início + vigência mas omite término,
        # o sistema calcula automaticamente para reduzir erro operacional.
        if data_inicial and vigencia and not data_fim:
            cleaned_data["data_fim"] = add_months(data_inicial, vigencia)
        return cleaned_data
