"""
Modelos persistentes do app `folha_ponto`.

Este arquivo representa a camada de domínio de RH para folha de ponto e integra-se com:
- `views.py`, que consulta e consolida feriados/férias na impressão mensal;
- `forms.py`, que valida e escreve registros administrativos;
- `admin.py`, que expõe manutenção de dados para perfis autorizados;
- app `ramais`, de onde vem o vínculo do servidor (`PessoaRamal`).
"""

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models

from ramais.models import PessoaRamal


class Feriado(models.Model):
    """Representa um feriado oficial usado no cálculo da folha mensal.

    Regra de negócio:
    - Cada data de feriado é única para evitar duplicidade no fechamento do mês.
    - O cadastro impacta diretamente as linhas marcadas como "feriado" na impressão.
    """

    data = models.DateField(unique=True)
    descricao = models.CharField(max_length=180)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Metadados de ordenação e nomenclatura administrativa no Django."""

        ordering = ["data"]
        verbose_name = "Feriado"
        verbose_name_plural = "Feriados"

    def __str__(self) -> str:
        """Retorna rótulo legível do feriado para admin e seleções.

        Retorno:
        - `str` no formato `dd/mm/aaaa - descrição`.
        """

        return f"{self.data:%d/%m/%Y} - {self.descricao}"


class FeriasServidor(models.Model):
    """Registra período de férias de um servidor (`PessoaRamal`).

    Papel no domínio:
    - Define intervalos que serão marcados como "FÉRIAS" no espelho de ponto mensal.
    - Mantém rastreabilidade de quem lançou o registro (`criado_por`).
    """

    servidor = models.ForeignKey(
        PessoaRamal,
        on_delete=models.CASCADE,
        related_name="ferias_registros",
    )
    data_inicio = models.DateField()
    data_fim = models.DateField()
    observacao = models.CharField(max_length=220, blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ferias_lancadas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Metadados de ordenação e nomenclatura para administração de RH."""

        ordering = ["-data_inicio", "-data_fim"]
        verbose_name = "Ferias"
        verbose_name_plural = "Ferias"

    def clean(self):
        """Valida consistência do período de férias antes da persistência.

        Regra de negócio:
        - `data_fim` não pode ser anterior a `data_inicio`.
        - A validação protege tanto formulários quanto chamadas de modelo em código.
        """

        super().clean()
        if self.data_fim and self.data_inicio and self.data_fim < self.data_inicio:
            from django.core.exceptions import ValidationError

            raise ValidationError({"data_fim": "A data final deve ser maior ou igual a data inicial."})

    def __str__(self) -> str:
        """Retorna resumo textual do período de férias do servidor.

        Retorno:
        - `str` contendo servidor e intervalo formatado para leitura humana.
        """

        return f"{self.servidor.nome_display} - {self.data_inicio:%d/%m/%Y} a {self.data_fim:%d/%m/%Y}"


class ConfiguracaoRH(models.Model):
    """Armazena configuração global de RH para renderização da folha.

    Entidade singleton de configuração:
    - Guarda o brasão exibido no layout de impressão.
    - A view de manutenção garante existência de um registro ativo.
    """

    brasao = models.ImageField(
        upload_to="folha_ponto/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg"])],
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Define nomes administrativos da configuração no Django Admin."""

        verbose_name = "Configuracao RH"
        verbose_name_plural = "Configuracoes RH"

    def __str__(self) -> str:
        """Retorna descrição fixa da configuração global de RH.

        Retorno:
        - `str` amigável para interfaces administrativas.
        """

        return "Configuracao RH"
