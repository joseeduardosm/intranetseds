"""
Filtros de template do app `lousa_digital`.

Este módulo integra-se aos templates para decisões de apresentação, mantendo
regras visuais (como cor por destino) fora das views.
"""

import hashlib

from django import template

from sala_situacao_v2.models import sigla_marcador


register = template.Library()

DESTINO_PALETA = (
    "#7452a7",
    "#d43d3d",
    "#2f7d32",
    "#c26712",
    "#0f766e",
    "#3557a8",
    "#8d5b2c",
    "#6b7280",
)


@register.filter
def marcador_cor(valor):
    """Retorna cor consistente para um destino textual.

    Estratégia:
    - aplica hash MD5 do texto para escolher índice fixo na paleta;
    - garante que o mesmo destino sempre receba a mesma cor entre renderizações.
    """

    texto = (valor or "").strip()
    if not texto:
        return DESTINO_PALETA[0]
    indice = int(hashlib.md5(texto.encode("utf-8")).hexdigest(), 16) % len(DESTINO_PALETA)
    return DESTINO_PALETA[indice]


@register.filter
def marcador_sigla(valor):
    """Retorna a sigla visual do destino usando a mesma regra da Sala de Situacao V2."""

    return sigla_marcador(valor)
