"""
Modelos de domínio do app `noticias`.

Este arquivo define as entidades persistidas em banco de dados que sustentam
o fluxo de publicação de notícias da intranet. As classes daqui são usadas
pelas views para consulta/escrita, pelo admin para gestão interna e pelos
templates para renderização de conteúdo.
"""
from django.db import models


class Noticia(models.Model):
    """
    Entidade de notícia publicada na intranet institucional.

    No domínio de negócio, cada instância representa uma peça de comunicação
    que pode ser listada na página inicial, exibida em detalhe e administrada
    por usuários com permissão de gestão de conteúdo.
    """
    # Título principal da notícia.
    titulo = models.CharField(max_length=200)
    # Conteúdo textual da notícia.
    texto = models.TextField()
    # Data oficial de publicação.
    data_publicacao = models.DateField()
    # Categoria/tema da notícia.
    categoria = models.CharField(max_length=100)
    # Imagem opcional para destaque em listagem e detalhe.
    imagem_destaque = models.ImageField(upload_to='noticias/', blank=True, null=True)

    class Meta:
        # Regra de ordenação padrão:
        # 1) Notícias mais recentes primeiro (data desc).
        # 2) Em empate de data, usa id desc para manter estabilidade de exibição.
        ordering = ['-data_publicacao', '-id']

    def __str__(self) -> str:
        """
        Retorna representação legível da entidade.

        Retorno:
            str: título da notícia, usado em admin, logs e shell.
        """
        return self.titulo
