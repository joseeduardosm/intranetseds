"""
Comando de importação em lote para a Lousa Digital.

Integração arquitetural:
- consome arquivo CSV externo (separador `;`);
- cria/atualiza `Processo` e cria `Encaminhamento` quando houver prazo;
- associa autoria e grupo ao usuário responsável pela carga;
- executa tudo em transação atômica para consistência dos dados.
"""

import csv
from datetime import datetime, time
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from lousa_digital.models import Encaminhamento, Processo


class Command(BaseCommand):
    """Implementa `manage.py importar_lousa_csv` para carga histórica/operacional."""

    help = "Importa processos/encaminhamentos para a Lousa Digital a partir de CSV."

    def add_arguments(self, parser):
        """Declara parâmetros obrigatórios do comando.

        Parâmetros:
        - `--arquivo`: caminho do CSV de origem;
        - `--username`: usuário que será dono da importação.
        """

        parser.add_argument("--arquivo", required=True, help="Caminho do CSV.")
        parser.add_argument("--username", required=True, help="Usuario dono da importacao.")

    def _parse_data(self, valor):
        """Converte texto `YYYY-MM-DD` para `date`, aceitando vazio/'-' como nulo."""

        texto = (valor or "").strip()
        if not texto or texto == "-":
            return None
        return datetime.strptime(texto, "%Y-%m-%d").date()

    def _parse_datahora(self, valor):
        """Converte texto `YYYY-MM-DD HH:MM:SS` para `datetime` timezone-aware."""

        texto = (valor or "").strip()
        if not texto or texto == "-":
            return None
        dt = datetime.strptime(texto, "%Y-%m-%d %H:%M:%S")
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    def _mapear_status(self, valor_status, data_baixa):
        """Mapeia status textual do legado para enum de `Processo.Status`.

        Fallback:
        - sem status reconhecido, conclui se existir `data_baixa`, senão mantém aberto.
        """

        normalizado = (valor_status or "").strip().lower()
        if normalizado == "em aberto":
            return Processo.Status.EM_ABERTO
        if normalizado == "finalizado":
            return Processo.Status.CONCLUIDO
        return Processo.Status.CONCLUIDO if data_baixa else Processo.Status.EM_ABERTO

    @transaction.atomic
    def handle(self, *args, **options):
        """Executa importação linha a linha com idempotência parcial por processo.

        Regras de negócio relevantes:
        - ignora linha sem `dem_numero`;
        - cria processo quando inexistente; atualiza campos-chave quando já existe;
        - cria encaminhamento apenas se não houver duplicado por (processo, destino, prazo, início);
        - fecha ativo remanescente quando processo importado como concluído.
        """

        caminho = Path(options["arquivo"])
        if not caminho.exists():
            raise CommandError(f"Arquivo nao encontrado: {caminho}")

        User = get_user_model()
        try:
            usuario = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError(f"Usuario nao encontrado: {options['username']}") from exc

        grupo = usuario.groups.order_by("name", "id").first()
        now = timezone.now()

        processos_criados = 0
        processos_atualizados = 0
        encaminhamentos_criados = 0
        linhas_puladas = 0

        # `utf-8-sig` evita problema com BOM em planilhas exportadas.
        with caminho.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            for idx, row in enumerate(reader, start=2):
                numero_sei = (row.get("dem_numero") or "").strip()
                if not numero_sei or numero_sei == "-":
                    linhas_puladas += 1
                    self.stdout.write(self.style.WARNING(f"Linha {idx}: dem_numero vazio, ignorada."))
                    continue

                assunto = (row.get("dem_assunto") or "").strip()
                assunto = assunto[:255] if len(assunto) > 255 else assunto
                if not assunto:
                    assunto = "Sem assunto"

                destino = (row.get("departamento_descricao") or "").strip()
                if not destino or destino == "-":
                    destino = "OUTROS"

                prazo_data = self._parse_data(row.get("dem_prazo"))
                data_cadastro = self._parse_datahora(row.get("data_cadastro"))
                data_baixa = self._parse_datahora(row.get("data_baixa"))
                status = self._mapear_status(row.get("dem_status_descricao"), data_baixa)

                # Defaults aplicados somente na criação; atualização é tratada em bloco específico.
                defaults = {
                    "assunto": assunto,
                    "link_sei": "",
                    "caixa_origem": destino,
                    "status": status,
                    "atualizado_por": usuario,
                    "criado_por": usuario,
                    "grupo_insercao": grupo,
                }
                processo, created = Processo.objects.get_or_create(numero_sei=numero_sei, defaults=defaults)
                if created:
                    processos_criados += 1
                else:
                    # Update direto reduz side-effects e mantém `atualizado_em` consistente com a carga.
                    Processo.objects.filter(pk=processo.pk).update(
                        assunto=assunto,
                        caixa_origem=destino,
                        status=status,
                        atualizado_por=usuario,
                        grupo_insercao=grupo,
                        atualizado_em=now,
                    )
                    processos_atualizados += 1
                    processo.refresh_from_db()

                if prazo_data:
                    inicio = data_cadastro or now
                    data_conclusao = None
                    if status == Processo.Status.CONCLUIDO:
                        data_conclusao = data_baixa
                        if data_conclusao is None:
                            limite = datetime.combine(prazo_data, time(23, 59, 59))
                            if timezone.is_naive(limite):
                                limite = timezone.make_aware(limite, timezone.get_current_timezone())
                            data_conclusao = max(limite, inicio)

                    # Evita duplicação de encaminhamento em reimportações do mesmo arquivo.
                    ja_existe = Encaminhamento.objects.filter(
                        processo=processo,
                        destino=destino,
                        prazo_data=prazo_data,
                        data_inicio=inicio,
                    ).exists()
                    if not ja_existe:
                        enc = Encaminhamento.objects.create(
                            processo=processo,
                            destino=destino,
                            prazo_data=prazo_data,
                            criado_por=usuario,
                            concluido_por=usuario if data_conclusao else None,
                        )
                        Encaminhamento.objects.filter(pk=enc.pk).update(
                            data_inicio=inicio,
                            data_conclusao=data_conclusao,
                        )
                        encaminhamentos_criados += 1

                # Consistência final: processo concluído não deve manter encaminhamento ativo.
                if processo.status == Processo.Status.CONCLUIDO and processo.encaminhamentos.filter(data_conclusao__isnull=True).exists():
                    ultimo_ativo = processo.encaminhamentos.filter(data_conclusao__isnull=True).order_by("-data_inicio").first()
                    if ultimo_ativo:
                        ultimo_ativo.data_conclusao = data_baixa or now
                        ultimo_ativo.concluido_por = usuario
                        ultimo_ativo.save(update_fields=["data_conclusao", "concluido_por"])

        self.stdout.write(self.style.SUCCESS("Importacao concluida."))
        self.stdout.write(f"Processos criados: {processos_criados}")
        self.stdout.write(f"Processos atualizados: {processos_atualizados}")
        self.stdout.write(f"Encaminhamentos criados: {encaminhamentos_criados}")
        self.stdout.write(f"Linhas puladas: {linhas_puladas}")
