"""
Formulários do app `ramais`.

Este módulo define a camada de entrada/validação de dados para operações de
CRUD de `PessoaRamal`, controlando widgets e regras de edição por perfil.
"""
from django import forms

from usuarios.permissions import ADMIN_GROUP_NAME

from .models import PessoaRamal


class PessoaRamalForm(forms.ModelForm):
    """
    Formulário principal de criação/edição de ramais.

    Papel arquitetural:
    - Traduz campos do model para inputs HTML.
    - Aplica restrições de edição em tempo de execução conforme permissões.
    """
    class Meta:
        model = PessoaRamal
        fields = [
            "usuario",
            "nome",
            "cargo",
            "setor",
            "ramal",
            "email",
            "bio",
            "foto",
            "superior",
            "jornada_horas_semanais",
            "horario_trabalho_inicio",
            "horario_trabalho_fim",
            "intervalo_inicio",
            "intervalo_fim",
            "rg",
            "regime_plantao",
            "horario_estudante",
        ]
        widgets = {
            # Inputs de horário no formato nativo do navegador.
            "horario_trabalho_inicio": forms.TimeInput(attrs={"type": "time"}),
            "horario_trabalho_fim": forms.TimeInput(attrs={"type": "time"}),
            "intervalo_inicio": forms.TimeInput(attrs={"type": "time"}),
            "intervalo_fim": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        """
        Inicializa o formulário aplicando política dinâmica de acesso a campos.

        Parâmetros:
            *args: argumentos posicionais padrão de formulário.
            user: usuário da requisição, usado para autorização de campos.
            **kwargs: argumentos nomeados padrão de formulário.

        Regras de negócio:
        - Usuários sem privilégio de alteração global não podem trocar vínculo
          de `usuario`, `nome` e `superior`.
        - Campos funcionais avançados ficam editáveis apenas para perfis
          administrativos/RH definidos por permissões específicas.
        """
        super().__init__(*args, **kwargs)
        try:
            from usuarios.models import SetorNode

            setor_names = list(
                SetorNode.objects.select_related("group")
                .filter(ativo=True)
                .exclude(group__name__iexact=ADMIN_GROUP_NAME)
                .order_by("group__name")
                .values_list("group__name", flat=True)
            )
            setor_atual = (self.instance.setor or "").strip() if self.instance and self.instance.pk else ""
            if setor_atual and setor_atual not in setor_names:
                setor_names.append(setor_atual)
            self.fields["setor"] = forms.ChoiceField(
                choices=[("", "Selecione um setor")] + [(name, name) for name in setor_names],
                required=True,
                widget=forms.Select(attrs={"class": "form-control"}),
            )
        except Exception:
            pass
        if "setor" in self.fields:
            self.fields["setor"].required = True
            # Evita seleção automática no primeiro acesso/edição.
            if not self.is_bound:
                self.fields["setor"].initial = ""
        if user and not (user.is_staff or user.has_perm("ramais.change_pessoaramal")):
            self.fields.pop("usuario", None)
            self.fields.pop("nome", None)
            self.fields.pop("superior", None)
        # RG pode ser editado pelo proprio usuario.
        # Dados funcionais avancados ficam restritos ao RH/admin.
        if user and not (
            user.is_superuser
            or user.has_perm("folha_ponto.change_feriado")
            or user.has_perm("folha_ponto.change_feriasservidor")
        ):
            # Em vez de remover campos funcionais, eles são mantidos visíveis e
            # desabilitados para transparência do dado ao usuário comum.
            for field_name in [
                "jornada_horas_semanais",
                "horario_trabalho_inicio",
                "horario_trabalho_fim",
                "intervalo_inicio",
                "intervalo_fim",
                "regime_plantao",
                "horario_estudante",
            ]:
                if field_name in self.fields:
                    self.fields[field_name].disabled = True

    def clean_setor(self):
        """Exige escolha explícita de setor no cadastro/edição."""

        setor = (self.cleaned_data.get("setor") or "").strip()
        if not setor:
            raise forms.ValidationError("Selecione um setor.")
        return setor

    def clean_foto(self):
        """Exige foto no cadastro e para perfis que ainda não possuem imagem."""

        foto = self.cleaned_data.get("foto")
        if foto is not None:
            return foto

        foto_atual = getattr(getattr(self, "instance", None), "foto", None)
        if foto_atual:
            return foto_atual
        raise forms.ValidationError("A foto é obrigatória.")
