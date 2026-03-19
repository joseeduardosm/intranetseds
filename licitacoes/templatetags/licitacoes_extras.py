import re

from django import template

register = template.Library()


@register.filter
def expand_seds(value):
    return re.sub(r"\bSEDS\b", "Secretaria de Desenvolvimento Social", value or "")
