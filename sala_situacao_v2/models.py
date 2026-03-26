import ast
from datetime import datetime, time, timedelta
from decimal import Decimal
import re
import secrets

from django.contrib.auth.models import Group
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils import timezone

_MARCADORES_PALETA = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#17becf",
    "#bcbd22",
    "#7f7f7f",
]
_FORMULA_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PERIODICIDADES_SEM_DIA_REFERENCIA = {"DIARIO", "SEMANAL", "QUINZENAL"}


def normalizar_nome_marcador(valor):
    return re.sub(r"\s+", " ", (valor or "").strip()).casefold()


def escolher_cor_marcador():
    return secrets.choice(_MARCADORES_PALETA)


def _obter_ou_criar_marcador_por_grupo(grupo):
    nome = re.sub(r"\s+", " ", (grupo.name or "").strip())
    nome_normalizado = normalizar_nome_marcador(nome)
    marcador = Marcador.objects.filter(nome_normalizado=nome_normalizado).first()
    if marcador:
        if not marcador.ativo:
            marcador.ativo = True
            marcador.save(update_fields=["ativo", "atualizado_em"])
        return marcador
    return Marcador.objects.create(
        nome=nome,
        nome_normalizado=nome_normalizado,
        cor=escolher_cor_marcador(),
        ativo=True,
    )


def _sincronizar_marcadores_automaticos_grupo_item(item, grupos_ids):
    if not item or not getattr(item, "pk", None):
        return
    content_type = ContentType.objects.get_for_model(item.__class__)
    grupos_ids = {int(item_id) for item_id in (grupos_ids or []) if str(item_id).isdigit()}
    existentes = {
        row.grupo_id: row
        for row in MarcadorVinculoAutomaticoGrupoItem.objects.filter(
            content_type=content_type,
            object_id=item.pk,
        ).select_related("grupo")
    }
    remover = set(existentes.keys()) - grupos_ids
    if remover:
        MarcadorVinculoAutomaticoGrupoItem.objects.filter(
            content_type=content_type,
            object_id=item.pk,
            grupo_id__in=remover,
        ).delete()
    adicionar = grupos_ids - set(existentes.keys())
    if not adicionar:
        return
    for grupo in Group.objects.filter(id__in=adicionar):
        marcador = _obter_ou_criar_marcador_por_grupo(grupo)
        MarcadorVinculoAutomaticoGrupoItem.objects.get_or_create(
            content_type=content_type,
            object_id=item.pk,
            grupo=grupo,
            defaults={"marcador": marcador},
        )


def ultimo_dia_mes(data_base):
    proximo_mes = data_base.replace(day=28) + timedelta(days=4)
    return proximo_mes - timedelta(days=proximo_mes.day)


def primeiro_dia_mes(data_base):
    return data_base.replace(day=1)


def ultimo_dia_util_mes(data_base):
    ultimo_dia = ultimo_dia_mes(data_base)
    while ultimo_dia.weekday() >= 5:
        ultimo_dia -= timedelta(days=1)
    return ultimo_dia


def adicionar_meses(data_base, meses):
    total = (data_base.year * 12 + (data_base.month - 1)) + meses
    ano = total // 12
    mes = (total % 12) + 1
    return data_base.replace(year=ano, month=mes, day=1)


def passo_meses_periodicidade(periodicidade):
    mapa = {
        "DIARIO": 0,
        "SEMANAL": 0,
        "QUINZENAL": 0,
        "MENSAL": 1,
        "TRIMESTRAL": 3,
        "SEMESTRAL": 6,
        "ANUAL": 12,
    }
    return mapa.get(periodicidade, 1)


def dia_referencia_no_mes(data_base, dia_referencia):
    dia = int(dia_referencia or 1)
    ultimo_dia = ultimo_dia_mes(data_base).day
    dia = max(1, min(dia, ultimo_dia))
    return data_base.replace(day=dia)


class Marcador(models.Model):
    nome = models.CharField("Nome", max_length=60)
    nome_normalizado = models.CharField(max_length=60, unique=True)
    cor = models.CharField(max_length=7, default=escolher_cor_marcador)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]

    def save(self, *args, **kwargs):
        self.nome = re.sub(r"\s+", " ", (self.nome or "").strip())
        self.nome_normalizado = normalizar_nome_marcador(self.nome)
        if not self.cor:
            self.cor = escolher_cor_marcador()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nome


class MarcadorVinculoAutomaticoGrupoItem(models.Model):
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="sala_situacao_v2_marcadores_automaticos_grupo_itens",
    )
    object_id = models.PositiveIntegerField()
    item = GenericForeignKey("content_type", "object_id")
    marcador = models.ForeignKey(
        Marcador,
        on_delete=models.CASCADE,
        related_name="vinculos_automaticos_grupo_itens_v2",
    )
    grupo = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="vinculos_automaticos_marcadores_sala_v2",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("content_type", "object_id", "grupo")
        ordering = ["marcador__nome"]


class BaseTimelineModel(models.Model):
    nome = models.CharField(max_length=255)
    descricao = models.TextField(blank=True, default="")
    data_lancamento = models.DateField("Data de lancamento", null=True, blank=True, editable=False)
    data_lancamento_em = models.DateTimeField("Data de lancamento (timestamp)", null=True, blank=True, editable=False)
    data_entrega_estipulada = models.DateField("Data de entrega estipulada", null=True, blank=True)
    evolucao_manual = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"))
    grupos_responsaveis = models.ManyToManyField(Group, related_name="%(class)s_v2_responsavel", blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["nome", "id"]

    def save(self, *args, **kwargs):
        if not self.data_lancamento:
            self.data_lancamento = timezone.localdate()
        if not self.data_lancamento_em:
            self.data_lancamento_em = timezone.now()
        super().save(*args, **kwargs)

    def _pais_para_marcadores(self):
        return []

    def _filhos_para_evolucao(self):
        return []

    def data_fim_monitoramento(self):
        return self.data_entrega_estipulada

    def _coletar_ancestrais_marcadores(self):
        visitados = set()
        itens = []

        def _visitar(obj):
            for pai in obj._pais_para_marcadores():
                if not pai or not getattr(pai, "pk", None):
                    continue
                chave = (pai._meta.label_lower, pai.pk)
                if chave in visitados:
                    continue
                visitados.add(chave)
                itens.append(pai)
                _visitar(pai)

        _visitar(self)
        return itens

    @property
    def marcadores_locais(self):
        if not self.pk:
            return []
        content_type = ContentType.objects.get_for_model(self.__class__)
        return list(
            Marcador.objects.filter(
                ativo=True,
                vinculos_automaticos_grupo_itens_v2__content_type=content_type,
                vinculos_automaticos_grupo_itens_v2__object_id=self.pk,
            )
            .distinct()
            .order_by("nome")
        )

    @property
    def marcadores_efetivos(self):
        marcador_por_id = {}
        for marcador in self.marcadores_locais:
            marcador_por_id[marcador.id] = marcador
        for item in self._coletar_ancestrais_marcadores():
            for marcador in item.marcadores_locais:
                marcador_por_id[marcador.id] = marcador
        return sorted(marcador_por_id.values(), key=lambda item: (item.nome or "").lower())

    @property
    def marcadores_herdados(self):
        return self.marcadores_efetivos

    def sincronizar_marcadores_automaticos_por_grupo(self):
        if not self.pk:
            return
        _sincronizar_marcadores_automaticos_grupo_item(
            self,
            self.grupos_responsaveis.values_list("id", flat=True),
        )

    @property
    def dias_para_vencer(self):
        if not self.data_entrega_estipulada:
            return None
        data_referencia = self._data_referencia_prazo
        return (self.data_entrega_estipulada - data_referencia).days

    @property
    def esta_concluido(self):
        return self.progresso_percentual >= 100

    @property
    def _instante_conclusao_prazo(self):
        if not self.esta_concluido:
            return None
        return self.atualizado_em or self.data_lancamento_em or timezone.now()

    @property
    def _data_referencia_prazo(self):
        instante_conclusao = self._instante_conclusao_prazo
        if instante_conclusao is not None:
            return timezone.localtime(instante_conclusao).date()
        return timezone.localdate()

    @property
    def texto_prazo(self):
        dias = self.dias_para_vencer
        if dias is None:
            return "Concluido" if self.esta_concluido else "Prazo nao definido"
        if self.esta_concluido:
            if dias > 0:
                return f"Concluido com {dias} dias de antecedencia"
            if dias == 0:
                return "Concluido no prazo"
            return f"Concluido com {abs(dias)} dias de atraso"
        if dias > 0:
            return f"{dias} dias para vencer"
        if dias == 0:
            return "Vence hoje"
        return f"Vencido ha {abs(dias)} dias"

    @property
    def progresso_prazo(self):
        if not self.data_entrega_estipulada:
            return 0.0
        agora = self._instante_conclusao_prazo or timezone.now()
        inicio = self.data_lancamento_em
        if not inicio:
            data_base = self.data_lancamento or timezone.localdate()
            inicio = timezone.make_aware(
                datetime.combine(data_base, time.min),
                timezone.get_current_timezone(),
            )
        fim = timezone.make_aware(
            datetime.combine(self.data_entrega_estipulada, time.max),
            timezone.get_current_timezone(),
        )
        if agora <= inicio:
            return 0.0
        if fim <= inicio or agora >= fim:
            return 100.0
        percentual = ((agora - inicio).total_seconds() / (fim - inicio).total_seconds()) * 100
        return max(0.0, min(round(percentual, 2), 100.0))

    @property
    def tem_filhos_relacionados(self):
        return len(self._filhos_para_evolucao()) > 0

    @property
    def evolucao_automatica(self):
        filhos = self._filhos_para_evolucao()
        if not filhos:
            return None
        return round(sum(item.progresso_percentual for item in filhos) / len(filhos), 2)

    @property
    def progresso_percentual(self):
        if self.tem_filhos_relacionados:
            return self.evolucao_automatica or 0
        return float(max(0, min(self.evolucao_manual or 0, 100)))

    @property
    def progresso_classe(self):
        percentual = self.progresso_percentual
        if percentual <= 50:
            return "progresso-vermelho"
        if percentual <= 75:
            return "progresso-amarelo"
        return "progresso-verde"

    @property
    def prazo_classe(self):
        percentual = self.progresso_prazo
        if percentual <= 50:
            return "progresso-verde"
        if percentual <= 75:
            return "progresso-amarelo"
        return "progresso-vermelho"

    @property
    def progresso_snapshot(self):
        prazo_percentual = float(self.progresso_prazo or 0)
        conclusao_percentual = float(self.progresso_percentual or 0)
        delta = round(conclusao_percentual - prazo_percentual, 2)
        sinal = "+" if delta > 0 else ""
        if delta > 0:
            delta_classe = "delta-positivo"
        elif delta < 0:
            delta_classe = "delta-negativo"
        else:
            delta_classe = "delta-neutro"
        return {
            "titulo_conclusao": "Alcance/Conclusao",
            "prazo_percentual": prazo_percentual,
            "prazo_classe": self.prazo_classe,
            "conclusao_percentual": conclusao_percentual,
            "conclusao_classe": self.progresso_classe,
            "delta_classe": delta_classe,
            "delta_texto": f"{sinal}{delta:.2f} p.p.",
        }


class Indicador(BaseTimelineModel):
    class PeriodicidadeMonitoramento(models.TextChoices):
        DIARIO = "DIARIO", "Diario"
        SEMANAL = "SEMANAL", "Semanal"
        QUINZENAL = "QUINZENAL", "Quinzenal"
        MENSAL = "MENSAL", "Mensal"
        TRIMESTRAL = "TRIMESTRAL", "Trimestral"
        SEMESTRAL = "SEMESTRAL", "Semestral"
        ANUAL = "ANUAL", "Anual"

    class TipoIndicador(models.TextChoices):
        PROCESSUAL = "PROCESSUAL", "Processual"
        MATEMATICO = "MATEMATICO", "Matematico"
        MATEMATICO_ACUMULATIVO = "MATEMATICO_ACUMULATIVO", "Matematico Acumulativo"

    tipo_indicador = models.CharField(max_length=32, choices=TipoIndicador.choices, default=TipoIndicador.PROCESSUAL)
    formula_expressao = models.TextField(blank=True, default="")
    meta_valor = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("100"))
    meta_unidade_medida = models.CharField(max_length=40, blank=True, default="%")
    valor_atual = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    grupos_criadores = models.ManyToManyField(Group, related_name="indicadores_v2_criados", blank=True)

    class Meta(BaseTimelineModel.Meta):
        verbose_name = "Indicador V2"
        verbose_name_plural = "Indicadores V2"
        permissions = (
            ("monitorar_indicador", "Pode monitorar indicador v2"),
        )

    def __str__(self):
        return self.nome

    def _filhos_para_evolucao(self):
        if self.tipo_indicador != self.TipoIndicador.PROCESSUAL:
            return []
        return list(self.processos.all())

    @property
    def atingimento_meta_percentual(self):
        if not self.meta_valor:
            return 0
        if self.valor_atual is None:
            return 0
        percentual = (Decimal(self.valor_atual) / Decimal(self.meta_valor)) * 100
        return float(max(Decimal("0"), min(percentual, Decimal("100"))))

    @property
    def desempenho_meta_classe(self):
        percentual = self.atingimento_meta_percentual
        if percentual < 50:
            return "progresso-vermelho"
        if percentual < 75:
            return "progresso-amarelo"
        return "progresso-verde"

    @property
    def eh_indicador_matematico(self):
        return self.tipo_indicador in {
            self.TipoIndicador.MATEMATICO,
            self.TipoIndicador.MATEMATICO_ACUMULATIVO,
        }

    @property
    def eh_indicador_matematico_acumulativo(self):
        return self.tipo_indicador == self.TipoIndicador.MATEMATICO_ACUMULATIVO

    @property
    def progresso_percentual(self):
        if self.eh_indicador_matematico:
            return self.atingimento_meta_percentual
        return super().progresso_percentual

    @property
    def progresso_snapshot(self):
        snapshot = super().progresso_snapshot
        if not self.eh_indicador_matematico:
            return snapshot
        conclusao_percentual = float(self.atingimento_meta_percentual or 0)
        prazo_percentual = float(self.progresso_prazo or 0)
        delta = round(conclusao_percentual - prazo_percentual, 2)
        sinal = "+" if delta > 0 else ""
        if delta > 0:
            delta_classe = "delta-positivo"
        elif delta < 0:
            delta_classe = "delta-negativo"
        else:
            delta_classe = "delta-neutro"
        snapshot.update(
            {
                "titulo_conclusao": "Atingimento da Meta",
                "conclusao_percentual": conclusao_percentual,
                "conclusao_classe": self.desempenho_meta_classe,
                "delta_classe": delta_classe,
                "delta_texto": f"{sinal}{delta:.2f} p.p.",
            }
        )
        return snapshot

    def nomes_variaveis_formula(self):
        if not self.formula_expressao:
            return []
        tree = ast.parse(self.formula_expressao.strip(), mode="eval")
        return sorted({node.id for node in ast.walk(tree) if isinstance(node, ast.Name)})

    @staticmethod
    def _formula_percentual_node_valido(node):
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Mult):
            return False

        def _is_const_100(item):
            if not isinstance(item, ast.Constant):
                return False
            try:
                return Decimal(str(item.value)) == Decimal("100")
            except Exception:
                return False

        def _is_divisao_variaveis(item):
            return (
                isinstance(item, ast.BinOp)
                and isinstance(item.op, ast.Div)
                and isinstance(item.left, ast.Name)
                and isinstance(item.right, ast.Name)
            )

        return (
            (_is_divisao_variaveis(node.left) and _is_const_100(node.right))
            or (_is_const_100(node.left) and _is_divisao_variaveis(node.right))
        )

    def _validar_formula(self):
        if not self.formula_expressao:
            return
        try:
            tree = ast.parse(self.formula_expressao.strip(), mode="eval")
        except SyntaxError as exc:
            raise ValidationError({"formula_expressao": f"Formula invalida: {exc.msg}"}) from exc
        permitidos = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Name,
            ast.Load,
            ast.Constant,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.UAdd,
            ast.USub,
        )
        for node in ast.walk(tree):
            if not isinstance(node, permitidos):
                raise ValidationError(
                    {"formula_expressao": "A formula permite apenas variaveis, numeros e operadores + - * /."}
                )
            if isinstance(node, ast.Name) and not _FORMULA_VAR_RE.match(node.id):
                raise ValidationError({"formula_expressao": f"Nome de variavel invalido: {node.id}"})
        if self.eh_indicador_matematico and not self._formula_percentual_node_valido(tree.body):
            raise ValidationError(
                {
                    "formula_expressao": (
                        "Para indicadores matematicos, informe a formula no formato percentual "
                        "(x/y)*100. Use uma variavel no numerador e outra no denominador. "
                        "Exemplos validos: (qtdd_de_familias/meta_de_familias)*100 e "
                        "(total_de_refeicoes/meta_de_refeicoes)*100."
                    )
                }
            )

    def clean(self):
        super().clean()
        if self.eh_indicador_matematico:
            self._validar_formula()

    def _eval_formula_node(self, node, variaveis):
        if isinstance(node, ast.Expression):
            return self._eval_formula_node(node.body, variaveis)
        if isinstance(node, ast.Constant):
            return Decimal(str(node.value))
        if isinstance(node, ast.Name):
            if node.id not in variaveis:
                raise ValidationError(f"Variavel '{node.id}' sem valor informado.")
            return Decimal(str(variaveis[node.id]))
        if isinstance(node, ast.UnaryOp):
            valor = self._eval_formula_node(node.operand, variaveis)
            if isinstance(node.op, ast.USub):
                return -valor
            if isinstance(node.op, ast.UAdd):
                return valor
        if isinstance(node, ast.BinOp):
            esquerda = self._eval_formula_node(node.left, variaveis)
            direita = self._eval_formula_node(node.right, variaveis)
            if isinstance(node.op, ast.Add):
                return esquerda + direita
            if isinstance(node.op, ast.Sub):
                return esquerda - direita
            if isinstance(node.op, ast.Mult):
                return esquerda * direita
            if isinstance(node.op, ast.Div):
                if direita == 0:
                    raise ValidationError("Divisao por zero na formula.")
                return esquerda / direita
        raise ValidationError("Expressao da formula nao suportada.")

    def avaliar_formula(self, valores_variaveis):
        if not self.formula_expressao:
            raise ValidationError("Formula nao informada.")
        tree = ast.parse(self.formula_expressao.strip(), mode="eval")
        return self._eval_formula_node(tree, valores_variaveis)

    def sincronizar_variaveis_da_formula(self):
        if not self.eh_indicador_matematico or not self.pk:
            return []
        nomes = self.nomes_variaveis_formula()
        criadas = []
        for ordem, nome in enumerate(nomes, start=1):
            _, created = IndicadorVariavel.objects.get_or_create(
                indicador=self,
                nome=nome,
                defaults={
                    "descricao": f"Variavel '{nome}' do indicador {self.nome}",
                    "unidade_medida": self.meta_unidade_medida or "%",
                    "periodicidade_monitoramento": self.PeriodicidadeMonitoramento.MENSAL,
                    "ordem": ordem,
                },
            )
            if created:
                criadas.append(nome)
        IndicadorVariavel.objects.filter(indicador=self).exclude(nome__in=nomes).delete()
        return criadas

    def _valor_variavel_por_data(self, variavel, data_referencia):
        if self.eh_indicador_matematico_acumulativo:
            return (
                IndicadorCicloValor.objects.filter(
                    variavel=variavel,
                    ciclo__periodo_fim__lte=data_referencia,
                ).aggregate(total=models.Sum("valor"))["total"]
                or Decimal("0")
            )
        ultimo = (
            IndicadorCicloValor.objects.filter(
                variavel=variavel,
                ciclo__periodo_fim__lte=data_referencia,
            )
            .order_by("-ciclo__periodo_fim", "-atualizado_em", "-id")
            .first()
        )
        if not ultimo:
            raise ValidationError(f"Variavel '{variavel.nome}' sem valor informado ate {data_referencia:%d/%m/%Y}.")
        return ultimo.valor

    def recalcular_resultado_por_data(self, data_referencia):
        if not self.eh_indicador_matematico:
            return None
        variaveis = list(self.variaveis.order_by("ordem", "nome"))
        valores_variaveis = {}
        try:
            for variavel in variaveis:
                valores_variaveis[variavel.nome] = self._valor_variavel_por_data(variavel, data_referencia)
            resultado = self.avaliar_formula(valores_variaveis)
        except ValidationError:
            return None
        self.valor_atual = resultado
        self.save(update_fields=["valor_atual", "atualizado_em"])
        return resultado

    def recalc_valor_atual_por_ciclos(self):
        if not self.eh_indicador_matematico:
            return
        ultimo_valor = (
            IndicadorCicloValor.objects.filter(variavel__indicador=self)
            .order_by("-ciclo__periodo_fim", "-atualizado_em", "-id")
            .first()
        )
        if not ultimo_valor:
            self.valor_atual = Decimal("0")
            self.save(update_fields=["valor_atual", "atualizado_em"])
            return
        self.recalcular_resultado_por_data(ultimo_valor.ciclo.periodo_fim)

    def sincronizar_estrutura_processual_monitoramento(self):
        if not self.eh_indicador_matematico or not self.pk:
            return
        variaveis_locais = list(self.variaveis.order_by("ordem", "nome"))
        if not variaveis_locais:
            return
        grupos_indicador_ids = set()
        grupos_criadores_indicador_ids = set(self.grupos_criadores.values_list("id", flat=True))
        for variavel in variaveis_locais:
            variavel.gerar_ciclos_monitoramento()
            grupos_variavel_ids = set(variavel.grupos_monitoramento.values_list("id", flat=True))
            grupos_indicador_ids.update(grupos_variavel_ids)
            nome_processo = f'Monitoramento de "{variavel.nome}" do indicador "{self.nome}"'
            processo, _ = Processo.objects.get_or_create(
                nome=nome_processo,
                defaults={
                    "descricao": f"Processo automatico de coleta da variavel {variavel.nome}.",
                    "data_entrega_estipulada": self.data_entrega_estipulada,
                    "evolucao_manual": Decimal("0"),
                },
            )
            processo.indicadores.add(self)
            alterou_processo = False
            if processo.data_entrega_estipulada != self.data_entrega_estipulada:
                processo.data_entrega_estipulada = self.data_entrega_estipulada
                alterou_processo = True
            if processo.criado_por_id != self.criado_por_id:
                processo.criado_por = self.criado_por
                alterou_processo = True
            if alterou_processo:
                processo.save(update_fields=["data_entrega_estipulada", "criado_por", "atualizado_em"])
            processo.grupos_criadores.set(grupos_criadores_indicador_ids)
            processo.grupos_responsaveis.set(grupos_variavel_ids)
            entregas_variavel = []
            for ciclo in variavel.ciclos_monitoramento.order_by("numero"):
                sufixo_inicial = " (Inicial)" if ciclo.eh_inicial else ""
                entrega_nome = f'Registro de monitoramento "{variavel.nome}" - {ciclo.periodo_inicio:%m/%Y}{sufixo_inicial}'
                prazo_ciclo = variavel.prazo_entrega_para_ciclo(ciclo)
                entrega, _ = Entrega.objects.get_or_create(
                    nome=entrega_nome,
                    defaults={
                        "descricao": (
                            f'Alimentacao da variavel {variavel.nome} para {ciclo.titulo}. '
                            "Entrega automatica de monitoramento."
                        ),
                        "data_entrega_estipulada": prazo_ciclo,
                        "ciclo_monitoramento": ciclo,
                        "variavel_monitoramento": variavel,
                        "periodo_inicio": ciclo.periodo_inicio,
                        "periodo_fim": ciclo.periodo_fim,
                    },
                )
                alterou = False
                if entrega.ciclo_monitoramento_id != ciclo.id:
                    entrega.ciclo_monitoramento = ciclo
                    alterou = True
                if entrega.variavel_monitoramento_id != variavel.id:
                    entrega.variavel_monitoramento = variavel
                    alterou = True
                if entrega.data_entrega_estipulada != prazo_ciclo:
                    entrega.data_entrega_estipulada = prazo_ciclo
                    alterou = True
                if entrega.periodo_inicio != ciclo.periodo_inicio:
                    entrega.periodo_inicio = ciclo.periodo_inicio
                    alterou = True
                if entrega.periodo_fim != ciclo.periodo_fim:
                    entrega.periodo_fim = ciclo.periodo_fim
                    alterou = True
                if entrega.criado_por_id != self.criado_por_id:
                    entrega.criado_por = self.criado_por
                    alterou = True
                if alterou:
                    entrega.save(
                        update_fields=[
                            "ciclo_monitoramento",
                            "variavel_monitoramento",
                            "data_entrega_estipulada",
                            "periodo_inicio",
                            "periodo_fim",
                            "criado_por",
                            "atualizado_em",
                        ]
                    )
                entrega.processos.add(processo)
                entrega.grupos_criadores.set(grupos_criadores_indicador_ids)
                entrega.grupos_responsaveis.set(grupos_variavel_ids)
                entregas_variavel.append(entrega)
            _sincronizar_marcadores_automaticos_grupo_item(processo, grupos_variavel_ids)
            for entrega in entregas_variavel:
                _sincronizar_marcadores_automaticos_grupo_item(entrega, grupos_variavel_ids)
        _sincronizar_marcadores_automaticos_grupo_item(self, grupos_indicador_ids)


class Processo(BaseTimelineModel):
    indicadores = models.ManyToManyField(Indicador, related_name="processos", blank=True)
    grupos_criadores = models.ManyToManyField(Group, related_name="processos_v2_criados", blank=True)

    class Meta(BaseTimelineModel.Meta):
        verbose_name = "Processo V2"
        verbose_name_plural = "Processos V2"

    def _pais_para_marcadores(self):
        if self.entregas.filter(variavel_monitoramento__isnull=False).exists():
            return []
        return list(self.indicadores.all())

    def _filhos_para_evolucao(self):
        return list(self.entregas.all())

    def __str__(self):
        return self.nome


class Entrega(BaseTimelineModel):
    processos = models.ManyToManyField(Processo, related_name="entregas", blank=True)
    grupos_criadores = models.ManyToManyField(Group, related_name="entregas_v2_criadas", blank=True)
    periodo_inicio = models.DateField(null=True, blank=True)
    periodo_fim = models.DateField(null=True, blank=True)
    ciclo_monitoramento = models.ForeignKey(
        "IndicadorVariavelCicloMonitoramento",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entregas_monitoramento",
    )
    variavel_monitoramento = models.ForeignKey(
        "IndicadorVariavel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entregas_monitoramento",
    )
    valor_monitoramento = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    evidencia_monitoramento = models.FileField(upload_to="sala_situacao_v2/evidencias/", null=True, blank=True)
    monitorado_em = models.DateTimeField(null=True, blank=True)

    class Meta(BaseTimelineModel.Meta):
        verbose_name = "Entrega V2"
        verbose_name_plural = "Entregas V2"
        permissions = (
            ("monitorar_entrega", "Pode monitorar entrega v2"),
        )

    def _pais_para_marcadores(self):
        if self.eh_entrega_monitoramento:
            return []
        return list(self.processos.all())

    @property
    def eh_entrega_monitoramento(self):
        return bool(self.variavel_monitoramento_id and self.ciclo_monitoramento_id)

    @property
    def eh_entrega_manual(self):
        return not self.eh_entrega_monitoramento

    def _entregas_manuais_ordenadas_no_processo(self, processo):
        if not processo or not getattr(processo, "pk", None):
            return Entrega.objects.none()
        return processo.entregas.filter(
            variavel_monitoramento__isnull=True,
            ciclo_monitoramento__isnull=True,
        ).order_by(
            F("data_entrega_estipulada").asc(nulls_last=True),
            "nome",
            "id",
        )

    def numero_no_processo(self, processo):
        if not self.pk or not self.eh_entrega_manual:
            return None
        ids_ordenados = list(self._entregas_manuais_ordenadas_no_processo(processo).values_list("id", flat=True))
        if self.pk not in ids_ordenados:
            return None
        return ids_ordenados.index(self.pk) + 1

    def total_no_processo(self, processo):
        return self._entregas_manuais_ordenadas_no_processo(processo).count()

    def rotulo_numeracao_no_processo(self, processo):
        numero = self.numero_no_processo(processo)
        if numero is None:
            return ""
        total = self.total_no_processo(processo)
        return f"{numero}/{total}"

    @property
    def numeracao_processos(self):
        if not self.pk or not self.eh_entrega_manual:
            return []
        dados = []
        for processo in self.processos.order_by("nome"):
            rotulo = self.rotulo_numeracao_no_processo(processo)
            if not rotulo:
                continue
            dados.append(
                {
                    "processo": processo,
                    "rotulo": rotulo,
                    "numero": self.numero_no_processo(processo),
                    "total": self.total_no_processo(processo),
                }
            )
        return dados

    @property
    def _instante_conclusao_prazo(self):
        if not self.esta_concluido:
            return None
        return self.monitorado_em or super()._instante_conclusao_prazo

    def __str__(self):
        return self.nome


class IndicadorVariavel(models.Model):
    class TipoNumerico(models.TextChoices):
        INTEIRO = "INTEIRO", "Inteiro"
        DECIMAL = "DECIMAL", "Decimal"

    indicador = models.ForeignKey(
        Indicador,
        on_delete=models.CASCADE,
        related_name="variaveis",
    )
    nome = models.CharField(max_length=60)
    descricao = models.TextField(blank=True, default="")
    tipo_numerico = models.CharField(max_length=10, choices=TipoNumerico.choices, default=TipoNumerico.DECIMAL)
    unidade_medida = models.CharField(max_length=40, default="%")
    periodicidade_monitoramento = models.CharField(
        max_length=20,
        choices=Indicador.PeriodicidadeMonitoramento.choices,
    )
    dia_referencia_monitoramento = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )
    grupos_monitoramento = models.ManyToManyField(
        Group,
        related_name="variaveis_monitoramento_sala_v2",
        blank=True,
    )
    ordem = models.PositiveSmallIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ordem", "nome"]
        unique_together = ("indicador", "nome")

    def clean(self):
        super().clean()
        if self.nome:
            nome_limpo = self.nome.strip()
            if not _FORMULA_VAR_RE.match(nome_limpo):
                raise ValidationError({"nome": "Use apenas letras, numeros e '_' iniciando por letra."})
            self.nome = nome_limpo
        if not self.indicador.eh_indicador_matematico:
            raise ValidationError("Variaveis so podem ser cadastradas em indicadores matematicos.")
        if not self.periodicidade_monitoramento:
            raise ValidationError({"periodicidade_monitoramento": "Periodicidade da variavel e obrigatoria."})
        if (
            self.periodicidade_monitoramento not in _PERIODICIDADES_SEM_DIA_REFERENCIA
            and not self.dia_referencia_monitoramento
        ):
            raise ValidationError({"dia_referencia_monitoramento": "Dia de referencia obrigatorio."})

    def prazo_entrega_para_ciclo(self, ciclo):
        if (self.periodicidade_monitoramento or "").upper() in _PERIODICIDADES_SEM_DIA_REFERENCIA:
            prazo_referencia = ciclo.periodo_fim
        else:
            prazo_referencia = dia_referencia_no_mes(ciclo.periodo_inicio, self.dia_referencia_monitoramento)
        if prazo_referencia < ciclo.periodo_inicio:
            prazo_referencia = ciclo.periodo_inicio
        if prazo_referencia > ciclo.periodo_fim:
            prazo_referencia = ciclo.periodo_fim
        data_lancamento = self.indicador.data_lancamento or timezone.localdate()
        if ciclo.eh_inicial and data_lancamento and prazo_referencia < data_lancamento:
            return data_lancamento
        return prazo_referencia

    def __str__(self):
        return f"{self.nome} ({self.unidade_medida})"

    def gerar_ciclos_monitoramento(self):
        indicador = self.indicador
        if not indicador or not indicador.eh_indicador_matematico:
            return
        data_fim = indicador.data_fim_monitoramento()
        if not data_fim:
            return
        inicio_referencia = indicador.data_lancamento or timezone.localdate()
        periodicidade = (self.periodicidade_monitoramento or "").upper()
        if periodicidade in {
            Indicador.PeriodicidadeMonitoramento.DIARIO,
            Indicador.PeriodicidadeMonitoramento.SEMANAL,
            Indicador.PeriodicidadeMonitoramento.QUINZENAL,
        }:
            desejados = []
            numero = 1
            cursor_inicio = inicio_referencia
            passo_dias = {
                Indicador.PeriodicidadeMonitoramento.DIARIO: 1,
                Indicador.PeriodicidadeMonitoramento.SEMANAL: 7,
                Indicador.PeriodicidadeMonitoramento.QUINZENAL: 15,
            }[periodicidade]
            while cursor_inicio <= data_fim:
                cursor_fim = min(cursor_inicio + timedelta(days=passo_dias - 1), data_fim)
                desejados.append(
                    {
                        "numero": numero,
                        "periodo_inicio": cursor_inicio,
                        "periodo_fim": cursor_fim,
                        "eh_inicial": numero == 1,
                    }
                )
                cursor_inicio = cursor_fim + timedelta(days=1)
                numero += 1
            existentes = {item.numero: item for item in self.ciclos_monitoramento.all()}
            numeros_desejados = {item["numero"] for item in desejados}
            for dado in desejados:
                ciclo = existentes.get(dado["numero"])
                if ciclo is None:
                    IndicadorVariavelCicloMonitoramento.objects.create(
                        variavel=self,
                        numero=dado["numero"],
                        periodo_inicio=dado["periodo_inicio"],
                        periodo_fim=dado["periodo_fim"],
                        eh_inicial=dado["eh_inicial"],
                    )
                    continue
                campos_update = []
                if ciclo.periodo_inicio != dado["periodo_inicio"]:
                    ciclo.periodo_inicio = dado["periodo_inicio"]
                    campos_update.append("periodo_inicio")
                if ciclo.periodo_fim != dado["periodo_fim"]:
                    ciclo.periodo_fim = dado["periodo_fim"]
                    campos_update.append("periodo_fim")
                if ciclo.eh_inicial != dado["eh_inicial"]:
                    ciclo.eh_inicial = dado["eh_inicial"]
                    campos_update.append("eh_inicial")
                if campos_update:
                    ciclo.save(update_fields=campos_update + ["atualizado_em"])
            for numero_existente, ciclo in existentes.items():
                if numero_existente not in numeros_desejados:
                    ciclo.entregas_monitoramento.all().delete()
                    ciclo.delete()
            return

        inicio_ancora = primeiro_dia_mes(inicio_referencia)
        fim_ancora = primeiro_dia_mes(data_fim)
        if inicio_ancora > fim_ancora:
            return
        passo_meses = passo_meses_periodicidade(periodicidade)
        exige_ciclo_inicial = True
        desejados = []
        numero = 1
        if exige_ciclo_inicial:
            desejados.append(
                {
                    "numero": numero,
                    "periodo_inicio": inicio_ancora,
                    "periodo_fim": ultimo_dia_mes(inicio_ancora),
                    "eh_inicial": True,
                }
            )
            numero += 1
            cursor = adicionar_meses(inicio_ancora, passo_meses)
        else:
            cursor = inicio_ancora
        while cursor <= fim_ancora:
            desejados.append(
                {
                    "numero": numero,
                    "periodo_inicio": cursor,
                    "periodo_fim": ultimo_dia_mes(cursor),
                    "eh_inicial": False,
                }
            )
            cursor = adicionar_meses(cursor, passo_meses)
            numero += 1
        existentes = {item.numero: item for item in self.ciclos_monitoramento.all()}
        numeros_desejados = {item["numero"] for item in desejados}
        for dado in desejados:
            ciclo = existentes.get(dado["numero"])
            if ciclo is None:
                IndicadorVariavelCicloMonitoramento.objects.create(
                    variavel=self,
                    numero=dado["numero"],
                    periodo_inicio=dado["periodo_inicio"],
                    periodo_fim=dado["periodo_fim"],
                    eh_inicial=dado["eh_inicial"],
                )
                continue
            campos_update = []
            if ciclo.periodo_inicio != dado["periodo_inicio"]:
                ciclo.periodo_inicio = dado["periodo_inicio"]
                campos_update.append("periodo_inicio")
            if ciclo.periodo_fim != dado["periodo_fim"]:
                ciclo.periodo_fim = dado["periodo_fim"]
                campos_update.append("periodo_fim")
            if ciclo.eh_inicial != dado["eh_inicial"]:
                ciclo.eh_inicial = dado["eh_inicial"]
                campos_update.append("eh_inicial")
            if campos_update:
                ciclo.save(update_fields=campos_update + ["atualizado_em"])
        for numero_existente, ciclo in existentes.items():
            if numero_existente not in numeros_desejados:
                ciclo.entregas_monitoramento.all().delete()
                ciclo.delete()


class IndicadorVariavelCicloMonitoramento(models.Model):
    class Status(models.TextChoices):
        ABERTO = "ABERTO", "Aberto"
        FECHADO = "FECHADO", "Fechado"

    variavel = models.ForeignKey(
        IndicadorVariavel,
        on_delete=models.CASCADE,
        related_name="ciclos_monitoramento",
    )
    numero = models.PositiveIntegerField()
    periodo_inicio = models.DateField()
    periodo_fim = models.DateField()
    eh_inicial = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABERTO)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["periodo_inicio", "numero"]
        unique_together = ("variavel", "numero")
        indexes = [models.Index(fields=["variavel", "periodo_fim"])]

    @property
    def titulo(self):
        if self.periodo_inicio and self.periodo_fim:
            return f"{self.periodo_inicio:%m/%Y} - {self.periodo_fim:%m/%Y}"
        return f"Ciclo {self.numero}"

    def __str__(self):
        return f"{self.variavel.nome} - ciclo {self.numero}"


class IndicadorCicloValor(models.Model):
    ciclo = models.ForeignKey(
        IndicadorVariavelCicloMonitoramento,
        on_delete=models.CASCADE,
        related_name="valores",
    )
    variavel = models.ForeignKey(
        IndicadorVariavel,
        on_delete=models.CASCADE,
        related_name="valores_ciclo",
    )
    valor = models.DecimalField(max_digits=18, decimal_places=4)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("ciclo", "variavel")


def _sincronizar_marcadores_automaticos_em_item(instance):
    if instance and getattr(instance, "pk", None):
        instance.sincronizar_marcadores_automaticos_por_grupo()


@receiver(m2m_changed, sender=Indicador.grupos_responsaveis.through)
def _indicador_grupos_responsaveis_changed(sender, instance, action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        _sincronizar_marcadores_automaticos_em_item(instance)


@receiver(m2m_changed, sender=Processo.grupos_responsaveis.through)
def _processo_grupos_responsaveis_changed(sender, instance, action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        _sincronizar_marcadores_automaticos_em_item(instance)


@receiver(m2m_changed, sender=Entrega.grupos_responsaveis.through)
def _entrega_grupos_responsaveis_changed(sender, instance, action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        _sincronizar_marcadores_automaticos_em_item(instance)
