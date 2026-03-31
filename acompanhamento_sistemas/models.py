from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.db import models
from django.urls import reverse
from django.utils import timezone


User = get_user_model()


class TipoInteressado(models.TextChoices):
    DEV = "DEV", "Dev"
    GESTAO = "GESTAO", "Gestao"
    NEGOCIO = "NEGOCIO", "Negocio"


class Sistema(models.Model):
    nome = models.CharField(max_length=180)
    descricao = models.TextField()
    url_homologacao = models.URLField(blank=True)
    url_producao = models.URLField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sistemas_acompanhamento_criados",
    )
    atualizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sistemas_acompanhamento_atualizados",
    )

    class Meta:
        ordering = ["nome"]
        verbose_name = "Sistema"
        verbose_name_plural = "Sistemas"

    def __str__(self) -> str:
        return self.nome

    def get_absolute_url(self):
        return reverse("acompanhamento_sistemas_detail", kwargs={"pk": self.pk})

    @property
    def interessados_emails(self) -> list[str]:
        emails = []
        emails.extend(
            self.interessados.filter(email_snapshot__gt="").values_list("email_snapshot", flat=True)
        )
        emails.extend(
            self.interessados_manuais.filter(email__gt="").values_list("email", flat=True)
        )
        return list(dict.fromkeys([item.strip() for item in emails if item and item.strip()]))

    @property
    def progresso_percentual(self) -> float:
        entregas = list(self.entregas.all())
        if not entregas:
            return 0.0
        return round(sum(entrega.progresso_percentual for entrega in entregas) / len(entregas), 2)

    @property
    def progresso_classe(self) -> str:
        percentual = self.progresso_percentual
        if percentual <= 50:
            return "progresso-vermelho"
        if percentual <= 75:
            return "progresso-amarelo"
        return "progresso-verde"

    @property
    def progresso_snapshot(self) -> dict[str, object]:
        return {
            "titulo": "Evolução do Sistema",
            "percentual": float(self.progresso_percentual or 0),
            "classe": self.progresso_classe,
        }


class EntregaSistema(models.Model):
    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name="entregas")
    titulo = models.CharField(max_length=180)
    descricao = models.TextField(blank=True)
    ordem = models.PositiveIntegerField(default=1)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entregas_sistema_criadas",
    )
    atualizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entregas_sistema_atualizadas",
    )

    class Meta:
        ordering = ["ordem", "id"]
        unique_together = ("sistema", "ordem")
        verbose_name = "Entrega do sistema"
        verbose_name_plural = "Entregas do sistema"

    def __str__(self) -> str:
        return f"{self.sistema.nome} - {self.titulo}"

    def get_absolute_url(self):
        return reverse("acompanhamento_sistemas_entrega_detail", kwargs={"pk": self.pk})

    @property
    def progresso_percentual(self) -> float:
        etapas = list(self.etapas.all())
        if not etapas:
            return 0.0
        return round(sum(etapa.progresso_percentual for etapa in etapas) / len(etapas), 2)

    @property
    def progresso_classe(self) -> str:
        percentual = self.progresso_percentual
        if percentual <= 50:
            return "progresso-vermelho"
        if percentual <= 75:
            return "progresso-amarelo"
        return "progresso-verde"

    @property
    def progresso_snapshot(self) -> dict[str, object]:
        return {
            "titulo": "Evolução da Entrega",
            "percentual": float(self.progresso_percentual or 0),
            "classe": self.progresso_classe,
        }


class EtapaSistema(models.Model):
    class TipoEtapa(models.TextChoices):
        REQUISITOS = "REQUISITOS", "Requisitos"
        HOMOLOGACAO_REQUISITOS = "HOMOLOGACAO_REQUISITOS", "Homologacao de Requisitos"
        DESENVOLVIMENTO = "DESENVOLVIMENTO", "Desenvolvimento"
        HOMOLOGACAO_DESENVOLVIMENTO = "HOMOLOGACAO_DESENVOLVIMENTO", "Homologacao do Desenvolvimento"
        PRODUCAO = "PRODUCAO", "Producao"

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
        ENTREGUE = "ENTREGUE", "Entregue"

    entrega = models.ForeignKey(EntregaSistema, on_delete=models.CASCADE, related_name="etapas")
    tipo_etapa = models.CharField(max_length=40, choices=TipoEtapa.choices)
    data_etapa = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)
    ordem = models.PositiveIntegerField(default=1)
    tempo_desde_etapa_anterior_em_dias = models.IntegerField(null=True, blank=True)
    ticket_externo = models.CharField(max_length=120, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etapas_sistema_criadas",
    )
    atualizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etapas_sistema_atualizadas",
    )

    class Meta:
        ordering = ["ordem", "id"]
        unique_together = ("entrega", "tipo_etapa")
        verbose_name = "Etapa do sistema"
        verbose_name_plural = "Etapas do sistema"

    def __str__(self) -> str:
        return f"{self.entrega} - {self.get_tipo_etapa_display()}"

    def get_absolute_url(self):
        return reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": self.pk})

    @property
    def expira_em_dias(self) -> int:
        return (self.data_etapa - timezone.localdate()).days

    @property
    def expira_em_texto(self) -> str:
        dias = self.expira_em_dias
        if dias == 0:
            return "Expira hoje"
        if dias > 0:
            return f"Expira em {dias} dia(s)"
        return f"Expirou ha {abs(dias)} dia(s)"

    @property
    def progresso_percentual(self) -> float:
        mapa = {
            self.Status.PENDENTE: 0.0,
            self.Status.EM_ANDAMENTO: 50.0,
            self.Status.ENTREGUE: 100.0,
        }
        return mapa.get(self.status, 0.0)


class HistoricoEtapaSistema(models.Model):
    class TipoEvento(models.TextChoices):
        STATUS = "STATUS", "Status"
        DATA = "DATA", "Data"
        NOTA = "NOTA", "Nota"
        ANEXO = "ANEXO", "Anexo"
        CRIACAO = "CRIACAO", "Criacao"

    etapa = models.ForeignKey(EtapaSistema, on_delete=models.CASCADE, related_name="historicos")
    tipo_evento = models.CharField(max_length=20, choices=TipoEvento.choices)
    descricao = models.TextField(blank=True)
    status_anterior = models.CharField(max_length=20, blank=True)
    status_novo = models.CharField(max_length=20, blank=True)
    data_anterior = models.DateField(null=True, blank=True)
    data_nova = models.DateField(null=True, blank=True)
    justificativa = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historicos_etapa_sistema_criados",
    )

    class Meta:
        ordering = ["-criado_em", "-id"]
        verbose_name = "Historico da etapa"
        verbose_name_plural = "Historicos da etapa"

    def __str__(self) -> str:
        return f"Historico #{self.pk} - {self.etapa}"


class AnexoHistoricoEtapa(models.Model):
    historico = models.ForeignKey(HistoricoEtapaSistema, on_delete=models.CASCADE, related_name="anexos")
    arquivo = models.FileField(upload_to="acompanhamento_sistemas/anexos/")
    nome_original = models.CharField(max_length=255, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Anexo do historico"
        verbose_name_plural = "Anexos do historico"

    def save(self, *args, **kwargs):
        if self.arquivo and not self.nome_original:
            self.nome_original = getattr(self.arquivo, "name", "") or ""
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nome_original or f"Anexo #{self.pk}"

    @property
    def nome_exibicao(self) -> str:
        return self.nome_original or os.path.basename(getattr(self.arquivo, "name", "") or "")


class InteressadoSistema(models.Model):
    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name="interessados")
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="interesses_em_sistemas")
    tipo_interessado = models.CharField(max_length=20, choices=TipoInteressado.choices)
    nome_snapshot = models.CharField(max_length=255)
    email_snapshot = models.EmailField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interessados_sistema_criados",
    )

    class Meta:
        ordering = ["nome_snapshot", "id"]
        unique_together = ("sistema", "usuario", "tipo_interessado")
        verbose_name = "Interessado do sistema"
        verbose_name_plural = "Interessados do sistema"

    def __str__(self) -> str:
        return f"{self.nome_snapshot} - {self.sistema.nome}"


class InteressadoSistemaManual(models.Model):
    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name="interessados_manuais")
    tipo_interessado = models.CharField(max_length=20, choices=TipoInteressado.choices)
    nome = models.CharField(max_length=255)
    email = models.EmailField()
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interessados_manuais_sistema_criados",
    )

    class Meta:
        ordering = ["nome", "id"]
        unique_together = ("sistema", "email", "tipo_interessado")
        verbose_name = "Interessado manual do sistema"
        verbose_name_plural = "Interessados manuais do sistema"

    def __str__(self) -> str:
        return f"{self.nome} - {self.sistema.nome}"
