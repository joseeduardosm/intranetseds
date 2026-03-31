from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q


User = get_user_model()

USUARIOS_OCULTOS_EXATOS = {
    "smokev2",
}
USUARIOS_OCULTOS_PREFIXOS = (
    "tmp",
    "smoke",
)


def usuarios_ocultos_q(campo_username: str = "username") -> Q:
    q = Q()
    for username in USUARIOS_OCULTOS_EXATOS:
        q |= Q(**{campo_username: username})
    for prefixo in USUARIOS_OCULTOS_PREFIXOS:
        q |= Q(**{f"{campo_username}__istartswith": prefixo})
    return q


def usuarios_visiveis(queryset=None):
    queryset = queryset if queryset is not None else User.objects.all()
    return queryset.exclude(usuarios_ocultos_q())
