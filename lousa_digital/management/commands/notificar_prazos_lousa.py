"""
Comando de notificação diária de prazos da Lousa Digital.

Executa envio de e-mail para encaminhamentos ativos que vencem em até 3 dias
(janela de calendário `hoje..hoje+3`) e ainda não foram notificados.
"""

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from administracao.models import SMTPConfiguration
from auditoria.models import AuditLog
from lousa_digital.models import Encaminhamento, EventoTimeline


class Command(BaseCommand):
    help = "Envia alerta de prazo (3 dias) para encaminhamentos da Lousa Digital."
    lock_name = "notificar_prazos_lousa_command_lock"

    @staticmethod
    def _destinatarios(encaminhamento):
        """
        Retorna apenas o e-mail informado no encaminhamento.
        """

        emails = []
        descricoes = []
        email_encaminhamento = (encaminhamento.email_notificacao or "").strip()
        if email_encaminhamento:
            emails.append(email_encaminhamento)
            descricoes.append(email_encaminhamento)
        return Command._deduplicar_emails(emails), descricoes

    @staticmethod
    def _deduplicar_emails(emails):
        vistos = set()
        resultado = []
        for email in emails:
            chave = email.lower()
            if chave in vistos:
                continue
            vistos.add(chave)
            resultado.append(email)
        return resultado

    @staticmethod
    def _registrar_auditoria_execucao(inicio, hoje, limite):
        """
        Registra no app de auditoria que o comando foi executado.
        """

        try:
            content_type = ContentType.objects.get_for_model(Encaminhamento)
            return AuditLog.objects.create(
                user=None,
                action=AuditLog.Action.CREATE,
                content_type=content_type,
                object_id=f"execucao-notificar-prazos-lousa:{inicio.isoformat()}",
                object_repr="Execucao do comando notificar_prazos_lousa",
                changes={
                    "comando": "notificar_prazos_lousa",
                    "janela_inicio": hoje.isoformat(),
                    "janela_fim": limite.isoformat(),
                },
            )
        except Exception:
            return None

    @staticmethod
    def _atualizar_auditoria_execucao(log_execucao, total, enviados, falhas, sem_destinatarios):
        if not log_execucao:
            return
        try:
            log_execucao.changes = {
                **(log_execucao.changes or {}),
                "total_elegiveis_janela": total,
                "enviados": enviados,
                "falhas": falhas,
                "sem_destinatarios": sem_destinatarios,
            }
            log_execucao.save(update_fields=["changes"])
        except Exception:
            pass

    @classmethod
    def _acquire_lock(cls) -> bool:
        """Evita execucao concorrente do comando no mesmo banco MySQL."""

        with connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 0)", [cls.lock_name])
            resultado = cursor.fetchone()
        return bool(resultado and resultado[0] == 1)

    @classmethod
    def _release_lock(cls) -> None:
        """Libera trava advisory usada para serializar execucoes."""

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", [cls.lock_name])
        except Exception:
            pass

    def handle(self, *args, **options):
        if not self._acquire_lock():
            self.stdout.write(
                self.style.WARNING(
                    "Outra execução de notificar_prazos_lousa já está em andamento. Saindo sem enviar."
                )
            )
            return

        try:
            config = SMTPConfiguration.objects.filter(ativo=True).order_by("-atualizado_em").first()
            if config is None:
                self.stdout.write(
                    self.style.ERROR("Nenhuma configuração SMTP ativa encontrada. Envio cancelado.")
                )
                return

            hoje = timezone.localdate()
            limite = hoje + timedelta(days=3)
            agora = timezone.now()
            log_execucao = self._registrar_auditoria_execucao(agora, hoje, limite)

            self.stdout.write(
                f"Iniciando notificação de prazo (3 dias). Janela: {hoje.strftime('%d/%m/%Y')} a {limite.strftime('%d/%m/%Y')}."
            )

            encaminhamentos = (
                Encaminhamento.objects.select_related("processo", "processo__grupo_insercao")
                .prefetch_related("processo__grupo_insercao__user_set__ramal_perfil")
                .filter(
                    data_conclusao__isnull=True,
                    notificado_72h_em__isnull=True,
                    prazo_data__range=(hoje, limite),
                )
                .order_by("prazo_data", "id")
            )

            total = encaminhamentos.count()
            if total == 0:
                self.stdout.write("Nenhum encaminhamento elegível para notificação de prazo (3 dias).")
                self._atualizar_auditoria_execucao(log_execucao, total=0, enviados=0, falhas=0, sem_destinatarios=0)
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

            enviados = 0
            falhas = 0
            sem_destinatarios = 0
            for encaminhamento in encaminhamentos:
                processo = encaminhamento.processo
                destinatarios_email, destinatarios_desc = self._destinatarios(encaminhamento)
                if not destinatarios_email:
                    sem_destinatarios += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"Encaminhamento #{encaminhamento.id} sem destinatários válidos; envio ignorado."
                        )
                    )
                    continue

                destinatarios_texto = "; ".join(destinatarios_desc)
                subject = f"[SGI SEDS] Prazo próximo: {processo.numero_sei}"
                body = (
                    "Aviso automático de prazo.\n\n"
                    f"Processo: {processo.numero_sei}\n"
                    f"Link do processo: {processo.link_sei or '-'}\n"
                    f"Assunto: {processo.assunto}\n"
                    f"Destino: {encaminhamento.destino}\n"
                    f"Prazo: {encaminhamento.prazo_data.strftime('%d/%m/%Y')}\n\n"
                    "Este encaminhamento vence nos próximos 3 dias.\n\n"
                    "Não responda esse e-mail."
                )
                message = EmailMessage(
                    subject=subject,
                    body=body,
                    from_email=config.from_email,
                    to=destinatarios_email,
                    connection=connection_email,
                )
                try:
                    message.send(fail_silently=False)
                except Exception as exc:
                    falhas += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"Falha ao enviar e-mail do encaminhamento #{encaminhamento.id}: {exc}"
                        )
                    )
                    continue

                encaminhamento.notificado_72h_em = agora
                encaminhamento.save(update_fields=["notificado_72h_em"])
                EventoTimeline.objects.create(
                    processo=processo,
                    encaminhamento=encaminhamento,
                    tipo=EventoTimeline.Tipo.EMAIL_72H_ENVIADO,
                    descricao=(
                        f"Notificação automática de prazo (3 dias) enviada. Processo: {processo.numero_sei}; "
                        f"Prazo: {encaminhamento.prazo_data.strftime('%d/%m/%Y')}; "
                        f"Destinatários: {destinatarios_texto}."
                    ),
                    usuario=None,
                )

                try:
                    content_type = ContentType.objects.get_for_model(Encaminhamento)
                    AuditLog.objects.create(
                        user=None,
                        action=AuditLog.Action.UPDATE,
                        content_type=content_type,
                        object_id=str(encaminhamento.pk),
                        object_repr=f"Envio de email de prazo - {processo.numero_sei}",
                        changes={
                            "comando": "notificar_prazos_lousa",
                            "processo": processo.numero_sei,
                            "prazo": encaminhamento.prazo_data.isoformat(),
                            "destinatarios": destinatarios_desc,
                        },
                    )
                except (OperationalError, ProgrammingError, Exception):
                    pass

                self.stdout.write(
                    self.style.SUCCESS(
                        "Email enviado: "
                        f"Processo {processo.numero_sei}, prazo {encaminhamento.prazo_data.strftime('%d/%m/%Y')}, "
                        f"destinatários [{destinatarios_texto}]"
                    )
                )
                enviados += 1

            self._atualizar_auditoria_execucao(
                log_execucao,
                total=total,
                enviados=enviados,
                falhas=falhas,
                sem_destinatarios=sem_destinatarios,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    "Notificação de prazo (3 dias) concluída. "
                    f"Elegíveis: {total}, enviados: {enviados}, falhas: {falhas}, sem destinatários: {sem_destinatarios}."
                )
            )
        finally:
            self._release_lock()
