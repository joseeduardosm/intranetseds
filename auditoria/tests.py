from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from auditoria import signals
from auditoria.models import AuditLog
from sala_situacao_v2.models import Indicador


class AuditLogDateSerializationTests(TestCase):
    def test_update_com_datefield_gera_diff_serializavel(self):
        get_user_model().objects.create_user(username="auditoria-user", password="123456")
        signals._TABLES_READY = None
        indicador = Indicador.objects.create(
            nome="Indicador de teste",
            descricao="Teste de auditoria",
        )
        data_original = indicador.data_entrega_estipulada
        nova_data = timezone.localdate() + timedelta(days=5)

        indicador.data_entrega_estipulada = nova_data
        indicador.save()

        log = AuditLog.objects.filter(
            object_id=str(indicador.pk),
            action=AuditLog.Action.UPDATE,
        ).first()

        self.assertIsNotNone(log)
        self.assertEqual(
            log.changes["data_entrega_estipulada"],
            {
                "from": data_original.isoformat() if data_original else None,
                "to": nova_data.isoformat(),
            },
        )
