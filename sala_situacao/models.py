"""
Modelos de domínio do app `sala_situacao`.

Este arquivo concentra a estrutura de dados e regras centrais de persistência da
Sala de Situação: indicadores estratégicos/táticos, processos, entregas,
marcadores, variáveis e ciclos de monitoramento.

Integração com arquitetura Django:
- `forms.py`: validação de entrada e aplicação de regras de negócio no save;
- `views.py`: consultas, filtros e montagem de contexto para templates/APIs;
- `admin.py`: operação administrativa dos objetos de monitoramento;
- `auditoria` e `contenttypes`: rastreabilidade e relações genéricas entre itens.
"""

import ast
from functools import lru_cache
import re
import secrets
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import connection, models
from django.utils import timezone


_FORMULA_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
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


@lru_cache(maxsize=1)
def nota_item_anexo_storage_ready():
    """Indica se a tabela física de anexos de nota existe no banco atual."""

    return NotaItemAnexo._meta.db_table in connection.introspection.table_names()


def normalizar_nome_marcador(valor):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `valor`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    return re.sub(r"\s+", " ", (valor or "").strip()).casefold()


def escolher_cor_marcador():
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    return secrets.choice(_MARCADORES_PALETA)


def _obter_ou_criar_marcador_por_grupo(grupo):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `grupo`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

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
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

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


def _adicionar_periodicidade(data_base, periodicidade):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if periodicidade == "SEMANAL":
        return data_base + timedelta(days=7)
    if periodicidade == "QUINZENAL":
        return data_base + timedelta(days=14)
    if periodicidade == "MENSAL":
        mes = 1 if data_base.month == 12 else data_base.month + 1
        ano = data_base.year + (1 if data_base.month == 12 else 0)
        dia = min(data_base.day, 28)
        return data_base.replace(year=ano, month=mes, day=dia)
    if periodicidade == "TRIMESTRAL":
        return _adicionar_periodicidade(
            _adicionar_periodicidade(_adicionar_periodicidade(data_base, "MENSAL"), "MENSAL"),
            "MENSAL",
        )
    if periodicidade == "SEMESTRAL":
        atual = data_base
        for _ in range(6):
            atual = _adicionar_periodicidade(atual, "MENSAL")
        return atual
    if periodicidade == "ANUAL":
        try:
            return data_base.replace(year=data_base.year + 1)
        except ValueError:
            return data_base.replace(year=data_base.year + 1, day=28)
    raise ValidationError("Periodicidade inválida para geração de ciclos.")


def _periodicidade_alinhada_no_inicio(data_inicio, periodicidade, data_ciclo):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if not data_inicio or not periodicidade or not data_ciclo:
        return False
    if data_ciclo < data_inicio:
        return False
    cursor = data_inicio
    tentativas = 0
    while cursor <= data_ciclo and tentativas < 1000:
        if cursor == data_ciclo:
            return True
        cursor = _adicionar_periodicidade(cursor, periodicidade)
        tentativas += 1
    return False


def _periodicidade_compativel_com_base(data_inicio, periodicidade_base, periodicidade_variavel):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    if not periodicidade_variavel or not periodicidade_base:
        return True
    if periodicidade_variavel == periodicidade_base:
        return True
    limite = data_inicio
    inicios_base = {data_inicio}
    for _ in range(120):
        limite = _adicionar_periodicidade(limite, periodicidade_base)
        inicios_base.add(limite)
    cursor = data_inicio
    for _ in range(120):
        cursor = _adicionar_periodicidade(cursor, periodicidade_variavel)
        if cursor > limite:
            return True
        if cursor not in inicios_base:
            return False
    return True


def ultimo_dia_util_mes(data_base):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `data_base`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    ultimo_dia = ultimo_dia_mes(data_base)
    while ultimo_dia.weekday() >= 5:
        ultimo_dia -= timedelta(days=1)
    return ultimo_dia


def primeiro_dia_mes(data_base):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `data_base`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    return data_base.replace(day=1)


def ultimo_dia_mes(data_base):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `data_base`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    proximo_mes = data_base.replace(day=28) + timedelta(days=4)
    return proximo_mes - timedelta(days=proximo_mes.day)


def adicionar_meses(data_base, meses):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    total = (data_base.year * 12 + (data_base.month - 1)) + meses
    ano = total // 12
    mes = (total % 12) + 1
    return data_base.replace(year=ano, month=mes, day=1)


def passo_meses_periodicidade(periodicidade):
    """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `periodicidade`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

    mapa = {
        "MENSAL": 1,
        "TRIMESTRAL": 3,
        "SEMESTRAL": 6,
        "ANUAL": 12,
        "SEMANAL": 1,
        "QUINZENAL": 1,
    }
    return mapa.get(periodicidade, 1)


class SalaSituacaoPainel(models.Model):
    """Classe `SalaSituacaoPainel` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    titulo = models.CharField(max_length=120, default="Painel Sala de Situação")
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Classe `SalaSituacaoPainel.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        verbose_name = "Sala de Situação"
        verbose_name_plural = "Sala de Situação"

    def __str__(self):
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

        return self.titulo


class Marcador(models.Model):
    """Classe `Marcador` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    nome = models.CharField("Nome", max_length=60)
    nome_normalizado = models.CharField(max_length=60, unique=True)
    cor = models.CharField(max_length=7, default=escolher_cor_marcador)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Classe `Marcador.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        ordering = ["nome"]

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

        super().clean()
        self.nome = re.sub(r"\s+", " ", (self.nome or "").strip())
        if not self.nome:
            raise ValidationError({"nome": "Informe o nome do marcador."})
        self.nome_normalizado = normalizar_nome_marcador(self.nome)
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", self.cor or ""):
            raise ValidationError({"cor": "Cor inválida. Use o formato #RRGGBB."})

    def save(self, *args, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.nome = re.sub(r"\s+", " ", (self.nome or "").strip())
        self.nome_normalizado = normalizar_nome_marcador(self.nome)
        if not self.cor:
            self.cor = escolher_cor_marcador()
        return super().save(*args, **kwargs)

    def __str__(self):
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

        return self.nome


class MarcadorVinculoItem(models.Model):
    """Classe `MarcadorVinculoItem` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="sala_situacao_marcadores_itens",
    )
    object_id = models.PositiveIntegerField()
    item = GenericForeignKey("content_type", "object_id")
    marcador = models.ForeignKey(
        Marcador,
        on_delete=models.CASCADE,
        related_name="vinculos_itens",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Classe `MarcadorVinculoItem.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        unique_together = ("content_type", "object_id", "marcador")
        ordering = ["marcador__nome"]


class MarcadorVinculoAutomaticoGrupoItem(models.Model):
    """Classe `MarcadorVinculoAutomaticoGrupoItem` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="sala_situacao_marcadores_automaticos_grupo_itens",
    )
    object_id = models.PositiveIntegerField()
    item = GenericForeignKey("content_type", "object_id")
    marcador = models.ForeignKey(
        Marcador,
        on_delete=models.CASCADE,
        related_name="vinculos_automaticos_grupo_itens",
    )
    grupo = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="vinculos_automaticos_marcadores_sala",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Classe `MarcadorVinculoAutomaticoGrupoItem.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        unique_together = ("content_type", "object_id", "grupo")
        ordering = ["marcador__nome"]


class ItemHierarquicoBase(models.Model):
    """Classe `ItemHierarquicoBase` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    nome = models.CharField(max_length=180)
    descricao = models.TextField(blank=True)
    data_lancamento = models.DateField("Data de lançamento", null=True, blank=True, editable=False)
    data_lancamento_em = models.DateTimeField(
        "Data/hora de lançamento",
        null=True,
        blank=True,
        editable=False,
    )
    data_entrega_estipulada = models.DateField(
        "Data-alvo",
        null=True,
        blank=True,
        help_text="Data planejada para conclusão deste item.",
    )
    atualizado_em = models.DateTimeField(auto_now=True)
    evolucao_manual = models.DecimalField(
        "Evolução manual (%)",
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Use este campo quando o item não possuir filhos relacionados.",
    )
    marcadores_vinculos = GenericRelation(
        "MarcadorVinculoItem",
        content_type_field="content_type",
        object_id_field="object_id",
        related_query_name="itens_sala",
    )

    class Meta:
        """Classe `ItemHierarquicoBase.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        abstract = True
        ordering = ["nome"]

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

        super().clean()
        referencia_lancamento = self.data_lancamento or timezone.localdate()
        if (
            self.data_entrega_estipulada
            and self.data_entrega_estipulada < referencia_lancamento
        ):
            raise ValidationError(
                {
                    "data_entrega_estipulada": (
                        "A data-alvo deve ser maior ou igual à data de lançamento."
                    )
                }
            )

    def save(self, *args, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        for key in (
            "_cache_filhos_evolucao",
            "_cache_tem_filhos_relacionados",
            "_cache_evolucao_automatica",
            "_cache_progresso_percentual",
            "_cache_ancestrais_marcadores",
            "_cache_marcadores_locais",
            "_cache_marcadores_efetivos",
        ):
            if hasattr(self, key):
                delattr(self, key)
        if not self.data_lancamento:
            self.data_lancamento = timezone.localdate()
        if not self.data_lancamento_em:
            self.data_lancamento_em = timezone.now()
        response = super().save(*args, **kwargs)
        self._invalidate_progress_cache_ascendentes()
        return response

    @property
    def prazo_total_dias(self):
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

        if not self.data_lancamento or not self.data_entrega_estipulada:
            return None
        return (self.data_entrega_estipulada - self.data_lancamento).days

    @property
    def dias_para_vencer(self):
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

        if not self.data_entrega_estipulada:
            return None
        hoje = timezone.localdate()
        return (self.data_entrega_estipulada - hoje).days

    @property
    def texto_prazo(self):
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

        dias = self.dias_para_vencer
        if dias is None:
            return "Prazo não definido"
        if dias > 0:
            return f"{dias} dias para vencer"
        if dias == 0:
            return "Vence hoje"
        return f"Vencido há {abs(dias)} dias"

    @property
    def progresso_prazo(self):
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

        if not self.data_entrega_estipulada:
            return 0

        agora = timezone.now()
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
            return 0
        if fim <= inicio or agora >= fim:
            return 100

        total_segundos = (fim - inicio).total_seconds()
        decorridos_segundos = (agora - inicio).total_seconds()
        percentual = (decorridos_segundos / total_segundos) * 100
        return max(0, min(round(percentual, 2), 100))

    def _filhos_para_evolucao(self):
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

        return []

    def _get_memoized(self, key, compute):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if hasattr(self, key):
            return getattr(self, key)
        value = compute()
        setattr(self, key, value)
        return value

    def _clear_progress_runtime_cache(self):
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

        for key in (
            "_cache_filhos_evolucao",
            "_cache_tem_filhos_relacionados",
            "_cache_evolucao_automatica",
            "_cache_progresso_percentual",
        ):
            if hasattr(self, key):
                delattr(self, key)

    def _pais_para_invalida_cache(self):
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

        return []

    def _invalidate_progress_cache_ascendentes(self, visitados=None):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if visitados is None:
            visitados = set()
        for pai in self._pais_para_invalida_cache():
            if not pai or not getattr(pai, "pk", None):
                continue
            chave = (pai._meta.label_lower, pai.pk)
            if chave in visitados:
                continue
            visitados.add(chave)
            pai._clear_progress_runtime_cache()
            pai._invalidate_progress_cache_ascendentes(visitados=visitados)

    @property
    def tem_filhos_relacionados(self):
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

        return len(self._filhos_para_evolucao()) > 0

    @property
    def evolucao_automatica(self):
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

        filhos = self._filhos_para_evolucao()
        if not filhos:
            return None
        return round(sum(item.progresso_percentual for item in filhos) / len(filhos), 2)

    @property
    def origem_evolucao(self):
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

        return "Automática" if self.tem_filhos_relacionados else "Manual"

    @property
    def progresso_percentual(self):
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

        if self.tem_filhos_relacionados:
            return self.evolucao_automatica or 0
        return float(self.evolucao_manual or 0)

    @property
    def progresso_classe(self):
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

        percentual = self.progresso_percentual
        if percentual <= 50:
            return "progresso-vermelho"
        if percentual <= 75:
            return "progresso-amarelo"
        return "progresso-verde"

    @property
    def prazo_classe(self):
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

        percentual = self.progresso_prazo
        if percentual <= 50:
            return "progresso-verde"
        if percentual <= 75:
            return "progresso-amarelo"
        return "progresso-vermelho"

    @property
    def delta_prazo_conclusao(self):
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

        return round(self.progresso_percentual - self.progresso_prazo, 2)

    @property
    def delta_texto(self):
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

        delta = self.delta_prazo_conclusao
        sinal = "+" if delta > 0 else ""
        return f"{sinal}{delta:.2f} p.p."

    @property
    def delta_classe(self):
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

        if not self.data_entrega_estipulada:
            return "delta-neutro"
        if self.delta_prazo_conclusao > 0:
            return "delta-positivo"
        if self.delta_prazo_conclusao < 0:
            return "delta-negativo"
        return "delta-neutro"

    @property
    def progresso_snapshot(self):
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

        prazo_percentual = float(self.progresso_prazo or 0)
        conclusao_percentual = float(self.progresso_percentual or 0)
        delta = round(conclusao_percentual - prazo_percentual, 2)
        sinal = "+" if delta > 0 else ""
        if not self.data_entrega_estipulada:
            delta_classe = "delta-neutro"
        elif delta > 0:
            delta_classe = "delta-positivo"
        elif delta < 0:
            delta_classe = "delta-negativo"
        else:
            delta_classe = "delta-neutro"
        return {
            "titulo_conclusao": "Alcance/Conclusão",
            "prazo_percentual": prazo_percentual,
            "prazo_classe": self.prazo_classe,
            "conclusao_percentual": conclusao_percentual,
            "conclusao_classe": self.progresso_classe,
            "delta_classe": delta_classe,
            "delta_texto": f"{sinal}{delta:.2f} p.p.",
        }

    def _filhos_para_marcadores(self):
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

        return []

    def _pais_para_marcadores(self):
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

        return []

    def _coletar_ancestrais_marcadores(self):
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

        visitados = set()
        itens = []

        def _visitar(obj):
            """Executa uma rotina de apoio ao domínio de Sala de Situação.

    Contexto arquitetural:
    - Encapsula uma regra reutilizável para evitar duplicação entre camadas.
    - Deve ser interpretada em conjunto com os pontos de chamada no fluxo.

    Parâmetros:
    - `obj`.

    Retorno:
    - Valor calculado, objeto de domínio, coleção ORM ou estrutura de apoio
      conforme a responsabilidade desta função.
    """

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

        cache_vinculos = getattr(self, "_prefetched_objects_cache", {}).get("marcadores_vinculos")
        if cache_vinculos is not None:
            marcador_por_id = {}
            for vinculo in cache_vinculos:
                marcador = getattr(vinculo, "marcador", None)
                if marcador and marcador.ativo:
                    marcador_por_id[marcador.id] = marcador
            content_type = ContentType.objects.get_for_model(self.__class__)
            automaticos = Marcador.objects.filter(
                ativo=True,
                vinculos_automaticos_grupo_itens__content_type=content_type,
                vinculos_automaticos_grupo_itens__object_id=self.pk,
            )
            for marcador in automaticos:
                marcador_por_id[marcador.id] = marcador
            return sorted(
                marcador_por_id.values(),
                key=lambda item: (item.nome or "").lower(),
            )

        content_type = ContentType.objects.get_for_model(self.__class__)
        manuais = Marcador.objects.filter(
            ativo=True,
            vinculos_itens__content_type=content_type,
            vinculos_itens__object_id=self.pk,
        )
        automaticos = Marcador.objects.filter(
            ativo=True,
            vinculos_automaticos_grupo_itens__content_type=content_type,
            vinculos_automaticos_grupo_itens__object_id=self.pk,
        )
        return list((manuais | automaticos).distinct().order_by("nome"))

    @property
    def marcadores_efetivos(self):
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

        marcador_por_id = {}
        for marcador in self.marcadores_locais:
            marcador_por_id[marcador.id] = marcador
        for item in self._coletar_ancestrais_marcadores():
            for marcador in item.marcadores_locais:
                marcador_por_id[marcador.id] = marcador
        return sorted(marcador_por_id.values(), key=lambda item: (item.nome or "").lower())

    def definir_marcadores_locais_por_ids(self, ids):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if not self.pk:
            return
        for key in ("_cache_marcadores_locais", "_cache_marcadores_efetivos", "_cache_ancestrais_marcadores"):
            if hasattr(self, key):
                delattr(self, key)
        content_type = ContentType.objects.get_for_model(self.__class__)
        ids_desejados = {int(item_id) for item_id in (ids or []) if str(item_id).isdigit()}
        ids_validos = set(
            Marcador.objects.filter(id__in=ids_desejados, ativo=True).values_list("id", flat=True)
        )

        existentes = set(
            MarcadorVinculoItem.objects.filter(
                content_type=content_type,
                object_id=self.pk,
            ).values_list("marcador_id", flat=True)
        )
        novos = ids_validos - existentes
        removidos = existentes - ids_validos

        if removidos:
            MarcadorVinculoItem.objects.filter(
                content_type=content_type,
                object_id=self.pk,
                marcador_id__in=removidos,
            ).delete()
        for marcador_id in novos:
            MarcadorVinculoItem.objects.create(
                content_type=content_type,
                object_id=self.pk,
                marcador_id=marcador_id,
            )


class IndicadorBase(ItemHierarquicoBase):
    """Classe `IndicadorBase` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    class TipoIndicador(models.TextChoices):
        """Classe `IndicadorBase.TipoIndicador` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        PROCESSUAL = "PROCESSUAL", "Processual"
        MATEMATICO = "MATEMATICO", "Matemático"
        MATEMATICO_ACUMULATIVO = "MATEMATICO_ACUMULATIVO", "Matemático acumulativo"

    class PeriodicidadeMonitoramento(models.TextChoices):
        """Classe `IndicadorBase.PeriodicidadeMonitoramento` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        SEMANAL = "SEMANAL", "Semanal"
        QUINZENAL = "QUINZENAL", "Quinzenal"
        MENSAL = "MENSAL", "Mensal"
        TRIMESTRAL = "TRIMESTRAL", "Trimestral"
        SEMESTRAL = "SEMESTRAL", "Semestral"
        ANUAL = "ANUAL", "Anual"

    tipo_indicador = models.CharField(
        "Tipo de indicador",
        max_length=30,
        choices=TipoIndicador.choices,
        default=TipoIndicador.PROCESSUAL,
    )
    meta_valor = models.DecimalField(
        "Valor da meta",
        max_digits=14,
        decimal_places=2,
        default=Decimal("100.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    meta_unidade_medida = models.CharField(
        "Unidade de medida da meta",
        max_length=40,
        default="%",
    )
    formula_expressao = models.TextField(
        "Fórmula matemática",
        blank=True,
        help_text="Use variáveis por nome e operadores + - * /, por exemplo: (A + B) / C",
    )
    formula_estrutura = models.JSONField(
        "Estrutura da fórmula",
        default=list,
        blank=True,
    )
    valor_atual = models.DecimalField(
        "Valor atual do indicador",
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="%(class)s_indicadores_criados_sala",
        null=True,
        blank=True,
    )

    class Meta:
        """Classe `IndicadorBase.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        abstract = True

    @property
    def eh_indicador_matematico(self):
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

        return self.tipo_indicador in {
            self.TipoIndicador.MATEMATICO,
            self.TipoIndicador.MATEMATICO_ACUMULATIVO,
        }

    @property
    def eh_indicador_matematico_acumulativo(self):
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

        return self.tipo_indicador == self.TipoIndicador.MATEMATICO_ACUMULATIVO

    def periodicidade_efetiva_variavel(self, variavel):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        periodicidade_variavel = getattr(variavel, "periodicidade_monitoramento", "") or ""
        return periodicidade_variavel

    def variavel_prevista_no_ciclo(self, variavel, ciclo):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if not self.eh_indicador_matematico:
            return False
        if not variavel or not ciclo or getattr(ciclo, "variavel_id", None) != getattr(variavel, "id", None):
            return False
        periodicidade = self.periodicidade_efetiva_variavel(variavel)
        if not periodicidade:
            return False
        return True

    def _build_formula_estrutura(self):
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

        if not self.formula_expressao:
            return []
        formula = self.formula_expressao.strip()
        return re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[\d]+(?:\.\d+)?|[()+\-*/]", formula)

    def nomes_variaveis_formula(self):
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

        if not self.formula_expressao:
            return []
        tree = ast.parse(self.formula_expressao.strip(), mode="eval")
        nomes = sorted({node.id for node in ast.walk(tree) if isinstance(node, ast.Name)})
        return nomes

    def _validar_formula(self):
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

        if not self.formula_expressao:
            return
        formula = self.formula_expressao.strip()
        try:
            tree = ast.parse(formula, mode="eval")
        except SyntaxError as exc:
            raise ValidationError({"formula_expressao": f"Fórmula inválida: {exc.msg}"}) from exc

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
                    {"formula_expressao": "A fórmula permite apenas variáveis, números e operadores + - * /."}
                )
            if isinstance(node, ast.Name) and not _FORMULA_VAR_RE.match(node.id):
                raise ValidationError({"formula_expressao": f"Nome de variável inválido: {node.id}"})

    def _eval_formula_node(self, node, variaveis):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if isinstance(node, ast.Expression):
            return self._eval_formula_node(node.body, variaveis)
        if isinstance(node, ast.Constant):
            return Decimal(str(node.value))
        if isinstance(node, ast.Name):
            if node.id not in variaveis:
                raise ValidationError(f"Variável '{node.id}' sem valor informado no ciclo.")
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
                    raise ValidationError("Divisão por zero na fórmula.")
                return esquerda / direita
        raise ValidationError("Expressão da fórmula não suportada.")

    def avaliar_formula(self, valores_variaveis):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if not self.formula_expressao:
            raise ValidationError("Fórmula não informada.")
        tree = ast.parse(self.formula_expressao.strip(), mode="eval")
        return self._eval_formula_node(tree, valores_variaveis)

    def data_fim_monitoramento(self):
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

        return None

    def gerar_ciclos_monitoramento(self):
        # Mantido para compatibilidade com chamadas existentes.
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

        if not self.eh_indicador_matematico or not self.pk:
            return
        content_type = ContentType.objects.get_for_model(self.__class__)
        variaveis = IndicadorVariavel.objects.filter(
            content_type=content_type,
            object_id=self.pk,
            origem_reaproveitada=False,
        )
        for variavel in variaveis:
            variavel.gerar_ciclos_monitoramento()

    def recalc_valor_atual_por_ciclos(self):
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

        if not self.eh_indicador_matematico:
            return
        content_type = ContentType.objects.get_for_model(self.__class__)
        ultimo_valor = (
            IndicadorCicloValor.objects.filter(
                variavel__content_type=content_type,
                variavel__object_id=self.pk,
            )
            .order_by("-ciclo__periodo_fim", "-atualizado_em", "-id")
            .first()
        )
        if not ultimo_valor:
            self.valor_atual = None
            return
        self.recalcular_resultado_por_data(ultimo_valor.ciclo.periodo_fim)

    def _valor_variavel_por_data(self, variavel, data_referencia):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if variavel.origem_reaproveitada and variavel.variavel_origem_id:
            if self.eh_indicador_matematico_acumulativo:
                return (
                    IndicadorCicloValor.objects.filter(
                        variavel_id=variavel.variavel_origem_id,
                        ciclo__periodo_fim__lte=data_referencia,
                    ).aggregate(total=models.Sum("valor"))["total"]
                    or Decimal("0")
                )
            ultimo = (
                IndicadorCicloValor.objects.filter(
                    variavel_id=variavel.variavel_origem_id,
                    ciclo__periodo_fim__lte=data_referencia,
                )
                .order_by("-ciclo__periodo_fim", "-atualizado_em", "-id")
                .first()
            )
            if not ultimo:
                raise ValidationError(f"Variável '{variavel.nome}' sem valor disponível para reuso global.")
            return ultimo.valor

        if self.eh_indicador_matematico_acumulativo:
            return (
                IndicadorCicloValor.objects.filter(
                    variavel=variavel,
                    ciclo__periodo_fim__lte=data_referencia,
                ).aggregate(total=models.Sum("valor"))["total"]
                or Decimal("0")
            )

        ultimo_local = (
            IndicadorCicloValor.objects.filter(
                variavel=variavel,
                ciclo__periodo_fim__lte=data_referencia,
            )
            .order_by("-ciclo__periodo_fim", "-atualizado_em", "-id")
            .first()
        )
        if not ultimo_local:
            raise ValidationError(f"Variável '{variavel.nome}' sem valor informado até {data_referencia:%d/%m/%Y}.")
        return ultimo_local.valor

    def recalcular_resultado_por_data(self, data_referencia):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if not self.eh_indicador_matematico:
            return None
        content_type = ContentType.objects.get_for_model(self.__class__)
        variaveis = list(
            IndicadorVariavel.objects.filter(
                content_type=content_type,
                object_id=self.pk,
            ).order_by("ordem", "nome")
        )
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

    def sincronizar_variaveis_da_formula(self):
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

        if not self.eh_indicador_matematico or not self.pk:
            return []
        content_type = ContentType.objects.get_for_model(self.__class__)
        nomes = self.nomes_variaveis_formula()
        criadas = []
        for ordem, nome in enumerate(nomes, start=1):
            _, was_created = IndicadorVariavel.objects.get_or_create(
                content_type=content_type,
                object_id=self.pk,
                nome=nome,
                defaults={
                    "descricao": f"Variável '{nome}' do indicador {self.nome}",
                    "tipo_numerico": IndicadorVariavel.TipoNumerico.DECIMAL,
                    "unidade_medida": self.meta_unidade_medida or "%",
                    "ordem": ordem,
                },
            )
            if was_created:
                criadas.append(nome)
        return criadas

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

        super().clean()
        if self.eh_indicador_matematico:
            if not self.formula_expressao:
                raise ValidationError({"formula_expressao": "Fórmula é obrigatória para indicador matemático."})
            self._validar_formula()
            if self.pk:
                content_type = ContentType.objects.get_for_model(self.__class__)
                variaveis_existentes = set(
                    IndicadorVariavel.objects.filter(
                        content_type=content_type,
                        object_id=self.pk,
                    ).values_list("nome", flat=True)
                )
                variaveis_formula = set(self.nomes_variaveis_formula())
                novas_variaveis = sorted(variaveis_formula - variaveis_existentes)
                if novas_variaveis:
                    raise ValidationError(
                        {
                            "formula_expressao": (
                                "Não é permitido lançar novas variáveis após a criação do indicador. "
                                f"Variáveis novas detectadas: {', '.join(novas_variaveis)}."
                            )
                        }
                    )
            self.evolucao_manual = 0
        else:
            self.formula_expressao = ""
            self.formula_estrutura = []
            self.valor_atual = None

    def save(self, *args, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        formula_alterada = False
        if self.pk:
            update_fields = kwargs.get("update_fields")
            if update_fields is None or "formula_expressao" in update_fields:
                anterior = self.__class__.objects.filter(pk=self.pk).only("formula_expressao").first()
                if anterior:
                    formula_alterada = (anterior.formula_expressao or "") != (self.formula_expressao or "")

        self.formula_estrutura = self._build_formula_estrutura() if self.formula_expressao else []
        response = super().save(*args, **kwargs)

        if formula_alterada and self.eh_indicador_matematico:
            self.recalc_valor_atual_por_ciclos()
        return response

    @property
    def atingimento_meta_percentual(self):
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

        if not self.meta_valor:
            return 0
        if self.valor_atual is None:
            return 0
        percentual = (Decimal(self.valor_atual) / Decimal(self.meta_valor)) * 100
        return float(max(Decimal("0"), min(percentual, Decimal("100"))))

    @property
    def desempenho_meta_classe(self):
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

        percentual = self.atingimento_meta_percentual
        if percentual < 50:
            return "progresso-vermelho"
        if percentual < 75:
            return "progresso-amarelo"
        return "progresso-verde"

    @property
    def origem_evolucao(self):
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

        if self.eh_indicador_matematico:
            return "Matemática"
        return super().origem_evolucao

    @property
    def progresso_percentual(self):
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

        if self.eh_indicador_matematico:
            return self.atingimento_meta_percentual
        return super().progresso_percentual

    @property
    def progresso_snapshot(self):
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

        snapshot = super().progresso_snapshot
        if not self.eh_indicador_matematico:
            return snapshot
        conclusao_percentual = float(self.atingimento_meta_percentual or 0)
        prazo_percentual = float(self.progresso_prazo or 0)
        delta = round(conclusao_percentual - prazo_percentual, 2)
        sinal = "+" if delta > 0 else ""
        if not self.data_entrega_estipulada:
            delta_classe = "delta-neutro"
        elif delta > 0:
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


class IndicadorEstrategico(IndicadorBase):
    """Classe `IndicadorEstrategico` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    class Meta:
        """Classe `IndicadorEstrategico.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        ordering = ["nome"]

    @property
    def indicadores_taticos_relacionados(self):
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

        return self.indicadores_taticos.all().distinct()

    def _filhos_para_evolucao(self):
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

        if self.eh_indicador_matematico:
            return []
        # Fluxo atual: IE agrega progresso por processos vinculados diretamente.
        # Mantém fallback legado via IT para cenários antigos sem migração completa.
        processos = list(self.processos.all().distinct())
        if processos:
            return processos
        return list(self.indicadores_taticos_relacionados)

    def _pais_para_marcadores(self):
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

        return []

    def _pais_para_invalida_cache(self):
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

        return []

    def data_fim_monitoramento(self):
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

        return self.data_entrega_estipulada

    def sincronizar_estrutura_processual_monitoramento(self):
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

        if not self.eh_indicador_matematico or not self.pk:
            return
        content_type = ContentType.objects.get_for_model(self.__class__)
        variaveis_locais = list(
            IndicadorVariavel.objects.filter(
                content_type=content_type,
                object_id=self.pk,
                origem_reaproveitada=False,
            ).order_by("ordem", "nome")
        )
        if not variaveis_locais:
            return
        for variavel in variaveis_locais:
            variavel.gerar_ciclos_monitoramento()
        ciclos_por_variavel = {
            variavel.id: list(variavel.ciclos_monitoramento.order_by("numero"))
            for variavel in variaveis_locais
        }
        grupos_indicador_ids = set()
        for variavel in variaveis_locais:
            nome_variavel = variavel.nome
            grupos_variavel_ids = set(variavel.grupos_monitoramento.values_list("id", flat=True))
            grupos_indicador_ids.update(grupos_variavel_ids)
            nome_processo = f'Monitoramento de "{nome_variavel}" do indicador "{self.nome}"'
            processo, _ = Processo.objects.get_or_create(
                nome=nome_processo,
                defaults={
                    "descricao": f"Processo automático de coleta da variável {nome_variavel}.",
                    "data_entrega_estipulada": self.data_entrega_estipulada,
                    "origem_automatica_monitoramento": True,
                },
            )
            if not processo.origem_automatica_monitoramento:
                processo.origem_automatica_monitoramento = True
                processo.save(update_fields=["origem_automatica_monitoramento", "atualizado_em"])
            processo.indicadores_estrategicos.add(self)

            entregas_variavel = []
            for ciclo in ciclos_por_variavel.get(variavel.id, []):
                sufixo_inicial = " (Inicial)" if ciclo.eh_inicial else ""
                entrega_nome = f'Registro de monitoramento "{nome_variavel}" - {ciclo.periodo_inicio:%m/%Y}{sufixo_inicial}'
                entrega, _ = Entrega.objects.get_or_create(
                    nome=entrega_nome,
                    defaults={
                        "descricao": (
                            f'Alimentação da variável {nome_variavel} para {ciclo.titulo}. '
                            "Entrega automática de monitoramento."
                        ),
                        "data_entrega_estipulada": ultimo_dia_util_mes(ciclo.periodo_fim),
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
                if variavel and entrega.variavel_monitoramento_id != variavel.id:
                    entrega.variavel_monitoramento = variavel
                    alterou = True
                prazo_ciclo = ultimo_dia_util_mes(ciclo.periodo_fim)
                if entrega.data_entrega_estipulada != prazo_ciclo:
                    entrega.data_entrega_estipulada = prazo_ciclo
                    alterou = True
                if entrega.periodo_inicio != ciclo.periodo_inicio:
                    entrega.periodo_inicio = ciclo.periodo_inicio
                    alterou = True
                if entrega.periodo_fim != ciclo.periodo_fim:
                    entrega.periodo_fim = ciclo.periodo_fim
                    alterou = True
                if alterou:
                    entrega.save(
                        update_fields=[
                            "ciclo_monitoramento",
                            "variavel_monitoramento",
                            "data_entrega_estipulada",
                            "periodo_inicio",
                            "periodo_fim",
                            "atualizado_em",
                        ]
                    )
                entrega.processos.add(processo)
                entregas_variavel.append(entrega)
            _sincronizar_marcadores_automaticos_grupo_item(processo, grupos_variavel_ids)
            for entrega in entregas_variavel:
                _sincronizar_marcadores_automaticos_grupo_item(entrega, grupos_variavel_ids)
        _sincronizar_marcadores_automaticos_grupo_item(self, grupos_indicador_ids)

    def __str__(self):
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

        return self.nome


class IndicadorTatico(IndicadorBase):
    """Classe `IndicadorTatico` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    indicadores_estrategicos = models.ManyToManyField(
        IndicadorEstrategico,
        related_name="indicadores_taticos",
        blank=True,
    )

    class Meta:
        """Classe `IndicadorTatico.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        ordering = ["nome"]

    def _filhos_para_evolucao(self):
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

        if self.eh_indicador_matematico:
            return []
        return list(self.processos.all())

    def _pais_para_marcadores(self):
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

        return list(self.indicadores_estrategicos.all())

    def _pais_para_invalida_cache(self):
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

        return list(self.indicadores_estrategicos.all())

    @property
    def indicadores_estrategicos_herdados(self):
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

        return self.indicadores_estrategicos.all().order_by("nome")

    def data_fim_monitoramento(self):
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

        return self.data_entrega_estipulada

    def sincronizar_estrutura_processual_monitoramento(self):
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

        if not self.eh_indicador_matematico or not self.pk:
            return
        content_type = ContentType.objects.get_for_model(self.__class__)
        variaveis_locais = list(
            IndicadorVariavel.objects.filter(
                content_type=content_type,
                object_id=self.pk,
                origem_reaproveitada=False,
            ).order_by("ordem", "nome")
        )
        if not variaveis_locais:
            return
        for variavel in variaveis_locais:
            variavel.gerar_ciclos_monitoramento()
        ciclos_por_variavel = {
            variavel.id: list(variavel.ciclos_monitoramento.order_by("numero"))
            for variavel in variaveis_locais
        }
        grupos_indicador_ids = set()
        for variavel in variaveis_locais:
            nome_variavel = variavel.nome
            grupos_variavel_ids = set(variavel.grupos_monitoramento.values_list("id", flat=True))
            grupos_indicador_ids.update(grupos_variavel_ids)
            nome_processo = f'Monitoramento de "{nome_variavel}" do indicador "{self.nome}"'
            processo, _ = Processo.objects.get_or_create(
                nome=nome_processo,
                defaults={
                    "descricao": f"Processo automático de coleta da variável {nome_variavel}.",
                    "data_entrega_estipulada": self.data_entrega_estipulada,
                    "origem_automatica_monitoramento": True,
                },
            )
            if not processo.origem_automatica_monitoramento:
                processo.origem_automatica_monitoramento = True
                processo.save(update_fields=["origem_automatica_monitoramento", "atualizado_em"])
            processo.indicadores_taticos.add(self)
            if self.indicadores_estrategicos.exists():
                processo.indicadores_estrategicos.add(*self.indicadores_estrategicos.all())

            entregas_variavel = []
            for ciclo in ciclos_por_variavel.get(variavel.id, []):
                sufixo_inicial = " (Inicial)" if ciclo.eh_inicial else ""
                entrega_nome = f'Registro de monitoramento "{nome_variavel}" - {ciclo.periodo_inicio:%m/%Y}{sufixo_inicial}'
                entrega, _ = Entrega.objects.get_or_create(
                    nome=entrega_nome,
                    defaults={
                        "descricao": (
                            f'Alimentação da variável {nome_variavel} para {ciclo.titulo}. '
                            "Entrega automática de monitoramento."
                        ),
                        "data_entrega_estipulada": ultimo_dia_util_mes(ciclo.periodo_fim),
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
                if variavel and entrega.variavel_monitoramento_id != variavel.id:
                    entrega.variavel_monitoramento = variavel
                    alterou = True
                prazo_ciclo = ultimo_dia_util_mes(ciclo.periodo_fim)
                if entrega.data_entrega_estipulada != prazo_ciclo:
                    entrega.data_entrega_estipulada = prazo_ciclo
                    alterou = True
                if entrega.periodo_inicio != ciclo.periodo_inicio:
                    entrega.periodo_inicio = ciclo.periodo_inicio
                    alterou = True
                if entrega.periodo_fim != ciclo.periodo_fim:
                    entrega.periodo_fim = ciclo.periodo_fim
                    alterou = True
                if alterou:
                    entrega.save(
                        update_fields=[
                            "ciclo_monitoramento",
                            "variavel_monitoramento",
                            "data_entrega_estipulada",
                            "periodo_inicio",
                            "periodo_fim",
                            "atualizado_em",
                        ]
                    )
                entrega.processos.add(processo)
                entregas_variavel.append(entrega)
            _sincronizar_marcadores_automaticos_grupo_item(processo, grupos_variavel_ids)
            for entrega in entregas_variavel:
                _sincronizar_marcadores_automaticos_grupo_item(entrega, grupos_variavel_ids)
        _sincronizar_marcadores_automaticos_grupo_item(self, grupos_indicador_ids)

    def __str__(self):
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

        return self.nome


class Processo(ItemHierarquicoBase):
    """Classe `Processo` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    indicadores_taticos = models.ManyToManyField(
        IndicadorTatico,
        related_name="processos",
        blank=True,
    )
    indicadores_estrategicos = models.ManyToManyField(
        IndicadorEstrategico,
        related_name="processos",
        blank=False,
    )
    origem_automatica_monitoramento = models.BooleanField(default=False)

    class Meta:
        """Classe `Processo.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        ordering = ["nome"]

    def _filhos_para_evolucao(self):
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

        return list(self.entregas.all())

    def _pais_para_marcadores(self):
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

        pais = list(self.indicadores_estrategicos.all())
        # Processos de monitoramento podem existir sem IT pai; nesses casos,
        # herdam marcadores do indicador dono da variável monitorada via entregas.
        for entrega in self.entregas.select_related("variavel_monitoramento__content_type").all():
            variavel = getattr(entrega, "variavel_monitoramento", None)
            if not variavel:
                continue
            indicador_origem = getattr(variavel, "indicador", None)
            if indicador_origem and getattr(indicador_origem, "pk", None) and indicador_origem not in pais:
                pais.append(indicador_origem)
        return pais

    def _pais_para_invalida_cache(self):
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

        return list(self.indicadores_estrategicos.all())

    @property
    def indicadores_estrategicos_herdados(self):
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

        return self.indicadores_estrategicos.all().distinct().order_by("nome")

    def __str__(self):
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

        return self.nome


class ProcessoMarcador(models.Model):
    """Classe `ProcessoMarcador` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    processo = models.ForeignKey(
        Processo,
        on_delete=models.CASCADE,
        related_name="marcadores",
    )
    texto = models.CharField("Marcador", max_length=60)
    cor = models.CharField(max_length=7, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Classe `ProcessoMarcador.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        ordering = ["texto"]
        unique_together = ("processo", "texto")

    def save(self, *args, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.texto = (self.texto or "").strip()
        if not self.cor:
            self.cor = secrets.choice(_MARCADORES_PALETA)
        return super().save(*args, **kwargs)

    def __str__(self):
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

        return self.texto


class Entrega(ItemHierarquicoBase):
    """Classe `Entrega` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    processos = models.ManyToManyField(
        Processo,
        related_name="entregas",
        blank=False,
    )
    ciclo_monitoramento = models.ForeignKey(
        "sala_situacao.IndicadorVariavelCicloMonitoramento",
        on_delete=models.SET_NULL,
        related_name="entregas_monitoramento",
        null=True,
        blank=True,
    )
    variavel_monitoramento = models.ForeignKey(
        "sala_situacao.IndicadorVariavel",
        on_delete=models.SET_NULL,
        related_name="entregas_monitoramento",
        null=True,
        blank=True,
    )
    valor_monitoramento = models.DecimalField(
        "Valor da variável no ciclo",
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    evidencia_monitoramento = models.FileField(
        "Evidência",
        upload_to="sala_situacao/evidencias/%Y/%m/",
        null=True,
        blank=True,
    )
    monitorado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="entregas_monitoradas",
        null=True,
        blank=True,
    )
    monitorado_em = models.DateTimeField(null=True, blank=True)
    periodo_inicio = models.DateField(null=True, blank=True)
    periodo_fim = models.DateField(null=True, blank=True)

    class Meta:
        """Classe `Entrega.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        ordering = ["nome"]
        permissions = (
            ("monitorar_entrega", "Pode monitorar entrega"),
        )

    @property
    def eh_entrega_monitoramento(self):
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

        return bool(self.ciclo_monitoramento_id and self.variavel_monitoramento_id)

    @property
    def marcadores_herdados(self):
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

        return self.marcadores_efetivos

    def _pais_para_marcadores(self):
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

        pais = list(self.processos.all())
        if self.variavel_monitoramento_id:
            indicador_origem = getattr(self.variavel_monitoramento, "indicador", None)
            if indicador_origem and getattr(indicador_origem, "pk", None):
                if indicador_origem not in pais:
                    pais.append(indicador_origem)
        return pais

    def _pais_para_invalida_cache(self):
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

        return list(self.processos.all())

    def save(self, *args, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        referencia = (
            self.ciclo_monitoramento.periodo_inicio
            if self.ciclo_monitoramento_id and self.ciclo_monitoramento and self.ciclo_monitoramento.periodo_inicio
            else (
                self.data_entrega_estipulada
                or self.data_lancamento
                or timezone.localdate()
            )
        )
        self.periodo_inicio = primeiro_dia_mes(referencia)
        self.periodo_fim = ultimo_dia_mes(referencia)
        if not self.data_entrega_estipulada:
            self.data_entrega_estipulada = ultimo_dia_util_mes(referencia)
        if self.eh_entrega_monitoramento:
            self.data_entrega_estipulada = ultimo_dia_util_mes(self.periodo_fim)
        return super().save(*args, **kwargs)

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

        super().clean()
        if self.periodo_inicio and not self.periodo_fim:
            raise ValidationError({"periodo_fim": "Informe o fim do período mensal."})
        if self.periodo_fim and not self.periodo_inicio:
            raise ValidationError({"periodo_inicio": "Informe o início do período mensal."})
        if not self.periodo_inicio or not self.periodo_fim:
            return
        if self.periodo_inicio.day != 1:
            raise ValidationError({"periodo_inicio": "O período deve iniciar no dia 1 do mês."})
        fim_esperado = ultimo_dia_mes(self.periodo_inicio)
        if self.periodo_fim != fim_esperado:
            raise ValidationError(
                {"periodo_fim": "O período deve terminar no último dia do mês de referência."}
            )
        if self.periodo_inicio > self.periodo_fim:
            raise ValidationError({"periodo_inicio": "Período inválido."})
        if self.data_entrega_estipulada and (
            self.data_entrega_estipulada.month != self.periodo_inicio.month
            or self.data_entrega_estipulada.year != self.periodo_inicio.year
        ):
            raise ValidationError(
                {"data_entrega_estipulada": "A data-alvo deve estar no mesmo mês do período da entrega."}
            )

    def __str__(self):
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

        return self.nome


class IndicadorVariavel(models.Model):
    """Classe `IndicadorVariavel` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    class TipoNumerico(models.TextChoices):
        """Classe `IndicadorVariavel.TipoNumerico` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        INTEIRO = "INTEIRO", "Inteiro"
        DECIMAL = "DECIMAL", "Decimal"

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="sala_situacao_variaveis",
    )
    object_id = models.PositiveIntegerField()
    indicador = GenericForeignKey("content_type", "object_id")
    nome = models.CharField(max_length=60)
    descricao = models.TextField(blank=True)
    tipo_numerico = models.CharField(
        max_length=10,
        choices=TipoNumerico.choices,
        default=TipoNumerico.DECIMAL,
    )
    unidade_medida = models.CharField(max_length=40, default="%")
    periodicidade_monitoramento = models.CharField(
        "Periodicidade de monitoramento da variável",
        max_length=20,
        choices=IndicadorBase.PeriodicidadeMonitoramento.choices,
        blank=False,
        help_text="Periodicidade obrigatória para geração do monitoramento da variável.",
    )
    variavel_origem = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="variaveis_reutilizadas",
    )
    origem_reaproveitada = models.BooleanField(default=False)
    grupos_monitoramento = models.ManyToManyField(
        Group,
        related_name="variaveis_monitoramento_sala",
        blank=True,
    )
    ordem = models.PositiveSmallIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Classe `IndicadorVariavel.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        ordering = ["ordem", "nome"]
        unique_together = ("content_type", "object_id", "nome")
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(origem_reaproveitada=False, variavel_origem__isnull=True)
                    | models.Q(origem_reaproveitada=True, variavel_origem__isnull=False)
                ),
                name="ck_indicadorvariavel_reuso_consistente",
            ),
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

        super().clean()
        if self.nome:
            nome_limpo = self.nome.strip()
            if not _FORMULA_VAR_RE.match(nome_limpo):
                raise ValidationError({"nome": "Use apenas letras, números e '_' iniciando por letra."})
            self.nome = nome_limpo
        if self.indicador and not getattr(self.indicador, "eh_indicador_matematico", False):
            raise ValidationError("Variáveis só podem ser cadastradas em indicadores matemáticos.")
        if not self.periodicidade_monitoramento:
            raise ValidationError({"periodicidade_monitoramento": "Periodicidade da variável é obrigatória."})
        if self.variavel_origem_id and self.variavel_origem_id == self.pk:
            raise ValidationError({"variavel_origem": "A variável de origem deve ser diferente da variável atual."})
        if self.origem_reaproveitada and not self.variavel_origem_id:
            raise ValidationError({"variavel_origem": "Selecione a variável de origem para reuso."})
        if not self.origem_reaproveitada:
            self.variavel_origem = None

    def __str__(self):
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

        return f"{self.nome} ({self.unidade_medida})"

    def gerar_ciclos_monitoramento(self):
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

        indicador = self.indicador
        if not indicador or not getattr(indicador, "eh_indicador_matematico", False):
            return
        data_fim = indicador.data_fim_monitoramento()
        if not data_fim:
            return
        inicio_referencia = indicador.data_lancamento or timezone.localdate()
        inicio_ancora = primeiro_dia_mes(inicio_referencia)
        fim_ancora = primeiro_dia_mes(data_fim)
        if inicio_ancora > fim_ancora:
            return

        periodicidade = (self.periodicidade_monitoramento or "").upper()
        passo_meses = passo_meses_periodicidade(periodicidade)
        exige_ciclo_inicial = periodicidade in {"TRIMESTRAL", "SEMESTRAL", "ANUAL"}

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
            if ciclo.status == IndicadorVariavelCicloMonitoramento.Status.LEGADO:
                ciclo.status = IndicadorVariavelCicloMonitoramento.Status.ABERTO
                campos_update.append("status")
            if campos_update:
                ciclo.save(update_fields=campos_update + ["atualizado_em"])

        for numero_existente, ciclo in existentes.items():
            if numero_existente in numeros_desejados:
                continue
            possui_valor = ciclo.valores.exists() or ciclo.historico_registros.exists()
            if possui_valor:
                if ciclo.status != IndicadorVariavelCicloMonitoramento.Status.LEGADO:
                    ciclo.status = IndicadorVariavelCicloMonitoramento.Status.LEGADO
                    ciclo.save(update_fields=["status", "atualizado_em"])
                continue
            ciclo.entregas_monitoramento.all().delete()
            ciclo.delete()


class IndicadorVariavelCicloMonitoramento(models.Model):
    """Classe `IndicadorVariavelCicloMonitoramento` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    class Status(models.TextChoices):
        """Classe `IndicadorVariavelCicloMonitoramento.Status` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        ABERTO = "ABERTO", "Aberto"
        FECHADO = "FECHADO", "Fechado"
        LEGADO = "LEGADO", "Legado"

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
        """Classe `IndicadorVariavelCicloMonitoramento.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        ordering = ["periodo_inicio", "numero"]
        unique_together = ("variavel", "numero")
        indexes = [
            models.Index(fields=["variavel", "periodo_fim"]),
        ]

    @property
    def indicador(self):
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

        return self.variavel.indicador

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

        super().clean()
        if self.periodo_inicio and self.periodo_inicio.day != 1:
            raise ValidationError({"periodo_inicio": "Ciclo deve iniciar no dia 1 do mês."})
        if self.periodo_inicio and self.periodo_fim and self.periodo_fim != ultimo_dia_mes(self.periodo_inicio):
            raise ValidationError({"periodo_fim": "Ciclo deve encerrar no último dia do mês."})
        if (
            self.eh_inicial
            and self.variavel_id
            and IndicadorVariavelCicloMonitoramento.objects.filter(
                variavel_id=self.variavel_id,
                eh_inicial=True,
            )
            .exclude(pk=self.pk)
            .exists()
        ):
            raise ValidationError({"eh_inicial": "A variável já possui ciclo inicial obrigatório."})

    @property
    def titulo(self):
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

        titulo = f"{self.variavel.nome} - {self.periodo_inicio:%m/%Y}"
        if self.eh_inicial:
            return f"{titulo} (Inicial)"
        return titulo

    def __str__(self):
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

        return self.titulo


class IndicadorCicloMonitoramento(models.Model):
    """Classe `IndicadorCicloMonitoramento` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    class Status(models.TextChoices):
        """Classe `IndicadorCicloMonitoramento.Status` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        ABERTO = "ABERTO", "Aberto"
        FECHADO = "FECHADO", "Fechado"

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="sala_situacao_ciclos",
    )
    object_id = models.PositiveIntegerField()
    indicador = GenericForeignKey("content_type", "object_id")
    numero = models.PositiveIntegerField()
    periodo_inicio = models.DateField()
    periodo_fim = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABERTO)
    valor_resultado = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Classe `IndicadorCicloMonitoramento.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        ordering = ["periodo_inicio", "numero"]
        unique_together = ("content_type", "object_id", "numero")

    @property
    def titulo(self):
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

        return f"Ciclo {self.numero} ({self.periodo_inicio:%d/%m/%Y} a {self.periodo_fim:%d/%m/%Y})"

    def valores_por_variavel(self):
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

        return {
            item.variavel.nome: item.valor
            for item in self.valores.select_related("variavel").all()
        }

    def valores_para_calculo(self):
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

        valores = self.valores_por_variavel()
        indicador = self.indicador
        if not indicador:
            return valores

        content_type = ContentType.objects.get_for_model(indicador.__class__)
        variaveis = list(
            IndicadorVariavel.objects.filter(
                content_type=content_type,
                object_id=indicador.pk,
            )
        )
        if not variaveis:
            return valores

        variaveis_faltantes = [variavel for variavel in variaveis if variavel.nome not in valores]
        if not variaveis_faltantes:
            return valores

        variaveis_reuso = [variavel for variavel in variaveis_faltantes if variavel.origem_reaproveitada]
        variaveis_locais = [variavel for variavel in variaveis_faltantes if not variavel.origem_reaproveitada]

        historico = (
            IndicadorCicloValor.objects.filter(
                variavel__in=variaveis_locais,
                ciclo__content_type=content_type,
                ciclo__object_id=indicador.pk,
                ciclo__numero__lt=self.numero,
            )
            .select_related("variavel", "ciclo")
            .order_by("variavel_id", "-ciclo__numero", "-atualizado_em")
        )
        ultima_por_variavel = {}
        for item in historico:
            if item.variavel_id in ultima_por_variavel:
                continue
            ultima_por_variavel[item.variavel_id] = item.valor

        for variavel in variaveis_locais:
            if variavel.id in ultima_por_variavel:
                valores[variavel.nome] = ultima_por_variavel[variavel.id]
        for variavel in variaveis_reuso:
            if not variavel.variavel_origem_id:
                raise ValidationError(f"Variável '{variavel.nome}' sem origem configurada para reuso.")
            ultimo_global = (
                IndicadorCicloValor.objects.filter(variavel_id=variavel.variavel_origem_id)
                .select_related("ciclo")
                .order_by("-ciclo__periodo_fim", "-atualizado_em", "-id")
                .first()
            )
            if not ultimo_global:
                raise ValidationError(
                    f"Variável '{variavel.nome}' sem valor disponível para reuso global."
                )
            valores[variavel.nome] = ultimo_global.valor
        return valores

    def valores_para_calculo_acumulativo(self):
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

        valores = {}
        indicador = self.indicador
        if not indicador:
            return valores

        content_type = ContentType.objects.get_for_model(indicador.__class__)
        variaveis = list(
            IndicadorVariavel.objects.filter(
                content_type=content_type,
                object_id=indicador.pk,
            )
        )
        for variavel in variaveis:
            if variavel.origem_reaproveitada and variavel.variavel_origem_id:
                acumulado = (
                    IndicadorCicloValor.objects.filter(
                        variavel_id=variavel.variavel_origem_id,
                        ciclo__periodo_fim__lte=self.periodo_fim,
                    ).aggregate(total=models.Sum("valor"))["total"]
                    or Decimal("0")
                )
            else:
                acumulado = (
                    IndicadorCicloValor.objects.filter(
                        variavel=variavel,
                        ciclo__content_type=content_type,
                        ciclo__object_id=indicador.pk,
                        ciclo__numero__lte=self.numero,
                    ).aggregate(total=models.Sum("valor"))["total"]
                    or Decimal("0")
                )
            valores[variavel.nome] = acumulado
        return valores

    @property
    def atingimento_meta_percentual(self):
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

        if not self.indicador or not getattr(self.indicador, "meta_valor", None):
            return 0
        if self.valor_resultado is None:
            return 0
        percentual = (Decimal(self.valor_resultado) / Decimal(self.indicador.meta_valor)) * 100
        return float(max(Decimal("0"), min(percentual, Decimal("100"))))

    @property
    def desempenho_meta_classe(self):
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

        percentual = self.atingimento_meta_percentual
        if percentual < 50:
            return "progresso-vermelho"
        if percentual < 75:
            return "progresso-amarelo"
        return "progresso-verde"

    def recalcular_resultado(self):
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

        indicador = self.indicador
        if not indicador or not indicador.eh_indicador_matematico:
            return None
        try:
            if indicador.eh_indicador_matematico_acumulativo:
                resultado = indicador.avaliar_formula(self.valores_para_calculo_acumulativo())
            else:
                resultado = indicador.avaliar_formula(self.valores_para_calculo())
        except ValidationError:
            return None
        self.valor_resultado = resultado
        self.save(update_fields=["valor_resultado", "atualizado_em"])
        indicador.valor_atual = resultado
        indicador.save(update_fields=["valor_atual", "atualizado_em"])
        return resultado

    def __str__(self):
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

        return self.titulo


class IndicadorCicloValor(models.Model):
    """Classe `IndicadorCicloValor` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    ciclo = models.ForeignKey(
        IndicadorVariavelCicloMonitoramento,
        on_delete=models.CASCADE,
        related_name="valores",
        null=True,
        blank=True,
    )
    variavel = models.ForeignKey(
        IndicadorVariavel,
        on_delete=models.CASCADE,
        related_name="valores_ciclo",
    )
    valor = models.DecimalField(max_digits=14, decimal_places=4)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sala_situacao_valores_atualizados",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Classe `IndicadorCicloValor.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        unique_together = ("ciclo", "variavel")

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

        super().clean()
        if self.ciclo.variavel_id != self.variavel_id:
            raise ValidationError("O ciclo deve pertencer à mesma variável do valor informado.")

    def save(self, *args, **kwargs):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        if self.variavel.tipo_numerico == IndicadorVariavel.TipoNumerico.INTEIRO:
            self.valor = Decimal(int(self.valor))
        response = super().save(*args, **kwargs)
        IndicadorCicloHistorico.objects.create(
            ciclo=self.ciclo,
            variavel=self.variavel,
            valor=self.valor,
            registrado_por=self.atualizado_por,
        )
        indicador = self.ciclo.indicador
        if indicador and hasattr(indicador, "recalcular_resultado_por_data"):
            try:
                indicador.recalcular_resultado_por_data(self.ciclo.periodo_fim)
            except ValidationError:
                # Fórmula incompleta no momento do lançamento: mantém valor_atual atual sem interromper salvamento.
                pass
        return response

    def __str__(self):
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

        return f"{self.ciclo} - {self.variavel.nome}: {self.valor}"


class IndicadorCicloHistorico(models.Model):
    """Classe `IndicadorCicloHistorico` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    ciclo = models.ForeignKey(
        IndicadorVariavelCicloMonitoramento,
        on_delete=models.CASCADE,
        related_name="historico_registros",
        null=True,
        blank=True,
    )
    variavel = models.ForeignKey(
        IndicadorVariavel,
        on_delete=models.CASCADE,
        related_name="historico_registros",
    )
    valor = models.DecimalField(max_digits=14, decimal_places=4)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sala_situacao_historicos_registrados",
    )
    registrado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Classe `IndicadorCicloHistorico.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        ordering = ["-registrado_em"]

    def __str__(self):
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

        return f"{self.ciclo} - {self.variavel.nome}: {self.valor} ({self.registrado_em:%d/%m/%Y %H:%M})"


class NotaItem(models.Model):
    """Classe `NotaItem` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="sala_situacao_notas",
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    texto = models.TextField("Nota")
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sala_situacao_notas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Classe `NotaItem.Meta` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

        ordering = ["-criado_em"]
        verbose_name = "Nota da Sala de Situação"
        verbose_name_plural = "Notas da Sala de Situação"

    def __str__(self):
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

        return f"Nota #{self.pk} - {self.content_type} {self.object_id}"


class NotaItemAnexo(models.Model):
    nota = models.ForeignKey(
        NotaItem,
        on_delete=models.CASCADE,
        related_name="anexos",
    )
    arquivo = models.FileField(upload_to="sala_situacao/notas/")
    nome_original = models.CharField(max_length=255, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Anexo da nota"
        verbose_name_plural = "Anexos das notas"

    def save(self, *args, **kwargs):
        if self.arquivo and not self.nome_original:
            self.nome_original = getattr(self.arquivo, "name", "") or ""
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nome_original or f"Anexo #{self.pk}"
