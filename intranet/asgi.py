"""
Configuração ASGI do projeto intranet.

Expõe o callable ASGI como variável de módulo `application`.

Mais informações:
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

# Define o módulo de configurações do Django para o servidor ASGI.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'intranet.settings')

# Objeto ASGI que o servidor usa para receber requisições.
application = get_asgi_application()
