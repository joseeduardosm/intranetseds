from __future__ import annotations

import calendar
import os

from django.contrib.auth import get_user_model
from django.db import models
from django.urls import reverse
from django.utils import timezone
from datetime import date, datetime, time


User = get_user_model()


def _adicionar_meses(data_base: date, meses: int) -> date:
    total_meses = (data_base.year * 12 + (data_base.month - 1)) + meses
    ano = total_meses // 12
    mes = (total_meses % 12) + 1
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    dia = min(data_base.day, ultimo_dia)
    return date(ano, mes, dia)


def _componentes_periodo(inicio: date, fim: date) -> tuple[int, int, int]:
    if fim <= inicio:
        return 0, 0, max((fim - inicio).days, 0)

    anos = fim.year - inicio.year
    cursor = _adicionar_meses(inicio, anos * 12)
    if cursor > fim:
        anos -= 1
        cursor = _adicionar_meses(inicio, anos * 12)

    meses = (fim.year - cursor.year) * 12 + (fim.month - cursor.month)
    cursor_meses = _adicionar_meses(cursor, meses)
    if cursor_meses > fim:
        meses -= 1
        cursor_meses = _adicionar_meses(cursor, meses)

    dias = max((fim - cursor_meses).days, 0)
    return anos, meses, dias


def _pluralizar(valor: int, singular: str, plural: str) -> str:
    return f"{valor} {singular if valor == 1 else plural}"


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

    @property
    def possui_etapas_em_aberto(self) -> bool:
        return self.entregas.filter(etapas__status__in=[
            EtapaSistema.Status.PENDENTE,
            EtapaSistema.Status.EM_ANDAMENTO,
        ]).exists()

    @property
    def ultima_data_etapa(self):
        return (
            self.entregas.order_by()
            .values_list("etapas__data_etapa", flat=True)
            .exclude(etapas__data_etapa__isnull=True)
            .order_by("-etapas__data_etapa")
            .first()
        )

    @property
    def data_fim_lead_time(self):
        ultima_data = self.ultima_data_etapa
        if ultima_data and not self.possui_etapas_em_aberto:
            return ultima_data
        return timezone.localdate()

    @property
    def lead_time_dias(self) -> int:
        data_inicio = timezone.localtime(self.criado_em).date() if self.criado_em else timezone.localdate()
        data_fim = self.data_fim_lead_time or timezone.localdate()
        return max((data_fim - data_inicio).days, 0)

    @property
    def lead_time_texto(self) -> str:
        data_inicio = timezone.localtime(self.criado_em).date() if self.criado_em else timezone.localdate()
        data_fim = self.data_fim_lead_time or timezone.localdate()
        anos, meses, dias = _componentes_periodo(data_inicio, data_fim)

        if anos > 0:
            return ", ".join(
                [
                    _pluralizar(anos, "ano", "anos"),
                    f"{_pluralizar(meses, 'mês', 'meses')} e {_pluralizar(dias, 'dia', 'dias')}",
                ]
            )
        if meses > 0:
            return f"{_pluralizar(meses, 'mês', 'meses')} e {_pluralizar(dias, 'dia', 'dias')}"
        return _pluralizar(dias, "dia", "dias")


class EntregaSistema(models.Model):
    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        PUBLICADO = "PUBLICADO", "Publicado"

    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name="entregas")
    titulo = models.CharField(max_length=180)
    descricao = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RASCUNHO)
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
    processo_requisito_origem = models.ForeignKey(
        "ProcessoRequisito",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entregas_geradas",
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

    def _ciclos_ordenados_no_sistema(self):
        if not self.sistema_id:
            return EntregaSistema.objects.none()
        return self.sistema.entregas.order_by("ordem", "id")

    def numero_no_sistema(self):
        if not self.pk:
            return None
        ids_ordenados = list(self._ciclos_ordenados_no_sistema().values_list("id", flat=True))
        if self.pk not in ids_ordenados:
            return None
        return ids_ordenados.index(self.pk) + 1

    def total_no_sistema(self):
        return self._ciclos_ordenados_no_sistema().count()

    @property
    def rotulo_numeracao_no_sistema(self):
        numero = self.numero_no_sistema()
        if numero is None:
            return ""
        return f"{numero}/{self.total_no_sistema()}"

    @property
    def titulo_com_numeracao(self):
        if not self.rotulo_numeracao_no_sistema:
            return self.titulo
        return f"{self.rotulo_numeracao_no_sistema} {self.titulo}"

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
    def prazo_final_ciclo(self):
        ultima_data = (
            self.etapas.exclude(data_etapa__isnull=True)
            .order_by("-data_etapa", "-ordem", "-id")
            .values_list("data_etapa", flat=True)
            .first()
        )
        return ultima_data

    @property
    def progresso_prazo(self) -> float:
        prazo_final = self.prazo_final_ciclo
        if not prazo_final:
            return 0.0

        agora = timezone.now()
        inicio = self.criado_em
        if not inicio:
            inicio = timezone.now()

        if timezone.is_naive(inicio):
            inicio = timezone.make_aware(inicio, timezone.get_current_timezone())

        fim = timezone.make_aware(
            datetime.combine(prazo_final, time.max),
            timezone.get_current_timezone(),
        )

        if agora <= inicio:
            return 0.0
        if fim <= inicio or agora >= fim:
            return 100.0

        percentual = ((agora - inicio).total_seconds() / (fim - inicio).total_seconds()) * 100
        return max(0.0, min(round(percentual, 2), 100.0))

    @property
    def prazo_classe(self) -> str:
        percentual = self.progresso_prazo
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

    @property
    def prazo_snapshot(self) -> dict[str, object]:
        return {
            "titulo": "Evolução do Prazo",
            "percentual": float(self.progresso_prazo or 0),
            "classe": self.prazo_classe,
        }

    @property
    def etapa_atual(self):
        return self.etapas.exclude(
            status__in=[
                EtapaSistema.Status.ENTREGUE,
                EtapaSistema.Status.APROVADO,
            ]
        ).order_by("ordem", "id").first() or self.etapas.order_by("-ordem", "-id").first()


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
        APROVADO = "APROVADO", "Aprovado"
        REPROVADO = "REPROVADO", "Reprovado"

    entrega = models.ForeignKey(EntregaSistema, on_delete=models.CASCADE, related_name="etapas")
    tipo_etapa = models.CharField(max_length=40, choices=TipoEtapa.choices)
    data_etapa = models.DateField(null=True, blank=True)
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
        if not self.data_etapa:
            return 0
        return (self.data_etapa - timezone.localdate()).days

    @property
    def expira_em_texto(self) -> str:
        if not self.data_etapa:
            return "Data nao definida"
        dias = self.expira_em_dias
        if dias == 0:
            return "Expira hoje"
        if dias > 0:
            return f"Expira em {dias} dia(s)"
        return f"Expirou ha {abs(dias)} dia(s)"

    @property
    def prazo_marcador(self) -> dict[str, str] | None:
        if not self.data_etapa:
            return None
        if self.status in {self.Status.ENTREGUE, self.Status.APROVADO}:
            return None
        dias = self.expira_em_dias
        if dias < 0:
            return {"label": "Atrasado", "classe": "atrasado"}
        if dias <= 2:
            return {"label": "Atenção", "classe": "atencao"}
        return {"label": "Em dia", "classe": "em_dia"}

    @property
    def progresso_percentual(self) -> float:
        mapa = {
            self.Status.PENDENTE: 0.0,
            self.Status.EM_ANDAMENTO: 50.0,
            self.Status.ENTREGUE: 100.0,
            self.Status.APROVADO: 100.0,
            self.Status.REPROVADO: 0.0,
        }
        return mapa.get(self.status, 0.0)

    @property
    def eh_homologacao(self) -> bool:
        return self.tipo_etapa in {
            self.TipoEtapa.HOMOLOGACAO_REQUISITOS,
            self.TipoEtapa.HOMOLOGACAO_DESENVOLVIMENTO,
        }

    @property
    def status_exibicao(self) -> str:
        if self.eh_homologacao:
            if self.status == self.Status.EM_ANDAMENTO:
                return self.Status.EM_ANDAMENTO.label
            if self.status == self.Status.PENDENTE:
                ultimo_status_relevante = next(
                    (
                        historico.status_novo
                        for historico in self._historicos_lista()
                        if historico.status_novo in {self.Status.APROVADO, self.Status.REPROVADO}
                    ),
                    "",
                )
                if ultimo_status_relevante == self.Status.REPROVADO:
                    return self.Status.REPROVADO.label
            ultimo_status_relevante = next(
                (
                    historico.status_novo
                    for historico in self._historicos_lista()
                    if historico.status_novo in {self.Status.APROVADO, self.Status.REPROVADO}
                ),
                "",
            )
            if self.status in {self.Status.APROVADO, self.Status.ENTREGUE} or ultimo_status_relevante == self.Status.APROVADO:
                return self.Status.APROVADO.label
        return self.get_status_display()

    @property
    def status_visual_classe(self) -> str:
        mapa = {
            "Pendente": "pendente",
            "Em andamento": "em_andamento",
            "Entregue": "entregue",
            "Aprovado": "aprovado",
            "Reprovado": "reprovado",
        }
        return mapa.get(self.status_exibicao, (self.status or "").lower())

    def _historicos_lista(self):
        return list(self.historicos.all())

    def ja_foi_iniciada(self) -> bool:
        return any(
            historico.status_novo in {
                self.Status.EM_ANDAMENTO,
                self.Status.ENTREGUE,
                self.Status.APROVADO,
                self.Status.REPROVADO,
            }
            for historico in self._historicos_lista()
        )

    def ja_foi_concluida(self) -> bool:
        return any(
            historico.status_novo in {self.Status.ENTREGUE, self.Status.APROVADO}
            for historico in self._historicos_lista()
        )

    def foi_reaberta(self) -> bool:
        return any(historico.status_novo == self.Status.REPROVADO for historico in self._historicos_lista())

    def total_retomadas_por_reprovacao(self) -> int:
        proxima = (
            self.entrega.etapas.filter(ordem__gt=self.ordem)
            .order_by("ordem", "id")
            .first()
        )
        if proxima is None or not proxima.eh_homologacao:
            return 0
        return sum(1 for historico in proxima.historicos.all() if historico.status_novo == self.Status.REPROVADO)

    @property
    def marcadores_historicos(self) -> list[dict[str, str]]:
        marcadores = []
        total_retomadas = self.total_retomadas_por_reprovacao()
        if total_retomadas:
            label = "Retomada"
            if total_retomadas > 1:
                label = f"Retomada ({total_retomadas})"
            marcadores.append({"label": label, "classe": "retorno"})
        vistos = set()
        resultado = []
        for marcador in marcadores:
            chave = (marcador["label"], marcador["classe"])
            if chave in vistos:
                continue
            vistos.add(chave)
            resultado.append(marcador)
        return resultado


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


class HistoricoSistema(models.Model):
    class TipoEvento(models.TextChoices):
        NOTA = "NOTA", "Nota"

    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name="historicos_sistema")
    tipo_evento = models.CharField(max_length=20, choices=TipoEvento.choices, default=TipoEvento.NOTA)
    descricao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historicos_sistema_criados",
    )

    class Meta:
        ordering = ["-criado_em", "-id"]
        verbose_name = "Historico do sistema"
        verbose_name_plural = "Historicos do sistema"

    def __str__(self) -> str:
        return f"Historico sistema #{self.pk} - {self.sistema}"


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


class AnexoHistoricoSistema(models.Model):
    historico = models.ForeignKey(HistoricoSistema, on_delete=models.CASCADE, related_name="anexos")
    arquivo = models.FileField(upload_to="acompanhamento_sistemas/anexos/")
    nome_original = models.CharField(max_length=255, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Anexo do historico do sistema"
        verbose_name_plural = "Anexos do historico do sistema"

    def save(self, *args, **kwargs):
        if self.arquivo and not self.nome_original:
            self.nome_original = getattr(self.arquivo, "name", "") or ""
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nome_original or f"Anexo sistema #{self.pk}"

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


class ProcessoRequisito(models.Model):
    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name="processos_requisito")
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
        related_name="processos_requisito_criados",
    )
    atualizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processos_requisito_atualizados",
    )

    class Meta:
        ordering = ["ordem", "id"]
        unique_together = ("sistema", "ordem")
        verbose_name = "Processo de requisito"
        verbose_name_plural = "Processos de requisito"

    def __str__(self) -> str:
        return f"{self.sistema.nome} - {self.titulo}"

    def get_absolute_url(self):
        return reverse("acompanhamento_sistemas_processo_detail", kwargs={"pk": self.pk})

    @property
    def etapas_ordenadas(self):
        return self.etapas.order_by("ordem", "id")

    @property
    def processo_finalizado(self) -> bool:
        etapas = list(self.etapas_ordenadas)
        if len(etapas) != 3:
            return False
        status_finais = {
            EtapaProcessoRequisito.Status.APROVADO,
            EtapaProcessoRequisito.Status.RETIRADO_ESCOPO,
        }
        return all(etapa.status in status_finais for etapa in etapas)


class EtapaProcessoRequisito(models.Model):
    class TipoEtapa(models.TextChoices):
        AS_IS = "AS_IS", "AS IS"
        DIAGNOSTICO = "DIAGNOSTICO", "Diagnóstico"
        TO_BE = "TO_BE", "TO BE"

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
        VALIDACAO = "VALIDACAO", "Validação"
        APROVADO = "APROVADO", "Aprovado"
        REPROVADO = "REPROVADO", "Reprovado"
        RETIRADO_ESCOPO = "RETIRADO_ESCOPO", "Retirado do escopo"

    processo = models.ForeignKey(ProcessoRequisito, on_delete=models.CASCADE, related_name="etapas")
    tipo_etapa = models.CharField(max_length=30, choices=TipoEtapa.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)
    ordem = models.PositiveIntegerField(default=1)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etapas_processo_requisito_criadas",
    )
    atualizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etapas_processo_requisito_atualizadas",
    )

    class Meta:
        ordering = ["ordem", "id"]
        unique_together = ("processo", "tipo_etapa")
        verbose_name = "Etapa do processo de requisito"
        verbose_name_plural = "Etapas do processo de requisito"

    @property
    def etapas_anteriores(self):
        return self.processo.etapas.filter(ordem__lt=self.ordem).order_by("ordem", "id")

    @property
    def status_finais_dependencia(self) -> set[str]:
        return {
            self.Status.APROVADO,
            self.Status.RETIRADO_ESCOPO,
        }

    @property
    def dependencias_concluidas(self) -> bool:
        return all(etapa.status in self.status_finais_dependencia for etapa in self.etapas_anteriores)

    @property
    def mensagem_bloqueio_dependencia(self) -> str:
        if self.tipo_etapa == self.TipoEtapa.DIAGNOSTICO:
            return "Diagnóstico só pode ser alterado após AS IS estar Aprovado ou Retirado do escopo."
        if self.tipo_etapa == self.TipoEtapa.TO_BE:
            return "TO BE só pode ser alterado após AS IS e Diagnóstico estarem Aprovados ou Retirados do escopo."
        return ""

    @property
    def proximos_status_permitidos(self) -> list[str]:
        mapa = {
            self.Status.PENDENTE: [self.Status.EM_ANDAMENTO],
            self.Status.EM_ANDAMENTO: [self.Status.VALIDACAO],
            self.Status.VALIDACAO: [
                self.Status.APROVADO,
                self.Status.REPROVADO,
                self.Status.RETIRADO_ESCOPO,
            ],
            self.Status.APROVADO: [],
            self.Status.REPROVADO: [],
            self.Status.RETIRADO_ESCOPO: [],
        }
        return mapa.get(self.status, [])

    def _historicos_lista(self):
        return list(self.historicos.all())

    def total_retomadas_por_reprovacao(self) -> int:
        proxima = self.processo.etapas.filter(ordem__gt=self.ordem).order_by("ordem", "id").first()
        if proxima is None:
            return 0
        return sum(1 for historico in proxima.historicos.all() if historico.status_novo == self.Status.REPROVADO)

    @property
    def marcadores_historicos(self) -> list[dict[str, str]]:
        marcadores = []
        total_retomadas = self.total_retomadas_por_reprovacao()
        if total_retomadas:
            label = "Retomada"
            if total_retomadas > 1:
                label = f"Retomada ({total_retomadas})"
            marcadores.append({"label": label, "classe": "retorno"})
        vistos = set()
        resultado = []
        for marcador in marcadores:
            chave = (marcador["label"], marcador["classe"])
            if chave in vistos:
                continue
            vistos.add(chave)
            resultado.append(marcador)
        return resultado

    @property
    def pode_alterar_status(self) -> bool:
        return bool(self.proximos_status_permitidos) and self.dependencias_concluidas

    def __str__(self) -> str:
        return f"{self.processo} - {self.get_tipo_etapa_display()}"

    def get_absolute_url(self):
        return reverse("acompanhamento_sistemas_processo_etapa_detail", kwargs={"pk": self.pk})

    @property
    def status_visual_classe(self) -> str:
        mapa = {
            self.Status.PENDENTE: "pendente",
            self.Status.EM_ANDAMENTO: "em_andamento",
            self.Status.VALIDACAO: "validacao",
            self.Status.APROVADO: "aprovado",
            self.Status.REPROVADO: "reprovado_vivo",
            self.Status.RETIRADO_ESCOPO: "retirado_escopo",
        }
        return mapa.get(self.status, "pendente")


class HistoricoProcessoRequisito(models.Model):
    class TipoEvento(models.TextChoices):
        CRIACAO = "CRIACAO", "Criação"
        EDICAO = "EDICAO", "Edição"
        EXCLUSAO = "EXCLUSAO", "Exclusão"
        NOTA = "NOTA", "Nota"
        GERACAO_CICLO = "GERACAO_CICLO", "Geração de ciclo"
        GERACAO_SISTEMA = "GERACAO_SISTEMA", "Geração de sistema"

    processo = models.ForeignKey(ProcessoRequisito, on_delete=models.CASCADE, related_name="historicos")
    tipo_evento = models.CharField(max_length=30, choices=TipoEvento.choices)
    descricao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historicos_processo_requisito_criados",
    )

    class Meta:
        ordering = ["-criado_em", "-id"]
        verbose_name = "Histórico do processo de requisito"
        verbose_name_plural = "Históricos do processo de requisito"

    def __str__(self) -> str:
        return f"Histórico processo #{self.pk} - {self.processo}"


class HistoricoEtapaProcessoRequisito(models.Model):
    class TipoEvento(models.TextChoices):
        CRIACAO = "CRIACAO", "Criação"
        STATUS = "STATUS", "Status"
        NOTA = "NOTA", "Nota"
        ANEXO = "ANEXO", "Anexo"

    etapa = models.ForeignKey(EtapaProcessoRequisito, on_delete=models.CASCADE, related_name="historicos")
    tipo_evento = models.CharField(max_length=20, choices=TipoEvento.choices)
    descricao = models.TextField(blank=True)
    status_anterior = models.CharField(max_length=20, blank=True)
    status_novo = models.CharField(max_length=20, blank=True)
    justificativa = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historicos_etapa_processo_requisito_criados",
    )

    class Meta:
        ordering = ["-criado_em", "-id"]
        verbose_name = "Histórico da etapa do processo de requisito"
        verbose_name_plural = "Históricos da etapa do processo de requisito"

    def __str__(self) -> str:
        return f"Histórico etapa processo #{self.pk} - {self.etapa}"


class AnexoHistoricoProcessoRequisito(models.Model):
    historico = models.ForeignKey(HistoricoProcessoRequisito, on_delete=models.CASCADE, related_name="anexos")
    arquivo = models.FileField(upload_to="acompanhamento_sistemas/anexos/")
    nome_original = models.CharField(max_length=255, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Anexo do histórico do processo de requisito"
        verbose_name_plural = "Anexos do histórico do processo de requisito"

    def save(self, *args, **kwargs):
        if self.arquivo and not self.nome_original:
            self.nome_original = getattr(self.arquivo, "name", "") or ""
        return super().save(*args, **kwargs)

    @property
    def nome_exibicao(self) -> str:
        return self.nome_original or os.path.basename(getattr(self.arquivo, "name", "") or "")


class AnexoHistoricoEtapaProcessoRequisito(models.Model):
    historico = models.ForeignKey(HistoricoEtapaProcessoRequisito, on_delete=models.CASCADE, related_name="anexos")
    arquivo = models.FileField(upload_to="acompanhamento_sistemas/anexos/")
    nome_original = models.CharField(max_length=255, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Anexo do histórico da etapa do processo de requisito"
        verbose_name_plural = "Anexos do histórico da etapa do processo de requisito"

    def save(self, *args, **kwargs):
        if self.arquivo and not self.nome_original:
            self.nome_original = getattr(self.arquivo, "name", "") or ""
        return super().save(*args, **kwargs)

    @property
    def nome_exibicao(self) -> str:
        return self.nome_original or os.path.basename(getattr(self.arquivo, "name", "") or "")
