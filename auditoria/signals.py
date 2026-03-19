"""
Signal handlers do app `auditoria`.

Este módulo observa eventos de persistência dos models (pre_save,
post_save, post_delete e m2m_changed) para gerar trilha de auditoria
em `AuditLog`.
Integra-se com:
- middleware/thread-local para identificar usuário da request;
- ContentType para referenciar qualquer entidade do sistema.
"""

from django.apps import apps
from decimal import Decimal
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError, IntegrityError
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.db.models.fields.files import FieldFile
from django.dispatch import receiver

from .models import AuditLog
from .threadlocal import get_current_user


_OLD_STATE = {}
_TABLES_READY = None


def _audit_tables_ready():
    """
    Verifica se a tabela de auditoria já existe no banco.

    Retorno:
    - `bool`: True quando `auditoria_auditlog` está disponível.

    Regra de robustez:
    - Evita exceções durante bootstrap/migrations, quando sinais podem
      disparar antes da criação da tabela.
    """

    global _TABLES_READY
    if _TABLES_READY is not None:
        return _TABLES_READY
    try:
        tables = connection.introspection.table_names()
    except Exception:
        _TABLES_READY = False
        return False
    _TABLES_READY = "auditoria_auditlog" in tables
    return _TABLES_READY


def _is_tracked(sender):
    """
    Determina se o model emissor deve ser auditado.

    Parâmetros:
    - `sender`: classe do model que disparou o sinal.

    Retorno:
    - `bool`: True para apps de negócio, False para infraestrutura.

    Regra de negócio:
    - ignora apps internos do Django e o próprio app `auditoria`
      para evitar logs recursivos e ruído operacional.
    """
    if sender is None:
        return False
    app_label = sender._meta.app_label
    if app_label in {"auditoria", "admin", "contenttypes", "sessions"}:
        return False
    if app_label.startswith("django"):
        return False
    return True


def _get_object_repr(instance):
    """
    Gera representação textual segura do objeto auditado.

    Parâmetros:
    - `instance`: objeto de domínio afetado.

    Retorno:
    - `str`: representação curta (até 255 chars) para uso no log.
    """
    try:
        return str(instance)[:255]
    except Exception:
        return f"{instance.__class__.__name__}({instance.pk})"[:255]


def _serialize_value(value):
    """
    Converte valores para tipos serializáveis em JSON.

    Parâmetros:
    - `value`: valor bruto de campo/model.

    Retorno:
    - valor normalizado para tipos simples (dict/list/str/number/null).

    Regra de negócio:
    - preserva dados úteis do diff sem quebrar persistência em `JSONField`.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, FieldFile):
        return value.name or None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "pk"):
        return value.pk
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    return value


def _build_changes(old_obj, new_obj):
    """
    Monta diff campo-a-campo entre estado anterior e atual.

    Parâmetros:
    - `old_obj`: instância anterior (pré-save).
    - `new_obj`: instância após alterações.

    Retorno:
    - `dict`: mapa `{campo: {"from": ..., "to": ...}}`.
    """
    changes = {}
    for field in new_obj._meta.fields:
        name = field.name
        if name in {"id"}:
            continue
        old_val = getattr(old_obj, name, None)
        new_val = getattr(new_obj, name, None)
        if old_val != new_val:
            changes[name] = {
                "from": _serialize_value(old_val),
                "to": _serialize_value(new_val),
            }
    return changes


@receiver(pre_save)
def audit_pre_save(sender, instance, **kwargs):
    """
    Captura snapshot pré-save para cálculo de diff no post-save.

    Parâmetros:
    - `sender`: model emissor.
    - `instance`: objeto em persistência.
    - `**kwargs`: metadados do sinal.
    """
    if not _is_tracked(sender):
        return
    if instance.pk:
        try:
            _OLD_STATE[(sender, instance.pk)] = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            _OLD_STATE.pop((sender, instance.pk), None)


@receiver(post_save)
def audit_post_save(sender, instance, created, **kwargs):
    """
    Registra eventos de criação/edição após persistência.

    Parâmetros:
    - `sender`: model emissor.
    - `instance`: objeto salvo.
    - `created`: flag de criação (True) ou atualização (False).
    - `**kwargs`: metadados do sinal.

    Consulta ORM relevante:
    - `ContentType.objects.get_for_model(sender)` identifica a entidade
      auditada para chave genérica em `AuditLog`.
    """
    if not _is_tracked(sender):
        return
    if not _audit_tables_ready():
        return
    user = get_current_user()
    try:
        content_type = ContentType.objects.get_for_model(sender)
    except (ContentType.DoesNotExist, OperationalError, ProgrammingError, IntegrityError):
        return
    if created:
        AuditLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            action=AuditLog.Action.CREATE,
            content_type=content_type,
            object_id=str(instance.pk),
            object_repr=_get_object_repr(instance),
            changes=None,
        )
        return
    old_obj = _OLD_STATE.pop((sender, instance.pk), None)
    # Usa o estado capturado no pre_save para registrar apenas alterações reais.
    changes = _build_changes(old_obj, instance) if old_obj else None
    AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=AuditLog.Action.UPDATE,
        content_type=content_type,
        object_id=str(instance.pk),
        object_repr=_get_object_repr(instance),
        changes=changes,
    )


@receiver(post_delete)
def audit_post_delete(sender, instance, **kwargs):
    """
    Registra exclusão lógica/física de objetos auditáveis.

    Parâmetros:
    - `sender`: model emissor.
    - `instance`: objeto removido.
    - `**kwargs`: metadados do sinal.
    """
    if not _is_tracked(sender):
        return
    if not _audit_tables_ready():
        return
    user = get_current_user()
    try:
        content_type = ContentType.objects.get_for_model(sender)
    except (ContentType.DoesNotExist, OperationalError, ProgrammingError, IntegrityError):
        return
    AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=AuditLog.Action.DELETE,
        content_type=content_type,
        object_id=str(instance.pk),
        object_repr=_get_object_repr(instance),
        changes=None,
    )


@receiver(m2m_changed)
def audit_m2m(sender, instance, action, reverse, model, pk_set, **kwargs):
    """
    Registra alterações em relações many-to-many.

    Parâmetros:
    - `sender`: tabela intermediária da relação.
    - `instance`: objeto principal da relação.
    - `action`: tipo de ação (`post_add`, `post_remove`, `post_clear`).
    - `reverse`, `model`: metadados do evento M2M.
    - `pk_set`: conjunto de PKs envolvidos (quando aplicável).
    - `**kwargs`: inclui referência ao campo M2M.

    Regra de negócio:
    - somente eventos `post_*` são registrados para refletir estado final.
    """
    if not _is_tracked(instance.__class__):
        return
    if not _audit_tables_ready():
        return
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    user = get_current_user()
    try:
        content_type = ContentType.objects.get_for_model(instance.__class__)
    except (ContentType.DoesNotExist, OperationalError, ProgrammingError, IntegrityError):
        return
    action_map = {
        "post_add": AuditLog.Action.M2M_ADD,
        "post_remove": AuditLog.Action.M2M_REMOVE,
        "post_clear": AuditLog.Action.M2M_CLEAR,
    }
    field = kwargs.get("field")
    field_name = field.name if field else "m2m"
    # `changes` armazena contexto mínimo para explicar qual relação foi afetada.
    changes = {"field": field_name, "related_pks": list(pk_set)}
    AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action_map[action],
        content_type=content_type,
        object_id=str(instance.pk),
        object_repr=_get_object_repr(instance),
        changes=changes,
    )
