"""
Formulários do app `diario_bordo`.

Este módulo transforma modelos de domínio em formulários HTTP com widgets
e validações apropriadas para templates de criação/edição de blocos e
incrementos.
"""

from django import forms
from django.contrib.auth.models import User

from usuarios.utils import usuarios_visiveis

from .models import BlocoTrabalho, Incremento, IncrementoAnexo


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        cleaned = super().clean
        if isinstance(data, (list, tuple)):
            return [cleaned(item, initial) for item in data]
        if not data:
            return []
        return [cleaned(data, initial)]


class BaseBlocoTrabalhoForm(forms.ModelForm):
    marcadores_ids = forms.CharField(
        required=False,
        label="Marcadores",
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        if instance and getattr(instance, "pk", None):
            ids = [item.id for item in instance.marcadores_locais]
            self.fields["marcadores_ids"].initial = ",".join(str(item_id) for item_id in ids)

    def _parse_marcadores_ids(self):
        bruto = (self.cleaned_data.get("marcadores_ids") or "").strip()
        if not bruto:
            return []
        return [int(item.strip()) for item in bruto.split(",") if item.strip().isdigit()]

    def save(self, commit=True):
        obj = super().save(commit=commit)
        if commit and getattr(obj, "pk", None):
            obj.definir_marcadores_locais_por_ids(self._parse_marcadores_ids())
        return obj


class BlocoTrabalhoCreateForm(BaseBlocoTrabalhoForm):
    """
    Formulário de criação de bloco de trabalho.

    Permite definir participantes já no cadastro inicial.
    """

    participantes = forms.ModelMultipleChoiceField(
        label="Participantes",
        required=False,
        queryset=usuarios_visiveis(User.objects.order_by("username")),
        widget=forms.SelectMultiple(attrs={"class": "form-select"}),
    )

    class Meta:
        """Mapeamento entre campos exibidos e modelo `BlocoTrabalho`."""

        model = BlocoTrabalho
        fields = ["nome", "descricao", "marcadores_ids", "participantes"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "descricao": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        """
        Ajusta rótulo das opções de participantes para nome legível.

        Retorno:
        - não retorna valor; configura o campo em runtime.
        """

        super().__init__(*args, **kwargs)
        self.fields["participantes"].label_from_instance = (
            lambda obj: obj.get_full_name() or obj.username
        )


class IncrementoForm(forms.ModelForm):
    """
    Formulário de inclusão/edição de incrementos de um bloco.

    Suporta texto obrigatório e anexos opcionais.
    """

    anexos = MultipleFileField(
        required=False,
        label="Anexos",
    )

    class Meta:
        """Define campos permitidos de `Incremento` no formulário."""

        model = Incremento
        fields = ["texto", "imagem"]
        widgets = {
            "texto": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    def save(self, commit=True):
        obj = super().save(commit=commit)
        if commit:
            for arquivo in self.cleaned_data.get("anexos", []):
                IncrementoAnexo.objects.create(incremento=obj, arquivo=arquivo)
        return obj


class BlocoTrabalhoUpdateForm(BaseBlocoTrabalhoForm):
    """
    Formulário de atualização de bloco existente.

    Além dos campos básicos, permite alteração de status operacional.
    """

    participantes = forms.ModelMultipleChoiceField(
        label="Participantes",
        required=False,
        queryset=usuarios_visiveis(User.objects.order_by("username")),
        widget=forms.SelectMultiple(attrs={"class": "form-select"}),
    )

    class Meta:
        """Mapeamento de campos de edição para `BlocoTrabalho`."""

        model = BlocoTrabalho
        fields = ["nome", "descricao", "status", "marcadores_ids", "participantes"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "descricao": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        """
        Uniformiza apresentação dos participantes por nome completo.

        Retorno:
        - não retorna valor.
        """

        super().__init__(*args, **kwargs)
        self.fields["participantes"].label_from_instance = (
            lambda obj: obj.get_full_name() or obj.username
        )
