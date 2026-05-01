from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model

from usuarios.utils import usuarios_visiveis

from .models import (
    EntregaSistema,
    EtapaProcessoRequisito,
    EtapaSistema,
    InteressadoSistema,
    InteressadoSistemaManual,
    ProcessoRequisito,
    Sistema,
    TipoInteressado,
)
from .utils import nome_usuario_exibicao

ETAPAS_SEM_DATA = {
    EtapaSistema.TipoEtapa.REQUISITOS,
    EtapaSistema.TipoEtapa.HOMOLOGACAO_REQUISITOS,
}

ETAPAS_FINAIS_COM_DATA_OBRIGATORIA = {
    EtapaSistema.TipoEtapa.DESENVOLVIMENTO,
    EtapaSistema.TipoEtapa.HOMOLOGACAO_DESENVOLVIMENTO,
    EtapaSistema.TipoEtapa.PRODUCAO,
}


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


class ProcessoRequisitoForm(forms.ModelForm):
    class Meta:
        model = ProcessoRequisito
        fields = ["titulo", "descricao"]
        widgets = {
            "titulo": forms.TextInput(attrs={"class": "form-control"}),
            "descricao": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class EtapaProcessoRequisitoAtualizacaoForm(forms.ModelForm):
    justificativa_status = forms.CharField(
        required=False,
        label="Nota / acompanhamento",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )
    anexos = MultipleFileField(
        required=False,
        label="Anexos",
        widget=MultipleFileInput(attrs={"class": "form-control", "multiple": True}),
    )

    class Meta:
        model = EtapaProcessoRequisito
        fields = ["status"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and getattr(self.instance, "pk", None):
            choices = [(self.instance.status, self.instance.get_status_display())]
            if self.instance.dependencias_concluidas:
                choices.extend(
                    [
                        (status, EtapaProcessoRequisito.Status(status).label)
                        for status in self.instance.proximos_status_permitidos
                    ]
                )
            self.fields["status"].choices = choices
            self.initial.setdefault("status", self.instance.status)
            if not self.instance.dependencias_concluidas and self.instance.mensagem_bloqueio_dependencia:
                self.fields["status"].help_text = self.instance.mensagem_bloqueio_dependencia
            elif not self.instance.proximos_status_permitidos:
                self.fields["status"].help_text = "Esta etapa já está em um status final e não aceita novas mudanças."

    def clean(self):
        cleaned_data = super().clean()
        status_novo = cleaned_data.get("status")
        justificativa = (cleaned_data.get("justificativa_status") or "").strip()
        anexos = cleaned_data.get("anexos") or []
        if self.instance and getattr(self.instance, "pk", None):
            if status_novo and status_novo != self.instance.status:
                if not self.instance.dependencias_concluidas:
                    self.add_error("status", self.instance.mensagem_bloqueio_dependencia)
                elif status_novo not in self.instance.proximos_status_permitidos:
                    self.add_error("status", "Transição de status inválida para esta etapa.")
            if status_novo and status_novo != self.instance.status and not justificativa:
                self.add_error("justificativa_status", "Informe a nota/acompanhamento ao alterar o status.")
            if (
                self.instance.status != EtapaProcessoRequisito.Status.VALIDACAO
                and status_novo == EtapaProcessoRequisito.Status.VALIDACAO
                and not anexos
            ):
                self.add_error("anexos", "Ao enviar para Validação, anexe obrigatoriamente um arquivo.")
        return cleaned_data


class GerarProcessoTransformacaoForm(forms.Form):
    acao = forms.ChoiceField(
        choices=[
            ("ciclo", "Gerar ciclo no sistema atual"),
            ("sistema", "Gerar novo sistema"),
        ],
        widget=forms.RadioSelect,
        label="Ação",
    )


class GerarNovoSistemaAPartirProcessosForm(forms.ModelForm):
    class Meta:
        model = Sistema
        fields = ["nome", "descricao", "url_homologacao", "url_producao"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "descricao": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "url_homologacao": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://..."}),
            "url_producao": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://..."}),
        }


class EtapaSistemaAtualizacaoForm(forms.ModelForm):
    data_etapa = forms.DateField(
        required=False,
        label="Data da etapa",
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"class": "form-control", "type": "date"}),
    )
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
            "status": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_etapa"].input_formats = ["%Y-%m-%d"]
        self.fields["data_etapa"].help_text = "Preencha a data planejada da etapa. Em rascunho, ela pode ficar em branco até a publicação do ciclo."
        if self.instance and getattr(self.instance, "pk", None):
            if self.instance.eh_homologacao:
                status_choices = [
                    (EtapaSistema.Status.PENDENTE, EtapaSistema.Status.PENDENTE.label),
                    (EtapaSistema.Status.EM_ANDAMENTO, EtapaSistema.Status.EM_ANDAMENTO.label),
                    (EtapaSistema.Status.APROVADO, EtapaSistema.Status.APROVADO.label),
                    (EtapaSistema.Status.REPROVADO, EtapaSistema.Status.REPROVADO.label),
                ]
            else:
                status_choices = [
                    (EtapaSistema.Status.PENDENTE, EtapaSistema.Status.PENDENTE.label),
                    (EtapaSistema.Status.EM_ANDAMENTO, EtapaSistema.Status.EM_ANDAMENTO.label),
                    (EtapaSistema.Status.ENTREGUE, EtapaSistema.Status.ENTREGUE.label),
                ]
            if self.instance.status and self.instance.status not in {choice[0] for choice in status_choices}:
                status_choices.append((self.instance.status, self.instance.get_status_display()))
            self.fields["status"].choices = status_choices
            self.initial.setdefault("data_etapa", self.instance.data_etapa)
            self.initial.setdefault("status", self.instance.status)
            if self.instance.tipo_etapa == EtapaSistema.TipoEtapa.REQUISITOS:
                self.fields["anexos"].label = "Anexo dos requisitos"
                self.fields["anexos"].help_text = "Ao concluir Requisitos, anexe obrigatoriamente o documento de requisitos."
            if self.instance.tipo_etapa in ETAPAS_SEM_DATA:
                self.fields["data_etapa"].help_text = "Esta etapa não utiliza data."

    def clean(self):
        cleaned_data = super().clean()
        status_novo = cleaned_data.get("status")
        justificativa = (cleaned_data.get("justificativa_status") or "").strip()
        anexos = cleaned_data.get("anexos") or []
        if self.instance and getattr(self.instance, "pk", None) and self.instance.tipo_etapa in ETAPAS_SEM_DATA:
            cleaned_data["data_etapa"] = None
        if self.instance and getattr(self.instance, "pk", None):
            if status_novo and status_novo != self.instance.status and not justificativa:
                self.add_error("justificativa_status", "Informe a justificativa ao alterar o status.")
            if (
                self.instance.entrega.status == EntregaSistema.Status.PUBLICADO
                and self.instance.tipo_etapa not in ETAPAS_SEM_DATA
                and not cleaned_data.get("data_etapa")
            ):
                self.add_error("data_etapa", "Informe a data da etapa.")
            if self.instance.tipo_etapa in ETAPAS_FINAIS_COM_DATA_OBRIGATORIA:
                etapas = {etapa.tipo_etapa: etapa for etapa in self.instance.entrega.etapas.all()}
                faltam_datas = []
                for tipo_etapa in ETAPAS_FINAIS_COM_DATA_OBRIGATORIA:
                    etapa = etapas.get(tipo_etapa)
                    data_referencia = cleaned_data.get("data_etapa") if tipo_etapa == self.instance.tipo_etapa else (etapa.data_etapa if etapa else None)
                    if not data_referencia:
                        faltam_datas.append(etapa.get_tipo_etapa_display() if etapa is not None else tipo_etapa)
                if faltam_datas:
                    self.add_error(
                        "data_etapa",
                        "Defina a data de Desenvolvimento, Homologação do Desenvolvimento e Produção antes de atualizar essas etapas.",
                    )
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


class NotaSistemaForm(forms.Form):
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
        queryset=usuarios_visiveis(User.objects.order_by("username")),
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
        self.fields["usuario"].queryset = usuarios_visiveis(User.objects.order_by("first_name", "username"))

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
