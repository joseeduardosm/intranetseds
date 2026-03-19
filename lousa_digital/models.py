"""
Modelos de domínio da Lousa Digital.

Este arquivo define as entidades persistidas que compõem o fluxo de monitoramento
de processos e encaminhamentos. Ele se integra com:
- `views.py`, que executa consultas e transições de estado;
- `forms.py`, que valida entrada de criação/edição;
- templates da lousa, que exibem timeline e indicadores de prazo;
- comando de importação CSV, que popula as tabelas em lote.
"""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import models
from django.utils import timezone


User = get_user_model()


class Processo(models.Model):
    """Entidade central da lousa, representando um processo SEI monitorado.

    Cada processo possui dados básicos, status operacional e metadados de
    auditoria (quem criou/atualizou e grupo de inserção para visibilidade).
    """

    class Status(models.TextChoices):
        """Estados de ciclo de vida do processo no quadro da lousa."""

        EM_ABERTO = "EM_ABERTO", "Em aberto"
        CONCLUIDO = "CONCLUIDO", "Concluido"

    numero_sei = models.CharField("Numero SEI", max_length=120, unique=True)
    assunto = models.CharField(max_length=255)
    link_sei = models.URLField("Link SEI", max_length=500, blank=True)
    caixa_origem = models.CharField(max_length=180)
    arquivo_morto = models.BooleanField("Arquivo morto", default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.EM_ABERTO)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    atualizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processos_lousa_atualizados",
    )
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processos_lousa_criados",
    )
    grupo_insercao = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processos_lousa",
    )

    class Meta:
        """Mantém processos mais recentes no topo da listagem principal."""

        ordering = ["-atualizado_em"]

    def __str__(self) -> str:
        """Retorna identificação legível para admin e seleções."""

        return f"{self.numero_sei} - {self.assunto}"

    @property
    def encaminhamentos_ativos(self):
        """Consulta apenas encaminhamentos ainda não devolvidos.

        Retorno:
        - `QuerySet[Encaminhamento]` com `data_conclusao` nula.
        """

        return self.encaminhamentos.filter(data_conclusao__isnull=True)

    def encaminhamento_ativo_prioritario(self):
        """Seleciona o ativo com prazo mais próximo (mais urgente).

        Retorno:
        - `Encaminhamento` prioritário ou `None` quando não há ativos.
        """

        ativos = list(self.encaminhamentos_ativos)
        if not ativos:
            return None
        return min(ativos, key=lambda item: item.prazo_limite)

    def atualizar_status_por_encaminhamentos(self):
        """Sincroniza status do processo com a existência de encaminhamentos ativos.

        Regra de negócio:
        - existe ativo => `EM_ABERTO`;
        - nenhum ativo => `CONCLUIDO`.

        Retorno:
        - `True` se houve mudança de status;
        - `False` se já estava consistente.
        """

        novo_status = self.Status.EM_ABERTO if self.encaminhamentos_ativos.exists() else self.Status.CONCLUIDO
        if self.status != novo_status:
            self.status = novo_status
            self.save(update_fields=["status", "atualizado_em"])
            return True
        return False


class Encaminhamento(models.Model):
    """Representa movimentação de um processo para um destino com prazo definido.

    A entidade registra início, devolução e responsáveis pela criação/conclusão,
    permitindo calcular SLA e percentual de consumo do prazo.
    """

    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name="encaminhamentos")
    destino = models.CharField(max_length=180)
    prazo_data = models.DateField("Prazo")
    data_inicio = models.DateTimeField(auto_now_add=True)
    data_conclusao = models.DateTimeField(null=True, blank=True)
    email_notificacao = models.EmailField(blank=True, null=True)
    notificado_72h_em = models.DateTimeField(null=True, blank=True)
    criado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="encaminhamentos_criados",
    )
    concluido_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="encaminhamentos_concluidos",
    )

    class Meta:
        """Ordena do mais recente para o mais antigo no histórico do processo."""

        ordering = ["-data_inicio"]

    def __str__(self) -> str:
        """Resumo textual do vínculo processo -> destino."""

        return f"{self.processo.numero_sei} -> {self.destino}"

    @property
    def prazo_limite(self):
        """Calcula datetime final do prazo (23:59:59 da data de prazo).

        Retorno:
        - `datetime` timezone-aware no fuso configurado do sistema.
        """

        limite = datetime.combine(self.prazo_data, time(23, 59, 59))
        if timezone.is_naive(limite):
            return timezone.make_aware(limite, timezone.get_current_timezone())
        return limite

    @property
    def esta_ativo(self):
        """Indica se o encaminhamento ainda está em aberto."""

        return self.data_conclusao is None

    def minutos_decorridos(self):
        """Retorna tempo decorrido em minutos desde início até conclusão/agora."""

        fim = self.data_conclusao or timezone.now()
        total = (fim - self.data_inicio).total_seconds() / 60
        return max(int(total), 0)

    def minutos_prazo_total(self):
        """Retorna janela total do prazo em minutos (mínimo 1)."""

        total = (self.prazo_limite - self.data_inicio).total_seconds() / 60
        return max(int(total), 1)

    def percentual_consumido(self):
        """Calcula percentual de prazo consumido, limitado em 100%."""

        return min((self.minutos_decorridos() / self.minutos_prazo_total()) * 100, 100)

    def marcar_devolvido(self, usuario):
        """Conclui encaminhamento ativo e registra usuário de devolução.

        Parâmetros:
        - `usuario`: usuário autenticado que executou a devolução.

        Retorno:
        - `True` se a devolução foi aplicada;
        - `False` se já estava concluído.
        """

        if self.data_conclusao:
            return False
        self.data_conclusao = timezone.now()
        if usuario and usuario.is_authenticated:
            self.concluido_por = usuario
        self.save(update_fields=["data_conclusao", "concluido_por"])
        return True


class EventoTimeline(models.Model):
    """Registro imutável de eventos de auditoria e comunicação do processo."""

    class Tipo(models.TextChoices):
        """Tipos de eventos suportados na timeline da lousa."""

        PROCESSO_CRIADO = "PROCESSO_CRIADO", "Processo criado"
        PROCESSO_EDITADO = "PROCESSO_EDITADO", "Processo editado"
        ENCAMINHAMENTO_CRIADO = "ENCAMINHAMENTO_CRIADO", "Encaminhamento criado"
        ENCAMINHAMENTO_DEVOLVIDO = "ENCAMINHAMENTO_DEVOLVIDO", "Encaminhamento devolvido"
        EMAIL_72H_ENVIADO = "EMAIL_72H_ENVIADO", "E-mail 72h enviado"
        NOTA = "NOTA", "Nota"
        STATUS_ALTERADO = "STATUS_ALTERADO", "Status alterado"

    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name="eventos")
    encaminhamento = models.ForeignKey(
        Encaminhamento,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos",
    )
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    descricao = models.TextField()
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Exibe eventos mais recentes primeiro na timeline do detalhe."""

        ordering = ["-criado_em", "-id"]

    def __str__(self) -> str:
        """Representação curta do evento para administração e debug."""

        return f"{self.get_tipo_display()} - {self.processo.numero_sei}"
