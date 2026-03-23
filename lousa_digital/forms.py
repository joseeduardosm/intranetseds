"""
Formulários de entrada do app `lousa_digital`.

Este módulo faz a ponte entre templates e modelos, aplicando validações
de negócio antes da persistência no banco.
"""

from django import forms
import re
from django.utils import timezone

from .models import Encaminhamento, EventoTimeline, Processo


class ProcessoForm(forms.ModelForm):
    """Formulário de criação/edição dos dados básicos do processo."""

    def __init__(self, *args, origem_fixa=None, **kwargs):
        """Oculta a origem e a mantém sincronizada com a aba ativa."""

        self.origem_fixa = Processo.normalizar_aba_origem(origem_fixa)
        super().__init__(*args, **kwargs)
        self.fields["caixa_origem"].widget = forms.HiddenInput()
        self.fields["caixa_origem"].required = False
        if self.origem_fixa:
            self.initial["caixa_origem"] = self.origem_fixa

        origem_atual = (
            self.initial.get("caixa_origem")
            or getattr(self.instance, "caixa_origem", "")
            or self.origem_fixa
        )
        self.origem_exibicao = origem_atual or "-"

    class Meta:
        """Define campos editáveis e widgets para UI da lousa."""

        model = Processo
        fields = ["numero_sei", "assunto", "link_sei", "caixa_origem", "arquivo_morto"]
        widgets = {
            "numero_sei": forms.TextInput(attrs={"class": "form-control"}),
            "assunto": forms.TextInput(attrs={"class": "form-control"}),
            "link_sei": forms.URLInput(attrs={"class": "form-control"}),
            "caixa_origem": forms.TextInput(attrs={"class": "form-control"}),
            "arquivo_morto": forms.CheckboxInput(attrs={"class": "lousa-checkbox-input"}),
        }

    def clean_caixa_origem(self):
        """Mantém a origem preenchida mesmo com campo oculto."""

        caixa_origem = (
            self.cleaned_data.get("caixa_origem")
            or self.origem_fixa
            or getattr(self.instance, "caixa_origem", "")
        )
        caixa_origem = (caixa_origem or "").strip().upper()
        if not caixa_origem:
            raise forms.ValidationError("A origem do processo é obrigatória.")
        return caixa_origem


class EncaminhamentoForm(forms.ModelForm):
    """Formulário de abertura de encaminhamento com controle de prazo."""

    class Meta:
        """Expõe destino e data de prazo com input de data HTML5."""

        model = Encaminhamento
        fields = ["destino", "prazo_data", "email_notificacao"]
        widgets = {
            "destino": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "style": "text-transform: uppercase;",
                    "oninput": "this.value = this.value.toUpperCase();",
                }
            ),
            "prazo_data": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": "form-control", "type": "date"},
            ),
            "email_notificacao": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "exemplo@dominio.gov.br"}
            ),
        }
        labels = {
            "prazo_data": "Prazo",
            "email_notificacao": "E-mail para alerta (3 dias)",
        }

    def clean(self):
        """Valida regra de prazo mínimo.

        Regra de negócio:
        - não permite encaminhamento com prazo em data passada.
        """

        cleaned_data = super().clean()
        prazo_data = cleaned_data.get("prazo_data")
        hoje = timezone.localdate()
        if prazo_data and prazo_data < hoje:
            raise forms.ValidationError("O prazo deve ser hoje ou uma data futura.")
        return cleaned_data

    def clean_destino(self):
        """Normaliza e valida destino com apenas letras maiúsculas e espaços."""

        destino = (self.cleaned_data.get("destino") or "").strip().upper()
        if not re.fullmatch(r"[A-ZÀ-ÖØ-Ý\s]+", destino):
            raise forms.ValidationError("Destino deve conter apenas letras maiúsculas.")
        return destino


class NotaTimelineForm(forms.ModelForm):
    """Formulário para registro de nota textual na timeline do processo."""

    class Meta:
        """Mantém edição restrita ao campo de descrição da nota."""

        model = EventoTimeline
        fields = ["descricao"]
        widgets = {
            "descricao": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Registrar nota na timeline"}),
        }
        labels = {"descricao": "Nota"}
