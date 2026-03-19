"""
Modelos de domínio do app `contratos`.

Este módulo define a entidade central de gestão contratual (`Contrato`)
e utilitários de calendário usados para cálculo de vigência.
Integra-se com:
- formulários (`forms.py`) para validação de entrada;
- views (`views.py`) para exibição e CRUD;
- app `diario_bordo` para criação automática de bloco em determinado status.
"""

from datetime import date

from django.db import models
from django.apps import apps

from empresas.models import Empresa


def add_months(value: date, months: int) -> date:
    """
    Soma meses a uma data preservando coerência de dia no calendário.

    Parâmetros:
    - `value`: data base.
    - `months`: quantidade de meses a adicionar (pode ser negativa).

    Retorno:
    - `date`: nova data ajustada.

    Regra de negócio:
    - quando o dia não existe no mês-alvo, usa o último dia válido.
    """

    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    day = min(value.day, _month_last_day(year, month))
    return date(year, month, day)


def _month_last_day(year: int, month: int) -> int:
    """
    Calcula último dia de um mês específico.

    Parâmetros:
    - `year`: ano da referência.
    - `month`: mês da referência.

    Retorno:
    - `int`: dia final do mês (28..31).
    """

    if month == 2:
        if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
            return 29
        return 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


class Contrato(models.Model):
    """
    Entidade que representa um contrato administrativo.

    Cada registro concentra dados de processo, empresa vinculada,
    objeto, status e prazos de vigência/prorrogação, além de valores.
    Também mantém rastreio de atualização (`atualizado_em/atualizado_por`).
    """

    class Status(models.TextChoices):
        """Estados de ciclo de vida do contrato."""

        ENCERRADO = "ENCERRADO", "Encerrado"
        VIGENTE = "VIGENTE", "Vigente"
        EM_CONTRATACAO = "EM_CONTRATACAO", "Em Contratacao"

    class Vigencia(models.IntegerChoices):
        """Faixas de vigência contratual suportadas na interface."""

        MESES_12 = 12, "12 meses"
        MESES_24 = 24, "24 meses"
        MESES_36 = 36, "36 meses"
        MESES_48 = 48, "48 meses"

    class ProrrogacaoMaxima(models.IntegerChoices):
        """Limites máximos de prorrogação previstos para o contrato."""

        MESES_60 = 60, "60 meses"
        MESES_120 = 120, "120 meses"

    nro_sei = models.CharField(max_length=120)
    link_processo = models.URLField("Link do processo", max_length=500, blank=True)
    nro_contrato = models.CharField(max_length=120, blank=True)
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="contratos",
        null=True,
        blank=True,
    )
    objeto = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.VIGENTE,
        blank=True,
    )
    valor_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    valor_mensal = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    data_inicial = models.DateField(null=True, blank=True)
    vigencia_meses = models.IntegerField(choices=Vigencia.choices, null=True, blank=True)
    data_fim = models.DateField(null=True, blank=True)
    prorrogacao_maxima_meses = models.IntegerField(
        choices=ProrrogacaoMaxima.choices, null=True, blank=True
    )
    atualizado_em = models.DateTimeField(auto_now=True)
    atualizado_por = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contratos_atualizados',
    )

    class Meta:
        """Ordena por data de fim mais recente e número de processo."""

        ordering = ["-data_fim", "nro_sei"]

    def save(self, *args, **kwargs):
        """
        Persiste contrato com regras automáticas de domínio.

        Parâmetros:
        - `*args`, `**kwargs`: argumentos padrão do `models.Model.save`.

        Regras de negócio:
        - calcula `data_fim` a partir de `data_inicial + vigencia` quando ausente;
        - identifica usuário corrente via thread-local para auditoria funcional;
        - ao transitar para `EM_CONTRATACAO`, cria automaticamente um
          bloco de trabalho no Diário de Bordo (se ainda inexistente).
        """

        status_anterior = None
        if self.pk:
            # Consulta pontual para detectar transição de status sem carregar
            # o objeto completo.
            status_anterior = (
                type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            )
        if self.data_inicial and self.vigencia_meses and not self.data_fim:
            self.data_fim = add_months(self.data_inicial, self.vigencia_meses)
        try:
            from auditoria.threadlocal import get_current_user
        except Exception:
            user = None
        else:
            user = get_current_user()
        if getattr(user, "is_authenticated", False):
            self.atualizado_por = user
        super().save(*args, **kwargs)
        if self.status == self.Status.EM_CONTRATACAO and status_anterior != self.Status.EM_CONTRATACAO:
            # Integração entre apps: cria artefatos no Diário de Bordo somente
            # na primeira entrada em "Em Contratação".
            BlocoTrabalho = apps.get_model("diario_bordo", "BlocoTrabalho")
            Incremento = apps.get_model("diario_bordo", "Incremento")
            # Consulta ORM evita duplicidade de blocos para o mesmo contrato.
            if not BlocoTrabalho.objects.filter(contrato=self).exists():
                titulo_bloco = f"{self.nro_sei} - {self.objeto}".strip()
                bloco = BlocoTrabalho.objects.create(
                    nome=titulo_bloco,
                    descricao=self.objeto,
                    contrato=self,
                )
                Incremento.objects.create(
                    bloco=bloco,
                    texto=f"Bloco criado automaticamente para o contrato {self.nro_sei}.",
                )

    def __str__(self):
        """
        Representação textual padrão para admin/listagens.

        Retorno:
        - `str`: combinação de número SEI e número do contrato.
        """

        return f"{self.nro_sei} - {self.nro_contrato}"

    def get_absolute_url(self):
        """
        Resolve URL canônica de detalhe do contrato.

        Retorno:
        - `str`: rota nomeada `contratos_detail` para o próprio registro.
        """

        from django.urls import reverse

        return reverse("contratos_detail", kwargs={"pk": self.pk})
