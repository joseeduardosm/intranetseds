"""
Modelos de dados do app `prepostos`.

Este arquivo define as entidades persistidas em banco para o domínio de
prepostos vinculados a empresas. Os modelos são utilizados pelas views para
operações CRUD, pelo admin para gestão e pelos templates para apresentação.
"""
from django.db import models

from empresas.models import Empresa


class Preposto(models.Model):
    """
    Entidade de domínio que representa o preposto de uma empresa.

    No contexto de negócio, o preposto é a pessoa de contato/responsável
    associada a uma empresa cadastrada no sistema.
    """
    # Nome completo do preposto para identificação em listas e detalhes.
    nome = models.CharField(max_length=200)
    # CPF utilizado como identificador civil do preposto.
    cpf = models.CharField(max_length=14)
    # Telefone para contato, opcional.
    telefone = models.CharField(max_length=20, blank=True)
    # E-mail para contato, opcional.
    email = models.EmailField(blank=True)
    # Relação obrigatória com Empresa.
    # `on_delete=PROTECT` evita remoção de empresas que ainda possuem prepostos
    # vinculados, preservando integridade referencial.
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="prepostos")

    class Meta:
        # Ordenação padrão por nome para facilitar localização alfabética.
        ordering = ["nome"]

    def __str__(self):
        """
        Retorna representação textual da entidade.

        Retorno:
            str: nome do preposto para uso em admin, shell e logs.
        """
        return self.nome
