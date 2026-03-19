"""
Views do app `contratos`.

Este módulo controla os fluxos HTTP de listagem, criação, edição,
detalhamento e exclusão de contratos, além de utilitários de prazo.
Integra-se com:
- `ContratoForm` para validação de entrada;
- `Contrato` (ORM) para consultas e persistência;
- templates HTML para renderização de painel e formulários.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import ContratoForm
from .models import Contrato, add_months


def months_until(end_date: date, start_date: date) -> int:
    """
    Calcula diferença inteira em meses entre duas datas.

    Parâmetros:
    - `end_date`: data final.
    - `start_date`: data inicial de referência.

    Retorno:
    - `int`: número de meses (positivo, zero ou negativo).
    """

    months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
    if end_date >= start_date and end_date.day < start_date.day:
        months -= 1
    if end_date < start_date and end_date.day > start_date.day:
        months += 1
    return months


def months_days_until(end_date: date, start_date: date) -> tuple[int, int]:
    """
    Calcula diferença composta (meses, dias) entre datas.

    Parâmetros:
    - `end_date`: data final.
    - `start_date`: data inicial.

    Retorno:
    - `tuple[int, int]`: meses e dias restantes (ou negativos se vencido).

    Regra algorítmica:
    - usa data âncora por `add_months` para evitar inconsistências
      em meses com tamanhos diferentes.
    """

    if end_date >= start_date:
        months = months_until(end_date, start_date)
        anchor = add_months(start_date, months)
        if anchor > end_date:
            months -= 1
            anchor = add_months(start_date, months)
        days = max((end_date - anchor).days, 0)
        return months, days
    months = months_until(start_date, end_date)
    anchor = add_months(end_date, months)
    if anchor > start_date:
        months -= 1
        anchor = add_months(end_date, months)
    days = max((start_date - anchor).days, 0)
    return -months, -days


def format_months_days(months: int, days: int) -> str:
    """
    Formata prazo em linguagem legível para a interface.

    Parâmetros:
    - `months`: componente de meses.
    - `days`: componente de dias.

    Retorno:
    - `str`: texto humanizado (ex.: "3 meses e 5 dias", "-2 dias").
    """

    if months == 0 and days == 0:
        return "0 dias"
    negative = months < 0 or days < 0
    months_abs = abs(months)
    days_abs = abs(days)
    if months_abs == 0:
        texto = f"{days_abs} dia" if days_abs == 1 else f"{days_abs} dias"
    elif days_abs == 0:
        texto = f"{months_abs} mês" if months_abs == 1 else f"{months_abs} meses"
    else:
        mes_txt = "mês" if months_abs == 1 else "meses"
        dia_txt = "dia" if days_abs == 1 else "dias"
        texto = f"{months_abs} {mes_txt} e {days_abs} {dia_txt}"
    return f"-{texto}" if negative else texto


class ContratoListView(PermissionRequiredMixin, ListView):
    """
    View de listagem de contratos com indicadores de prazo.

    Fluxo HTTP:
    - GET consulta contratos e calcula métricas visuais para o dashboard.
    """

    model = Contrato
    template_name = "contratos/contrato_list.html"
    context_object_name = "contratos"
    permission_required = "contratos.view_contrato"

    def get_context_data(self, **kwargs):
        """
        Enriquecimento de contexto da listagem com cálculos de vigência.

        Retorno:
        - `dict`: inclui prazos, classes de alerta, total financeiro e ordenação.

        Consulta ORM relevante:
        - a `ListView` fornece queryset base de `Contrato`; aqui os registros
          são processados para métricas derivadas de apresentação.
        """

        context = super().get_context_data(**kwargs)
        hoje = timezone.localdate()
        for contrato in context["contratos"]:
            if contrato.data_fim:
                meses = months_until(contrato.data_fim, hoje)
                contrato.meses_para_fim = meses
                meses_calc, dias_calc = months_days_until(contrato.data_fim, hoje)
                contrato.prazo_restante = format_months_days(meses_calc, dias_calc)
                if meses <= 2:
                    # Contratos mais próximos do término recebem alerta mais crítico.
                    contrato.classe_alerta = "linha-alerta-preto"
                elif meses == 3:
                    contrato.classe_alerta = "linha-alerta-roxo"
                elif meses == 4:
                    contrato.classe_alerta = "linha-alerta-vermelho"
                elif meses == 5:
                    contrato.classe_alerta = "linha-alerta-laranja"
                elif meses == 6:
                    contrato.classe_alerta = "linha-alerta-amarelo"
                else:
                    contrato.classe_alerta = ""
            else:
                contrato.meses_para_fim = 9999
                contrato.prazo_restante = "-"
                contrato.classe_alerta = ""
        context["total_valor"] = sum(
            (contrato.valor_total or Decimal("0.00") for contrato in context["contratos"]),
            Decimal("0.00"),
        )
        context["contratos"] = sorted(
            context["contratos"],
            key=lambda item: item.meses_para_fim,
        )
        return context


class ContratoCreateView(PermissionRequiredMixin, CreateView):
    """Fluxo HTTP de criação de contrato com validação via `ContratoForm`."""

    model = Contrato
    form_class = ContratoForm
    template_name = "contratos/contrato_form.html"
    success_url = reverse_lazy("contratos_list")
    permission_required = "contratos.add_contrato"


class ContratoUpdateView(PermissionRequiredMixin, UpdateView):
    """Fluxo HTTP de edição de contrato existente."""

    model = Contrato
    form_class = ContratoForm
    template_name = "contratos/contrato_form.html"
    permission_required = "contratos.change_contrato"

    def get_success_url(self):
        """
        Redireciona para página de detalhe após atualização.

        Retorno:
        - `str`: URL absoluta do contrato atualizado.
        """

        return self.object.get_absolute_url()


class ContratoDetailView(PermissionRequiredMixin, DetailView):
    """
    View de detalhe de um contrato específico.

    Fluxo HTTP:
    - GET carrega registro por PK e apresenta campos com ajustes de exibição.
    """

    model = Contrato
    template_name = "contratos/contrato_detail.html"
    context_object_name = "contrato"
    permission_required = "contratos.view_contrato"

    def get_context_data(self, **kwargs):
        """
        Ajusta dados exibidos no detalhe do contrato.

        Regra de negócio:
        - se `data_inicial` estiver vazia mas houver `data_fim` e vigência,
          estima data inicial apenas para visualização.
        """

        context = super().get_context_data(**kwargs)
        contrato = context["contrato"]
        if not contrato.data_inicial and contrato.data_fim and contrato.vigencia_meses:
            contrato.data_inicial_exibicao = add_months(
                contrato.data_fim, -int(contrato.vigencia_meses)
            )
        else:
            contrato.data_inicial_exibicao = contrato.data_inicial
        return context


class ContratoDeleteView(PermissionRequiredMixin, DeleteView):
    """Fluxo HTTP de exclusão confirmada de contrato."""

    model = Contrato
    template_name = "contratos/contrato_confirm_delete.html"
    success_url = reverse_lazy("contratos_list")
    permission_required = "contratos.delete_contrato"

