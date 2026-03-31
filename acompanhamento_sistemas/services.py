from __future__ import annotations

from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend
from django.db import transaction
from django.utils import timezone

from administracao.models import SMTPConfiguration
from auditoria.models import AuditLog

from .models import (
    AnexoHistoricoEtapa,
    EntregaSistema,
    EtapaSistema,
    HistoricoEtapaSistema,
    Sistema,
)
from .utils import nome_usuario_exibicao


ETAPAS_INICIAIS = [
    (1, EtapaSistema.TipoEtapa.REQUISITOS),
    (2, EtapaSistema.TipoEtapa.HOMOLOGACAO_REQUISITOS),
    (3, EtapaSistema.TipoEtapa.DESENVOLVIMENTO),
    (4, EtapaSistema.TipoEtapa.HOMOLOGACAO_DESENVOLVIMENTO),
    (5, EtapaSistema.TipoEtapa.PRODUCAO),
]


def _usuario_ativo(usuario):
    return usuario if getattr(usuario, "is_authenticated", False) else None


def _registrar_auditoria(objeto, *, usuario=None, acao=AuditLog.Action.UPDATE, changes=None):
    AuditLog.objects.create(
        user=_usuario_ativo(usuario),
        action=acao,
        content_type=ContentType.objects.get_for_model(objeto.__class__),
        object_id=str(objeto.pk),
        object_repr=str(objeto),
        changes=changes or {},
    )


def _configuracao_smtp():
    return SMTPConfiguration.objects.filter(ativo=True).order_by("-atualizado_em").first()


def _destinatarios_sistema(sistema: Sistema) -> list[str]:
    return sistema.interessados_emails


def _conteudo_email_historico(historico: HistoricoEtapaSistema) -> str:
    if (
        historico.tipo_evento == HistoricoEtapaSistema.TipoEvento.STATUS
        and historico.status_anterior
        and historico.status_novo
    ):
        status_anterior = EtapaSistema.Status(historico.status_anterior).label.lower()
        status_novo = EtapaSistema.Status(historico.status_novo).label.lower()
        return f"Status alterado de {status_anterior} para {status_novo}."
    return (historico.descricao or "-").strip() or "-"


def _corpo_email_historico(historico: HistoricoEtapaSistema, *, responsavel: str, link: str) -> str:
    sistema = historico.etapa.entrega.sistema
    linhas = [
        f"Sistema: {sistema.nome}",
        f"Entrega: {historico.etapa.entrega.titulo}",
        f"Etapa: {historico.etapa.get_tipo_etapa_display()}",
        f"Tipo de atualização: {historico.get_tipo_evento_display()}",
        f"Conteúdo: {_conteudo_email_historico(historico)}",
    ]
    if historico.justificativa:
        linhas.append(f"Justificativa: {historico.justificativa}")
    linhas.extend(
        [
            f"Responsável: {responsavel}",
            f"Data/hora: {timezone.localtime(historico.criado_em).strftime('%d/%m/%Y %H:%M')}",
            "",
            "Este é um e-mail automático. Não responda.",
            "Para mais informações, acesse:",
            link,
        ]
    )
    return "\n".join(linhas)


def recalcular_tempos_etapas(entrega: EntregaSistema):
    etapas = list(entrega.etapas.order_by("ordem", "id"))
    anterior = None
    for etapa in etapas:
        novo_valor = None
        if anterior is not None:
            novo_valor = (etapa.data_etapa - anterior.data_etapa).days
        if etapa.tempo_desde_etapa_anterior_em_dias != novo_valor:
            etapa.tempo_desde_etapa_anterior_em_dias = novo_valor
            etapa.save(update_fields=["tempo_desde_etapa_anterior_em_dias", "atualizado_em"])
        anterior = etapa


@transaction.atomic
def criar_entrega_com_etapas(sistema: Sistema, *, usuario=None, titulo="", descricao="") -> EntregaSistema:
    proxima_ordem = (sistema.entregas.order_by("-ordem").values_list("ordem", flat=True).first() or 0) + 1
    entrega = EntregaSistema.objects.create(
        sistema=sistema,
        titulo=titulo,
        descricao=descricao,
        ordem=proxima_ordem,
        criado_por=_usuario_ativo(usuario),
        atualizado_por=_usuario_ativo(usuario),
    )
    _registrar_auditoria(entrega, usuario=usuario, acao=AuditLog.Action.CREATE, changes={"titulo": titulo})

    hoje = timezone.localdate()
    for ordem, tipo_etapa in ETAPAS_INICIAIS:
        etapa = EtapaSistema.objects.create(
            entrega=entrega,
            tipo_etapa=tipo_etapa,
            data_etapa=hoje,
            status=EtapaSistema.Status.PENDENTE,
            ordem=ordem,
            criado_por=_usuario_ativo(usuario),
            atualizado_por=_usuario_ativo(usuario),
        )
        HistoricoEtapaSistema.objects.create(
            etapa=etapa,
            tipo_evento=HistoricoEtapaSistema.TipoEvento.CRIACAO,
            descricao="Etapa criada automaticamente na abertura do ciclo.",
            status_novo=etapa.status,
            data_nova=etapa.data_etapa,
            criado_por=_usuario_ativo(usuario),
        )
        _registrar_auditoria(
            etapa,
            usuario=usuario,
            acao=AuditLog.Action.CREATE,
            changes={"status": etapa.status, "data_etapa": etapa.data_etapa.isoformat()},
        )
    recalcular_tempos_etapas(entrega)
    return entrega


def _descricao_historico(etapa: EtapaSistema, *, status_anterior="", status_novo="", data_anterior=None, data_nova=None, nota=""):
    nota = (nota or "").strip()
    partes = []
    if status_anterior and status_novo and status_anterior != status_novo:
        partes.append(
            f"Status alterado de {EtapaSistema.Status(status_anterior).label} para {EtapaSistema.Status(status_novo).label}."
        )
    if data_anterior and data_nova and data_anterior != data_nova:
        partes.append(
            f"Data alterada de {data_anterior.strftime('%d/%m/%Y')} para {data_nova.strftime('%d/%m/%Y')}."
        )
    if nota:
        partes.append(nota)
    if not partes:
        partes.append(f"Atualizacao registrada na etapa {etapa.get_tipo_etapa_display()}.")
    return " ".join(partes)


def enviar_notificacao_historico(historico: HistoricoEtapaSistema, *, request=None):
    if historico.tipo_evento not in {
        HistoricoEtapaSistema.TipoEvento.STATUS,
        HistoricoEtapaSistema.TipoEvento.DATA,
        HistoricoEtapaSistema.TipoEvento.NOTA,
        HistoricoEtapaSistema.TipoEvento.ANEXO,
    }:
        return

    destinatarios = _destinatarios_sistema(historico.etapa.entrega.sistema)
    if not destinatarios:
        return

    config = _configuracao_smtp()
    if config is None:
        return

    connection_email = EmailBackend(
        host=config.host,
        port=config.port,
        username=config.username,
        password=config.password,
        use_tls=config.use_tls,
        use_ssl=config.use_ssl,
        timeout=config.timeout,
        fail_silently=False,
    )
    sistema = historico.etapa.entrega.sistema
    if request is not None:
        link = request.build_absolute_uri(historico.etapa.get_absolute_url())
    else:
        link = sistema.get_absolute_url()
    assunto = f"Sistema SEDS - {sistema.nome} - Atualizações de {timezone.localdate().strftime('%d/%m/%Y')}"
    responsavel = "Sistema"
    if historico.criado_por:
        responsavel = nome_usuario_exibicao(historico.criado_por) or "Sistema"
    corpo = _corpo_email_historico(historico, responsavel=responsavel, link=link)
    message = EmailMessage(
        subject=assunto,
        body=corpo,
        from_email=config.from_email,
        to=destinatarios,
        connection=connection_email,
    )
    message.send(fail_silently=False)


def _avancar_proxima_etapa_automaticamente(etapa: EtapaSistema, *, usuario=None, request=None):
    if etapa.status != EtapaSistema.Status.ENTREGUE:
        return None

    proxima_etapa = (
        etapa.entrega.etapas.filter(ordem__gt=etapa.ordem)
        .order_by("ordem", "id")
        .first()
    )
    if proxima_etapa is None or proxima_etapa.status != EtapaSistema.Status.PENDENTE:
        return None

    status_anterior = proxima_etapa.status
    proxima_etapa.status = EtapaSistema.Status.EM_ANDAMENTO
    proxima_etapa.atualizado_por = _usuario_ativo(usuario)
    proxima_etapa.save(update_fields=["status", "atualizado_por", "atualizado_em"])

    historico = HistoricoEtapaSistema.objects.create(
        etapa=proxima_etapa,
        tipo_evento=HistoricoEtapaSistema.TipoEvento.STATUS,
        descricao=(
            f"Status alterado automaticamente de {EtapaSistema.Status(status_anterior).label} "
            f"para {EtapaSistema.Status(proxima_etapa.status).label} apos conclusao da etapa anterior."
        ),
        status_anterior=status_anterior,
        status_novo=proxima_etapa.status,
        justificativa="Avanço automático para a próxima etapa após conclusão da etapa anterior.",
        criado_por=_usuario_ativo(usuario),
    )
    _registrar_auditoria(
        proxima_etapa,
        usuario=usuario,
        acao=AuditLog.Action.UPDATE,
        changes={
            "status": [status_anterior, proxima_etapa.status],
            "tipo_evento": historico.tipo_evento,
        },
    )
    enviar_notificacao_historico(historico, request=request)
    return historico


@transaction.atomic
def atualizar_etapa_com_historico(
    etapa: EtapaSistema,
    *,
    nova_data: date,
    novo_status: str,
    justificativa: str,
    texto_nota: str,
    anexos,
    usuario=None,
    request=None,
) -> HistoricoEtapaSistema:
    justificativa = (justificativa or "").strip()
    texto_nota = (texto_nota or "").strip()
    anexos = anexos or []
    status_anterior = etapa.status
    data_anterior = etapa.data_etapa
    status_alterado = bool(novo_status and novo_status != etapa.status)
    data_alterada = bool(nova_data and nova_data != etapa.data_etapa)
    possui_nota = bool(texto_nota or anexos)

    if status_alterado and not justificativa:
        raise ValidationError("Toda alteração de status exige justificativa.")
    if not status_alterado and not data_alterada and not possui_nota:
        raise ValidationError("Nenhuma alteração foi informada.")

    if novo_status:
        etapa.status = novo_status
    if nova_data:
        etapa.data_etapa = nova_data
    etapa.atualizado_por = _usuario_ativo(usuario)
    etapa.save(update_fields=["status", "data_etapa", "atualizado_por", "atualizado_em"])
    recalcular_tempos_etapas(etapa.entrega)

    if status_alterado:
        tipo_evento = HistoricoEtapaSistema.TipoEvento.STATUS
    elif data_alterada:
        tipo_evento = HistoricoEtapaSistema.TipoEvento.DATA
    elif anexos and not texto_nota:
        tipo_evento = HistoricoEtapaSistema.TipoEvento.ANEXO
    else:
        tipo_evento = HistoricoEtapaSistema.TipoEvento.NOTA

    historico = HistoricoEtapaSistema.objects.create(
        etapa=etapa,
        tipo_evento=tipo_evento,
        descricao=_descricao_historico(
            etapa,
            status_anterior=status_anterior,
            status_novo=etapa.status,
            data_anterior=data_anterior,
            data_nova=etapa.data_etapa,
            nota=texto_nota,
        ),
        status_anterior=status_anterior if status_alterado else "",
        status_novo=etapa.status if status_alterado else "",
        data_anterior=data_anterior if data_alterada else None,
        data_nova=etapa.data_etapa if data_alterada else None,
        justificativa=justificativa,
        criado_por=_usuario_ativo(usuario),
    )
    for arquivo in anexos:
        AnexoHistoricoEtapa.objects.create(
            historico=historico,
            arquivo=arquivo,
            nome_original=getattr(arquivo, "name", "") or "",
        )

    _registrar_auditoria(
        etapa,
        usuario=usuario,
        acao=AuditLog.Action.UPDATE,
        changes={
            "status": [status_anterior, etapa.status] if status_alterado else etapa.status,
            "data_etapa": [
                data_anterior.isoformat() if data_anterior else "",
                etapa.data_etapa.isoformat() if etapa.data_etapa else "",
            ]
            if data_alterada
            else etapa.data_etapa.isoformat(),
            "tipo_evento": historico.tipo_evento,
        },
    )
    enviar_notificacao_historico(historico, request=request)
    _avancar_proxima_etapa_automaticamente(etapa, usuario=usuario, request=request)
    return historico


def adicionar_nota_etapa(etapa: EtapaSistema, *, texto: str, anexos, usuario=None, request=None) -> HistoricoEtapaSistema:
    return atualizar_etapa_com_historico(
        etapa,
        nova_data=etapa.data_etapa,
        novo_status=etapa.status,
        justificativa="",
        texto_nota=texto,
        anexos=anexos,
        usuario=usuario,
        request=request,
    )
