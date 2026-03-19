from django.contrib import admin

from .models import (
    ConexaoBancoMonitoramento,
    ConsultaDashboardMonitoramento,
    DashboardMonitoramento,
    GraficoDashboardMonitoramento,
    ProjetoMonitoramento,
    SnapshotEsquemaMonitoramento,
)


admin.site.register(ProjetoMonitoramento)
admin.site.register(ConexaoBancoMonitoramento)
admin.site.register(SnapshotEsquemaMonitoramento)
admin.site.register(DashboardMonitoramento)
admin.site.register(ConsultaDashboardMonitoramento)
admin.site.register(GraficoDashboardMonitoramento)
