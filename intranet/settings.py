"""
Configurações do Django para o projeto intranet.

Gerado por 'django-admin startproject' usando Django 6.0.1.

Para mais informações, veja:
https://docs.djangoproject.com/en/6.0/topics/settings/

Para a lista completa de opções disponíveis:
https://docs.djangoproject.com/en/6.0/ref/settings/
"""

import os
import time
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# Caminho base do projeto (pasta raiz).
BASE_DIR = Path(__file__).resolve().parent.parent

# Carrega variaveis de ambiente de um arquivo .env local, se existir.
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
    except Exception as exc:
        raise ImproperlyConfigured(
            "python-dotenv nao instalado, mas .env encontrado."
        ) from exc
    load_dotenv(_env_path)

# Mantem o processo Python alinhado ao fuso horario oficial da aplicacao.
PROJECT_TIME_ZONE = os.getenv("TZ", "America/Sao_Paulo")
os.environ["TZ"] = PROJECT_TIME_ZONE
if hasattr(time, "tzset"):
    time.tzset()


# Configurações rápidas para desenvolvimento (não usar em produção).
# Veja: https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# ATENÇÃO: mantenha a SECRET_KEY em segredo em produção!
SECRET_KEY = 'django-insecure-3ldqwwlp74jd-txa89@%w+6k+_km21sxh^qb&^kij&5w=n&=ee'

# ATENÇÃO: não deixe DEBUG=True em produção!
DEBUG = True

# Hosts permitidos a acessar a aplicação.
# ALLOWED_HOSTS = []
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "10.22.0.37", "sgi.seds.sp.gov.br"]

# Ambientes suportados para acesso interno e publicado.
CSRF_TRUSTED_ORIGINS = [
    "http://sgi.seds.sp.gov.br",
    "https://sgi.seds.sp.gov.br",
]
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False


# Definição dos apps instalados.

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'noticias',
    'ramais',
    'diario_bordo',
    'contratos',
    'empresas',
    'prepostos',
    'reserva_salas',
    'usuarios.apps.UsuariosConfig',
    'auditoria.apps.AuditoriaConfig',
    'administracao.apps.AdministracaoConfig',
    'monitoramento.apps.MonitoramentoConfig',
    'folha_ponto.apps.FolhaPontoConfig',
    'licitacoes.apps.LicitacoesConfig',
    'sala_situacao.apps.SalaSituacaoConfig',
    'sala_situacao_v2.apps.SalaSituacaoV2Config',
    'lousa_digital.apps.LousaDigitalConfig',
]

# Pipeline de middlewares (ordem importa).
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'auditoria.middleware.CurrentUserMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Arquivo raiz de URLs do projeto.
ROOT_URLCONF = 'intranet.urls'

# Configuração do mecanismo de templates.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'builtins': [
                'licitacoes.templatetags.licitacoes_extras',
            ],
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'intranet.context_processors.ramal_profile',
                'intranet.context_processors.diario_bordo_alert',
                'intranet.context_processors.sala_situacao_access',
                'intranet.context_processors.identidade_visual',
            ],
        },
    },
]

# Entrada WSGI para servidores web tradicionais.
WSGI_APPLICATION = 'intranet.wsgi.application'


# Banco de dados.
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

def _env(name, default=None):
    return os.environ.get(name, default)


_mysql_name = _env("MYSQL_NAME")
_mysql_user = _env("MYSQL_USER")
_mysql_password = _env("MYSQL_PASSWORD")
if not _mysql_name or not _mysql_user or _mysql_password is None:
    raise ImproperlyConfigured(
        "MYSQL_NAME, MYSQL_USER e MYSQL_PASSWORD precisam estar definidos."
    )
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': _mysql_name,
        'USER': _mysql_user,
        'PASSWORD': _mysql_password,
        'HOST': _env("MYSQL_HOST", "127.0.0.1"),
        'PORT': _env("MYSQL_PORT", "3306"),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

# Define tipo padrao de chave primaria para evitar warnings (Django 5.x).
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Static files com cache e versionamento (WhiteNoise).
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# Validações de senha.
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internacionalização.
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'pt-br'

TIME_ZONE = PROJECT_TIME_ZONE

USE_I18N = True

USE_TZ = True


# Arquivos estáticos (CSS, JavaScript, imagens).
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Arquivos de mídia enviados via formulário.
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# URLs padrão de autenticação.
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'
# Autenticacao (AD + banco local).
AUTHENTICATION_BACKENDS = [
    "administracao.ldap_backend.LDAPBackend",
    "usuarios.auth_backends.SetorPermissionBackend",
]
