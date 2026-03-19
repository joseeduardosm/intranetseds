"""
Configuração WSGI do projeto intranet.

Expõe o callable WSGI como variável de módulo `application`.

Mais informações:
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Define o módulo de configurações do Django para o servidor WSGI.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'intranet.settings')

# Objeto WSGI que o servidor usa para receber requisições.
application = get_wsgi_application()
