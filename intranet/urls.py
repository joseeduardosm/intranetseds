"""
Configuração de URLs do projeto intranet.

A lista `urlpatterns` mapeia URLs para views. Para mais detalhes:
https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    # Admin do Django.
    path('admin/', admin.site.urls),
    # Autenticação padrão.
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    # App de notícias como home.
    path('', include('noticias.urls')),
    # App de ramais.
    path('ramais/', include('ramais.urls')),
    # App de diário de bordo.
    path('diario-de-bordo/', include('diario_bordo.urls')),
    # App de contratos.
    path('contratos/', include('contratos.urls')),
    # App de empresas.
    path('empresas/', include('empresas.urls')),
    # App de prepostos.
    path('prepostos/', include('prepostos.urls')),
    # App de reserva de salas.
    path('reserva-salas/', include('reserva_salas.urls')),
    # App de usuarios.
    path('usuarios/', include('usuarios.urls')),
    # App de auditoria.
    path('auditoria/', include('auditoria.urls')),
    # App de monitoramento.
    path('administracao/monitoramento/', include('monitoramento.urls')),
    # App de administracao.
    path('administracao/', include('administracao.urls')),
    # App de folha de ponto.
    path('folha-ponto/', include('folha_ponto.urls')),
    # App de licitacoes.
    path('licitacoes/', include('licitacoes.urls')),
    # App de sala de situacao.
    path('sala-de-situacao/', include('sala_situacao.urls')),
    # App de lousa digital.
    path('lousa-digital/', include('lousa_digital.urls')),
]

if settings.DEBUG:
    # Em desenvolvimento, serve arquivos de mídia.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
