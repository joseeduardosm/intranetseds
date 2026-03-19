"""
Formulários do app `monitoramento`.
"""

from __future__ import annotations

from django import forms

from .models import (
    ConexaoBancoMonitoramento,
    DashboardMonitoramento,
    GraficoDashboardMonitoramento,
    ProjetoMonitoramento,
)
from .services import extract_sql_parameters, validate_read_only_sql


PARAMETER_TYPE_CHOICES = [
    ("date", "Data"),
    ("datetime", "Data e hora"),
    ("integer", "Inteiro"),
    ("decimal", "Decimal"),
    ("text", "Texto"),
]


class ProjetoMonitoramentoForm(forms.ModelForm):
    class Meta:
        model = ProjetoMonitoramento
        fields = ["nome", "descricao"]
        labels = {
            "nome": "Nome do projeto",
            "descricao": "Descrição",
        }
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 4}),
        }


class ConexaoBancoMonitoramentoForm(forms.ModelForm):
    senha = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(render_value=True),
        required=False,
    )

    class Meta:
        model = ConexaoBancoMonitoramento
        fields = ["tipo_banco", "host", "porta", "database", "schema", "usuario"]
        labels = {
            "tipo_banco": "Tipo do banco",
            "host": "Endereço IP / Host",
            "porta": "Porta",
            "database": "Database",
            "schema": "Schema padrão",
            "usuario": "Usuário",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["schema"].required = False
        self.fields["porta"].required = False
        if not self.initial.get("porta") and not getattr(self.instance, "porta", None):
            self.initial["porta"] = 3306

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo_banco")
        porta = cleaned.get("porta")
        if tipo == ConexaoBancoMonitoramento.TIPO_SQLSERVER and not porta:
            cleaned["porta"] = 1433
        elif tipo == ConexaoBancoMonitoramento.TIPO_MYSQL and not porta:
            cleaned["porta"] = 3306
        return cleaned


class DashboardMonitoramentoForm(forms.ModelForm):
    class Meta:
        model = DashboardMonitoramento
        fields = ["titulo", "descricao"]
        labels = {
            "titulo": "Título do dashboard",
            "descricao": "Descrição",
        }
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 3}),
        }


class ConsultaDashboardForm(forms.Form):
    nome = forms.CharField(label="Nome da consulta", max_length=180)
    sql_texto = forms.CharField(
        label="SQL da consulta",
        widget=forms.Textarea(attrs={"rows": 14, "spellcheck": "false"}),
        help_text="Aceita apenas SELECT/WITH com parâmetros como @DataInicio.",
    )

    def clean_sql_texto(self):
        sql_texto = self.cleaned_data["sql_texto"]
        validate_read_only_sql(sql_texto)
        return sql_texto

    def get_extracted_parameters(self):
        if not self.is_valid():
            return []
        return extract_sql_parameters(self.cleaned_data["sql_texto"])


class GraficoDashboardForm(forms.Form):
    titulo = forms.CharField(label="Título do gráfico", max_length=180, required=False)
    tipo_grafico = forms.ChoiceField(
        label="Tipo do gráfico",
        choices=GraficoDashboardMonitoramento.TIPO_GRAFICO_CHOICES,
    )
    campo_x = forms.CharField(label="Campo X", max_length=180, required=False)
    campo_y = forms.CharField(label="Campo Y", max_length=180, required=False)
    campo_serie = forms.CharField(label="Campo Série", max_length=180, required=False)
    campo_data = forms.CharField(label="Campo temporal", max_length=180, required=False)
    campo_detalhe = forms.CharField(label="Campo de detalhe/exportação", max_length=180, required=False)

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo_grafico")
        campo_x = (cleaned.get("campo_x") or "").strip()
        campo_y = (cleaned.get("campo_y") or "").strip()
        if tipo in {
            GraficoDashboardMonitoramento.TIPO_LINHA,
            GraficoDashboardMonitoramento.TIPO_BARRA,
            GraficoDashboardMonitoramento.TIPO_BARRA_HORIZONTAL,
            GraficoDashboardMonitoramento.TIPO_DISPERSAO,
            GraficoDashboardMonitoramento.TIPO_AREA,
        }:
            if not campo_x or not campo_y:
                raise forms.ValidationError("Informe os campos X e Y para o tipo de gráfico escolhido.")
        if tipo == GraficoDashboardMonitoramento.TIPO_PIZZA and not campo_x:
            raise forms.ValidationError("Informe o campo de categoria para o gráfico de pizza.")
        if tipo == GraficoDashboardMonitoramento.TIPO_PIZZA and not campo_y:
            raise forms.ValidationError("Informe o campo de valor para o gráfico de pizza.")
        return cleaned


def build_parameter_definitions(post_data, parameter_names):
    definitions = []
    for name in parameter_names:
        field_name = f"param_type_{name}"
        label_name = f"param_label_{name}"
        param_type = (post_data.get(field_name) or "date").strip()
        if param_type not in {choice[0] for choice in PARAMETER_TYPE_CHOICES}:
            param_type = "text"
        definitions.append(
            {
                "name": name,
                "type": param_type,
                "label": (post_data.get(label_name) or name).strip() or name,
            }
        )
    return definitions


def build_runtime_parameter_values(get_data, parameter_definitions):
    values = {}
    for item in parameter_definitions:
        selected = (get_data.get(item["name"]) or "").strip()
        options = item.get("options") or []
        if options:
            allowed_values = {str(opt.get("value", "")).strip() for opt in options}
            default_value = str(item.get("default") or "").strip()
            if not selected:
                selected = default_value
            if selected and selected not in allowed_values:
                selected = default_value if default_value in allowed_values else ""
        values[item["name"]] = selected
    return values
