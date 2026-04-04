from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from notificacoes.services import emitir_notificacao


User = get_user_model()


class Command(BaseCommand):
    help = "Cria uma notificação desktop de teste para um usuário."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Usuário destinatário da notificação.")
        parser.add_argument(
            "--title",
            default="Sistema: Intranet - Ciclo: Teste desktop",
            help="Título da notificação.",
        )
        parser.add_argument(
            "--body",
            default="Ciclo: Teste desktop\nEtapa: Requisitos - nota adicionada. Teste rápido\nSistema, 04/04/2026 10:00",
            help="Corpo curto da notificação. Use \\n para quebrar linha.",
        )
        parser.add_argument(
            "--target-url",
            default="/acompanhamento-sistemas/",
            help="URL de destino ao clicar na notificação.",
        )
        parser.add_argument(
            "--source-app",
            default="acompanhamento_sistemas",
            help="Origem da notificação.",
        )
        parser.add_argument(
            "--event-type",
            default="simulacao_manual",
            help="Tipo do evento salvo na notificação.",
        )
        parser.add_argument(
            "--dedupe-key",
            default="",
            help="Chave opcional de deduplicação.",
        )

    def handle(self, *args, **options):
        username = options["username"].strip()
        try:
            user = User.objects.get(username__iexact=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"Usuário não encontrado: {username}") from exc

        notificacoes = emitir_notificacao(
            users=[user],
            source_app=options["source_app"].strip(),
            event_type=options["event_type"].strip(),
            title=options["title"].strip(),
            body_short=options["body"].replace("\\n", "\n").strip(),
            target_url=options["target_url"].strip(),
            dedupe_key=options["dedupe_key"].strip(),
            payload_json={"simulada": True},
            dedupe_window_seconds=0,
        )

        if not notificacoes:
            raise CommandError("Nenhuma notificação foi criada.")

        notificacao = notificacoes[0]
        self.stdout.write(
            self.style.SUCCESS(
                f"Notificação criada com sucesso. id={notificacao.id} user={user.username} title={notificacao.title}"
            )
        )
