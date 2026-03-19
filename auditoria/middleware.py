"""
Middleware do app `auditoria`.

Este componente injeta o usuário corrente em armazenamento thread-local
durante o ciclo da request. Os signal handlers consultam esse estado para
atribuir autoria nos registros de `AuditLog` sem acoplamento direto às views.
"""

from .threadlocal import set_current_user


class CurrentUserMiddleware:
    """
    Middleware responsável por disponibilizar o usuário da request.

    Papel na arquitetura:
    - captura `request.user`;
    - grava no contexto thread-local;
    - permite que sinais de model identifiquem o autor da ação.
    """

    def __init__(self, get_response):
        """
        Inicializa middleware com o próximo callable da cadeia.

        Parâmetros:
        - `get_response`: função que processa a request adiante.
        """

        self.get_response = get_response

    def __call__(self, request):
        """
        Executa middleware para cada request HTTP.

        Parâmetros:
        - `request`: requisição atual.

        Retorno:
        - `HttpResponse`: resposta gerada pela cadeia de middlewares/views.
        """

        # Deixa o usuario acessivel durante toda a request.
        set_current_user(getattr(request, "user", None))
        response = self.get_response(request)
        return response
