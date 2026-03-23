"""
Formulários do app `sala_situacao`.

Este módulo encapsula validações de entrada e transformações necessárias para
persistência segura das entidades de monitoramento (indicadores, processos,
entregas e ciclos de variáveis).

Integração com arquitetura Django:
- consumido por `views.py` em fluxos Create/Update;
- usa `models.py` para validar consistência de regras de negócio;
- prepara dados para templates de formulário (campos, widgets e mensagens).
"""

import re
import json

from django import forms
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from .models import (
    Entrega,
    IndicadorVariavelCicloMonitoramento,
    IndicadorCicloValor,
    IndicadorEstrategico,
    IndicadorVariavel,
    IndicadorTatico,
    NotaItem,
    NotaItemAnexo,
    Processo,
    nota_item_anexo_storage_ready,
)

_ENTREGA_MONITOR_RE = re.compile(r'^Registro de monitoramento "([^"]+)" - (\d{2})/(\d{4})(?: \(Inicial\))?$')
_PROCESSO_INDICADOR_RE = re.compile(
    r'^Monitoramento de "([^"]+)" do indicador(?: estratégico| tático)? "([^"]+)"$'
)
_FORMULA_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if data in self.empty_values:
            return []
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data]
        return [single_file_clean(data, initial)]


def _normalizar_unidade(unidade):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `unidade`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    base = re.sub(r"\s+", "", (unidade or "").strip()).casefold()
    if base in {"%", "percentual", "porcentagem"}:
        return "%"
    return base


def _validar_data_alvo_com_superiores(form, superiores, descricao_superior):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    data_alvo = form.cleaned_data.get("data_entrega_estipulada")
    if not data_alvo:
        return
    datas_superiores = [
        item.data_entrega_estipulada
        for item in superiores
        if getattr(item, "data_entrega_estipulada", None)
    ]
    if not datas_superiores:
        return
    prazo_limite = min(datas_superiores)
    if data_alvo > prazo_limite:
        form.add_error(
            "data_entrega_estipulada",
            (
                "A data-alvo deve ser igual ou anterior ao prazo do nível superior "
                f"({descricao_superior}: {prazo_limite.strftime('%d/%m/%Y')})."
            ),
        )


class BaseSalaSituacaoForm(forms.ModelForm):
    """Classe `BaseSalaSituacaoForm` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    data_entrega_estipulada = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"}),
    )
    marcadores_ids = forms.CharField(
        required=False,
        label="Marcadores",
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                field.widget.attrs.update({"class": "form-select"})
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({"class": "form-control", "rows": 4})
            else:
                field.widget.attrs.update({"class": "form-control"})

        instance = getattr(self, "instance", None)
        if (
            instance
            and getattr(instance, "pk", None)
            and "evolucao_manual" in self.fields
            and instance.tem_filhos_relacionados
        ):
            self.fields["evolucao_manual"].disabled = True
            self.fields["evolucao_manual"].help_text = (
                "Este item possui filhos relacionados. A evolução é calculada automaticamente."
            )

        if instance and getattr(instance, "pk", None):
            ids = [item.id for item in instance.marcadores_locais]
            self.fields["marcadores_ids"].initial = ",".join(str(item_id) for item_id in ids)

    def _parse_marcadores_ids(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        bruto = (self.cleaned_data.get("marcadores_ids") or "").strip()
        if not bruto:
            return []
        return [int(item.strip()) for item in bruto.split(",") if item.strip().isdigit()]

    def save(self, commit=True):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        obj = super().save(commit=commit)
        if commit and getattr(obj, "pk", None):
            obj.definir_marcadores_locais_por_ids(self._parse_marcadores_ids())
        return obj


class IndicadorReusoVariavelFormMixin:
    """Classe `IndicadorReusoVariavelFormMixin` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    def __init__(self, *args, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        if instance and getattr(instance, "pk", None):
            self.fields["variaveis_reuso_map"].initial = self._mapa_reuso_atual_json()

    def _nomes_variaveis_da_formula(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        formula = (self.data.get("formula_expressao") if self.is_bound else self.initial.get("formula_expressao"))
        if formula is None:
            formula = getattr(self.instance, "formula_expressao", "")
        nomes = sorted(set(_FORMULA_TOKEN_RE.findall((formula or "").strip())))
        return nomes

    def _parse_variaveis_reuso_map(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        bruto = (self.cleaned_data.get("variaveis_reuso_map") or "").strip()
        if not bruto:
            return {}
        try:
            payload = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Mapa de reuso inválido.") from exc
        if not isinstance(payload, dict):
            raise forms.ValidationError("Mapa de reuso inválido.")
        resultado = {}
        for nome, config in payload.items():
            if not isinstance(nome, str) or not isinstance(config, dict):
                continue
            modo = (config.get("modo") or "local").strip().lower()
            if modo not in {"local", "reuso"}:
                modo = "local"
            variavel_origem_id = config.get("variavel_origem_id")
            if variavel_origem_id is not None and str(variavel_origem_id).isdigit():
                variavel_origem_id = int(variavel_origem_id)
            else:
                variavel_origem_id = None
            periodicidade_monitoramento = (config.get("periodicidade_monitoramento") or "").strip().upper()
            periodicidades_validas = {item[0] for item in IndicadorEstrategico.PeriodicidadeMonitoramento.choices}
            if periodicidade_monitoramento not in periodicidades_validas:
                periodicidade_monitoramento = ""
            grupos_ids = config.get("grupos_monitoramento_ids")
            if isinstance(grupos_ids, list):
                grupos_ids = [int(item) for item in grupos_ids if str(item).isdigit()]
            else:
                grupos_ids = []
            resultado[nome] = {
                "modo": modo,
                "variavel_origem_id": variavel_origem_id,
                "periodicidade_monitoramento": periodicidade_monitoramento,
                "grupos_monitoramento_ids": grupos_ids,
            }
        return resultado

    def _mapa_reuso_atual_json(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        indicador = self.instance
        if not indicador or not getattr(indicador, "pk", None):
            return "{}"
        content_type = ContentType.objects.get_for_model(indicador.__class__)
        mapa = {}
        for variavel in IndicadorVariavel.objects.filter(content_type=content_type, object_id=indicador.pk):
            if variavel.origem_reaproveitada and variavel.variavel_origem_id:
                mapa[variavel.nome] = {
                    "modo": "reuso",
                    "variavel_origem_id": variavel.variavel_origem_id,
                    "periodicidade_monitoramento": variavel.periodicidade_monitoramento or "",
                    "grupos_monitoramento_ids": list(
                        variavel.grupos_monitoramento.values_list("id", flat=True)
                    ),
                }
            else:
                mapa[variavel.nome] = {
                    "modo": "local",
                    "periodicidade_monitoramento": variavel.periodicidade_monitoramento or "",
                    "grupos_monitoramento_ids": list(
                        variavel.grupos_monitoramento.values_list("id", flat=True)
                    ),
                }
        return json.dumps(mapa, ensure_ascii=True)

    def _validar_compatibilidade_variavel_reuso(self, variavel_destino, variavel_origem):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if (
            variavel_destino.tipo_numerico == IndicadorVariavel.TipoNumerico.INTEIRO
            and variavel_origem.tipo_numerico == IndicadorVariavel.TipoNumerico.DECIMAL
        ):
            raise forms.ValidationError(
                f"A variável '{variavel_destino.nome}' não suporta reuso DECIMAL -> INTEIRO automaticamente."
            )
        unidade_destino = _normalizar_unidade(variavel_destino.unidade_medida)
        unidade_origem = _normalizar_unidade(variavel_origem.unidade_medida)
        if unidade_destino != unidade_origem:
            raise forms.ValidationError(
                (
                    f"A variável '{variavel_destino.nome}' exige unidade '{variavel_destino.unidade_medida}', "
                    f"mas a origem usa '{variavel_origem.unidade_medida}'."
                )
            )

    def _aplicar_mapa_reuso(self, indicador, mapa_reuso):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if not indicador or not indicador.pk or not indicador.eh_indicador_matematico:
            return
        content_type = ContentType.objects.get_for_model(indicador.__class__)
        variaveis = {
            item.nome: item
            for item in IndicadorVariavel.objects.filter(content_type=content_type, object_id=indicador.pk)
        }
        for nome_variavel, variavel in variaveis.items():
            conf = mapa_reuso.get(nome_variavel) or {"modo": "local"}
            periodicidade_variavel = (conf.get("periodicidade_monitoramento") or "").strip().upper()
            if periodicidade_variavel not in {item[0] for item in indicador.PeriodicidadeMonitoramento.choices}:
                periodicidade_variavel = ""
            grupos_monitoramento_ids = [
                int(item)
                for item in (conf.get("grupos_monitoramento_ids") or [])
                if str(item).isdigit()
            ]
            grupos_validos_ids = set(
                Group.objects.filter(id__in=grupos_monitoramento_ids).values_list("id", flat=True)
            )
            if conf.get("modo") != "reuso":
                campos_update = []
                if variavel.origem_reaproveitada or variavel.variavel_origem_id:
                    variavel.origem_reaproveitada = False
                    variavel.variavel_origem = None
                    campos_update.extend(["origem_reaproveitada", "variavel_origem"])
                if variavel.periodicidade_monitoramento != periodicidade_variavel:
                    variavel.periodicidade_monitoramento = periodicidade_variavel
                    campos_update.append("periodicidade_monitoramento")
                if campos_update:
                    variavel.save(update_fields=[*campos_update, "atualizado_em"])
                variavel.grupos_monitoramento.set(grupos_validos_ids)
                continue

            origem_id = conf.get("variavel_origem_id")
            variavel_origem = IndicadorVariavel.objects.filter(pk=origem_id).select_related("content_type").first()
            if not variavel_origem:
                raise forms.ValidationError(f"Origem inválida para a variável '{nome_variavel}'.")
            self._validar_compatibilidade_variavel_reuso(variavel, variavel_origem)
            variavel.origem_reaproveitada = True
            variavel.variavel_origem = variavel_origem
            variavel.periodicidade_monitoramento = periodicidade_variavel
            variavel.save(
                update_fields=[
                    "origem_reaproveitada",
                    "variavel_origem",
                    "periodicidade_monitoramento",
                    "atualizado_em",
                ]
            )
            variavel.grupos_monitoramento.set(grupos_validos_ids)

    def clean(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        cleaned_data = super().clean()
        if cleaned_data.get("tipo_indicador") not in {
            IndicadorEstrategico.TipoIndicador.MATEMATICO,
            IndicadorEstrategico.TipoIndicador.MATEMATICO_ACUMULATIVO,
        }:
            cleaned_data["variaveis_reuso_map"] = "{}"
            return cleaned_data

        nomes_formula = self._nomes_variaveis_da_formula()
        try:
            mapa = self._parse_variaveis_reuso_map()
        except forms.ValidationError as exc:
            self.add_error("variaveis_reuso_map", exc)
            return cleaned_data
        for nome_variavel in nomes_formula:
            conf = mapa.get(nome_variavel) or {"modo": "local"}
            periodicidade_variavel = (conf.get("periodicidade_monitoramento") or "").strip().upper()
            grupos_monitoramento_ids = conf.get("grupos_monitoramento_ids")
            if grupos_monitoramento_ids and not isinstance(grupos_monitoramento_ids, list):
                self.add_error(
                    "variaveis_reuso_map",
                    f"Lista de grupos inválida para '{nome_variavel}'.",
                )
                grupos_monitoramento_ids = []
            grupos_ids_validos = [
                int(item)
                for item in (grupos_monitoramento_ids or [])
                if str(item).isdigit()
            ]
            conf["grupos_monitoramento_ids"] = grupos_ids_validos
            if not periodicidade_variavel:
                self.add_error(
                    "variaveis_reuso_map",
                    f"Defina a periodicidade da variável '{nome_variavel}'.",
                )
            if conf.get("modo") != "reuso":
                continue
            origem_id = conf.get("variavel_origem_id")
            if not origem_id:
                self.add_error(
                    "variaveis_reuso_map",
                    f"Selecione a variável de origem para '{nome_variavel}'.",
                )
                continue
            variavel_origem = IndicadorVariavel.objects.filter(pk=origem_id).first()
            if not variavel_origem:
                self.add_error(
                    "variaveis_reuso_map",
                    f"Origem inválida para '{nome_variavel}'.",
                )
                continue
            unidade_destino = cleaned_data.get("meta_unidade_medida") or "%"
            tipo_destino = IndicadorVariavel.TipoNumerico.DECIMAL
            if self.instance and getattr(self.instance, "pk", None):
                content_type = ContentType.objects.get_for_model(self.instance.__class__)
                variavel_destino_existente = IndicadorVariavel.objects.filter(
                    content_type=content_type,
                    object_id=self.instance.pk,
                    nome=nome_variavel,
                ).first()
                if variavel_destino_existente:
                    unidade_destino = variavel_destino_existente.unidade_medida
                    tipo_destino = variavel_destino_existente.tipo_numerico
            destino_stub = IndicadorVariavel(
                nome=nome_variavel,
                unidade_medida=unidade_destino,
                tipo_numerico=tipo_destino,
            )
            try:
                self._validar_compatibilidade_variavel_reuso(destino_stub, variavel_origem)
            except forms.ValidationError as exc:
                self.add_error("variaveis_reuso_map", exc)
        cleaned_data["variaveis_reuso_map"] = json.dumps(mapa, ensure_ascii=True)
        return cleaned_data

    def save(self, commit=True):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        with transaction.atomic():
            indicador = super().save(commit=commit)
            if commit and indicador.eh_indicador_matematico:
                indicador.sincronizar_variaveis_da_formula()
                mapa = json.loads(self.cleaned_data.get("variaveis_reuso_map") or "{}")
                self._aplicar_mapa_reuso(indicador, mapa)
            return indicador


class IndicadorEstrategicoForm(IndicadorReusoVariavelFormMixin, BaseSalaSituacaoForm):
    """Classe `IndicadorEstrategicoForm` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    variaveis_reuso_map = forms.CharField(
        required=False,
        label="Mapeamento das variáveis",
        widget=forms.HiddenInput(),
    )
    class Meta:
        """Classe `IndicadorEstrategicoForm.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        model = IndicadorEstrategico
        fields = [
            "tipo_indicador",
            "nome",
            "descricao",
            "variaveis_reuso_map",
            "marcadores_ids",
            "meta_valor",
            "meta_unidade_medida",
            "formula_expressao",
            "data_entrega_estipulada",
            "evolucao_manual",
        ]

    def clean(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        cleaned_data = super().clean()
        if cleaned_data.get("tipo_indicador") in {
            IndicadorEstrategico.TipoIndicador.MATEMATICO,
            IndicadorEstrategico.TipoIndicador.MATEMATICO_ACUMULATIVO,
        }:
            cleaned_data["evolucao_manual"] = 0
        return cleaned_data


class IndicadorTaticoForm(IndicadorReusoVariavelFormMixin, BaseSalaSituacaoForm):
    """Classe `IndicadorTaticoForm` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    variaveis_reuso_map = forms.CharField(
        required=False,
        label="Mapeamento das variáveis",
        widget=forms.HiddenInput(),
    )
    indicadores_estrategicos = forms.ModelMultipleChoiceField(
        queryset=IndicadorEstrategico.objects.all().order_by("nome"),
        required=False,
        label="Indicadores vinculados",
        help_text="Opcional: selecione um ou mais indicadores.",
    )

    class Meta:
        """Classe `IndicadorTaticoForm.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        model = IndicadorTatico
        fields = [
            "indicadores_estrategicos",
            "tipo_indicador",
            "nome",
            "descricao",
            "variaveis_reuso_map",
            "marcadores_ids",
            "meta_valor",
            "meta_unidade_medida",
            "formula_expressao",
            "data_entrega_estipulada",
            "evolucao_manual",
        ]

    def clean(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        cleaned_data = super().clean()
        indicadores_estrategicos = cleaned_data.get("indicadores_estrategicos")
        if indicadores_estrategicos:
            _validar_data_alvo_com_superiores(
                self,
                indicadores_estrategicos,
                "Indicador",
            )
        if cleaned_data.get("tipo_indicador") in {
            IndicadorTatico.TipoIndicador.MATEMATICO,
            IndicadorTatico.TipoIndicador.MATEMATICO_ACUMULATIVO,
        }:
            cleaned_data["evolucao_manual"] = 0
        return cleaned_data

class ProcessoForm(BaseSalaSituacaoForm):
    """Classe `ProcessoForm` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    indicadores_estrategicos = forms.ModelMultipleChoiceField(
        queryset=IndicadorEstrategico.objects.filter(
            tipo_indicador=IndicadorEstrategico.TipoIndicador.PROCESSUAL
        ).order_by("nome"),
        required=True,
        label="Indicadores estratégicos processuais",
        help_text="Selecione um ou mais indicadores processuais.",
    )
    class Meta:
        """Classe `ProcessoForm.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        model = Processo
        fields = [
            "indicadores_estrategicos",
            "nome",
            "descricao",
            "marcadores_ids",
            "data_entrega_estipulada",
            "evolucao_manual",
        ]

    def clean(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        cleaned_data = super().clean()
        indicadores_estrategicos = cleaned_data.get("indicadores_estrategicos")
        if indicadores_estrategicos:
            _validar_data_alvo_com_superiores(
                self,
                indicadores_estrategicos,
                "Indicador",
            )
        return cleaned_data


class EntregaForm(BaseSalaSituacaoForm):
    """Classe `EntregaForm` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    processos = forms.ModelMultipleChoiceField(
        queryset=Processo.objects.all().order_by("nome"),
        required=True,
        label="Indicador",
        help_text="Selecione um ou mais itens vinculados.",
    )

    class Meta:
        """Classe `EntregaForm.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        model = Entrega
        fields = [
            "nome",
            "descricao",
            "processos",
            "marcadores_ids",
            "data_entrega_estipulada",
            "evolucao_manual",
            "valor_monitoramento",
        ]

    def __init__(self, *args, usuario=None, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.usuario = usuario
        super().__init__(*args, **kwargs)
        self.fields["marcadores_ids"].label = "Grupo"
        self.order_fields(
            [
                "nome",
                "descricao",
                "processos",
                "marcadores_ids",
                "data_entrega_estipulada",
                "evolucao_manual",
                "valor_monitoramento",
            ]
        )
        instance = getattr(self, "instance", None)
        if instance and instance.pk and not instance.eh_entrega_monitoramento:
            self._tentar_vincular_monitoramento(instance)
        if instance and instance.pk and instance.eh_entrega_monitoramento:
            self.fields.pop("evolucao_manual", None)
        if not (instance and instance.pk and instance.eh_entrega_monitoramento):
            self.fields.pop("valor_monitoramento", None)
        else:
            variavel = instance.variavel_monitoramento
            if variavel:
                self.fields["valor_monitoramento"].label = (
                    f'Valor da variável "{variavel.nome}"'
                )
            self.fields["valor_monitoramento"].required = False

    def _tentar_vincular_monitoramento(self, entrega):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        match_entrega = _ENTREGA_MONITOR_RE.match((entrega.nome or "").strip())
        if not match_entrega:
            return
        nome_variavel = match_entrega.group(1).strip()
        mes_ciclo = int(match_entrega.group(2))
        ano_ciclo = int(match_entrega.group(3))

        indicador_nomes = []
        for processo in entrega.processos.all():
            match_proc = _PROCESSO_INDICADOR_RE.match((processo.nome or "").strip())
            if match_proc:
                indicador_nomes.append(match_proc.group(2).strip())

        variavel_qs = IndicadorVariavel.objects.filter(nome=nome_variavel)
        if indicador_nomes:
            indicadores_ids = list(
                IndicadorEstrategico.objects.filter(nome__in=indicador_nomes).values_list("id", flat=True)
            )
            ct_indicador_estrategico = ContentType.objects.get_for_model(IndicadorEstrategico)
            variavel_qs = variavel_qs.filter(content_type=ct_indicador_estrategico, object_id__in=indicadores_ids)

        candidatas = []
        for variavel in variavel_qs:
            ciclo = IndicadorVariavelCicloMonitoramento.objects.filter(
                variavel=variavel,
                periodo_inicio__month=mes_ciclo,
                periodo_inicio__year=ano_ciclo,
            ).first()
            if ciclo:
                candidatas.append((variavel, ciclo))

        if len(candidatas) != 1:
            return
        variavel, ciclo = candidatas[0]
        entrega.variavel_monitoramento = variavel
        entrega.ciclo_monitoramento = ciclo
        entrega.save(update_fields=["variavel_monitoramento", "ciclo_monitoramento", "atualizado_em"])

    def clean(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        cleaned_data = super().clean()
        processos = cleaned_data.get("processos")
        if processos:
            _validar_data_alvo_com_superiores(
                self,
                processos,
                "Processo",
            )
        entrega = getattr(self, "instance", None)
        if (
            entrega
            and getattr(entrega, "pk", None)
            and entrega.eh_entrega_monitoramento
            and entrega.ciclo_monitoramento_id
            and entrega.ciclo_monitoramento.eh_inicial
            and cleaned_data.get("valor_monitoramento") is None
        ):
            self.add_error(
                "valor_monitoramento",
                "O ciclo inicial exige valor informado para viabilizar o cálculo do indicador.",
            )
        return cleaned_data

    def save(self, commit=True):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        entrega = super().save(commit=commit)
        if entrega and entrega.pk and not entrega.eh_entrega_monitoramento:
            self._tentar_vincular_monitoramento(entrega)
        if not entrega.eh_entrega_monitoramento:
            return entrega

        valor = self.cleaned_data.get("valor_monitoramento")
        if valor is None:
            return entrega

        if entrega.valor_monitoramento != valor or entrega.evolucao_manual != 100:
            entrega.valor_monitoramento = valor
            entrega.evolucao_manual = 100
            entrega.save(update_fields=["valor_monitoramento", "evolucao_manual", "atualizado_em"])

        IndicadorCicloValor.objects.update_or_create(
            ciclo=entrega.ciclo_monitoramento,
            variavel=entrega.variavel_monitoramento,
            defaults={
                "valor": valor,
                "atualizado_por": self.usuario if getattr(self.usuario, "is_authenticated", False) else None,
            },
        )
        return entrega


class MonitoramentoEntregaForm(forms.ModelForm):
    """Classe `MonitoramentoEntregaForm` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    class Meta:
        """Classe `MonitoramentoEntregaForm.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        model = Entrega
        fields = ["valor_monitoramento", "evidencia_monitoramento"]

    def __init__(self, *args, usuario=None, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.usuario = usuario
        super().__init__(*args, **kwargs)
        self.fields["valor_monitoramento"].required = False
        self.fields["evidencia_monitoramento"].required = False
        if self.instance and self.instance.variavel_monitoramento_id:
            self.fields["valor_monitoramento"].label = (
                f'Valor da variável "{self.instance.variavel_monitoramento.nome}"'
            )

    def clean(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        cleaned_data = super().clean()
        entrega = self.instance
        if not (entrega and entrega.pk and entrega.eh_entrega_monitoramento):
            raise forms.ValidationError("Ação de monitoramento disponível apenas para entregas de monitoramento.")
        valor = cleaned_data.get("valor_monitoramento")
        if entrega.ciclo_monitoramento_id and entrega.ciclo_monitoramento and entrega.ciclo_monitoramento.eh_inicial:
            if valor is None:
                self.add_error(
                    "valor_monitoramento",
                    "O ciclo inicial exige valor informado para viabilizar o cálculo do indicador.",
                )
        return cleaned_data

    def save(self, commit=True):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        entrega = super().save(commit=False)
        valor = self.cleaned_data.get("valor_monitoramento")
        if valor is not None:
            entrega.valor_monitoramento = valor
            entrega.evolucao_manual = 100
        if getattr(self.usuario, "is_authenticated", False):
            entrega.monitorado_por = self.usuario
        entrega.monitorado_em = timezone.now()
        if commit:
            entrega.save(
                update_fields=[
                    "valor_monitoramento",
                    "evidencia_monitoramento",
                    "evolucao_manual",
                    "monitorado_por",
                    "monitorado_em",
                    "atualizado_em",
                ]
            )
        if valor is not None:
            IndicadorCicloValor.objects.update_or_create(
                ciclo=entrega.ciclo_monitoramento,
                variavel=entrega.variavel_monitoramento,
                defaults={
                    "valor": valor,
                    "atualizado_por": self.usuario if getattr(self.usuario, "is_authenticated", False) else None,
                },
            )
        return entrega


class NotaItemForm(forms.ModelForm):
    """Classe `NotaItemForm` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    anexos = MultipleFileField(
        required=False,
        widget=MultipleFileInput(
            attrs={
                "class": "form-control",
                "multiple": True,
            }
        ),
        label="Anexos",
    )

    class Meta:
        """Classe `NotaItemForm.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        model = NotaItem
        fields = ["texto"]
        widgets = {
            "texto": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                }
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not nota_item_anexo_storage_ready():
            self.fields.pop("anexos", None)

    def save_anexos(self, nota, arquivos):
        if not nota or not getattr(nota, "pk", None) or not nota_item_anexo_storage_ready():
            return
        for arquivo in arquivos or []:
            NotaItemAnexo.objects.create(
                nota=nota,
                arquivo=arquivo,
                nome_original=getattr(arquivo, "name", "") or "",
            )


class IndicadorVariavelForm(forms.ModelForm):
    """Classe `IndicadorVariavelForm` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    class Meta:
        """Classe `IndicadorVariavelForm.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        model = IndicadorVariavel
        fields = ["nome", "descricao", "tipo_numerico", "unidade_medida", "periodicidade_monitoramento", "ordem"]
