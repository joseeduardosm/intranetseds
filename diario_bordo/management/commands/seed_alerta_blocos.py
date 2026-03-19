"""
Comando de seed para cenários de alerta do app `diario_bordo`.

Cria blocos de exemplo com diferentes idades de atualização para facilitar
testes visuais de classes de alerta e layout de monitoramento.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from diario_bordo.models import BlocoTrabalho, Incremento


class Command(BaseCommand):
    """
    Comando de apoio operacional para geração de dados de demonstração.
    """

    help = "Cria blocos de exemplo com diferentes dias sem atualizacao."

    def add_arguments(self, parser):
        """
        Define argumentos de execução do comando.

        Parâmetros:
        - `parser`: parser de argumentos do Django management.
        """

        parser.add_argument(
            "--nome-base",
            default="Exemplo para a Tamires",
            help="Prefixo do nome dos blocos.",
        )
        parser.add_argument(
            "--dias",
            nargs="*",
            type=int,
            default=[7, 6, 5, 4, 3, 2, 1],
            help="Lista de dias sem atualizacao.",
        )
        parser.add_argument(
            "--limpar",
            action="store_true",
            help="Remove blocos previamente criados com o mesmo prefixo.",
        )

    def handle(self, *args, **options):
        """
        Executa rotina de criação de blocos de exemplo.

        Regras de negócio:
        - opcionalmente remove seeds anteriores com mesmo prefixo;
        - deduplica dias informados preservando ordem;
        - cria incremento inicial para cada bloco novo.
        """

        nome_base = options["nome_base"].strip() or "Exemplo para a Tamires"
        dias_lista = list(dict.fromkeys(options["dias"]))
        if options["limpar"]:
            BlocoTrabalho.objects.filter(nome__startswith=nome_base).delete()

        agora = timezone.now()
        criados = 0
        for dias in dias_lista:
            nome = f"{nome_base} - {dias} dias"
            bloco, created = BlocoTrabalho.objects.get_or_create(
                nome=nome,
                defaults={
                    "descricao": f"Bloco com {dias} dias sem atualizacao.",
                    "status": BlocoTrabalho.Status.A_FAZER,
                    "criado_em": agora - timedelta(days=dias),
                    "atualizado_em": agora - timedelta(days=dias),
                },
            )
            if created:
                Incremento.objects.create(
                    bloco=bloco,
                    texto=f"Criado para simular {dias} dias sem atualizacao.",
                    criado_em=agora - timedelta(days=dias),
                )
                criados += 1

        self.stdout.write(self.style.SUCCESS(f"Blocos criados: {criados}"))
