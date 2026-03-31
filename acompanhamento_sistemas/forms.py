from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model

from .models import EntregaSistema, EtapaSistema, InteressadoSistema, InteressadoSistemaManual, Sistema, TipoInteressado
from .utils import nome_usuario_exibicao


User = get_user_model()


class UsuarioDisplayChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return nome_usuario_exibicao(obj) or obj.username


class UsuarioComEmailSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        instancia = getattr(value, "instance", None)
        if instancia is not None:
            option["attrs"]["data-email"] = (getattr(instancia, "email", "") or "").strip()
        return option


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        cleaned = super().clean
        if data in self.empty_values:
            return []
        if isinstance(data, (list, tuple)):
            return [cleaned(item, initial) for item in data]
        return [cleaned(data, initial)]


class SistemaForm(forms.ModelForm):
    class Meta:
        model = Sistema
        fields = ["nome", "descricao", "url_homologacao", "url_producao"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "descricao": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "url_homologacao": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://..."}),
            "url_producao": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://..."}),
        }


class EntregaSistemaForm(forms.ModelForm):
    class Meta:
        model = EntregaSistema
        fields = ["titulo", "descricao"]
        widgets = {
            "titulo": forms.TextInput(attrs={"class": "form-control"}),
            "descricao": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class EtapaSistemaAtualizacaoForm(forms.ModelForm):
    justificativa_status = forms.CharField(
        required=False,
        label="Justificativa da alteração de status",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )
    anexos = MultipleFileField(
        required=False,
        label="Anexos da etapa",
        widget=MultipleFileInput(attrs={"class": "form-control", "multiple": True}),
    )

    class Meta:
        model = EtapaSistema
        fields = ["data_etapa", "status"]
        widgets = {
            "data_etapa": forms.DateInput(format="%Y-%m-%d", attrs={"class": "form-control", "type": "date"}),
            "status": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_etapa"].input_formats = ["%Y-%m-%d"]
        self.fields["data_etapa"].help_text = "A data já vem preenchida com o valor cadastrado. Altere apenas se houver revisão da etapa."
        if self.instance and getattr(self.instance, "pk", None):
            self.initial.setdefault("data_etapa", self.instance.data_etapa)
            self.initial.setdefault("status", self.instance.status)
            if self.instance.tipo_etapa == EtapaSistema.TipoEtapa.REQUISITOS:
                self.fields["anexos"].label = "Anexo dos requisitos"
                self.fields["anexos"].help_text = "Ao concluir Requisitos, anexe obrigatoriamente o documento de requisitos."

    def clean(self):
        cleaned_data = super().clean()
        status_novo = cleaned_data.get("status")
        justificativa = (cleaned_data.get("justificativa_status") or "").strip()
        anexos = cleaned_data.get("anexos") or []
        if self.instance and getattr(self.instance, "pk", None):
            if status_novo and status_novo != self.instance.status and not justificativa:
                self.add_error("justificativa_status", "Informe a justificativa ao alterar o status.")
            if (
                self.instance.tipo_etapa == EtapaSistema.TipoEtapa.REQUISITOS
                and status_novo == EtapaSistema.Status.ENTREGUE
                and self.instance.status != EtapaSistema.Status.ENTREGUE
                and not anexos
            ):
                self.add_error("anexos", "Ao concluir Requisitos, anexe obrigatoriamente o documento de requisitos.")
        return cleaned_data


class NotaEtapaSistemaForm(forms.Form):
    texto_nota = forms.CharField(
        required=False,
        label="Anotação livre",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )
    anexos = MultipleFileField(
        required=False,
        label="Anexos",
        widget=MultipleFileInput(attrs={"class": "form-control", "multiple": True}),
    )

    def clean(self):
        cleaned_data = super().clean()
        texto = (cleaned_data.get("texto_nota") or "").strip()
        anexos = cleaned_data.get("anexos") or []
        if not texto and not anexos:
            raise forms.ValidationError("Informe uma anotação ou envie ao menos um anexo.")
        return cleaned_data


class InteressadoSistemaForm(forms.Form):
    usuario = UsuarioDisplayChoiceField(
        queryset=User.objects.order_by("username"),
        required=False,
        label="Usuário existente",
        widget=UsuarioComEmailSelect(attrs={"class": "form-control"}),
    )
    tipo_interessado = forms.ChoiceField(
        choices=TipoInteressado.choices,
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Tipo",
    )
    nome_manual = forms.CharField(
        required=False,
        label="Nome manual",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    email_manual = forms.EmailField(
        required=False,
        label="E-mail manual",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "nome@dominio.gov.br"}),
    )

    def __init__(self, *args, sistema=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sistema = sistema
        self.fields["usuario"].queryset = User.objects.order_by("first_name", "username")

    def clean(self):
        cleaned_data = super().clean()
        usuario = cleaned_data.get("usuario")
        tipo_interessado = cleaned_data.get("tipo_interessado")
        nome_manual = (cleaned_data.get("nome_manual") or "").strip()
        email_manual = (cleaned_data.get("email_manual") or "").strip()
        if not usuario and not (nome_manual and email_manual):
            raise forms.ValidationError("Selecione um usuário existente ou informe nome e e-mail manualmente.")
        if self.sistema and usuario and tipo_interessado:
            if InteressadoSistema.objects.filter(
                sistema=self.sistema,
                usuario=usuario,
                tipo_interessado=tipo_interessado,
            ).exists():
                raise forms.ValidationError("Esse usuário já está vinculado a este sistema com o tipo informado.")
        if self.sistema and nome_manual and email_manual and tipo_interessado:
            if InteressadoSistemaManual.objects.filter(
                sistema=self.sistema,
                email__iexact=email_manual,
                tipo_interessado=tipo_interessado,
            ).exists():
                raise forms.ValidationError("Esse contato manual já está vinculado a este sistema com o tipo informado.")
        return cleaned_data

    def save(self, sistema, usuario_autor):
        tipo_interessado = self.cleaned_data["tipo_interessado"]
        usuario = self.cleaned_data.get("usuario")
        if usuario:
            nome = nome_usuario_exibicao(usuario)
            email = (usuario.email or "").strip()
            return InteressadoSistema.objects.create(
                sistema=sistema,
                usuario=usuario,
                tipo_interessado=tipo_interessado,
                nome_snapshot=nome or usuario.username,
                email_snapshot=email,
                criado_por=usuario_autor if getattr(usuario_autor, "is_authenticated", False) else None,
            )
        return InteressadoSistemaManual.objects.create(
            sistema=sistema,
            tipo_interessado=tipo_interessado,
            nome=(self.cleaned_data.get("nome_manual") or "").strip(),
            email=(self.cleaned_data.get("email_manual") or "").strip(),
            criado_por=usuario_autor if getattr(usuario_autor, "is_authenticated", False) else None,
        )


class SistemaFiltroForm(forms.Form):
    q = forms.CharField(required=False, label="Sistema", widget=forms.TextInput(attrs={"class": "form-control"}))
    etapa = forms.ChoiceField(required=False, choices=[("", "Todas as etapas")] + list(EtapaSistema.TipoEtapa.choices), widget=forms.Select(attrs={"class": "form-control"}))
    status = forms.ChoiceField(required=False, choices=[("", "Todos os status")] + list(EtapaSistema.Status.choices), widget=forms.Select(attrs={"class": "form-control"}))
    responsavel = UsuarioDisplayChoiceField(
        required=False,
        queryset=User.objects.none(),
        label="Responsável da última ação",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, responsaveis=None, **kwargs):
        super().__init__(*args, **kwargs)
        if responsaveis is None:
            responsaveis = User.objects.none()
        self.fields["responsavel"].queryset = responsaveis
