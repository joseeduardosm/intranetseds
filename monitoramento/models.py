"""
Modelos do app `monitoramento`.
"""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class ProjetoMonitoramento(models.Model):
    nome = models.CharField(max_length=160)
    descricao = models.TextField(blank=True, default="")
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projetos_monitoramento_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome", "id"]
        verbose_name = "Projeto de monitoramento"
        verbose_name_plural = "Projetos de monitoramento"

    def __str__(self) -> str:
        return self.nome


class ConexaoBancoMonitoramento(models.Model):
    TIPO_MYSQL = "mysql"
    TIPO_SQLSERVER = "sqlserver"
    TIPO_BANCO_CHOICES = [
        (TIPO_MYSQL, "MySQL"),
        (TIPO_SQLSERVER, "SQL Server"),
    ]

    projeto = models.OneToOneField(
        ProjetoMonitoramento,
        on_delete=models.CASCADE,
        related_name="conexao",
    )
    tipo_banco = models.CharField(max_length=20, choices=TIPO_BANCO_CHOICES)
    host = models.CharField(max_length=255)
    porta = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    database = models.CharField(max_length=255)
    schema = models.CharField(max_length=255, blank=True, default="")
    usuario = models.CharField(max_length=255)
    senha_criptografada = models.TextField(blank=True, default="")
    status_ultima_conexao = models.CharField(max_length=32, blank=True, default="")
    ultimo_teste_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Conexão de banco monitorado"
        verbose_name_plural = "Conexões de bancos monitorados"

    def __str__(self) -> str:
        return f"{self.projeto} - {self.get_tipo_banco_display()}"


class SnapshotEsquemaMonitoramento(models.Model):
    projeto = models.ForeignKey(
        ProjetoMonitoramento,
        on_delete=models.CASCADE,
        related_name="snapshots_esquema",
    )
    estrutura_json = models.JSONField(default=dict, blank=True)
    gerado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-gerado_em"]
        verbose_name = "Snapshot de esquema"
        verbose_name_plural = "Snapshots de esquema"


class DashboardMonitoramento(models.Model):
    projeto = models.ForeignKey(
        ProjetoMonitoramento,
        on_delete=models.CASCADE,
        related_name="dashboards",
    )
    titulo = models.CharField(max_length=180)
    descricao = models.TextField(blank=True, default="")
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dashboards_monitoramento_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["titulo", "id"]
        verbose_name = "Dashboard de monitoramento"
        verbose_name_plural = "Dashboards de monitoramento"

    def __str__(self) -> str:
        return self.titulo


class ConsultaDashboardMonitoramento(models.Model):
    dashboard = models.ForeignKey(
        DashboardMonitoramento,
        on_delete=models.CASCADE,
        related_name="consultas",
    )
    nome = models.CharField(max_length=180)
    sql_texto = models.TextField()
    colunas_json = models.JSONField(default=list, blank=True)
    parametros_json = models.JSONField(default=list, blank=True)
    ultima_validacao_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["nome", "id"]
        verbose_name = "Consulta de dashboard"
        verbose_name_plural = "Consultas de dashboard"

    def __str__(self) -> str:
        return self.nome


class GraficoDashboardMonitoramento(models.Model):
    TIPO_LINHA = "linha"
    TIPO_BARRA = "barra"
    TIPO_BARRA_HORIZONTAL = "barra_horizontal"
    TIPO_DISPERSAO = "dispersao"
    TIPO_PIZZA = "pizza"
    TIPO_AREA = "area"
    TIPO_TABELA = "tabela"

    TIPO_GRAFICO_CHOICES = [
        (TIPO_LINHA, "Linha"),
        (TIPO_BARRA, "Barra vertical"),
        (TIPO_BARRA_HORIZONTAL, "Barra horizontal"),
        (TIPO_DISPERSAO, "Dispersão X/Y"),
        (TIPO_PIZZA, "Pizza"),
        (TIPO_AREA, "Área"),
        (TIPO_TABELA, "Tabela"),
    ]

    dashboard = models.ForeignKey(
        DashboardMonitoramento,
        on_delete=models.CASCADE,
        related_name="graficos",
    )
    consulta = models.ForeignKey(
        ConsultaDashboardMonitoramento,
        on_delete=models.CASCADE,
        related_name="graficos",
    )
    titulo = models.CharField(max_length=180, blank=True, default="")
    tipo_grafico = models.CharField(max_length=32, choices=TIPO_GRAFICO_CHOICES)
    campo_x = models.CharField(max_length=180, blank=True, default="")
    campo_y = models.CharField(max_length=180, blank=True, default="")
    campo_serie = models.CharField(max_length=180, blank=True, default="")
    campo_data = models.CharField(max_length=180, blank=True, default="")
    campo_detalhe = models.CharField(max_length=180, blank=True, default="")
    ordem = models.PositiveIntegerField(default=1)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordem", "id"]
        verbose_name = "Gráfico de dashboard"
        verbose_name_plural = "Gráficos de dashboard"

    def __str__(self) -> str:
        return self.titulo or f"{self.get_tipo_grafico_display()} #{self.pk}"
