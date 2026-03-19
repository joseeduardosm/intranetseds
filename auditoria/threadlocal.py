"""
Armazenamento thread-local para contexto de auditoria.

Este módulo desacopla signals da camada HTTP: middlewares gravam o usuário
corrente e os handlers de auditoria apenas leem esse estado para preencher
`AuditLog.user`.
"""

import threading


_state = threading.local()


def set_current_user(user):
    """
    Define usuário corrente no contexto da thread ativa.

    Parâmetros:
    - `user`: instância de usuário (ou `None`).
    """

    _state.user = user


def get_current_user():
    """
    Recupera usuário corrente do contexto thread-local.

    Retorno:
    - usuário armazenado para a request atual, ou `None`.
    """

    return getattr(_state, "user", None)
