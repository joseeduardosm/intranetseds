"""
Roteamento legado do app `sala_situacao` sob prefixo /sala-de-situacao-old/.

Este módulo reaproveita os mesmos callbacks do legado, mas com nomes de rota
prefixados para evitar colisão com os nomes oficiais da V2.
"""

from django.urls import path

from .urls import urlpatterns as legacy_urlpatterns


def _old_name(name):
    if not name:
        return None
    if name.startswith("sala_"):
        return f"sala_old_{name[5:]}"
    return f"old_{name}"


urlpatterns = [
    path(
        pattern.pattern._route,
        pattern.callback,
        kwargs=pattern.default_args,
        name=_old_name(pattern.name),
    )
    for pattern in legacy_urlpatterns
]

