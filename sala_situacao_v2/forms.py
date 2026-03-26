import json
import re
from functools import lru_cache

from django import forms
from django.contrib.auth.models import Group
from django.db import connection, transaction
from django.utils import timezone

from .models import Entrega, Indicador, IndicadorCicloValor, Processo

_FORMULA_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PERIODICIDADES_SEM_DIA_REFERENCIA = {"DIARIO", "SEMANAL", "QUINZENAL"}


@lru_cache(maxsize=1)
def _db_tem_dia_referencia_monitoramento():
    table_name = "sala_situacao_v2_indicadorvariavel"
    column_name = "dia_referencia_monitoramento"
    with connection.cursor() as cursor:
        descricao = connection.introspection.get_table_description(cursor, table_name)
    return any((col.name if hasattr(col, "name") else col[0]) == column_name for col in descricao)


def _validar_data_alvo_com_superiores(form, superiores, descricao_superior):
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
                "A data de entrega estipulada deve ser igual ou anterior ao prazo do nível superior "
                f"({descricao_superior}: {prazo_limite.strftime('%d/%m/%Y')})."
            ),
        )


class BaseV2Form(forms.ModelForm):
    class Meta:
        fields = (
            "nome",
            "descricao",
            "data_entrega_estipulada",
            "evolucao_manual",
            "grupos_responsaveis",
        )

    def __init__(self, *args, **kwargs):
        writable_group_ids = kwargs.pop("writable_group_ids", None)
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        if "data_entrega_estipulada" in self.fields:
            existing_attrs = dict(getattr(self.fields["data_entrega_estipulada"].widget, "attrs", {}))
            existing_attrs.update(
                {
                    "type": "date",
                    "class": "form-control",
                    "autocomplete": "off",
                }
            )
            self.fields["data_entrega_estipulada"].widget = forms.DateInput(
                format="%Y-%m-%d",
                attrs=existing_attrs,
            )
        if (
            instance
            and getattr(instance, "pk", None)
            and getattr(instance, "tem_filhos_relacionados", False)
            and "evolucao_manual" in self.fields
        ):
            self.fields.pop("evolucao_manual")
        if "nome" in self.fields:
            self.fields["nome"].required = True
        if "descricao" in self.fields:
            self.fields["descricao"].required = True
        if "data_entrega_estipulada" in self.fields:
            self.fields["data_entrega_estipulada"].required = True
        if "evolucao_manual" in self.fields:
            self.fields["evolucao_manual"].required = True
        if "grupos_responsaveis" in self.fields:
            qs = Group.objects.order_by("name")
            if writable_group_ids is not None:
                qs = qs.filter(id__in=writable_group_ids)
            self.fields["grupos_responsaveis"].queryset = qs
            self.fields["grupos_responsaveis"].required = True


class IndicadorForm(BaseV2Form):
    variaveis_config_map = forms.CharField(
        required=False,
        label="Configuracao das variaveis",
        widget=forms.HiddenInput(),
    )

    class Meta(BaseV2Form.Meta):
        model = Indicador
        fields = (
            "nome",
            "descricao",
            "grupos_responsaveis",
            "tipo_indicador",
            "formula_expressao",
            "data_entrega_estipulada",
            "evolucao_manual",
            "variaveis_config_map",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grupos_responsaveis"].label = "Setores responsáveis"
        self.fields["tipo_indicador"].label = "Tipo"
        self.fields["formula_expressao"].help_text = (
            "Para indicadores matematicos, use sempre o formato percentual (x/y)*100. "
            "Exemplos: (qtdd_de_familias/meta_de_familias)*100 ou "
            "(total_de_refeicoes/meta_de_refeicoes)*100."
        )
        self.fields["tipo_indicador"].choices = [
            choice
            for choice in self.fields["tipo_indicador"].choices
            if choice[0] != Indicador.TipoIndicador.MATEMATICO_ACUMULATIVO
        ]
        if self.instance and getattr(self.instance, "pk", None):
            mapa = {}
            for variavel in self.instance.variaveis.prefetch_related("grupos_monitoramento").all():
                mapa[variavel.nome] = {
                    "periodicidade_monitoramento": variavel.periodicidade_monitoramento,
                    "dia_referencia_monitoramento": variavel.dia_referencia_monitoramento,
                    "grupos_monitoramento_ids": list(variavel.grupos_monitoramento.values_list("id", flat=True)),
                }
            self.fields["variaveis_config_map"].initial = json.dumps(mapa, ensure_ascii=True)

    def _nomes_variaveis_da_formula(self):
        formula = self.cleaned_data.get("formula_expressao") or self.data.get("formula_expressao") or ""
        return sorted(set(_FORMULA_TOKEN_RE.findall((formula or "").strip())))

    def _parse_variaveis_config_map(self):
        bruto = (self.cleaned_data.get("variaveis_config_map") or self.data.get("variaveis_config_map") or "").strip()
        if not bruto:
            return {}
        try:
            valor = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Configuracao de variaveis invalida.") from exc
        if not isinstance(valor, dict):
            raise forms.ValidationError("Configuracao de variaveis invalida.")
        return valor

    def clean(self):
        cleaned_data = super().clean()
        tipo_indicador = cleaned_data.get("tipo_indicador")
        if tipo_indicador == Indicador.TipoIndicador.MATEMATICO_ACUMULATIVO:
            self.add_error("tipo_indicador", "O tipo Matematico Acumulativo esta desativado.")
            return cleaned_data
        if tipo_indicador not in {
            Indicador.TipoIndicador.MATEMATICO,
        }:
            cleaned_data["variaveis_config_map"] = "{}"
            return cleaned_data

        if not _db_tem_dia_referencia_monitoramento():
            self.add_error(
                "variaveis_config_map",
                (
                    "O monitoramento por variaveis ainda nao esta disponivel neste ambiente. "
                    "Aplique a migration pendente de sala_situacao_v2 e tente novamente."
                ),
            )
            return cleaned_data

        formula = cleaned_data.get("formula_expressao")
        if not formula:
            self.add_error("formula_expressao", "Formula e obrigatoria para indicador matematico.")
            return cleaned_data

        nomes_formula = self._nomes_variaveis_da_formula()
        try:
            mapa = self._parse_variaveis_config_map()
        except forms.ValidationError as exc:
            self.add_error("variaveis_config_map", exc)
            return cleaned_data

        periodicidades_validas = {item[0] for item in Indicador.PeriodicidadeMonitoramento.choices}
        for nome_variavel in nomes_formula:
            conf = mapa.get(nome_variavel) or {}
            periodicidade = (conf.get("periodicidade_monitoramento") or "").strip().upper()
            dia_referencia = conf.get("dia_referencia_monitoramento")
            grupos_ids = [
                int(item)
                for item in (conf.get("grupos_monitoramento_ids") or [])
                if str(item).isdigit()
            ]
            dia_referencia_int = int(dia_referencia) if str(dia_referencia).isdigit() else None
            conf["periodicidade_monitoramento"] = periodicidade
            if periodicidade in _PERIODICIDADES_SEM_DIA_REFERENCIA:
                conf["dia_referencia_monitoramento"] = None
            else:
                conf["dia_referencia_monitoramento"] = dia_referencia_int
            conf["grupos_monitoramento_ids"] = grupos_ids
            if periodicidade not in periodicidades_validas:
                self.add_error("variaveis_config_map", f"Defina a periodicidade da variavel '{nome_variavel}'.")
            if (
                periodicidade not in _PERIODICIDADES_SEM_DIA_REFERENCIA
                and (dia_referencia_int is None or not 1 <= dia_referencia_int <= 31)
            ):
                self.add_error("variaveis_config_map", f"Defina um dia de referencia valido (1-31) para a variavel '{nome_variavel}'.")
            if not grupos_ids:
                self.add_error("variaveis_config_map", f"Defina ao menos um grupo para a variavel '{nome_variavel}'.")
        cleaned_data["variaveis_config_map"] = json.dumps(mapa, ensure_ascii=True)
        return cleaned_data

    def _aplicar_config_variaveis(self, indicador, mapa):
        variaveis = {item.nome: item for item in indicador.variaveis.all()}
        for ordem, nome_variavel in enumerate(indicador.nomes_variaveis_formula(), start=1):
            variavel = variaveis.get(nome_variavel)
            if not variavel:
                continue
            conf = mapa.get(nome_variavel) or {}
            periodicidade = conf.get("periodicidade_monitoramento") or "MENSAL"
            variavel.periodicidade_monitoramento = periodicidade
            if periodicidade in _PERIODICIDADES_SEM_DIA_REFERENCIA:
                variavel.dia_referencia_monitoramento = 1
            else:
                variavel.dia_referencia_monitoramento = conf.get("dia_referencia_monitoramento") or 1
            variavel.ordem = ordem
            variavel.unidade_medida = indicador.meta_unidade_medida or "%"
            variavel.save(
                update_fields=[
                    "periodicidade_monitoramento",
                    "dia_referencia_monitoramento",
                    "ordem",
                    "unidade_medida",
                    "atualizado_em",
                ]
            )
            variavel.grupos_monitoramento.set(conf.get("grupos_monitoramento_ids") or [])

    def save(self, commit=True):
        with transaction.atomic():
            indicador = super().save(commit=commit)
            if commit and indicador.eh_indicador_matematico and _db_tem_dia_referencia_monitoramento():
                indicador.sincronizar_variaveis_da_formula()
                mapa = json.loads(self.cleaned_data.get("variaveis_config_map") or "{}")
                self._aplicar_config_variaveis(indicador, mapa)
                indicador.sincronizar_estrutura_processual_monitoramento()
            return indicador

class ProcessoForm(BaseV2Form):
    class Meta(BaseV2Form.Meta):
        model = Processo
        fields = (
            "nome",
            "descricao",
            "indicadores",
            "grupos_responsaveis",
            "data_entrega_estipulada",
            "evolucao_manual",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["indicadores"].queryset = Indicador.objects.order_by("nome")
        self.fields["indicadores"].label = "Indicador e seletor"
        self.fields["indicadores"].required = True
        self.fields["grupos_responsaveis"].label = "Grupos responsáveis"

    def clean(self):
        cleaned_data = super().clean()
        indicadores = cleaned_data.get("indicadores")
        grupos = cleaned_data.get("grupos_responsaveis")
        if indicadores and grupos is not None:
            grupos_herdados_ids = set(
                Group.objects.filter(indicador_v2_responsavel__in=indicadores).values_list("id", flat=True)
            )
            grupos_selecionados_ids = set(grupos.values_list("id", flat=True))
            cleaned_data["grupos_responsaveis"] = Group.objects.filter(
                id__in=(grupos_selecionados_ids | grupos_herdados_ids)
            ).order_by("name")
        if indicadores:
            _validar_data_alvo_com_superiores(self, indicadores, "Indicador")
        return cleaned_data


class EntregaForm(BaseV2Form):
    class Meta(BaseV2Form.Meta):
        model = Entrega
        fields = (
            "nome",
            "descricao",
            "processos",
            "grupos_responsaveis",
            "data_entrega_estipulada",
            "evolucao_manual",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["processos"].queryset = Processo.objects.order_by("nome")
        self.fields["processos"].required = True
        self.order_fields(self.Meta.fields)

    def clean(self):
        cleaned_data = super().clean()
        processos = cleaned_data.get("processos")
        grupos = cleaned_data.get("grupos_responsaveis")
        if processos and grupos is not None:
            grupos_herdados_ids = set(
                Group.objects.filter(processo_v2_responsavel__in=processos).values_list("id", flat=True)
            )
            grupos_selecionados_ids = set(grupos.values_list("id", flat=True))
            cleaned_data["grupos_responsaveis"] = Group.objects.filter(
                id__in=(grupos_selecionados_ids | grupos_herdados_ids)
            ).order_by("name")
        if processos:
            _validar_data_alvo_com_superiores(self, processos, "Processo")
        return cleaned_data


class EntregaMonitoramentoForm(forms.ModelForm):
    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)
        self.fields["valor_monitoramento"].label = "Monitorar"
        self.fields["valor_monitoramento"].widget.attrs.update(
            {
                "class": "form-control sala-monitoramento-input",
                "placeholder": "Informe o valor monitorado",
            }
        )
        self.fields["evidencia_monitoramento"].label = "Anexar arquivos"
        self.fields["evidencia_monitoramento"].widget.attrs.update(
            {
                "class": "form-control sala-monitoramento-file",
            }
        )

    class Meta:
        model = Entrega
        fields = ("valor_monitoramento", "evidencia_monitoramento")

    def clean(self):
        cleaned_data = super().clean()
        entrega = self.instance
        if not (entrega and entrega.pk and entrega.eh_entrega_monitoramento):
            raise forms.ValidationError("Acao de monitoramento disponivel apenas para entregas de monitoramento.")
        valor = cleaned_data.get("valor_monitoramento")
        if entrega.ciclo_monitoramento_id and entrega.ciclo_monitoramento and entrega.ciclo_monitoramento.eh_inicial:
            if valor is None:
                self.add_error(
                    "valor_monitoramento",
                    "O ciclo inicial exige valor informado para viabilizar o calculo do indicador.",
                )
        return cleaned_data

    def save(self, commit=True):
        entrega = super().save(commit=False)
        valor = self.cleaned_data.get("valor_monitoramento")
        if valor is not None:
            entrega.valor_monitoramento = valor
        # Toda entrega de monitoramento passa a constar como concluida apos o registro.
        entrega.evolucao_manual = 100
        entrega.monitorado_em = timezone.now()
        if commit:
            entrega.save(
                update_fields=[
                    "valor_monitoramento",
                    "evidencia_monitoramento",
                    "evolucao_manual",
                    "monitorado_em",
                    "atualizado_em",
                ]
            )
        if valor is not None and entrega.ciclo_monitoramento_id and entrega.variavel_monitoramento_id:
            IndicadorCicloValor.objects.update_or_create(
                ciclo=entrega.ciclo_monitoramento,
                variavel=entrega.variavel_monitoramento,
                defaults={"valor": valor},
            )
            entrega.variavel_monitoramento.indicador.recalc_valor_atual_por_ciclos()
        return entrega
