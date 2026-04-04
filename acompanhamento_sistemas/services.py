from __future__ import annotations

from datetime import date
import logging
import threading

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend
from django.db import close_old_connections, transaction
from django.utils import timezone

from administracao.models import SMTPConfiguration
from auditoria.models import AuditLog
from notificacoes.services import SOURCE_ACOMPANHAMENTO_SISTEMAS, emitir_notificacao

from .models import (
    AnexoHistoricoSistema,
    AnexoHistoricoEtapa,
    EntregaSistema,
    EtapaSistema,
    HistoricoSistema,
    HistoricoEtapaSistema,
    Sistema,
)
from .utils import nome_usuario_exibicao

logger = logging.getLogger(__name__)
User = get_user_model()


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


def _snapshot_configuracao_smtp(config):
    if config is None:
        return None
    return {
        "host": config.host,
        "port": config.port,
        "username": config.username,
        "password": config.password,
        "use_tls": config.use_tls,
        "use_ssl": config.use_ssl,
        "timeout": config.timeout,
        "from_email": config.from_email,
    }


def _enfileirar_email_background(*, config, subject: str, body: str, destinatarios: list[str]):
    if not config or not destinatarios:
        return

    config_snapshot = _snapshot_configuracao_smtp(config)
    destinatarios_snapshot = list(destinatarios)

    def _worker():
        close_old_connections()
        try:
            connection_email = EmailBackend(
                host=config_snapshot["host"],
                port=config_snapshot["port"],
                username=config_snapshot["username"],
                password=config_snapshot["password"],
                use_tls=config_snapshot["use_tls"],
                use_ssl=config_snapshot["use_ssl"],
                timeout=config_snapshot["timeout"],
                fail_silently=False,
            )
            message = EmailMessage(
                subject=subject,
                body=body,
                from_email=config_snapshot["from_email"],
                to=destinatarios_snapshot,
                connection=connection_email,
            )
            message.send(fail_silently=False)
        except Exception:
            logger.exception("Falha ao enviar e-mail assíncrono de acompanhamento de sistemas.")
        finally:
            close_old_connections()

    if getattr(settings, "EMAIL_DELIVERY_SYNC", False):
        _worker()
        return

    transaction.on_commit(lambda: threading.Thread(target=_worker, daemon=True).start())


def _destinatarios_sistema(sistema: Sistema) -> list[str]:
    return sistema.interessados_emails


def _usuarios_notificacao_sistema(sistema: Sistema):
    return User.objects.filter(interesses_em_sistemas__sistema=sistema).distinct()


def _titulo_notificacao_entrega(entrega: EntregaSistema) -> str:
    return f"Sistema: {entrega.sistema.nome}"


def _responsavel_e_data_hora(usuario, criado_em) -> str:
    responsavel = nome_usuario_exibicao(usuario) or "Sistema"
    data_hora = timezone.localtime(criado_em).strftime("%d/%m/%Y %H:%M")
    return f"{responsavel}, {data_hora}"


def _descricao_notificacao_historico_etapa(historico: HistoricoEtapaSistema) -> str:
    etapa = historico.etapa
    etapa_label = etapa.get_tipo_etapa_display()

    if (
        historico.tipo_evento == HistoricoEtapaSistema.TipoEvento.STATUS
        and historico.status_novo
    ):
        status_novo = EtapaSistema.Status(historico.status_novo).label
        return f"Etapa: {etapa_label} - status alterado para {status_novo}."

    if (
        historico.tipo_evento == HistoricoEtapaSistema.TipoEvento.DATA
        and historico.data_nova
    ):
        return f"Etapa: {etapa_label} - data alterada para {historico.data_nova.strftime('%d/%m/%Y')}."

    if historico.tipo_evento == HistoricoEtapaSistema.TipoEvento.NOTA:
        conteudo = (historico.descricao or "-").strip() or "-"
        return f"Etapa: {etapa_label} - nota adicionada. {conteudo[:260]}"

    if historico.tipo_evento == HistoricoEtapaSistema.TipoEvento.ANEXO:
        conteudo = (historico.descricao or "-").strip() or "-"
        return f"Etapa: {etapa_label} - anexo adicionado. {conteudo[:260]}"

    if historico.tipo_evento == HistoricoEtapaSistema.TipoEvento.CRIACAO:
        return f"Etapa: {etapa_label} - etapa criada."

    conteudo = (_conteudo_email_historico(historico) or "-").strip()
    return f"Etapa: {etapa_label} - {conteudo[:260]}"


def _descricao_notificacao_historico_sistema(historico: HistoricoSistema) -> str:
    conteudo = (_conteudo_email_historico_sistema(historico) or "-").strip()
    return f"Sistema: atualização registrada. {conteudo[:260]}"


def _emitir_notificacao_publicacao_desktop(entrega: EntregaSistema):
    emitir_notificacao(
        users=_usuarios_notificacao_sistema(entrega.sistema),
        source_app=SOURCE_ACOMPANHAMENTO_SISTEMAS,
        event_type="publicacao_ciclo",
        title=_titulo_notificacao_entrega(entrega),
        body_short=(
            f"Ciclo: {entrega.titulo}\n"
            "Etapa: Ciclo - cronograma inicial publicado.\n"
            f"{_responsavel_e_data_hora(entrega.atualizado_por or entrega.criado_por, entrega.atualizado_em or entrega.criado_em)}"
        ),
        target_url=entrega.get_absolute_url(),
        dedupe_key=f"acomp-publicacao-entrega-{entrega.pk}-{entrega.status}",
        payload_json={
            "sistema_id": entrega.sistema_id,
            "entrega_id": entrega.pk,
            "entrega_titulo": entrega.titulo_com_numeracao,
        },
    )


def _emitir_notificacao_historico_desktop(historico: HistoricoEtapaSistema):
    etapa = historico.etapa
    entrega = etapa.entrega
    if entrega.status != EntregaSistema.Status.PUBLICADO:
        return
    emitir_notificacao(
        users=_usuarios_notificacao_sistema(entrega.sistema),
        source_app=SOURCE_ACOMPANHAMENTO_SISTEMAS,
        event_type=f"etapa_{historico.tipo_evento.lower()}",
        title=_titulo_notificacao_entrega(entrega),
        body_short=(
            f"Ciclo: {entrega.titulo}\n"
            f"{_descricao_notificacao_historico_etapa(historico)}\n"
            f"{_responsavel_e_data_hora(historico.criado_por, historico.criado_em)}"
        ),
        target_url=etapa.get_absolute_url(),
        dedupe_key=f"acomp-historico-etapa-{historico.pk}",
        payload_json={
            "sistema_id": entrega.sistema_id,
            "entrega_id": entrega.pk,
            "etapa_id": etapa.pk,
            "historico_id": historico.pk,
            "tipo_evento": historico.tipo_evento,
        },
    )


def _emitir_notificacao_historico_sistema_desktop(historico: HistoricoSistema):
    sistema = historico.sistema
    emitir_notificacao(
        users=_usuarios_notificacao_sistema(sistema),
        source_app=SOURCE_ACOMPANHAMENTO_SISTEMAS,
        event_type="sistema_nota",
        title=f"Sistema: {sistema.nome}",
        body_short=(
            "Ciclo: Sistema\n"
            f"{_descricao_notificacao_historico_sistema(historico)}\n"
            f"{_responsavel_e_data_hora(historico.criado_por, historico.criado_em)}"
        ),
        target_url=sistema.get_absolute_url(),
        dedupe_key=f"acomp-historico-sistema-{historico.pk}",
        payload_json={
            "sistema_id": sistema.pk,
            "historico_sistema_id": historico.pk,
            "tipo_evento": historico.tipo_evento,
        },
    )


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


def _conteudo_email_historico_sistema(historico: HistoricoSistema) -> str:
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


def _corpo_email_historico_sistema(historico: HistoricoSistema, *, responsavel: str, link: str) -> str:
    sistema = historico.sistema
    linhas = [
        f"Sistema: {sistema.nome}",
        "Tipo de atualização: Nota do sistema",
        f"Conteúdo: {_conteudo_email_historico_sistema(historico)}",
    ]
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


def _corpo_email_publicacao(entrega: EntregaSistema, *, responsavel: str, link: str) -> str:
    linhas = [
        f"Sistema: {entrega.sistema.nome}",
        f"Ciclo: {entrega.titulo_com_numeracao}",
        "Tipo de atualização: Publicação do cronograma inicial",
        "",
        "Etapas publicadas:",
    ]
    for etapa in entrega.etapas.order_by("ordem", "id"):
        data_formatada = etapa.data_etapa.strftime("%d/%m/%Y") if etapa.data_etapa else "-"
        linhas.append(f"- {etapa.get_tipo_etapa_display()}: {data_formatada}")
    linhas.extend(
        [
            "",
            f"Responsável: {responsavel}",
            f"Data/hora: {timezone.localtime().strftime('%d/%m/%Y %H:%M')}",
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
        if anterior is not None and anterior.data_etapa and etapa.data_etapa:
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
        status=EntregaSistema.Status.RASCUNHO,
        ordem=proxima_ordem,
        criado_por=_usuario_ativo(usuario),
        atualizado_por=_usuario_ativo(usuario),
    )
    _registrar_auditoria(entrega, usuario=usuario, acao=AuditLog.Action.CREATE, changes={"titulo": titulo})

    for ordem, tipo_etapa in ETAPAS_INICIAIS:
        etapa = EtapaSistema.objects.create(
            entrega=entrega,
            tipo_etapa=tipo_etapa,
            data_etapa=None,
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
            changes={"status": etapa.status, "data_etapa": ""},
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
    if data_anterior != data_nova:
        if data_anterior and data_nova:
            partes.append(
                f"Data alterada de {data_anterior.strftime('%d/%m/%Y')} para {data_nova.strftime('%d/%m/%Y')}."
            )
        elif data_nova:
            partes.append(f"Data definida para {data_nova.strftime('%d/%m/%Y')}.")
        elif data_anterior:
            partes.append(f"Data removida (antes {data_anterior.strftime('%d/%m/%Y')}).")
    if nota:
        partes.append(nota)
    if not partes:
        partes.append(f"Atualizacao registrada na etapa {etapa.get_tipo_etapa_display()}.")
    return " ".join(partes)


def _status_eh_conclusao(etapa: EtapaSistema, status: str) -> bool:
    if etapa.eh_homologacao:
        return status in {EtapaSistema.Status.APROVADO, EtapaSistema.Status.ENTREGUE}
    return status == EtapaSistema.Status.ENTREGUE


def _status_exige_etapa_anterior_concluida(etapa: EtapaSistema, status: str) -> bool:
    return status in {
        EtapaSistema.Status.EM_ANDAMENTO,
        EtapaSistema.Status.ENTREGUE,
        EtapaSistema.Status.APROVADO,
        EtapaSistema.Status.REPROVADO,
    }


def enviar_notificacao_historico(historico: HistoricoEtapaSistema, *, request=None):
    _emitir_notificacao_historico_desktop(historico)

    if historico.etapa.entrega.status != EntregaSistema.Status.PUBLICADO:
        return

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

    sistema = historico.etapa.entrega.sistema
    if request is not None:
        link = request.build_absolute_uri(historico.etapa.get_absolute_url())
    else:
        link = sistema.get_absolute_url()
    assunto = f"Sistemas SEDS - {sistema.nome} - Atualizações de {timezone.localdate().strftime('%d/%m/%Y')}"
    responsavel = "Sistema"
    if historico.criado_por:
        responsavel = nome_usuario_exibicao(historico.criado_por) or "Sistema"
    corpo = _corpo_email_historico(historico, responsavel=responsavel, link=link)
    _enfileirar_email_background(
        config=config,
        subject=assunto,
        body=corpo,
        destinatarios=destinatarios,
    )


def enviar_notificacao_historico_sistema(historico: HistoricoSistema, *, request=None):
    _emitir_notificacao_historico_sistema_desktop(historico)

    destinatarios = _destinatarios_sistema(historico.sistema)
    if not destinatarios:
        return

    config = _configuracao_smtp()
    if config is None:
        return

    sistema = historico.sistema
    if request is not None:
        link = request.build_absolute_uri(sistema.get_absolute_url())
    else:
        link = sistema.get_absolute_url()
    assunto = f"Sistemas SEDS - {sistema.nome} - Atualizações de {timezone.localdate().strftime('%d/%m/%Y')}"
    responsavel = "Sistema"
    if historico.criado_por:
        responsavel = nome_usuario_exibicao(historico.criado_por) or "Sistema"
    corpo = _corpo_email_historico_sistema(historico, responsavel=responsavel, link=link)
    _enfileirar_email_background(
        config=config,
        subject=assunto,
        body=corpo,
        destinatarios=destinatarios,
    )


def enviar_notificacao_publicacao(entrega: EntregaSistema, *, usuario=None, request=None):
    _emitir_notificacao_publicacao_desktop(entrega)

    destinatarios = _destinatarios_sistema(entrega.sistema)
    if not destinatarios:
        return

    config = _configuracao_smtp()
    if config is None:
        return

    if request is not None:
        link = request.build_absolute_uri(entrega.get_absolute_url())
    else:
        link = entrega.get_absolute_url()
    responsavel = nome_usuario_exibicao(usuario) if usuario else ""
    assunto = (
        f"Sistemas SEDS - {entrega.sistema.nome} - Cronograma inicial do ciclo "
        f"{entrega.titulo_com_numeracao} - {timezone.localdate().strftime('%d/%m/%Y')}"
    )
    corpo = _corpo_email_publicacao(entrega, responsavel=responsavel or "Sistema", link=link)
    _enfileirar_email_background(
        config=config,
        subject=assunto,
        body=corpo,
        destinatarios=destinatarios,
    )


def _avancar_proxima_etapa_automaticamente(etapa: EtapaSistema, *, usuario=None, request=None):
    if etapa.entrega.status != EntregaSistema.Status.PUBLICADO:
        return None

    if not _status_eh_conclusao(etapa, etapa.status):
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
def publicar_entrega(entrega: EntregaSistema, *, usuario=None, request=None) -> EntregaSistema:
    entrega = (
        EntregaSistema.objects.select_related("sistema")
        .prefetch_related("etapas")
        .get(pk=entrega.pk)
    )
    if entrega.status == EntregaSistema.Status.PUBLICADO:
        raise ValidationError("Este ciclo já foi publicado.")

    etapas = list(entrega.etapas.order_by("ordem", "id"))
    if any(not etapa.data_etapa for etapa in etapas):
        raise ValidationError("Defina a data de todas as etapas antes de publicar o ciclo.")

    entrega.status = EntregaSistema.Status.PUBLICADO
    entrega.atualizado_por = _usuario_ativo(usuario)
    entrega.save(update_fields=["status", "atualizado_por", "atualizado_em"])
    _registrar_auditoria(
        entrega,
        usuario=usuario,
        acao=AuditLog.Action.UPDATE,
        changes={"status": [EntregaSistema.Status.RASCUNHO, EntregaSistema.Status.PUBLICADO]},
    )
    enviar_notificacao_publicacao(entrega, usuario=usuario, request=request)
    return entrega


@transaction.atomic
def atualizar_etapa_com_historico(
    etapa: EtapaSistema,
    *,
    nova_data: date | None,
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
    data_alterada = nova_data != etapa.data_etapa
    possui_nota = bool(texto_nota or anexos)
    etapa_anterior = (
        etapa.entrega.etapas.filter(ordem__lt=etapa.ordem)
        .order_by("-ordem", "-id")
        .first()
    )
    status_anterior_etapa_anterior = etapa_anterior.status if etapa_anterior is not None else ""

    if etapa.entrega.status != EntregaSistema.Status.PUBLICADO:
        if status_alterado:
            raise ValidationError("O status da etapa só pode ser alterado após a publicação do ciclo.")
    if (
        status_alterado
        and _status_exige_etapa_anterior_concluida(etapa, novo_status)
        and etapa_anterior is not None
        and not _status_eh_conclusao(etapa_anterior, etapa_anterior.status)
    ):
        raise ValidationError("A etapa anterior precisa estar como Entregue antes de alterar o status desta etapa.")

    if status_alterado and not justificativa:
        raise ValidationError("Toda alteração de status exige justificativa.")
    if not status_alterado and not data_alterada and not possui_nota:
        raise ValidationError("Nenhuma alteração foi informada.")
    if etapa.entrega.status == EntregaSistema.Status.PUBLICADO and not nova_data:
        raise ValidationError("Informe a data da etapa.")

    if etapa.eh_homologacao and status_alterado and novo_status == EtapaSistema.Status.REPROVADO:
        etapa.data_etapa = nova_data
        etapa.status = EtapaSistema.Status.PENDENTE
        etapa.atualizado_por = _usuario_ativo(usuario)
        etapa.save(update_fields=["status", "data_etapa", "atualizado_por", "atualizado_em"])
        if etapa_anterior is not None:
            etapa_anterior.status = EtapaSistema.Status.EM_ANDAMENTO
            etapa_anterior.atualizado_por = _usuario_ativo(usuario)
            etapa_anterior.save(update_fields=["status", "atualizado_por", "atualizado_em"])
        recalcular_tempos_etapas(etapa.entrega)

        historico = HistoricoEtapaSistema.objects.create(
            etapa=etapa,
            tipo_evento=HistoricoEtapaSistema.TipoEvento.STATUS,
            descricao=(
                f"Homologação reprovada. {etapa.get_tipo_etapa_display()} voltou para Pendente"
                + (
                    f" e {etapa_anterior.get_tipo_etapa_display()} retornou para Em andamento."
                    if etapa_anterior is not None else "."
                )
            ),
            status_anterior=status_anterior,
            status_novo=EtapaSistema.Status.REPROVADO,
            data_anterior=data_anterior if data_alterada else None,
            data_nova=etapa.data_etapa if data_alterada else None,
            justificativa=justificativa,
            criado_por=_usuario_ativo(usuario),
        )
        _registrar_auditoria(
            etapa,
            usuario=usuario,
            acao=AuditLog.Action.UPDATE,
            changes={
                "status": [status_anterior, EtapaSistema.Status.REPROVADO],
                "status_operacional": [status_anterior, EtapaSistema.Status.PENDENTE],
                "data_etapa": [
                    data_anterior.isoformat() if data_anterior else "",
                    etapa.data_etapa.isoformat() if etapa.data_etapa else "",
                ]
                if data_alterada
                else (etapa.data_etapa.isoformat() if etapa.data_etapa else ""),
                "tipo_evento": historico.tipo_evento,
            },
        )
        if etapa_anterior is not None:
            _registrar_auditoria(
                etapa_anterior,
                usuario=usuario,
                acao=AuditLog.Action.UPDATE,
                changes={"status": [status_anterior_etapa_anterior, EtapaSistema.Status.EM_ANDAMENTO]},
            )
        enviar_notificacao_historico(historico, request=request)
        return historico

    if novo_status:
        etapa.status = novo_status
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
            else (etapa.data_etapa.isoformat() if etapa.data_etapa else ""),
            "tipo_evento": historico.tipo_evento,
        },
    )
    enviar_notificacao_historico(historico, request=request)
    _avancar_proxima_etapa_automaticamente(etapa, usuario=usuario, request=request)
    return historico


def adicionar_nota_etapa(etapa: EtapaSistema, *, texto: str, anexos, usuario=None, request=None) -> HistoricoEtapaSistema:
    if etapa.entrega.status != EntregaSistema.Status.PUBLICADO:
        raise ValidationError("Comentários e anexos da etapa só podem ser lançados após a publicação do ciclo.")
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


@transaction.atomic
def adicionar_nota_sistema(sistema: Sistema, *, texto: str, anexos, usuario=None, request=None) -> HistoricoSistema:
    texto = (texto or "").strip()
    anexos = anexos or []
    if not texto and not anexos:
        raise ValidationError("Nenhuma alteração foi informada.")

    historico = HistoricoSistema.objects.create(
        sistema=sistema,
        tipo_evento=HistoricoSistema.TipoEvento.NOTA,
        descricao=texto,
        criado_por=_usuario_ativo(usuario),
    )
    for arquivo in anexos:
        AnexoHistoricoSistema.objects.create(
            historico=historico,
            arquivo=arquivo,
            nome_original=getattr(arquivo, "name", "") or "",
        )

    _registrar_auditoria(
        sistema,
        usuario=usuario,
        acao=AuditLog.Action.UPDATE,
        changes={"tipo_evento": historico.tipo_evento},
    )
    enviar_notificacao_historico_sistema(historico, request=request)
    return historico
