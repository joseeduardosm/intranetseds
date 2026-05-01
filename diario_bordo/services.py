from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone

from notificacoes.services import emitir_notificacao

from .models import BlocoTrabalho, Incremento, IncrementoCiencia


User = get_user_model()
SOURCE_DIARIO_BORDO = "diario_bordo"


def _usuarios_notificacao_bloco(bloco: BlocoTrabalho, *, exclude_user=None):
    queryset = bloco.participantes.filter(is_active=True).distinct()
    if exclude_user and getattr(exclude_user, "pk", None):
        queryset = queryset.exclude(pk=exclude_user.pk)
    return queryset


def _nome_usuario(usuario) -> str:
    if not usuario:
        return "Sistema"
    return (usuario.get_full_name() or usuario.username or "Sistema").strip()


def _data_hora(valor) -> str:
    return timezone.localtime(valor).strftime("%d/%m/%Y %H:%M")


def emitir_notificacao_incremento(incremento: Incremento):
    bloco = incremento.bloco
    users = _usuarios_notificacao_bloco(bloco, exclude_user=incremento.criado_por)
    emitir_notificacao(
        users=users,
        source_app=SOURCE_DIARIO_BORDO,
        event_type="incremento",
        title=f"Diário de Bordo: {bloco.nome}",
        body_short=(
            f"Incremento: {(incremento.texto or '-').strip()[:320]}\n"
            f"{_nome_usuario(incremento.criado_por)}, {_data_hora(incremento.criado_em)}"
        ),
        target_url=bloco.get_absolute_url(),
        dedupe_key=f"diario-bordo-incremento-{incremento.pk}",
        payload_json={
            "bloco_id": bloco.pk,
            "incremento_id": incremento.pk,
        },
    )


def emitir_notificacao_ciencia(ciencia: IncrementoCiencia):
    incremento = ciencia.incremento
    bloco = incremento.bloco
    users = _usuarios_notificacao_bloco(bloco, exclude_user=ciencia.usuario)
    emitir_notificacao(
        users=users,
        source_app=SOURCE_DIARIO_BORDO,
        event_type="ciencia_incremento",
        title=f"Diário de Bordo: {bloco.nome}",
        body_short=(
            f"Ciência registrada no incremento: {(incremento.texto or '-').strip()[:220]}\n"
            f"{_nome_usuario(ciencia.usuario)}, {_data_hora(ciencia.criado_em)}"
        ),
        target_url=bloco.get_absolute_url(),
        dedupe_key=f"diario-bordo-ciencia-{ciencia.pk}",
        payload_json={
            "bloco_id": bloco.pk,
            "incremento_id": incremento.pk,
            "ciencia_id": ciencia.pk,
        },
    )
