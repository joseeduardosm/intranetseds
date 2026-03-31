from django import template

from acompanhamento_sistemas.utils import nome_usuario_exibicao


register = template.Library()


@register.filter
def usuario_nome(valor):
    return nome_usuario_exibicao(valor)
