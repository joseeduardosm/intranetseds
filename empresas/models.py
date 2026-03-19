"""
Modelos de domínio do app `empresas`.

Este módulo define a entidade `Empresa`, usada como cadastro mestre de
fornecedores/parceiros e referência para outros apps, como prepostos e
contratos.
"""

from django.db import models


class Empresa(models.Model):
    """
    Entidade que representa uma empresa cadastrada no sistema.

    Cada registro armazena identificação textual e CNPJ opcional para
    relacionamento com outros domínios do projeto.
    """

    nome = models.CharField(max_length=200, unique=True)
    cnpj = models.CharField(max_length=20, blank=True)

    class Meta:
        """Ordena empresas alfabeticamente pelo nome."""

        ordering = ["nome"]

    def __str__(self):
        """
        Representação textual padrão para admin/listagens.

        Retorno:
        - `str`: nome da empresa.
        """

        return self.nome
