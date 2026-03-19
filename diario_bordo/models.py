"""
Modelos de domínio do app `diario_bordo`.

Este módulo representa a trilha operacional de blocos de trabalho e seus
incrementos, incluindo:
- registro de ciência por usuário;
- controle de leitura do último incremento visualizado;
- vínculo opcional com contratos do app `contratos`.
"""

import os
import re

from django.db import models
from django.urls import reverse
from django.utils import timezone


def normalizar_nome_marcador(nome: str) -> str:
    """Normaliza nome para deduplicação semântica de marcadores."""

    base = (nome or "").strip().lower()
    base = re.sub(r"\s+", " ", base)
    return base


def escolher_cor_marcador() -> str:
    """Retorna cor padrão para novo marcador do Diário."""

    return "#5b7db1"


class BlocoTrabalho(models.Model):
    """
    Entidade que representa um bloco de trabalho no Diário de Bordo.

    Cada bloco agrega contexto (nome/descrição), status de execução,
    participantes responsáveis e incrementos cronológicos.
    """

    class Status(models.TextChoices):
        """Estados operacionais possíveis para o ciclo de vida do bloco."""

        A_FAZER = "A_FAZER", "À Fazer"
        SOLICITO_TERCEIROS = "SOLICITO_TERCEIROS", "Solicitado à terceiros"
        AGUARDANDO_RESPOSTA = "AGUARDANDO_RESPOSTA", "Aguardando resposta"
        EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
        CONCLUIDO = "CONCLUIDO", "Concluído"

    nome = models.CharField(max_length=200)
    descricao = models.TextField(blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.A_FAZER)
    criado_em = models.DateTimeField(default=timezone.now)
    atualizado_em = models.DateTimeField(null=True, blank=True)
    atualizado_por = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blocos_atualizados',
    )
    contrato = models.ForeignKey(
        "contratos.Contrato",
        on_delete=models.SET_NULL,
        related_name="blocos_trabalho",
        null=True,
        blank=True,
    )
    participantes = models.ManyToManyField(
        "auth.User",
        related_name="blocos_trabalho",
        blank=True,
    )

    class Meta:
        """Ordena blocos por criação mais recente para priorizar operação atual."""

        ordering = ["-criado_em"]

    def __str__(self):
        """
        Representação textual padrão do bloco.

        Retorno:
        - `str`: nome do bloco.
        """

        return self.nome

    def get_absolute_url(self):
        """
        Resolve URL canônica de detalhe do bloco.

        Retorno:
        - `str`: rota nomeada `diario_bordo_detail`.
        """

        return reverse("diario_bordo_detail", kwargs={"pk": self.pk})

    @property
    def marcadores_locais(self):
        return [
            vinculo.marcador
            for vinculo in self.marcadores_vinculos.select_related("marcador")
            if vinculo.marcador and vinculo.marcador.ativo
        ]

    @property
    def marcadores_efetivos(self):
        return self.marcadores_locais

    def definir_marcadores_locais_por_ids(self, ids):
        ids_validos = {
            int(item) for item in (ids or []) if str(item).isdigit()
        }
        existentes = {
            vinculo.marcador_id: vinculo
            for vinculo in self.marcadores_vinculos.all()
        }
        para_remover = [pk for pk in existentes.keys() if pk not in ids_validos]
        if para_remover:
            DiarioMarcadorVinculo.objects.filter(
                bloco=self,
                marcador_id__in=para_remover,
            ).delete()
        for marcador_id in ids_validos:
            if marcador_id in existentes:
                continue
            DiarioMarcadorVinculo.objects.create(
                bloco=self,
                marcador_id=marcador_id,
            )


class Incremento(models.Model):
    """
    Registro de atualização textual/mídia dentro de um bloco.

    Cada incremento documenta uma evolução pontual do trabalho e pode conter
    texto, imagem e anexo, além do autor e horário da inclusão.
    """

    bloco = models.ForeignKey(BlocoTrabalho, on_delete=models.CASCADE, related_name="incrementos")
    texto = models.TextField()
    imagem = models.ImageField(upload_to="diario_bordo/imagens/", blank=True, null=True)
    anexo = models.FileField(upload_to="diario_bordo/anexos/", blank=True, null=True)
    criado_em = models.DateTimeField(default=timezone.now)
    criado_por = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='incrementos_criados',
    )

    class Meta:
        """Ordena incrementos do mais recente para o mais antigo."""

        ordering = ["-criado_em"]

    def __str__(self):
        """
        Representação curta para listagens/admin.

        Retorno:
        - `str`: bloco + timestamp do incremento.
        """

        return f"{self.bloco} - {self.criado_em:%d/%m/%Y %H:%M}"

    @property
    def anexo_nome(self):
        """
        Extrai apenas o nome do arquivo anexado.

        Retorno:
        - `str`: basename do caminho do anexo ou vazio.
        """

        if not self.anexo:
            return ""
        return os.path.basename(self.anexo.name)


class IncrementoAnexo(models.Model):
    """Arquivo anexado a um incremento."""

    incremento = models.ForeignKey(
        Incremento,
        on_delete=models.CASCADE,
        related_name="anexos",
    )
    arquivo = models.FileField(upload_to="diario_bordo/anexos/")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criado_em", "id"]

    @property
    def nome_arquivo(self):
        if not self.arquivo:
            return ""
        return os.path.basename(self.arquivo.name)


class IncrementoCiencia(models.Model):
    """
    Confirmação de ciência de um incremento por usuário.

    Entidade de rastreabilidade:
    - evita duplicidade por usuário/incremento (`unique_together`);
    - mantém histórico de quem confirmou leitura.
    """

    incremento = models.ForeignKey(
        Incremento,
        on_delete=models.CASCADE,
        related_name="ciencias",
    )
    usuario = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="incrementos_ciencias",
    )
    texto = models.TextField()
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        """Ordena por ordem cronológica e garante unicidade por usuário/incremento."""

        ordering = ["criado_em"]
        unique_together = ("incremento", "usuario")

    def __str__(self):
        """
        Representação técnica compacta da ciência registrada.

        Retorno:
        - `str`: ids envolvidos + timestamp.
        """

        return f"{self.incremento_id} - {self.usuario_id} - {self.criado_em:%d/%m/%Y %H:%M}"


class BlocoLeitura(models.Model):
    """
    Controla o último incremento visto por usuário em cada bloco.

    Serve para funcionalidades de "visualizado", evitando alertas/pendências
    para conteúdos já lidos pelo participante.
    """
    usuario = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="bloco_leituras",
    )
    bloco = models.ForeignKey(
        BlocoTrabalho,
        on_delete=models.CASCADE,
        related_name="leituras",
    )
    ultimo_incremento_visto_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        """Garante um registro de leitura por par usuário/bloco."""

        unique_together = ("usuario", "bloco")


class DiarioMarcador(models.Model):
    """Marcador reutilizável apenas no contexto do Diário de Bordo."""

    nome = models.CharField(max_length=80, unique=True)
    nome_normalizado = models.CharField(max_length=80, unique=True)
    cor = models.CharField(max_length=7, default=escolher_cor_marcador)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Marcador do Diário"
        verbose_name_plural = "Marcadores do Diário"

    def save(self, *args, **kwargs):
        self.nome = re.sub(r"\s+", " ", (self.nome or "").strip())
        self.nome_normalizado = normalizar_nome_marcador(self.nome)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome


class DiarioMarcadorVinculo(models.Model):
    """Vínculo entre bloco de trabalho e marcador."""

    bloco = models.ForeignKey(
        BlocoTrabalho,
        on_delete=models.CASCADE,
        related_name="marcadores_vinculos",
    )
    marcador = models.ForeignKey(
        DiarioMarcador,
        on_delete=models.CASCADE,
        related_name="blocos_vinculos",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("bloco", "marcador")
        ordering = ["id"]
