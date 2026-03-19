"""
Filtros de template do app `contratos`.

Este módulo registra utilitários para formatação de apresentação no lado
dos templates Django, mantendo regras visuais fora das views.
"""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def moeda_br(valor):
    """
    Formata número para padrão monetário brasileiro.

    Parâmetros:
    - `valor`: número/decimal recebido do contexto do template.

    Retorno:
    - `str`: valor no formato `R$ 1.234,56` ou string vazia se inválido.
    """

    if valor is None:
        return ""
    try:
        numero = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        return ""
    texto = f"{numero:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"
