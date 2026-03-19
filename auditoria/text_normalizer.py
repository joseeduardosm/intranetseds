"""
Normalização textual (atualmente desativada) no app `auditoria`.

Historicamente este módulo poderia interceptar `pre_save` para normalizar
campos de texto. No cenário atual, a estratégia foi desativada para preservar
acentos e demais caracteres Unicode sem transformação automática.
"""

from django.db.models.signals import pre_save
from django.dispatch import receiver


def _normalize_text(value: str) -> str:
    """
    Função de normalização mantida por compatibilidade.

    Parâmetros:
    - `value`: texto de entrada.

    Retorno:
    - `str`: retorna o próprio valor sem alterações.
    """

    # Preserva o texto original (acentos, cedilha e demais caracteres Unicode).
    return value


@receiver(pre_save, dispatch_uid="normalize_text_fields_pre_save")
def normalize_text_fields(sender, instance, **kwargs):
    """
    Receiver global de pre_save intencionalmente inativo.

    Parâmetros:
    - `sender`: model que disparou o sinal.
    - `instance`: objeto em persistência.
    - `**kwargs`: metadados do sinal.

    Regra de negócio:
    - não modificar automaticamente textos para evitar perda de caracteres.
    """

    # Comportamento desativado: nao alterar campos de texto automaticamente.
    return
