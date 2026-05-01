from __future__ import annotations

from datetime import date
import logging
import threading

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files.base import File
from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend
from django.db import close_old_connections, transaction
from django.utils import timezone

from administracao.models import SMTPConfiguration
from auditoria.models import AuditLog
from notificacoes.services import SOURCE_ACOMPANHAMENTO_SISTEMAS, emitir_notificacao

from .models import (
    AnexoHistoricoEtapaProcessoRequisito,
    AnexoHistoricoSistema,
    AnexoHistoricoEtapa,
    AnexoHistoricoProcessoRequisito,
    EntregaSistema,
    EtapaProcessoRequisito,
    EtapaSistema,
    HistoricoSistema,
    HistoricoEtapaSistema,
    HistoricoEtapaProcessoRequisito,
    HistoricoProcessoRequisito,
    InteressadoSistema,
    InteressadoSistemaManual,
    ProcessoRequisito,
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

ETAPAS_SEM_DATA = {
    EtapaSistema.TipoEtapa.REQUISITOS,
    EtapaSistema.TipoEtapa.HOMOLOGACAO_REQUISITOS,
}

ETAPAS_FINAIS_COM_DATA_OBRIGATORIA = (
    EtapaSistema.TipoEtapa.DESENVOLVIMENTO,
    EtapaSistema.TipoEtapa.HOMOLOGACAO_DESENVOLVIMENTO,
    EtapaSistema.TipoEtapa.PRODUCAO,
)

ETAPAS_PROCESSO_REQUISITO_INICIAIS = [
    (1, EtapaProcessoRequisito.TipoEtapa.AS_IS),
    (2, EtapaProcessoRequisito.TipoEtapa.DIAGNOSTICO),
    (3, EtapaProcessoRequisito.TipoEtapa.TO_BE),
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


def _apagar_auditoria_modelo_ids(model, ids) -> None:
    ids_limpos = [str(item) for item in ids if item]
    if not ids_limpos:
        return
    AuditLog.objects.filter(
        content_type=ContentType.objects.get_for_model(model),
        object_id__in=ids_limpos,
    ).delete()


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
    partes_nome = [parte for parte in responsavel.split() if parte.strip()]
    if len(partes_nome) >= 2:
        responsavel = f"{partes_nome[0]} {partes_nome[1]}"
    elif partes_nome:
        responsavel = partes_nome[0]
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
        return f"Etapa: {etapa_label} - Status alterado para {status_novo}."

    if (
        historico.tipo_evento == HistoricoEtapaSistema.TipoEvento.DATA
        and historico.data_nova
    ):
        return f"Etapa: {etapa_label} - Data alterada para {historico.data_nova.strftime('%d/%m/%Y')}."

    if historico.tipo_evento == HistoricoEtapaSistema.TipoEvento.NOTA:
        conteudo = (historico.descricao or "-").strip() or "-"
        return f"Etapa: {etapa_label} - Nota adicionada: {conteudo[:260]}"

    if historico.tipo_evento == HistoricoEtapaSistema.TipoEvento.ANEXO:
        conteudo = (historico.descricao or "-").strip() or "-"
        return f"Etapa: {etapa_label} - Anexo adicionado: {conteudo[:260]}"

    if historico.tipo_evento == HistoricoEtapaSistema.TipoEvento.CRIACAO:
        return f"Etapa: {etapa_label} - Etapa criada."

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
            "Etapa: Ciclo - cronograma inicial criado.\n"
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
        "Tipo de atualização: Criação do cronograma inicial",
        "",
        "Etapas do ciclo:",
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
    enviar_notificacao_publicacao(entrega, usuario=usuario)
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


def etapa_pode_alterar_status_em_rascunho(etapa: EtapaSistema) -> bool:
    return etapa.tipo_etapa in ETAPAS_SEM_DATA


def _etapa_exige_data(tipo_etapa: str) -> bool:
    return tipo_etapa not in ETAPAS_SEM_DATA


def entrega_pode_ser_publicada(entrega: EntregaSistema) -> bool:
    etapas = {etapa.tipo_etapa: etapa for etapa in entrega.etapas.all()}
    requisitos = etapas.get(EtapaSistema.TipoEtapa.REQUISITOS)
    homologacao_requisitos = etapas.get(EtapaSistema.TipoEtapa.HOMOLOGACAO_REQUISITOS)
    if requisitos is None or homologacao_requisitos is None:
        return False
    if requisitos.status != EtapaSistema.Status.ENTREGUE:
        return False
    if homologacao_requisitos.status != EtapaSistema.Status.EM_ANDAMENTO:
        return False

    for tipo_etapa in ETAPAS_FINAIS_COM_DATA_OBRIGATORIA:
        etapa = etapas.get(tipo_etapa)
        if etapa is None or not etapa.data_etapa:
            return False
    return True


def validar_publicacao_entrega(entrega: EntregaSistema) -> None:
    etapas = {etapa.tipo_etapa: etapa for etapa in entrega.etapas.all()}
    requisitos = etapas.get(EtapaSistema.TipoEtapa.REQUISITOS)
    homologacao_requisitos = etapas.get(EtapaSistema.TipoEtapa.HOMOLOGACAO_REQUISITOS)

    if requisitos is None or homologacao_requisitos is None:
        raise ValidationError("O ciclo não possui as etapas obrigatórias para publicação.")
    if requisitos.status != EtapaSistema.Status.ENTREGUE:
        raise ValidationError("Entregue a etapa de Requisitos antes de publicar o ciclo.")
    if homologacao_requisitos.status != EtapaSistema.Status.EM_ANDAMENTO:
        raise ValidationError(
            "A etapa de Homologação de Requisitos deve estar em andamento para publicar o ciclo."
        )

    etapas_sem_data = []
    for tipo_etapa in ETAPAS_FINAIS_COM_DATA_OBRIGATORIA:
        etapa = etapas.get(tipo_etapa)
        if etapa is not None and not etapa.data_etapa:
            etapas_sem_data.append(etapa.get_tipo_etapa_display())
    if etapas_sem_data:
        raise ValidationError(
            "Defina a data das etapas seguintes antes de publicar o ciclo: "
            + ", ".join(etapas_sem_data)
            + "."
        )


def enviar_notificacao_historico(historico: HistoricoEtapaSistema, *, request=None):
    _emitir_notificacao_historico_desktop(historico)

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
    if etapa.entrega.status != EntregaSistema.Status.PUBLICADO and not (
        etapa.entrega.status == EntregaSistema.Status.RASCUNHO
        and etapa.tipo_etapa in ETAPAS_SEM_DATA
    ):
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

    validar_publicacao_entrega(entrega)

    entrega.status = EntregaSistema.Status.PUBLICADO
    entrega.atualizado_por = _usuario_ativo(usuario)
    entrega.save(update_fields=["status", "atualizado_por", "atualizado_em"])
    _registrar_auditoria(
        entrega,
        usuario=usuario,
        acao=AuditLog.Action.UPDATE,
        changes={"status": [EntregaSistema.Status.RASCUNHO, EntregaSistema.Status.PUBLICADO]},
    )
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
    if etapa.tipo_etapa in ETAPAS_SEM_DATA:
        nova_data = None
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
        if status_alterado and not etapa_pode_alterar_status_em_rascunho(etapa):
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
    if (
        etapa.entrega.status == EntregaSistema.Status.PUBLICADO
        and _etapa_exige_data(etapa.tipo_etapa)
        and not nova_data
    ):
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


def _descricao_historico_etapa_processo(
    etapa: EtapaProcessoRequisito,
    *,
    status_anterior="",
    status_novo="",
    nota="",
):
    nota = (nota or "").strip()
    partes = []
    if status_anterior and status_novo and status_anterior != status_novo:
        partes.append(
            f"Status alterado de {EtapaProcessoRequisito.Status(status_anterior).label} "
            f"para {EtapaProcessoRequisito.Status(status_novo).label}."
        )
    if nota:
        partes.append(nota)
    if not partes:
        partes.append(f"Atualização registrada na etapa {etapa.get_tipo_etapa_display()}.")
    return " ".join(partes)


def _descricao_notificacao_historico_processo(historico: HistoricoProcessoRequisito) -> str:
    conteudo = (historico.descricao or "-").strip() or "-"
    return f"Processo: {historico.processo.titulo} - {conteudo[:260]}"


def _descricao_notificacao_historico_etapa_processo(historico: HistoricoEtapaProcessoRequisito) -> str:
    etapa = historico.etapa
    if historico.tipo_evento == HistoricoEtapaProcessoRequisito.TipoEvento.STATUS and historico.status_novo:
        status_novo = EtapaProcessoRequisito.Status(historico.status_novo).label
        return f"Processo: {etapa.processo.titulo} - {etapa.get_tipo_etapa_display()} em {status_novo}."
    conteudo = (historico.descricao or "-").strip() or "-"
    return f"Processo: {etapa.processo.titulo} - {etapa.get_tipo_etapa_display()} - {conteudo[:260]}"


def _corpo_email_historico_processo(historico: HistoricoProcessoRequisito, *, responsavel: str, link: str) -> str:
    return "\n".join(
        [
            f"Sistema: {historico.processo.sistema.nome}",
            f"Processo: {historico.processo.titulo}",
            f"Tipo de atualização: {historico.get_tipo_evento_display()}",
            f"Conteúdo: {(historico.descricao or '-').strip() or '-'}",
            "",
            f"Responsável: {responsavel}",
            f"Data/hora: {timezone.localtime(historico.criado_em).strftime('%d/%m/%Y %H:%M')}",
            "",
            "Este é um e-mail automático. Não responda.",
            "Para mais informações, acesse:",
            link,
        ]
    )


def _corpo_email_historico_etapa_processo(
    historico: HistoricoEtapaProcessoRequisito, *, responsavel: str, link: str
) -> str:
    conteudo = (historico.descricao or "-").strip() or "-"
    return "\n".join(
        [
            f"Sistema: {historico.etapa.processo.sistema.nome}",
            f"Processo: {historico.etapa.processo.titulo}",
            f"Etapa: {historico.etapa.get_tipo_etapa_display()}",
            f"Tipo de atualização: {historico.get_tipo_evento_display()}",
            f"Conteúdo: {conteudo}",
            f"Justificativa: {(historico.justificativa or '-').strip() or '-'}",
            "",
            f"Responsável: {responsavel}",
            f"Data/hora: {timezone.localtime(historico.criado_em).strftime('%d/%m/%Y %H:%M')}",
            "",
            "Este é um e-mail automático. Não responda.",
            "Para mais informações, acesse:",
            link,
        ]
    )


def _emitir_notificacao_historico_processo_desktop(historico: HistoricoProcessoRequisito):
    processo = historico.processo
    emitir_notificacao(
        users=_usuarios_notificacao_sistema(processo.sistema),
        source_app=SOURCE_ACOMPANHAMENTO_SISTEMAS,
        event_type=f"processo_{historico.tipo_evento.lower()}",
        title=f"Sistema: {processo.sistema.nome}",
        body_short=(
            f"{_descricao_notificacao_historico_processo(historico)}\n"
            f"{_responsavel_e_data_hora(historico.criado_por, historico.criado_em)}"
        ),
        target_url=processo.get_absolute_url(),
        dedupe_key=f"acomp-processo-{historico.pk}",
        payload_json={
            "sistema_id": processo.sistema_id,
            "processo_id": processo.pk,
            "historico_id": historico.pk,
        },
    )


def _emitir_notificacao_historico_etapa_processo_desktop(historico: HistoricoEtapaProcessoRequisito):
    etapa = historico.etapa
    emitir_notificacao(
        users=_usuarios_notificacao_sistema(etapa.processo.sistema),
        source_app=SOURCE_ACOMPANHAMENTO_SISTEMAS,
        event_type=f"processo_etapa_{historico.tipo_evento.lower()}",
        title=f"Sistema: {etapa.processo.sistema.nome}",
        body_short=(
            f"{_descricao_notificacao_historico_etapa_processo(historico)}\n"
            f"{_responsavel_e_data_hora(historico.criado_por, historico.criado_em)}"
        ),
        target_url=etapa.get_absolute_url(),
        dedupe_key=f"acomp-processo-etapa-{historico.pk}",
        payload_json={
            "sistema_id": etapa.processo.sistema_id,
            "processo_id": etapa.processo_id,
            "etapa_id": etapa.pk,
            "historico_id": historico.pk,
        },
    )


def enviar_notificacao_historico_processo(historico: HistoricoProcessoRequisito, *, request=None):
    _emitir_notificacao_historico_processo_desktop(historico)
    destinatarios = _destinatarios_sistema(historico.processo.sistema)
    if not destinatarios:
        return
    config = _configuracao_smtp()
    if config is None:
        return
    link = request.build_absolute_uri(historico.processo.get_absolute_url()) if request is not None else historico.processo.get_absolute_url()
    responsavel = nome_usuario_exibicao(historico.criado_por) if historico.criado_por else "Sistema"
    assunto = (
        f"Sistemas SEDS - {historico.processo.sistema.nome} - Processo de requisitos - "
        f"{timezone.localdate().strftime('%d/%m/%Y')}"
    )
    corpo = _corpo_email_historico_processo(historico, responsavel=responsavel or "Sistema", link=link)
    _enfileirar_email_background(config=config, subject=assunto, body=corpo, destinatarios=destinatarios)


def enviar_notificacao_historico_etapa_processo(historico: HistoricoEtapaProcessoRequisito, *, request=None):
    _emitir_notificacao_historico_etapa_processo_desktop(historico)
    destinatarios = _destinatarios_sistema(historico.etapa.processo.sistema)
    if not destinatarios:
        return
    config = _configuracao_smtp()
    if config is None:
        return
    link = request.build_absolute_uri(historico.etapa.get_absolute_url()) if request is not None else historico.etapa.get_absolute_url()
    responsavel = nome_usuario_exibicao(historico.criado_por) if historico.criado_por else "Sistema"
    assunto = (
        f"Sistemas SEDS - {historico.etapa.processo.sistema.nome} - Etapa do processo de requisitos - "
        f"{timezone.localdate().strftime('%d/%m/%Y')}"
    )
    corpo = _corpo_email_historico_etapa_processo(historico, responsavel=responsavel or "Sistema", link=link)
    _enfileirar_email_background(config=config, subject=assunto, body=corpo, destinatarios=destinatarios)


def _registrar_historico_processo(processo: ProcessoRequisito, *, tipo_evento: str, descricao: str, usuario=None):
    historico = HistoricoProcessoRequisito.objects.create(
        processo=processo,
        tipo_evento=tipo_evento,
        descricao=descricao,
        criado_por=_usuario_ativo(usuario),
    )
    _registrar_auditoria(
        processo,
        usuario=usuario,
        acao=AuditLog.Action.UPDATE if tipo_evento != HistoricoProcessoRequisito.TipoEvento.CRIACAO else AuditLog.Action.CREATE,
        changes={"tipo_evento": tipo_evento},
    )
    return historico


def _registrar_historico_sistema_por_processo(sistema: Sistema, *, descricao: str, usuario=None):
    historico = HistoricoSistema.objects.create(
        sistema=sistema,
        tipo_evento=HistoricoSistema.TipoEvento.NOTA,
        descricao=descricao,
        criado_por=_usuario_ativo(usuario),
    )
    _registrar_auditoria(
        sistema,
        usuario=usuario,
        acao=AuditLog.Action.UPDATE,
        changes={"tipo_evento": historico.tipo_evento},
    )
    return historico


@transaction.atomic
def criar_processo_requisito(sistema: Sistema, *, usuario=None, titulo="", descricao="") -> ProcessoRequisito:
    proxima_ordem = (sistema.processos_requisito.order_by("-ordem").values_list("ordem", flat=True).first() or 0) + 1
    processo = ProcessoRequisito.objects.create(
        sistema=sistema,
        titulo=titulo,
        descricao=descricao,
        ordem=proxima_ordem,
        criado_por=_usuario_ativo(usuario),
        atualizado_por=_usuario_ativo(usuario),
    )
    for ordem, tipo_etapa in ETAPAS_PROCESSO_REQUISITO_INICIAIS:
        etapa = EtapaProcessoRequisito.objects.create(
            processo=processo,
            tipo_etapa=tipo_etapa,
            ordem=ordem,
            status=EtapaProcessoRequisito.Status.PENDENTE,
            criado_por=_usuario_ativo(usuario),
            atualizado_por=_usuario_ativo(usuario),
        )
        HistoricoEtapaProcessoRequisito.objects.create(
            etapa=etapa,
            tipo_evento=HistoricoEtapaProcessoRequisito.TipoEvento.CRIACAO,
            descricao="Etapa criada automaticamente na abertura do processo de requisitos.",
            status_novo=etapa.status,
            criado_por=_usuario_ativo(usuario),
        )
    historico_processo = _registrar_historico_processo(
        processo,
        tipo_evento=HistoricoProcessoRequisito.TipoEvento.CRIACAO,
        descricao="Processo de requisitos criado.",
        usuario=usuario,
    )
    historico_sistema = _registrar_historico_sistema_por_processo(
        sistema,
        descricao=f"Processo de requisitos '{processo.titulo}' criado.",
        usuario=usuario,
    )
    enviar_notificacao_historico_processo(historico_processo)
    enviar_notificacao_historico_sistema(historico_sistema)
    return processo


@transaction.atomic
def clonar_processo_requisito_para_sistema(
    processo_origem: ProcessoRequisito,
    sistema_destino: Sistema,
    *,
    usuario=None,
) -> ProcessoRequisito:
    proxima_ordem = (sistema_destino.processos_requisito.order_by("-ordem").values_list("ordem", flat=True).first() or 0) + 1
    processo_destino = ProcessoRequisito.objects.create(
        sistema=sistema_destino,
        titulo=processo_origem.titulo,
        descricao=processo_origem.descricao,
        ordem=proxima_ordem,
        criado_por=_usuario_ativo(usuario),
        atualizado_por=_usuario_ativo(usuario),
    )
    HistoricoProcessoRequisito.objects.create(
        processo=processo_destino,
        tipo_evento=HistoricoProcessoRequisito.TipoEvento.CRIACAO,
        descricao=f"Processo herdado do sistema '{processo_origem.sistema.nome}'.",
        criado_por=_usuario_ativo(usuario),
    )
    _registrar_auditoria(
        processo_destino,
        usuario=usuario,
        acao=AuditLog.Action.CREATE,
        changes={"titulo": processo_destino.titulo},
    )

    etapas_origem = {etapa.tipo_etapa: etapa for etapa in processo_origem.etapas.all()}
    for ordem, tipo_etapa in ETAPAS_PROCESSO_REQUISITO_INICIAIS:
        etapa_origem = etapas_origem[tipo_etapa]
        etapa_destino = EtapaProcessoRequisito.objects.create(
            processo=processo_destino,
            tipo_etapa=tipo_etapa,
            ordem=ordem,
            status=etapa_origem.status,
            criado_por=_usuario_ativo(usuario),
            atualizado_por=_usuario_ativo(usuario),
        )
        HistoricoEtapaProcessoRequisito.objects.create(
            etapa=etapa_destino,
            tipo_evento=HistoricoEtapaProcessoRequisito.TipoEvento.CRIACAO,
            descricao=f"Etapa herdada do sistema '{processo_origem.sistema.nome}'.",
            status_novo=etapa_destino.status,
            criado_por=_usuario_ativo(usuario),
        )
        _registrar_auditoria(
            etapa_destino,
            usuario=usuario,
            acao=AuditLog.Action.CREATE,
            changes={"status": etapa_destino.status},
        )

    _registrar_historico_sistema_por_processo(
        sistema_destino,
        descricao=f"Processo de requisitos '{processo_destino.titulo}' herdado do sistema '{processo_origem.sistema.nome}'.",
        usuario=usuario,
    )
    return processo_destino


@transaction.atomic
def atualizar_processo_requisito(processo: ProcessoRequisito, *, usuario=None, titulo="", descricao="") -> ProcessoRequisito:
    titulo_anterior = processo.titulo
    descricao_anterior = processo.descricao
    processo.titulo = titulo
    processo.descricao = descricao
    processo.atualizado_por = _usuario_ativo(usuario)
    processo.save(update_fields=["titulo", "descricao", "atualizado_por", "atualizado_em"])
    descricao_historico = (
        f"Processo atualizado de '{titulo_anterior}' para '{processo.titulo}'."
        if titulo_anterior != processo.titulo
        else "Processo atualizado."
    )
    historico_processo = _registrar_historico_processo(
        processo,
        tipo_evento=HistoricoProcessoRequisito.TipoEvento.EDICAO,
        descricao=descricao_historico,
        usuario=usuario,
    )
    historico_sistema = _registrar_historico_sistema_por_processo(
        processo.sistema,
        descricao=f"Processo de requisitos '{processo.titulo}' atualizado.",
        usuario=usuario,
    )
    _registrar_auditoria(
        processo,
        usuario=usuario,
        acao=AuditLog.Action.UPDATE,
        changes={
            "titulo": [titulo_anterior, titulo],
            "descricao": [descricao_anterior, descricao],
        },
    )
    enviar_notificacao_historico_processo(historico_processo)
    enviar_notificacao_historico_sistema(historico_sistema)
    return processo


@transaction.atomic
def excluir_processo_requisito(processo: ProcessoRequisito, *, usuario=None):
    etapas_ids = list(processo.etapas.values_list("id", flat=True))
    _apagar_auditoria_modelo_ids(EtapaProcessoRequisito, etapas_ids)
    _apagar_auditoria_modelo_ids(ProcessoRequisito, [processo.pk])
    processo.delete()


@transaction.atomic
def excluir_entrega_sistema(entrega: EntregaSistema, *, usuario=None):
    etapas_ids = list(entrega.etapas.values_list("id", flat=True))
    _apagar_auditoria_modelo_ids(EtapaSistema, etapas_ids)
    _apagar_auditoria_modelo_ids(EntregaSistema, [entrega.pk])
    entrega.delete()


@transaction.atomic
def excluir_sistema(sistema: Sistema, *, usuario=None):
    entrega_ids = list(sistema.entregas.values_list("id", flat=True))
    etapa_ids = list(EtapaSistema.objects.filter(entrega__sistema=sistema).values_list("id", flat=True))
    processo_ids = list(sistema.processos_requisito.values_list("id", flat=True))
    etapa_processo_ids = list(
        EtapaProcessoRequisito.objects.filter(processo__sistema=sistema).values_list("id", flat=True)
    )
    interessado_ids = list(sistema.interessados.values_list("id", flat=True))
    interessado_manual_ids = list(sistema.interessados_manuais.values_list("id", flat=True))

    _apagar_auditoria_modelo_ids(EtapaSistema, etapa_ids)
    _apagar_auditoria_modelo_ids(EntregaSistema, entrega_ids)
    _apagar_auditoria_modelo_ids(EtapaProcessoRequisito, etapa_processo_ids)
    _apagar_auditoria_modelo_ids(ProcessoRequisito, processo_ids)
    _apagar_auditoria_modelo_ids(InteressadoSistema, interessado_ids)
    _apagar_auditoria_modelo_ids(InteressadoSistemaManual, interessado_manual_ids)
    _apagar_auditoria_modelo_ids(Sistema, [sistema.pk])
    sistema.delete()


@transaction.atomic
def atualizar_etapa_processo_requisito(
    etapa: EtapaProcessoRequisito,
    *,
    novo_status: str,
    justificativa: str,
    anexos,
    usuario=None,
    request=None,
) -> HistoricoEtapaProcessoRequisito:
    justificativa = (justificativa or "").strip()
    anexos = anexos or []
    status_anterior = etapa.status
    if not novo_status or novo_status == etapa.status:
        raise ValidationError("Selecione um status diferente para atualizar a etapa.")
    if not etapa.dependencias_concluidas:
        raise ValidationError(etapa.mensagem_bloqueio_dependencia)
    if novo_status not in etapa.proximos_status_permitidos:
        raise ValidationError(
            "Transição inválida. Use o fluxo: Pendente -> Em andamento -> Validação -> Aprovado/Reprovado/Retirado do escopo."
        )
    if not justificativa:
        raise ValidationError("Toda alteração de status exige nota/acompanhamento.")
    if (
        etapa.status != EtapaProcessoRequisito.Status.VALIDACAO
        and novo_status == EtapaProcessoRequisito.Status.VALIDACAO
        and not anexos
    ):
        raise ValidationError("Ao enviar a etapa para Validação, anexe obrigatoriamente um arquivo.")

    etapa_anterior = etapa.processo.etapas.filter(ordem__lt=etapa.ordem).order_by("-ordem", "-id").first()
    status_anterior_etapa_anterior = etapa_anterior.status if etapa_anterior is not None else ""

    if novo_status == EtapaProcessoRequisito.Status.REPROVADO:
        status_operacional = (
            EtapaProcessoRequisito.Status.PENDENTE
            if etapa_anterior is not None
            else EtapaProcessoRequisito.Status.EM_ANDAMENTO
        )
        etapa.status = status_operacional
        etapa.atualizado_por = _usuario_ativo(usuario)
        etapa.save(update_fields=["status", "atualizado_por", "atualizado_em"])
        if etapa_anterior is not None:
            etapa_anterior.status = EtapaProcessoRequisito.Status.EM_ANDAMENTO
            etapa_anterior.atualizado_por = _usuario_ativo(usuario)
            etapa_anterior.save(update_fields=["status", "atualizado_por", "atualizado_em"])

        historico = HistoricoEtapaProcessoRequisito.objects.create(
            etapa=etapa,
            tipo_evento=HistoricoEtapaProcessoRequisito.TipoEvento.STATUS,
            descricao=(
                f"Etapa reprovada. {etapa.get_tipo_etapa_display()} voltou para "
                f"{EtapaProcessoRequisito.Status(status_operacional).label}"
                + (
                    f" e {etapa_anterior.get_tipo_etapa_display()} retornou para Em andamento."
                    if etapa_anterior is not None
                    else "."
                )
            ),
            status_anterior=status_anterior,
            status_novo=EtapaProcessoRequisito.Status.REPROVADO,
            justificativa=justificativa,
            criado_por=_usuario_ativo(usuario),
        )
        for arquivo in anexos:
            AnexoHistoricoEtapaProcessoRequisito.objects.create(
                historico=historico,
                arquivo=arquivo,
                nome_original=getattr(arquivo, "name", "") or "",
            )

        historico_processo = _registrar_historico_processo(
            etapa.processo,
            tipo_evento=HistoricoProcessoRequisito.TipoEvento.NOTA,
            descricao=(
                f"Etapa {etapa.get_tipo_etapa_display()} reprovada e retornou para tratamento. {justificativa}"
            ),
            usuario=usuario,
        )
        historico_sistema = _registrar_historico_sistema_por_processo(
            etapa.processo.sistema,
            descricao=(
                f"Processo '{etapa.processo.titulo}' - {etapa.get_tipo_etapa_display()} reprovada e retornou para tratamento. {justificativa}"
            ),
            usuario=usuario,
        )
        _registrar_auditoria(
            etapa,
            usuario=usuario,
            acao=AuditLog.Action.UPDATE,
            changes={
                "status": [status_anterior, EtapaProcessoRequisito.Status.REPROVADO],
                "status_operacional": [status_anterior, status_operacional],
            },
        )
        if etapa_anterior is not None:
            _registrar_auditoria(
                etapa_anterior,
                usuario=usuario,
                acao=AuditLog.Action.UPDATE,
                changes={"status": [status_anterior_etapa_anterior, EtapaProcessoRequisito.Status.EM_ANDAMENTO]},
            )
        enviar_notificacao_historico_etapa_processo(historico, request=request)
        enviar_notificacao_historico_processo(historico_processo, request=request)
        enviar_notificacao_historico_sistema(historico_sistema, request=request)
        return historico

    etapa.status = novo_status
    etapa.atualizado_por = _usuario_ativo(usuario)
    etapa.save(update_fields=["status", "atualizado_por", "atualizado_em"])

    historico = HistoricoEtapaProcessoRequisito.objects.create(
        etapa=etapa,
        tipo_evento=HistoricoEtapaProcessoRequisito.TipoEvento.STATUS,
        descricao=_descricao_historico_etapa_processo(
            etapa,
            status_anterior=status_anterior,
            status_novo=novo_status,
            nota=justificativa,
        ),
        status_anterior=status_anterior,
        status_novo=novo_status,
        justificativa=justificativa,
        criado_por=_usuario_ativo(usuario),
    )
    for arquivo in anexos:
        AnexoHistoricoEtapaProcessoRequisito.objects.create(
            historico=historico,
            arquivo=arquivo,
            nome_original=getattr(arquivo, "name", "") or "",
        )

    historico_processo = _registrar_historico_processo(
        etapa.processo,
        tipo_evento=HistoricoProcessoRequisito.TipoEvento.NOTA,
        descricao=(
            f"Etapa {etapa.get_tipo_etapa_display()} alterada de "
            f"{EtapaProcessoRequisito.Status(status_anterior).label} para "
            f"{EtapaProcessoRequisito.Status(novo_status).label}. {justificativa}"
        ),
        usuario=usuario,
    )
    historico_sistema = _registrar_historico_sistema_por_processo(
        etapa.processo.sistema,
        descricao=(
            f"Processo '{etapa.processo.titulo}' - {etapa.get_tipo_etapa_display()} alterada para "
            f"{EtapaProcessoRequisito.Status(novo_status).label}. {justificativa}"
        ),
        usuario=usuario,
    )
    _registrar_auditoria(
        etapa,
        usuario=usuario,
        acao=AuditLog.Action.UPDATE,
        changes={"status": [status_anterior, novo_status]},
    )
    enviar_notificacao_historico_etapa_processo(historico, request=request)
    enviar_notificacao_historico_processo(historico_processo, request=request)
    enviar_notificacao_historico_sistema(historico_sistema, request=request)
    return historico


def _historico_anexo_mais_recente(etapa: EtapaProcessoRequisito):
    return (
        etapa.historicos.filter(anexos__isnull=False)
        .prefetch_related("anexos")
        .order_by("-criado_em", "-id")
        .first()
    )


def _data_base_processo(processo: ProcessoRequisito):
    datas = []
    for etapa in processo.etapas.all():
        historico = _historico_anexo_mais_recente(etapa)
        if historico is not None:
            datas.append(timezone.localtime(historico.criado_em).date())
    return max(datas) if datas else timezone.localdate()


def _copiar_anexos_para_historico_etapa(
    anexos_origem, historico_destino: HistoricoEtapaSistema
):
    for anexo_origem in anexos_origem:
        novo_anexo = AnexoHistoricoEtapa(historico=historico_destino, nome_original=anexo_origem.nome_exibicao)
        arquivo_origem = anexo_origem.arquivo
        arquivo_origem.open("rb")
        try:
            novo_anexo.arquivo.save(
                anexo_origem.nome_exibicao,
                File(arquivo_origem.file),
                save=False,
            )
        finally:
            arquivo_origem.close()
        novo_anexo.save()


@transaction.atomic
def gerar_ciclo_a_partir_processo(processo: ProcessoRequisito, *, usuario=None, request=None, sistema_destino=None) -> EntregaSistema:
    if not processo.processo_finalizado:
        raise ValidationError("O processo precisa estar finalizado para gerar um ciclo.")

    sistema_base = sistema_destino or processo.sistema
    entrega = criar_entrega_com_etapas(
        sistema_base,
        usuario=usuario,
        titulo=processo.titulo,
        descricao=processo.descricao,
    )
    entrega.processo_requisito_origem = processo
    entrega.atualizado_por = _usuario_ativo(usuario)
    entrega.save(update_fields=["processo_requisito_origem", "atualizado_por", "atualizado_em"])

    data_base = _data_base_processo(processo)
    etapas_destino = {etapa.tipo_etapa: etapa for etapa in entrega.etapas.all()}
    requisitos = etapas_destino[EtapaSistema.TipoEtapa.REQUISITOS]
    homologacao = etapas_destino[EtapaSistema.TipoEtapa.HOMOLOGACAO_REQUISITOS]
    desenvolvimento = etapas_destino[EtapaSistema.TipoEtapa.DESENVOLVIMENTO]
    homologacao_desenvolvimento = etapas_destino[EtapaSistema.TipoEtapa.HOMOLOGACAO_DESENVOLVIMENTO]
    producao = etapas_destino[EtapaSistema.TipoEtapa.PRODUCAO]

    requisitos.status = EtapaSistema.Status.ENTREGUE
    requisitos.data_etapa = None
    requisitos.atualizado_por = _usuario_ativo(usuario)
    requisitos.save(update_fields=["status", "data_etapa", "atualizado_por", "atualizado_em"])

    homologacao.status = EtapaSistema.Status.APROVADO
    homologacao.data_etapa = None
    homologacao.atualizado_por = _usuario_ativo(usuario)
    homologacao.save(update_fields=["status", "data_etapa", "atualizado_por", "atualizado_em"])

    desenvolvimento.status = EtapaSistema.Status.EM_ANDAMENTO
    desenvolvimento.data_etapa = data_base
    desenvolvimento.atualizado_por = _usuario_ativo(usuario)
    desenvolvimento.save(update_fields=["status", "data_etapa", "atualizado_por", "atualizado_em"])

    homologacao_desenvolvimento.data_etapa = data_base
    homologacao_desenvolvimento.atualizado_por = _usuario_ativo(usuario)
    homologacao_desenvolvimento.save(update_fields=["data_etapa", "atualizado_por", "atualizado_em"])

    producao.data_etapa = data_base
    producao.atualizado_por = _usuario_ativo(usuario)
    producao.save(update_fields=["data_etapa", "atualizado_por", "atualizado_em"])

    historico_requisitos = HistoricoEtapaSistema.objects.create(
        etapa=requisitos,
        tipo_evento=HistoricoEtapaSistema.TipoEvento.NOTA,
        descricao="Etapa concluída automaticamente a partir do processo de requisitos.",
        status_novo=requisitos.status,
        criado_por=_usuario_ativo(usuario),
    )
    HistoricoEtapaSistema.objects.create(
        etapa=homologacao,
        tipo_evento=HistoricoEtapaSistema.TipoEvento.NOTA,
        descricao="Etapa concluída automaticamente a partir do processo de requisitos.",
        status_novo=homologacao.status,
        criado_por=_usuario_ativo(usuario),
    )
    HistoricoEtapaSistema.objects.create(
        etapa=desenvolvimento,
        tipo_evento=HistoricoEtapaSistema.TipoEvento.NOTA,
        descricao="Etapa iniciada automaticamente a partir do processo de requisitos.",
        status_novo=desenvolvimento.status,
        criado_por=_usuario_ativo(usuario),
    )

    for etapa_origem in processo.etapas.all():
        historico_origem = _historico_anexo_mais_recente(etapa_origem)
        if historico_origem is None:
            continue
        _copiar_anexos_para_historico_etapa(historico_origem.anexos.all(), historico_requisitos)

    recalcular_tempos_etapas(entrega)

    historico_processo = _registrar_historico_processo(
        processo,
        tipo_evento=HistoricoProcessoRequisito.TipoEvento.GERACAO_CICLO,
        descricao=f"Ciclo '{entrega.titulo}' gerado a partir do processo.",
        usuario=usuario,
    )
    historico_sistema = _registrar_historico_sistema_por_processo(
        sistema_base,
        descricao=f"Novo ciclo '{entrega.titulo}' gerado a partir do processo '{processo.titulo}'.",
        usuario=usuario,
    )
    enviar_notificacao_historico_processo(historico_processo, request=request)
    enviar_notificacao_historico_sistema(historico_sistema, request=request)
    return entrega


def sistema_pode_gerar_novo_sistema(sistema: Sistema) -> bool:
    processos = list(sistema.processos_requisito.prefetch_related("etapas"))
    return bool(processos) and all(processo.processo_finalizado for processo in processos)


@transaction.atomic
def gerar_novo_sistema_a_partir_processos(
    sistema_origem: Sistema,
    *,
    usuario=None,
    nome: str,
    descricao: str,
    url_homologacao: str,
    url_producao: str,
    request=None,
) -> Sistema:
    if not sistema_pode_gerar_novo_sistema(sistema_origem):
        raise ValidationError("Todos os processos do sistema original precisam estar finalizados para gerar um novo sistema.")

    novo_sistema = Sistema.objects.create(
        nome=nome,
        descricao=descricao,
        url_homologacao=url_homologacao,
        url_producao=url_producao,
        criado_por=_usuario_ativo(usuario),
        atualizado_por=_usuario_ativo(usuario),
    )
    _registrar_auditoria(novo_sistema, usuario=usuario, acao=AuditLog.Action.CREATE, changes={"nome": nome})
    for processo in sistema_origem.processos_requisito.prefetch_related("etapas__historicos__anexos").all():
        clonar_processo_requisito_para_sistema(processo, novo_sistema, usuario=usuario)
        gerar_ciclo_a_partir_processo(processo, usuario=usuario, request=request, sistema_destino=novo_sistema)

    historico_origem = _registrar_historico_sistema_por_processo(
        sistema_origem,
        descricao=f"Novo sistema '{novo_sistema.nome}' gerado a partir dos processos de requisitos.",
        usuario=usuario,
    )
    historico_destino = _registrar_historico_sistema_por_processo(
        novo_sistema,
        descricao=f"Sistema criado a partir de '{sistema_origem.nome}' e seus processos de requisitos.",
        usuario=usuario,
    )
    enviar_notificacao_historico_sistema(historico_origem, request=request)
    enviar_notificacao_historico_sistema(historico_destino, request=request)
    return novo_sistema
