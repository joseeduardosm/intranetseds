from django import template

from acompanhamento_sistemas.utils import nome_usuario_exibicao


register = template.Library()


@register.filter
def usuario_nome(valor):
    return nome_usuario_exibicao(valor)


@register.filter
def primeiros_dois_nomes(valor):
    partes = [parte for parte in str(valor or "").strip().split() if parte]
    if not partes:
        return ""
    return " ".join(partes[:2])
