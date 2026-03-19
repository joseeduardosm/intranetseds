"""
Modelos de domínio do app `reserva_salas`.

Este arquivo concentra as entidades persistidas no banco de dados para o fluxo
 de agendamento de salas. Na arquitetura Django, ele é consumido por:
- `forms.py`: validações de capacidade, recursos e conflito de horário;
- `views.py`: consultas para listagem, detalhe e operações CRUD;
- `admin.py`: configuração de visualização no Django Admin;
- templates `templates/reserva_salas/*`: exibição dos dados de salas e reservas.

Também há integração com autenticação (`AUTH_USER_MODEL`) para rastrear quem
registrou a reserva e com o app `auditoria` (threadlocal) para preencher esse
usuário automaticamente durante o `save`.
"""

from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import models
import random
import uuid


User = get_user_model()


# Paleta de cores usada para identificar visualmente as salas no calendário.
SALA_COLORS = [
    "#1D4ED8",
    "#0F766E",
    "#7C3AED",
    "#B45309",
    "#BE185D",
    "#166534",
    "#C2410C",
    "#334155",
    "#0891B2",
    "#4F46E5",
    "#0369A1",
    "#15803D",
    "#A21CAF",
    "#9A3412",
    "#1E40AF",
    "#6D28D9",
    "#0E7490",
    "#854D0E",
    "#BE123C",
    "#14532D",
]


def random_sala_color() -> str:
    """
    Retorna uma cor aleatória da paleta de salas.

    Problema que resolve:
    - Evita que novas salas sejam cadastradas sem cor de identificação visual.

    Retorno:
    - `str`: código hexadecimal da cor (ex.: `#1D4ED8`).
    """
    return random.choice(SALA_COLORS)


class Sala(models.Model):
    """
    Entidade de catálogo de salas físicas reserváveis.

    Papel na arquitetura:
    - Representa os recursos estruturais disponíveis (capacidade e equipamentos)
      que serão reutilizados pelas reservas.

    Papel no domínio:
    - Cada registro representa um ambiente físico da organização, com limite de
      pessoas e infraestrutura (TV, projetor, videowall etc.).
    """

    nome = models.CharField("Nome da sala", max_length=120)
    capacidade = models.PositiveIntegerField("Capacidade de pessoas")
    localizacao = models.CharField("Localizacao", max_length=160)
    cor = models.CharField("Cor", max_length=7, default=random_sala_color, editable=False)

    televisao = models.BooleanField("Televisao", default=False)
    projetor = models.BooleanField("Projetor", default=False)
    som = models.BooleanField("Som", default=False)
    microfone_evento = models.BooleanField("Microfone (evento)", default=False)
    som_evento = models.BooleanField("Som (evento)", default=False)
    mesa_som_evento = models.BooleanField("Mesa de som (evento)", default=False)
    videowall = models.BooleanField("Videowall", default=False)
    wifi = models.BooleanField("Wi-Fi", default=False)

    class Meta:
        # Padroniza a navegação em telas/listas por ordem alfabética do nome.
        ordering = ["nome"]

    def __str__(self) -> str:
        """
        Retorna a representação textual da sala para admin, formulários e logs.
        """
        return self.nome

    @property
    def recursos_disponiveis(self):
        """
        Lista os recursos ativos da sala em formato legível para interface.

        Problema que resolve:
        - Centraliza a transformação dos campos booleanos em uma coleção textual
          reutilizável em templates e serializações simples.

        Retorno:
        - `list[str]`: nomes dos recursos habilitados na sala.
        """
        recursos = []
        if self.televisao:
            recursos.append("Televisao")
        if self.projetor:
            recursos.append("Projetor")
        if self.som:
            recursos.append("Som")
        if self.microfone_evento:
            recursos.append("Microfone (evento)")
        if self.som_evento:
            recursos.append("Som (evento)")
        if self.mesa_som_evento:
            recursos.append("Mesa de som (evento)")
        if self.videowall:
            recursos.append("Videowall")
        if self.wifi:
            recursos.append("Wi-Fi")
        return recursos

    def save(self, *args, **kwargs):
        """
        Garante cor válida antes de persistir o registro.

        Regra de negócio:
        - Se por qualquer motivo a cor estiver vazia, define uma cor da paleta
          para manter consistência visual do calendário.
        """
        if not self.cor:
            self.cor = random_sala_color()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """
        Retorna a rota canônica de detalhe da sala.

        Uso na arquitetura:
        - Permite que views genéricas e templates resolvam o destino pós-operação
          sem duplicar conhecimento de URL.
        """
        from django.urls import reverse

        return reverse("salas_detail", kwargs={"pk": self.pk})


class Reserva(models.Model):
    """
    Entidade transacional de reserva de sala para um evento.

    Papel na arquitetura:
    - Armazena data/hora, responsáveis e recursos solicitados no contexto de uma
      sala específica.

    Papel no domínio:
    - Cada registro representa um compromisso em agenda para bloqueio de uso de
      uma sala em um intervalo de tempo.
    """

    sala = models.ForeignKey(Sala, on_delete=models.CASCADE, related_name="reservas")
    data = models.DateField("Data")
    hora_inicio = models.TimeField("Hora de inicio")
    hora_fim = models.TimeField("Hora de fim")
    nome_evento = models.CharField("Nome do evento", max_length=160)
    responsavel_evento = models.CharField("Responsavel pelo evento", max_length=160)
    quantidade_pessoas = models.PositiveIntegerField("Quantidade de pessoas")

    televisao = models.BooleanField("Televisao", default=False)
    projetor = models.BooleanField("Projetor", default=False)
    som = models.BooleanField("Som", default=False)
    microfone_evento = models.BooleanField("Microfone (evento)", default=False)
    som_evento = models.BooleanField("Som (evento)", default=False)
    mesa_som_evento = models.BooleanField("Mesa de som (evento)", default=False)
    videowall = models.BooleanField("Videowall", default=False)
    wifi = models.BooleanField("Wi-Fi", default=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservas_registradas",
    )
    serie_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        # Exibe agenda priorizando datas mais recentes e horário de início.
        ordering = ["-data", "hora_inicio"]

    def __str__(self) -> str:
        """
        Representação curta para admin e referências rápidas da reserva.
        """
        return f"{self.nome_evento} - {self.sala.nome}"

    @property
    def inicio_datetime(self):
        """
        Converte a data e hora inicial em `datetime` para comparações temporais.

        Retorno:
        - `datetime`: instante de início da reserva.
        """
        return datetime.combine(self.data, self.hora_inicio)

    @property
    def fim_datetime(self):
        """
        Converte a data e hora final em `datetime` para comparações temporais.

        Retorno:
        - `datetime`: instante de término da reserva.
        """
        return datetime.combine(self.data, self.hora_fim)

    def get_absolute_url(self):
        """
        Retorna a rota canônica de detalhe da reserva.
        """
        from django.urls import reverse

        return reverse("reservas_detail", kwargs={"pk": self.pk})

    def _sync_registro(self):
        """
        Sincroniza o usuário autenticado no campo `registrado_por`.

        Integração externa:
        - Tenta ler o usuário corrente via `auditoria.threadlocal.get_current_user`.

        Regra de negócio:
        - Preenche o autor da reserva somente quando há usuário autenticado e o
          campo ainda não foi definido manualmente.
        """
        try:
            from auditoria.threadlocal import get_current_user
        except Exception:
            user = None
        else:
            user = get_current_user()
        if getattr(user, "is_authenticated", False) and not self.registrado_por:
            self.registrado_por = user

    def save(self, *args, **kwargs):
        """
        Hook de persistência para manter rastreabilidade de autoria.

        Fluxo:
        - Executa sincronização de usuário e delega o restante ao `save` padrão
          do Django sem alterar outras regras do ORM.
        """
        self._sync_registro()
        super().save(*args, **kwargs)
