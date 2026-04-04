import shutil
import tempfile
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from administracao.models import SMTPConfiguration
from auditoria.models import AuditLog
from notificacoes.models import NotificacaoUsuario

from .models import (
    HistoricoSistema,
    EntregaSistema,
    EtapaSistema,
    HistoricoEtapaSistema,
    InteressadoSistema,
    InteressadoSistemaManual,
    Sistema,
)
from .services import _corpo_email_historico, _corpo_email_publicacao
from .utils import nome_usuario_exibicao


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="acompanhamento-sistemas-test-")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class AcompanhamentoSistemasTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="gestor-sistemas",
            password="senha-123",
            email="gestor@exemplo.gov.br",
            first_name="Gestor",
        )
        self.viewer = get_user_model().objects.create_user(
            username="viewer-sistemas",
            password="senha-123",
            email="viewer@exemplo.gov.br",
        )
        self.outro = get_user_model().objects.create_user(
            username="outro-responsavel",
            password="senha-123",
            email="outro@exemplo.gov.br",
            first_name="Outro",
        )
        self._grant_perms(
            self.user,
            [
                "view_sistema",
                "add_sistema",
                "change_sistema",
                "delete_sistema",
                "view_entregasistema",
                "add_entregasistema",
                "change_entregasistema",
                "delete_entregasistema",
                "view_etapasistema",
                "change_etapasistema",
            ],
        )
        self._grant_perms(
            self.viewer,
            [
                "view_sistema",
                "view_entregasistema",
                "view_etapasistema",
            ],
        )
        self.client.force_login(self.user)
        self.smtp = SMTPConfiguration.objects.create(
            host="smtp.exemplo.gov.br",
            port=587,
            use_tls=True,
            use_ssl=False,
            username="user",
            password="pass",
            from_email="noreply@exemplo.gov.br",
            timeout=10,
            ativo=True,
        )

    def _grant_perms(self, user, codenames):
        for codename in codenames:
            perm = Permission.objects.get(codename=codename, content_type__app_label="acompanhamento_sistemas")
            user.user_permissions.add(perm)

    def _criar_sistema(self, nome="Portal SEDS"):
        response = self.client.post(
            reverse("acompanhamento_sistemas_create"),
            {
                "nome": nome,
                "descricao": "Sistema de apoio institucional",
                "url_homologacao": "https://homolog.exemplo.gov.br",
                "url_producao": "https://producao.exemplo.gov.br",
            },
        )
        self.assertEqual(response.status_code, 302)
        return Sistema.objects.get(nome=nome)

    def _criar_entrega(self, sistema, titulo="Entrega de teste", descricao=""):
        response = self.client.post(
            reverse("acompanhamento_sistemas_entrega_create", kwargs={"pk": sistema.pk}),
            {
                "titulo": titulo,
                "descricao": descricao,
            },
        )
        self.assertEqual(response.status_code, 302)
        return sistema.entregas.order_by("ordem", "id").last()

    def _definir_datas_ciclo(self, entrega, datas=None):
        datas = datas or [
            timezone.localdate() + timedelta(days=1),
            timezone.localdate() + timedelta(days=3),
            timezone.localdate() + timedelta(days=7),
            timezone.localdate() + timedelta(days=10),
            timezone.localdate() + timedelta(days=14),
        ]
        for etapa, data in zip(entrega.etapas.order_by("ordem"), datas):
            etapa.data_etapa = data
            etapa.save(update_fields=["data_etapa", "atualizado_em"])
        entrega.refresh_from_db()
        return datas

    def _publicar_entrega(self, entrega):
        response = self.client.post(
            reverse("acompanhamento_sistemas_entrega_publish", kwargs={"pk": entrega.pk})
        )
        self.assertEqual(response.status_code, 302)
        entrega.refresh_from_db()
        return response

    def test_criacao_de_sistema_nao_gera_entrega_automatica(self):
        sistema = self._criar_sistema()

        self.assertEqual(sistema.entregas.count(), 0)

    @patch("acompanhamento_sistemas.services.EmailMessage.send", return_value=1)
    def test_publicacao_de_entrega_gera_notificacao_desktop_para_interessado_vinculado(self, mock_send):
        sistema = self._criar_sistema()
        InteressadoSistema.objects.create(
            sistema=sistema,
            usuario=self.viewer,
            tipo_interessado="GESTAO",
            nome_snapshot="Viewer Sistemas",
            email_snapshot=self.viewer.email,
            criado_por=self.user,
        )
        entrega = self._criar_entrega(sistema, titulo="MVP Desktop")
        self._definir_datas_ciclo(entrega)

        self._publicar_entrega(entrega)

        notificacao = NotificacaoUsuario.objects.get(user=self.viewer, event_type="publicacao_ciclo")
        self.assertEqual(notificacao.title, f"Sistema: {sistema.nome}")
        self.assertIn(f"Ciclo: {entrega.titulo}", notificacao.body_short)
        self.assertIn("Etapa: Ciclo - cronograma inicial publicado.", notificacao.body_short)
        self.assertIn(f"/acompanhamento-sistemas/entregas/{entrega.pk}/", notificacao.target_url)

    @patch("acompanhamento_sistemas.services.EmailMessage.send", return_value=1)
    def test_historico_de_etapa_publicada_gera_notificacao_desktop(self, mock_send):
        sistema = self._criar_sistema(nome="Sistema Desktop")
        InteressadoSistema.objects.create(
            sistema=sistema,
            usuario=self.viewer,
            tipo_interessado="GESTAO",
            nome_snapshot="Viewer Sistemas",
            email_snapshot=self.viewer.email,
            criado_por=self.user,
        )
        entrega = self._criar_entrega(sistema, titulo="Entrega Desktop")
        self._definir_datas_ciclo(entrega)
        self._publicar_entrega(entrega)
        etapa = entrega.etapas.order_by("ordem").first()

        response = self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa.pk}),
            {
                "data_etapa": etapa.data_etapa.strftime("%Y-%m-%d"),
                "status": EtapaSistema.Status.EM_ANDAMENTO,
                "justificativa_status": "Inicio dos trabalhos",
                "texto_nota": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        notificacao = NotificacaoUsuario.objects.filter(user=self.viewer, event_type="etapa_status").latest("id")
        self.assertEqual(notificacao.title, f"Sistema: {sistema.nome}")
        self.assertIn(f"Ciclo: {entrega.titulo}", notificacao.body_short)
        self.assertIn(f"Etapa: {etapa.get_tipo_etapa_display()} - status alterado para Em andamento.", notificacao.body_short)
        self.assertIn(f"/acompanhamento-sistemas/etapas/{etapa.pk}/", notificacao.target_url)

    def test_nota_em_sistema_gera_notificacao_desktop_mesmo_sem_email(self):
        sistema = self._criar_sistema(nome="Sistema Nota")
        InteressadoSistema.objects.create(
            sistema=sistema,
            usuario=self.viewer,
            tipo_interessado="GESTAO",
            nome_snapshot="Viewer Sistemas",
            email_snapshot="",
            criado_por=self.user,
        )

        response = self.client.post(
            reverse("acompanhamento_sistemas_nota", kwargs={"pk": sistema.pk}),
            {"texto_nota": "Nova anotação do sistema"},
        )

        self.assertEqual(response.status_code, 302)
        notificacao = NotificacaoUsuario.objects.get(user=self.viewer, event_type="sistema_nota")
        self.assertEqual(notificacao.title, f"{sistema.nome} - Atualização do sistema")
        self.assertIn("Sistema: Nova anotação do sistema", notificacao.body_short)
        self.assertIn(f"/acompanhamento-sistemas/{sistema.pk}/", notificacao.target_url)

    def test_criacao_manual_de_entrega_gera_cinco_etapas(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="MVP", descricao="Primeira entrega")

        self.assertEqual(sistema.entregas.count(), 1)
        self.assertEqual(entrega.titulo, "MVP")
        self.assertEqual(entrega.status, EntregaSistema.Status.RASCUNHO)
        self.assertEqual(entrega.etapas.count(), 5)
        self.assertEqual(
            list(entrega.etapas.order_by("ordem").values_list("status", flat=True)),
            [EtapaSistema.Status.PENDENTE] * 5,
        )
        self.assertEqual(
            list(entrega.etapas.order_by("ordem").values_list("data_etapa", flat=True)),
            [None] * 5,
        )

    def test_ciclo_ganha_numeracao_dinamica_no_sistema(self):
        sistema = self._criar_sistema()
        ciclo_1 = self._criar_entrega(sistema, titulo="Sprint 01")
        ciclo_2 = self._criar_entrega(sistema, titulo="Sprint 02")
        ciclo_3 = self._criar_entrega(sistema, titulo="Sprint 03")

        self.assertEqual(ciclo_1.rotulo_numeracao_no_sistema, "1/3")
        self.assertEqual(ciclo_2.rotulo_numeracao_no_sistema, "2/3")
        self.assertEqual(ciclo_3.rotulo_numeracao_no_sistema, "3/3")
        self.assertEqual(ciclo_2.titulo_com_numeracao, "2/3 Sprint 02")

    def test_progresso_de_entrega_e_sistema_segue_media_processual_das_etapas(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="MVP")
        etapas = list(entrega.etapas.order_by("ordem"))
        etapas[0].status = EtapaSistema.Status.ENTREGUE
        etapas[0].save(update_fields=["status", "atualizado_em"])
        etapas[1].status = EtapaSistema.Status.EM_ANDAMENTO
        etapas[1].save(update_fields=["status", "atualizado_em"])

        entrega.refresh_from_db()
        sistema.refresh_from_db()

        self.assertEqual(etapas[0].progresso_percentual, 100.0)
        self.assertEqual(etapas[1].progresso_percentual, 50.0)
        self.assertEqual(entrega.progresso_percentual, 30.0)
        self.assertEqual(sistema.progresso_percentual, 30.0)
        self.assertEqual(entrega.progresso_classe, "progresso-vermelho")

    def test_progresso_de_prazo_do_ciclo_considera_cadastro_ate_ultima_etapa(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="Sprint Prazo")
        inicio = timezone.now() - timedelta(days=10)
        entrega.__class__.objects.filter(pk=entrega.pk).update(criado_em=inicio)
        entrega.refresh_from_db()
        self._definir_datas_ciclo(
            entrega,
            [timezone.localdate() + timedelta(days=10)] * 5,
        )

        self.assertGreater(entrega.progresso_prazo, 45.0)
        self.assertLess(entrega.progresso_prazo, 55.0)
        self.assertEqual(entrega.prazo_snapshot["titulo"], "Evolução do Prazo")

    def test_lead_time_do_sistema_usa_hoje_quando_ha_etapas_em_aberto(self):
        sistema = self._criar_sistema()
        self._criar_entrega(sistema, titulo="Sprint Lead")
        criado_em = timezone.now() - timedelta(days=5)
        Sistema.objects.filter(pk=sistema.pk).update(criado_em=criado_em)
        sistema.refresh_from_db()

        self.assertEqual(sistema.lead_time_dias, 5)
        self.assertEqual(sistema.lead_time_texto, "5 dias")

    def test_lead_time_do_sistema_usa_ultima_data_quando_tudo_esta_concluido(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="Sprint Concluída")
        criado_em = timezone.now() - timedelta(days=10)
        Sistema.objects.filter(pk=sistema.pk).update(criado_em=criado_em)
        datas = [
            timezone.localdate() - timedelta(days=8),
            timezone.localdate() - timedelta(days=7),
            timezone.localdate() - timedelta(days=6),
            timezone.localdate() - timedelta(days=5),
            timezone.localdate() - timedelta(days=4),
        ]
        for etapa, data in zip(entrega.etapas.order_by("ordem"), datas):
            etapa.status = EtapaSistema.Status.ENTREGUE
            etapa.data_etapa = data
            etapa.save(update_fields=["status", "data_etapa", "atualizado_em"])
        sistema.refresh_from_db()

        self.assertEqual(sistema.lead_time_dias, 6)
        self.assertEqual(sistema.lead_time_texto, "6 dias")

    def test_lead_time_do_sistema_formata_meses_e_dias(self):
        sistema = self._criar_sistema()
        Sistema.objects.filter(pk=sistema.pk).update(
            criado_em=timezone.make_aware(datetime(2026, 1, 15, 9, 0, 0))
        )
        entrega = self._criar_entrega(sistema, titulo="Sprint Meses")
        for etapa in entrega.etapas.order_by("ordem"):
            etapa.status = EtapaSistema.Status.ENTREGUE
            etapa.data_etapa = date(2026, 3, 20)
            etapa.save(update_fields=["status", "data_etapa", "atualizado_em"])
        sistema.refresh_from_db()

        self.assertEqual(sistema.lead_time_texto, "2 meses e 5 dias")

    def test_lead_time_do_sistema_formata_anos_meses_e_dias(self):
        sistema = self._criar_sistema()
        Sistema.objects.filter(pk=sistema.pk).update(
            criado_em=timezone.make_aware(datetime(2024, 1, 10, 9, 0, 0))
        )
        entrega = self._criar_entrega(sistema, titulo="Sprint Anos")
        for etapa in entrega.etapas.order_by("ordem"):
            etapa.status = EtapaSistema.Status.ENTREGUE
            etapa.data_etapa = date(2026, 3, 15)
            etapa.save(update_fields=["status", "data_etapa", "atualizado_em"])
        sistema.refresh_from_db()

        self.assertEqual(sistema.lead_time_texto, "2 anos, 2 meses e 5 dias")

    def test_alteracao_de_status_sem_justificativa_falha(self):
        sistema = self._criar_sistema()
        self._criar_entrega(sistema)
        etapa = sistema.entregas.get().etapas.order_by("ordem").first()

        response = self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa.pk}),
            {
                "data_etapa": "",
                "status": EtapaSistema.Status.EM_ANDAMENTO,
                "justificativa_status": "",
                "texto_nota": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        etapa.refresh_from_db()
        self.assertEqual(etapa.status, EtapaSistema.Status.PENDENTE)
        self.assertContains(response, "Informe a justificativa ao alterar o status.")
        self.assertContains(response, 'data-message-text="Informe a justificativa ao alterar o status."', html=False)

    def test_requisitos_entregue_exige_anexo_dos_requisitos(self):
        sistema = self._criar_sistema()
        self._criar_entrega(sistema)
        etapa = sistema.entregas.get().etapas.order_by("ordem").first()

        response = self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa.pk}),
            {
                "data_etapa": "",
                "status": EtapaSistema.Status.ENTREGUE,
                "justificativa_status": "Documento finalizado",
            },
        )

        self.assertEqual(response.status_code, 200)
        etapa.refresh_from_db()
        self.assertEqual(etapa.status, EtapaSistema.Status.PENDENTE)
        self.assertContains(response, "Ao concluir Requisitos, anexe obrigatoriamente o documento de requisitos.")

    @patch("acompanhamento_sistemas.services.EmailMessage.send", return_value=1)
    def test_alteracao_de_status_grava_historico_auditoria_e_notifica(self, mock_send):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
        self._definir_datas_ciclo(entrega)
        self._publicar_entrega(entrega)
        etapa = sistema.entregas.get().etapas.order_by("ordem").first()
        InteressadoSistemaManual.objects.create(
            sistema=sistema,
            tipo_interessado="GESTAO",
            nome="Gestora",
            email="gestora@exemplo.gov.br",
            criado_por=self.user,
        )

        response = self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa.pk}),
            {
                "data_etapa": etapa.data_etapa.isoformat(),
                "status": EtapaSistema.Status.EM_ANDAMENTO,
                "justificativa_status": "Priorização da equipe",
                "texto_nota": "A etapa foi iniciada.",
            },
        )

        self.assertEqual(response.status_code, 302)
        etapa.refresh_from_db()
        self.assertEqual(etapa.status, EtapaSistema.Status.EM_ANDAMENTO)
        historico = etapa.historicos.first()
        self.assertEqual(historico.tipo_evento, HistoricoEtapaSistema.TipoEvento.STATUS)
        self.assertEqual(historico.justificativa, "Priorização da equipe")
        self.assertNotIn("email enviado:", historico.descricao)
        self.assertTrue(
            AuditLog.objects.filter(
                content_type__app_label="acompanhamento_sistemas",
                object_id=str(etapa.pk),
            ).exists()
        )
        self.assertEqual(mock_send.call_count, 1)

    def test_corpo_do_email_destaca_conteudo_e_justificativa_do_status(self):
        sistema = self._criar_sistema(nome="Monitora")
        entrega = self._criar_entrega(sistema, titulo="Prestação de Contas")
        self._definir_datas_ciclo(entrega)
        etapa = entrega.etapas.order_by("ordem").first()
        historico = HistoricoEtapaSistema.objects.create(
            etapa=etapa,
            tipo_evento=HistoricoEtapaSistema.TipoEvento.STATUS,
            descricao="Status alterado de Pendente para Entregue.",
            status_anterior=EtapaSistema.Status.PENDENTE,
            status_novo=EtapaSistema.Status.ENTREGUE,
            justificativa="XXXXXXXXXXXXXXXXXX",
            criado_por=self.user,
        )

        corpo = _corpo_email_historico(
            historico,
            responsavel="Administrador",
            link="http://sgi.seds.sp.gov.br/acompanhamento-sistemas/etapas/41/",
        )

        self.assertIn("Sistema: Monitora", corpo)
        self.assertIn("Entrega: Prestação de Contas", corpo)
        self.assertIn("Etapa: Requisitos", corpo)
        self.assertIn("Tipo de atualização: Status", corpo)
        self.assertIn("Conteúdo: Status alterado de pendente para entregue.", corpo)
        self.assertIn("Justificativa: XXXXXXXXXXXXXXXXXX", corpo)
        self.assertIn("Responsável: Administrador", corpo)

    def test_corpo_do_email_de_publicacao_lista_etapas_e_datas(self):
        sistema = self._criar_sistema(nome="Monitora")
        entrega = self._criar_entrega(sistema, titulo="Prestação de Contas")
        self._definir_datas_ciclo(
            entrega,
            [
                date(2026, 4, 1),
                date(2026, 4, 5),
                date(2026, 4, 10),
                date(2026, 4, 15),
                date(2026, 4, 20),
            ],
        )

        corpo = _corpo_email_publicacao(
            entrega,
            responsavel="Administrador",
            link="http://sgi.seds.sp.gov.br/acompanhamento-sistemas/entregas/11/",
        )

        self.assertIn("Tipo de atualização: Publicação do cronograma inicial", corpo)
        self.assertIn("- Requisitos: 01/04/2026", corpo)
        self.assertIn("- Producao: 20/04/2026", corpo)
        self.assertIn("Responsável: Administrador", corpo)

    @patch("acompanhamento_sistemas.services.EmailMessage.send", return_value=1)
    def test_publicacao_do_ciclo_envia_email_consolidado(self, mock_send):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="Sprint 01")
        self._definir_datas_ciclo(entrega)
        InteressadoSistemaManual.objects.create(
            sistema=sistema,
            tipo_interessado="GESTAO",
            nome="Gestora",
            email="gestora@exemplo.gov.br",
            criado_por=self.user,
        )

        response = self.client.post(
            reverse("acompanhamento_sistemas_entrega_publish", kwargs={"pk": entrega.pk})
        )

        self.assertEqual(response.status_code, 302)
        entrega.refresh_from_db()
        self.assertEqual(entrega.status, EntregaSistema.Status.PUBLICADO)
        self.assertEqual(mock_send.call_count, 1)

    @patch("acompanhamento_sistemas.services.EmailMessage.send", return_value=1)
    def test_rascunho_nao_envia_email_em_alteracao_individual(self, mock_send):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
        etapa = entrega.etapas.order_by("ordem").first()
        InteressadoSistemaManual.objects.create(
            sistema=sistema,
            tipo_interessado="GESTAO",
            nome="Gestora",
            email="gestora@exemplo.gov.br",
            criado_por=self.user,
        )

        response = self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa.pk}),
            {
                "data_etapa": (timezone.localdate() + timedelta(days=2)).isoformat(),
                "status": etapa.status,
                "justificativa_status": "",
                "texto_nota": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(mock_send.call_count, 0)

    @patch("acompanhamento_sistemas.services.EmailMessage.send", return_value=1)
    def test_publicacao_exige_todas_as_datas(self, mock_send):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
        primeira_etapa = entrega.etapas.order_by("ordem").first()
        primeira_etapa.data_etapa = timezone.localdate() + timedelta(days=1)
        primeira_etapa.save(update_fields=["data_etapa", "atualizado_em"])

        response = self.client.post(
            reverse("acompanhamento_sistemas_entrega_publish", kwargs={"pk": entrega.pk}),
            follow=True,
        )

        entrega.refresh_from_db()
        self.assertEqual(entrega.status, EntregaSistema.Status.RASCUNHO)
        self.assertEqual(mock_send.call_count, 0)
        self.assertContains(response, "Defina a data de todas as etapas antes de publicar o ciclo.")

    def test_tela_do_ciclo_exibe_modal_de_publicacao(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
        self._definir_datas_ciclo(entrega)

        response = self.client.get(reverse("acompanhamento_sistemas_entrega_detail", kwargs={"pk": entrega.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Você tem certeza que deseja publicar esse ciclo?")
        self.assertContains(response, "Confirmar publicação")
        self.assertContains(response, "Publicar ciclo")

    def test_etapa_entregue_avanca_proxima_para_em_andamento_e_grava_historico(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
        self._definir_datas_ciclo(entrega)
        self._publicar_entrega(entrega)
        etapa_atual, proxima_etapa = list(entrega.etapas.order_by("ordem")[:2])

        response = self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_atual.pk}),
            {
                "data_etapa": etapa_atual.data_etapa.isoformat(),
                "status": EtapaSistema.Status.ENTREGUE,
                "justificativa_status": "Etapa concluída",
                "anexos": [SimpleUploadedFile("requisitos.pdf", b"pdf-requisitos")],
            },
        )

        self.assertEqual(response.status_code, 302)
        etapa_atual.refresh_from_db()
        proxima_etapa.refresh_from_db()
        self.assertEqual(etapa_atual.status, EtapaSistema.Status.ENTREGUE)
        self.assertEqual(proxima_etapa.status, EtapaSistema.Status.EM_ANDAMENTO)
        self.assertEqual(etapa_atual.historicos.first().anexos.count(), 1)
        historico_proxima = proxima_etapa.historicos.first()
        self.assertEqual(historico_proxima.tipo_evento, HistoricoEtapaSistema.TipoEvento.STATUS)
        self.assertEqual(historico_proxima.status_novo, EtapaSistema.Status.EM_ANDAMENTO)
        self.assertNotContains(
            self.client.get(reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": proxima_etapa.pk})),
            "Status alterado automaticamente de Pendente para Em andamento apos conclusao da etapa anterior.",
        )

    def test_homologacao_de_requisitos_exibe_anexo_herdado_da_etapa_requisitos(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
        self._definir_datas_ciclo(entrega)
        self._publicar_entrega(entrega)
        etapa_requisitos, etapa_homologacao = list(entrega.etapas.order_by("ordem")[:2])

        self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_requisitos.pk}),
            {
                "data_etapa": etapa_requisitos.data_etapa.isoformat(),
                "status": EtapaSistema.Status.ENTREGUE,
                "justificativa_status": "Documento finalizado",
                "anexos": [SimpleUploadedFile("requisitos.pdf", b"pdf-requisitos")],
            },
        )

        response = self.client.get(reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa_homologacao.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Homologacao de Requisitos em Andamento. Documento de requisitos disponibilizado para a etapa de Homologacao de Requisitos.")
        self.assertContains(response, "Justificativa:</strong> Documento finalizado", html=False)
        self.assertContains(response, "requisitos.pdf")

    def test_nao_permite_alterar_status_da_proxima_etapa_sem_concluir_a_anterior(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
        self._definir_datas_ciclo(entrega)
        self._publicar_entrega(entrega)
        primeira_etapa, segunda_etapa = list(entrega.etapas.order_by("ordem")[:2])

        response = self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": segunda_etapa.pk}),
            {
                "data_etapa": segunda_etapa.data_etapa.isoformat(),
                "status": EtapaSistema.Status.EM_ANDAMENTO,
                "justificativa_status": "Tentativa de avanço antecipado",
            },
        )

        self.assertEqual(response.status_code, 200)
        primeira_etapa.refresh_from_db()
        segunda_etapa.refresh_from_db()
        self.assertEqual(primeira_etapa.status, EtapaSistema.Status.PENDENTE)
        self.assertEqual(segunda_etapa.status, EtapaSistema.Status.PENDENTE)
        self.assertContains(response, "A etapa anterior precisa estar como Entregue antes de alterar o status desta etapa.")

    def test_homologacao_exibe_status_aprovado_e_reprovado_no_formulario(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
        self._definir_datas_ciclo(entrega)
        self._publicar_entrega(entrega)
        etapa_requisitos, etapa_homologacao = list(entrega.etapas.order_by("ordem")[:2])
        self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_requisitos.pk}),
            {
                "data_etapa": etapa_requisitos.data_etapa.isoformat(),
                "status": EtapaSistema.Status.ENTREGUE,
                "justificativa_status": "Documento finalizado",
                "anexos": [SimpleUploadedFile("requisitos.pdf", b"pdf-requisitos")],
            },
        )

        response = self.client.get(reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa_homologacao.pk}))

        self.assertContains(response, "Aprovado")
        self.assertContains(response, "Reprovado")
        self.assertNotContains(response, "<option value=\"ENTREGUE\">Entregue</option>", html=False)

    def test_homologacao_aprovada_avanca_para_proxima_etapa(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
        self._definir_datas_ciclo(entrega)
        self._publicar_entrega(entrega)
        etapa_requisitos, etapa_homologacao, etapa_desenvolvimento = list(entrega.etapas.order_by("ordem")[:3])
        self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_requisitos.pk}),
            {
                "data_etapa": etapa_requisitos.data_etapa.isoformat(),
                "status": EtapaSistema.Status.ENTREGUE,
                "justificativa_status": "Documento finalizado",
                "anexos": [SimpleUploadedFile("requisitos.pdf", b"pdf-requisitos")],
            },
        )

        response = self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_homologacao.pk}),
            {
                "data_etapa": etapa_homologacao.data_etapa.isoformat(),
                "status": EtapaSistema.Status.APROVADO,
                "justificativa_status": "Homologado com sucesso",
            },
        )

        self.assertEqual(response.status_code, 302)
        etapa_homologacao.refresh_from_db()
        etapa_desenvolvimento.refresh_from_db()
        self.assertEqual(etapa_homologacao.status, EtapaSistema.Status.APROVADO)
        self.assertEqual(etapa_desenvolvimento.status, EtapaSistema.Status.EM_ANDAMENTO)
        response_etapa_anterior = self.client.get(reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa_requisitos.pk}))
        self.assertContains(response_etapa_anterior, "Homologação aprovada. Esta etapa foi validada e o fluxo avançou.")
        self.assertContains(response_etapa_anterior, "Homologado com sucesso")

    def test_homologacao_reprovada_retorna_fluxo_e_exibe_marcadores_visuais(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="Ciclo Visual")
        self._definir_datas_ciclo(entrega)
        self._publicar_entrega(entrega)
        etapa_requisitos, etapa_homologacao = list(entrega.etapas.order_by("ordem")[:2])
        self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_requisitos.pk}),
            {
                "data_etapa": etapa_requisitos.data_etapa.isoformat(),
                "status": EtapaSistema.Status.ENTREGUE,
                "justificativa_status": "Documento finalizado",
                "anexos": [SimpleUploadedFile("requisitos.pdf", b"pdf-requisitos")],
            },
        )

        response_reprovacao = self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_homologacao.pk}),
            {
                "data_etapa": etapa_homologacao.data_etapa.isoformat(),
                "status": EtapaSistema.Status.REPROVADO,
                "justificativa_status": "Necessita ajustes",
            },
        )

        self.assertEqual(response_reprovacao.status_code, 302)
        etapa_requisitos.refresh_from_db()
        etapa_homologacao.refresh_from_db()
        self.assertEqual(etapa_requisitos.status, EtapaSistema.Status.EM_ANDAMENTO)
        self.assertEqual(etapa_homologacao.status, EtapaSistema.Status.PENDENTE)

        response_ciclo = self.client.get(reverse("acompanhamento_sistemas_entrega_detail", kwargs={"pk": entrega.pk}))
        self.assertContains(response_ciclo, "Retomada")
        self.assertNotContains(response_ciclo, "Já iniciada")
        self.assertNotContains(response_ciclo, "Reaberta")
        self.assertContains(response_ciclo, "Reprovado")

        response_etapa = self.client.get(reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa_homologacao.pk}))
        self.assertContains(response_etapa, "Homologação reprovada.")
        self.assertContains(response_etapa, "Necessita ajustes")
        response_etapa_anterior = self.client.get(reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa_requisitos.pk}))
        self.assertContains(response_etapa_anterior, "Homologação reprovada. Esta etapa retornou para tratamento.")
        self.assertContains(response_etapa_anterior, "Necessita ajustes")

    def test_etapa_retomada_entregue_novamente_reabre_homologacao_em_andamento(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="Ciclo Retorno")
        self._definir_datas_ciclo(entrega)
        self._publicar_entrega(entrega)
        etapa_requisitos, etapa_homologacao = list(entrega.etapas.order_by("ordem")[:2])

        self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_requisitos.pk}),
            {
                "data_etapa": etapa_requisitos.data_etapa.isoformat(),
                "status": EtapaSistema.Status.ENTREGUE,
                "justificativa_status": "Primeira entrega",
                "anexos": [SimpleUploadedFile("requisitos.pdf", b"pdf-requisitos")],
            },
        )
        self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_homologacao.pk}),
            {
                "data_etapa": etapa_homologacao.data_etapa.isoformat(),
                "status": EtapaSistema.Status.REPROVADO,
                "justificativa_status": "Precisa ajustar",
            },
        )

        response_reentrega = self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_requisitos.pk}),
            {
                "data_etapa": etapa_requisitos.data_etapa.isoformat(),
                "status": EtapaSistema.Status.ENTREGUE,
                "justificativa_status": "Segunda entrega após ajustes",
                "anexos": [SimpleUploadedFile("requisitos-ajustados.pdf", b"pdf-requisitos-2")],
            },
        )

        self.assertEqual(response_reentrega.status_code, 302)
        etapa_homologacao.refresh_from_db()
        self.assertEqual(etapa_homologacao.status, EtapaSistema.Status.EM_ANDAMENTO)

        response_ciclo = self.client.get(reverse("acompanhamento_sistemas_entrega_detail", kwargs={"pk": entrega.pk}))
        self.assertContains(response_ciclo, "Em andamento")
        self.assertNotContains(response_ciclo, "<td>Reprovado</td>", html=False)

    def test_marcador_retomada_exibe_contador_quando_houver_nova_reprovacao(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="Ciclo Retorno 2")
        self._definir_datas_ciclo(entrega)
        self._publicar_entrega(entrega)
        etapa_requisitos, etapa_homologacao = list(entrega.etapas.order_by("ordem")[:2])

        for indice in range(2):
            self.client.post(
                reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_requisitos.pk}),
                {
                    "data_etapa": etapa_requisitos.data_etapa.isoformat(),
                    "status": EtapaSistema.Status.ENTREGUE,
                    "justificativa_status": f"Entrega {indice + 1}",
                    "anexos": [SimpleUploadedFile(f"requisitos-{indice + 1}.pdf", b"pdf-requisitos")],
                },
            )
            self.client.post(
                reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_homologacao.pk}),
                {
                    "data_etapa": etapa_homologacao.data_etapa.isoformat(),
                    "status": EtapaSistema.Status.REPROVADO,
                    "justificativa_status": f"Reprovacao {indice + 1}",
                },
            )
            etapa_requisitos.refresh_from_db()
            etapa_homologacao.refresh_from_db()

        response_ciclo = self.client.get(reverse("acompanhamento_sistemas_entrega_detail", kwargs={"pk": entrega.pk}))

        self.assertContains(response_ciclo, "Retomada (2)")

    @patch("acompanhamento_sistemas.services.EmailMessage.send", return_value=1)
    def test_anotacao_livre_aceita_multiplos_anexos(self, mock_send):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
        self._definir_datas_ciclo(entrega)
        self._publicar_entrega(entrega)
        etapa = sistema.entregas.get().etapas.order_by("ordem").first()
        InteressadoSistemaManual.objects.create(
            sistema=sistema,
            tipo_interessado="DEV",
            nome="Dev",
            email="dev@exemplo.gov.br",
            criado_por=self.user,
        )

        response = self.client.post(
            reverse("acompanhamento_sistemas_etapa_nota", kwargs={"pk": etapa.pk}),
            {
                "texto_nota": "Nota com anexos",
                "anexos": [
                    SimpleUploadedFile("um.txt", b"conteudo-1"),
                    SimpleUploadedFile("dois.txt", b"conteudo-2"),
                ],
            },
        )

        self.assertEqual(response.status_code, 302)
        historico = etapa.historicos.first()
        self.assertEqual(historico.tipo_evento, HistoricoEtapaSistema.TipoEvento.NOTA)
        self.assertEqual(historico.anexos.count(), 2)
        self.assertEqual(mock_send.call_count, 1)

    @patch("acompanhamento_sistemas.services.EmailMessage.send", return_value=1)
    def test_anotacao_do_sistema_aceita_multiplos_anexos_e_notifica_interessados(self, mock_send):
        sistema = self._criar_sistema()
        InteressadoSistemaManual.objects.create(
            sistema=sistema,
            tipo_interessado="GESTAO",
            nome="Gestora",
            email="gestora@exemplo.gov.br",
            criado_por=self.user,
        )

        response = self.client.post(
            reverse("acompanhamento_sistemas_nota", kwargs={"pk": sistema.pk}),
            {
                "texto_nota": "Anotação geral do sistema",
                "anexos": [
                    SimpleUploadedFile("um.txt", b"conteudo-1"),
                    SimpleUploadedFile("dois.txt", b"conteudo-2"),
                ],
            },
        )

        self.assertEqual(response.status_code, 302)
        historico = sistema.historicos_sistema.first()
        self.assertIsNotNone(historico)
        self.assertEqual(historico.tipo_evento, HistoricoSistema.TipoEvento.NOTA)
        self.assertEqual(historico.anexos.count(), 2)
        self.assertEqual(mock_send.call_count, 1)

    def test_recalcula_tempo_entre_etapas(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
        self._definir_datas_ciclo(entrega)
        etapa_1, etapa_2 = list(entrega.etapas.order_by("ordem")[:2])

        response = self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_2.pk}),
            {
                "data_etapa": (etapa_1.data_etapa + timedelta(days=4)).isoformat(),
                "status": etapa_2.status,
                "justificativa_status": "",
                "texto_nota": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        etapa_2.refresh_from_db()
        self.assertEqual(etapa_2.tempo_desde_etapa_anterior_em_dias, 4)

    def test_expira_em_texto_cobre_futuro_hoje_e_passado(self):
        sistema = self._criar_sistema()
        self._criar_entrega(sistema)
        etapa = sistema.entregas.get().etapas.order_by("ordem").first()
        etapa.data_etapa = timezone.localdate() + timedelta(days=2)
        self.assertEqual(etapa.expira_em_texto, "Expira em 2 dia(s)")
        self.assertEqual(etapa.prazo_marcador, {"label": "Atenção", "classe": "atencao"})
        etapa.data_etapa = timezone.localdate() + timedelta(days=4)
        self.assertEqual(etapa.prazo_marcador, {"label": "Em dia", "classe": "em_dia"})
        etapa.data_etapa = timezone.localdate()
        self.assertEqual(etapa.expira_em_texto, "Expira hoje")
        self.assertEqual(etapa.prazo_marcador, {"label": "Atenção", "classe": "atencao"})
        etapa.data_etapa = timezone.localdate() - timedelta(days=3)
        self.assertEqual(etapa.expira_em_texto, "Expirou ha 3 dia(s)")
        self.assertEqual(etapa.prazo_marcador, {"label": "Atrasado", "classe": "atrasado"})

    def test_inclusao_de_interessado_por_usuario_salva_snapshot(self):
        sistema = self._criar_sistema()

        response = self.client.post(
            reverse("acompanhamento_sistemas_interessado_add", kwargs={"pk": sistema.pk}),
            {
                "usuario": str(self.outro.pk),
                "tipo_interessado": "NEGOCIO",
                "nome_manual": "",
                "email_manual": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        interessado = InteressadoSistema.objects.get(sistema=sistema, usuario=self.outro)
        self.assertEqual(interessado.nome_snapshot, "Outro")
        self.assertEqual(interessado.email_snapshot, "outro@exemplo.gov.br")

    def test_formulario_de_interessado_oculta_usuarios_tecnicos(self):
        tecnico = get_user_model().objects.create_user(
            username="tmp-email-check",
            password="senha-123",
            email="tmp-email-check@exemplo.gov.br",
            first_name="Tmp",
        )
        sistema = self._criar_sistema()

        response = self.client.get(reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "tmp-email-check")
        self.assertNotContains(response, f'value="{tecnico.pk}"')

    def test_inclusao_de_interessado_manual_salva_nome_e_email(self):
        sistema = self._criar_sistema()

        response = self.client.post(
            reverse("acompanhamento_sistemas_interessado_add", kwargs={"pk": sistema.pk}),
            {
                "usuario": "",
                "tipo_interessado": "GESTAO",
                "nome_manual": "Pessoa Externa",
                "email_manual": "externa@exemplo.gov.br",
            },
        )

        self.assertEqual(response.status_code, 302)
        manual = InteressadoSistemaManual.objects.get(sistema=sistema, email="externa@exemplo.gov.br")
        self.assertEqual(manual.nome, "Pessoa Externa")

    @patch("acompanhamento_sistemas.services.EmailMessage.send", return_value=1)
    def test_remover_interessado_impede_novo_envio(self, mock_send):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
        self._definir_datas_ciclo(entrega)
        self._publicar_entrega(entrega)
        etapa = sistema.entregas.get().etapas.order_by("ordem").first()
        manual = InteressadoSistemaManual.objects.create(
            sistema=sistema,
            tipo_interessado="DEV",
            nome="Dev Externo",
            email="dev.ext@exemplo.gov.br",
            criado_por=self.user,
        )
        self.client.post(
            reverse("acompanhamento_sistemas_interessado_remove", kwargs={"pk": sistema.pk, "interessado_pk": manual.pk})
        )

        response = self.client.post(
            reverse("acompanhamento_sistemas_etapa_nota", kwargs={"pk": etapa.pk}),
            {"texto_nota": "Sem destinatários após remoção"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(mock_send.call_count, 0)

    def test_usuario_com_view_acessa_e_sem_change_nao_atualiza(self):
        sistema = self._criar_sistema()
        self._criar_entrega(sistema)
        etapa = sistema.entregas.get().etapas.order_by("ordem").first()

        self.client.force_login(self.viewer)
        response_get = self.client.get(reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa.pk}))
        response_post = self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa.pk}),
            {
                "data_etapa": "",
                "status": EtapaSistema.Status.EM_ANDAMENTO,
                "justificativa_status": "Teste",
                "texto_nota": "",
            },
        )

        self.assertEqual(response_get.status_code, 200)
        self.assertEqual(response_post.status_code, 404)

    def test_interessado_interno_ganha_leitura_restrita_ao_proprio_sistema(self):
        sistema_visivel = self._criar_sistema(nome="Sistema Interessado")
        sistema_oculto = self._criar_sistema(nome="Sistema Restrito")
        entrega = self._criar_entrega(sistema_visivel, titulo="Ciclo Interessado")
        self._criar_entrega(sistema_oculto, titulo="Ciclo Restrito")
        etapa = entrega.etapas.order_by("ordem").first()
        InteressadoSistema.objects.create(
            sistema=sistema_visivel,
            usuario=self.outro,
            tipo_interessado="GESTAO",
            nome_snapshot="Outro",
            email_snapshot="outro@exemplo.gov.br",
            criado_por=self.user,
        )

        self.client.force_login(self.outro)

        response_list = self.client.get(reverse("acompanhamento_sistemas_list"))
        response_detail = self.client.get(reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema_visivel.pk}))
        response_entrega = self.client.get(reverse("acompanhamento_sistemas_entrega_detail", kwargs={"pk": entrega.pk}))
        response_etapa = self.client.get(reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa.pk}))
        response_oculto = self.client.get(reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema_oculto.pk}))

        self.assertEqual(response_list.status_code, 200)
        self.assertContains(response_list, "Sistema Interessado")
        self.assertNotContains(response_list, "Sistema Restrito")
        self.assertEqual(response_detail.status_code, 200)
        self.assertEqual(response_entrega.status_code, 200)
        self.assertEqual(response_etapa.status_code, 200)
        self.assertEqual(response_oculto.status_code, 404)

    def test_filtros_da_listagem_funcionam_por_nome_status_e_responsavel(self):
        sistema_a = self._criar_sistema(nome="Sistema Alfa")
        sistema_b = self._criar_sistema(nome="Sistema Beta")
        self._criar_entrega(sistema_a, titulo="Entrega Alfa")
        self._criar_entrega(sistema_b, titulo="Entrega Beta")
        etapa_a = sistema_a.entregas.get().etapas.order_by("ordem").first()
        etapa_b = sistema_b.entregas.get().etapas.order_by("ordem").first()

        self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_a.pk}),
            {
                "data_etapa": "",
                "status": EtapaSistema.Status.EM_ANDAMENTO,
                "justificativa_status": "Fluxo alfa",
                "texto_nota": "",
            },
        )
        self.client.force_login(self.outro)
        self._grant_perms(
            self.outro,
            ["view_sistema", "view_entregasistema", "view_etapasistema", "change_etapasistema"],
        )
        self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa_b.pk}),
            {
                "data_etapa": "",
                "status": EtapaSistema.Status.EM_ANDAMENTO,
                "justificativa_status": "Fluxo beta",
                "texto_nota": "",
            },
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("acompanhamento_sistemas_list"),
            {
                "q": "Alfa",
                "status": EtapaSistema.Status.EM_ANDAMENTO,
                "responsavel": str(self.user.pk),
            },
        )

        self.assertContains(response, "Sistema Alfa")
        self.assertNotContains(response, "Sistema Beta")
        self.assertContains(response, "Evolução do Sistema")

    def test_listagem_exibe_lead_time_e_ultima_acao_no_rodape(self):
        sistema = self._criar_sistema(nome="Sistema Lead Time")
        self._criar_entrega(sistema, titulo="Sprint 01")
        Sistema.objects.filter(pk=sistema.pk).update(criado_em=timezone.now() - timedelta(days=3))
        sistema.refresh_from_db()

        response = self.client.get(reverse("acompanhamento_sistemas_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tempo de atendimento")
        self.assertContains(response, "3 dias")
        self.assertContains(response, "Última ação em")
        self.assertContains(response, "acompanhamento-card-footer")
        self.assertContains(response, "Sistemas visíveis")
        self.assertContains(response, "Aguardando homologação")

    def test_tela_da_etapa_renderiza_duas_colunas(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
        self._definir_datas_ciclo(entrega)
        etapa = sistema.entregas.get().etapas.order_by("ordem").first()

        response = self.client.get(reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "acompanhamento-detail-grid")
        self.assertContains(response, "Timeline da etapa -")
        self.assertContains(response, "Lançar nota")
        self.assertNotContains(response, "Anotação da etapa")
        self.assertContains(response, f'value="{etapa.data_etapa.isoformat()}"', html=False)
        self.assertContains(response, "Em rascunho, ela pode ficar em branco até a publicação do ciclo.")
        self.assertNotContains(response, "Calendário")
        self.assertContains(response, "Selecionar data da etapa")

    def test_api_do_calendario_retorna_etapas_de_todos_os_sistemas_com_ciclo_e_status(self):
        sistema_a = self._criar_sistema(nome="Sistema Alfa")
        sistema_b = self._criar_sistema(nome="Sistema Beta")
        ciclo_a = self._criar_entrega(sistema_a, titulo="Sprint 01")
        self._criar_entrega(sistema_a, titulo="Sprint 02")
        ciclo_b = self._criar_entrega(sistema_b, titulo="Sprint 03")
        self._definir_datas_ciclo(ciclo_a)
        self._definir_datas_ciclo(ciclo_b)
        etapa_a = ciclo_a.etapas.order_by("ordem").first()
        etapa_b = ciclo_b.etapas.order_by("ordem").first()
        etapa_b.status = EtapaSistema.Status.EM_ANDAMENTO
        etapa_b.save(update_fields=["status", "atualizado_em"])

        response = self.client.get(
            reverse("acompanhamento_sistemas_etapa_calendario"),
            {"ano": etapa_a.data_etapa.year, "mes": etapa_a.data_etapa.month},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("results", payload)
        self.assertTrue(any(item["sistema"] == "Sistema Alfa" and item["ciclo"] == "1/2 Sprint 01" for item in payload["results"]))
        self.assertTrue(any(item["sistema"] == "Sistema Beta" and item["ciclo"] == "1/1 Sprint 03" for item in payload["results"]))
        self.assertTrue(any(item["etapa"] == etapa_a.get_tipo_etapa_display() for item in payload["results"]))
        self.assertTrue(any(item["status"] == EtapaSistema.Status.EM_ANDAMENTO for item in payload["results"]))
        self.assertTrue(any(item["url"] == reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa_b.pk}) for item in payload["results"]))

    def test_timeline_da_etapa_exibe_apenas_historico_da_propria_etapa(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="Sprint 02")
        etapas = list(entrega.etapas.order_by("ordem")[:2])
        etapa_atual, outra_etapa = etapas

        self.client.post(
            reverse("acompanhamento_sistemas_etapa_nota", kwargs={"pk": outra_etapa.pk}),
            {"texto_nota": "Evento em outra etapa"},
        )

        response = self.client.get(reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa_atual.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Timeline da etapa -")
        self.assertContains(response, etapa_atual.get_tipo_etapa_display())
        self.assertContains(response, "Etapa criada automaticamente na abertura do ciclo.")
        self.assertNotContains(response, "Ciclo Sprint 02 criado.")
        self.assertNotContains(response, "Evento em outra etapa")
        self.assertNotContains(response, outra_etapa.get_tipo_etapa_display())
        self.assertNotContains(response, "Interessados do sistema")
        self.assertNotContains(response, "Adicionar interessado")
        self.assertNotContains(response, "Auditoria complementar do sistema")

    def test_timeline_consolidada_do_sistema_e_paginada_em_seis_eventos(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="Sprint 01")
        etapa = entrega.etapas.order_by("ordem").first()
        for indice in range(7):
            self.client.post(
                reverse("acompanhamento_sistemas_etapa_nota", kwargs={"pk": etapa.pk}),
                {"texto_nota": f"Nota {indice + 1}"},
            )

        response_pagina_1 = self.client.get(reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema.pk}))
        response_pagina_2 = self.client.get(
            reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema.pk}),
            {"pagina_timeline": 2},
        )

        self.assertContains(response_pagina_1, "Página 1 de 2")
        self.assertContains(response_pagina_1, "?pagina_timeline=2")
        self.assertContains(response_pagina_1, "Nota 7")
        self.assertNotContains(response_pagina_1, "Nota 1")
        self.assertContains(response_pagina_2, "Página 2 de 2")
        self.assertContains(response_pagina_2, "Nota 1")

    def test_timeline_da_etapa_e_paginada_em_seis_eventos(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="Sprint 01")
        etapa = entrega.etapas.order_by("ordem").first()
        for indice in range(7):
            self.client.post(
                reverse("acompanhamento_sistemas_etapa_nota", kwargs={"pk": etapa.pk}),
                {"texto_nota": f"Evento etapa {indice + 1}"},
            )

        response_pagina_1 = self.client.get(reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa.pk}))
        response_pagina_2 = self.client.get(
            reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa.pk}),
            {"pagina_timeline": 2},
        )

        self.assertContains(response_pagina_1, "Página 1 de 2")
        self.assertContains(response_pagina_1, "?pagina_timeline=2")
        self.assertContains(response_pagina_1, "Evento etapa 7")
        self.assertNotContains(response_pagina_1, "Evento etapa 1")
        self.assertContains(response_pagina_2, "Página 2 de 2")
        self.assertContains(response_pagina_2, "Evento etapa 1")

    def test_detalhe_do_sistema_exibe_timeline_consolidada_e_interessados_na_coluna_esquerda(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="Sprint 01", descricao="Resumo das tarefas que serão feitas na sprint 01")
        self._criar_entrega(sistema, titulo="Sprint 02", descricao="Resumo das tarefas que serão feitas na sprint 02")
        etapa = entrega.etapas.order_by("ordem").first()
        self.client.post(
            reverse("acompanhamento_sistemas_etapa_nota", kwargs={"pk": etapa.pk}),
            {"texto_nota": "Histórico do sistema"},
        )

        response = self.client.get(reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Timeline consolidada do sistema")
        self.assertContains(response, "Lançar nota")
        self.assertContains(response, "Ciclos")
        self.assertContains(response, "Novo Ciclo")
        self.assertNotContains(response, "Titulo:")
        self.assertNotContains(response, "Descricao:")
        self.assertContains(response, "Ciclo Sprint 01 criado.")
        self.assertContains(response, "Ciclo Sprint 01: Criacao")
        self.assertContains(response, "Histórico do sistema")
        self.assertNotContains(response, "Etapa criada automaticamente na abertura do ciclo.")
        self.assertNotContains(response, "Auditoria complementar do sistema")
        self.assertContains(response, 'data-email="outro@exemplo.gov.br"', html=False)
        self.assertContains(response, "Evolução do Sistema")
        self.assertContains(response, "Evolução da Entrega")
        self.assertContains(response, "Evolução do Prazo")
        self.assertContains(response, 'id="acompanhamento-open-interessado-modal"', html=False)
        self.assertContains(response, 'id="acompanhamento-interessado-modal"', html=False)
        self.assertContains(response, 'id="acompanhamento-open-sistema-note-modal"', html=False)
        self.assertContains(response, 'id="acompanhamento-sistema-note-modal"', html=False)
        self.assertContains(response, "Adicionar interessado")
        self.assertContains(response, "Vincular")
        self.assertContains(response, "1/2 Sprint 01")
        self.assertContains(response, "2/2 Sprint 02")
        self.assertContains(response, reverse("acompanhamento_sistemas_entrega_detail", kwargs={"pk": entrega.pk}))
        self.assertNotContains(response, "Tempo entre etapas")

    def test_timeline_consolidada_do_sistema_exibe_anotacao_do_proprio_sistema(self):
        sistema = self._criar_sistema()

        self.client.post(
            reverse("acompanhamento_sistemas_nota", kwargs={"pk": sistema.pk}),
            {"texto_nota": "Nota do sistema"},
        )

        response = self.client.get(reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sistema Portal SEDS: Nota")
        self.assertContains(response, "Nota do sistema")

    def test_detalhe_da_entrega_exibe_tabela_de_etapas(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="Sprint 01", descricao="Resumo das tarefas que serão feitas na sprint 01")
        self._criar_entrega(sistema, titulo="Sprint 02", descricao="Resumo das tarefas que serão feitas na sprint 02")

        response = self.client.get(reverse("acompanhamento_sistemas_entrega_detail", kwargs={"pk": entrega.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1/2 Sprint 01")
        self.assertContains(response, "Resumo do ciclo")
        self.assertContains(response, "Tempo entre etapas")
        self.assertContains(response, "Requisitos")
        self.assertContains(response, "Homologacao de Requisitos")
        self.assertContains(response, "acompanhamento-row--pendente")
        self.assertContains(response, "Resumo visual do fluxo")
        self.assertContains(response, "acompanhamento-stepper")
        self.assertContains(response, reverse("acompanhamento_sistemas_entrega_update", kwargs={"pk": entrega.pk}))
        self.assertContains(response, reverse("acompanhamento_sistemas_entrega_delete", kwargs={"pk": entrega.pk}))
        self.assertContains(response, "Editar ciclo")
        self.assertContains(response, "Excluir ciclo")

    def test_tela_de_edicao_do_ciclo_exibe_botao_de_excluir(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="Sprint 03")

        response = self.client.get(reverse("acompanhamento_sistemas_entrega_update", kwargs={"pk": entrega.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editar ciclo")
        self.assertContains(response, reverse("acompanhamento_sistemas_entrega_delete", kwargs={"pk": entrega.pk}))
        self.assertContains(response, "Excluir ciclo")

    def test_edicao_do_ciclo_aparece_na_timeline_do_sistema(self):
        sistema = self._criar_sistema(nome="Sistema Timeline")
        entrega = self._criar_entrega(sistema, titulo="Sprint Inicial", descricao="Descricao original")

        response_update = self.client.post(
            reverse("acompanhamento_sistemas_entrega_update", kwargs={"pk": entrega.pk}),
            {
                "titulo": "Sprint Planejada",
                "descricao": "Descricao revisada do ciclo",
            },
        )

        self.assertEqual(response_update.status_code, 302)

        response = self.client.get(reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ciclo Sprint Planejada: Edicao")
        self.assertContains(response, "Ciclo renomeado de")
        self.assertContains(response, "Sprint Inicial")
        self.assertContains(response, "Sprint Planejada")
        self.assertContains(response, "Descrição atualizada: Descricao revisada do ciclo")

    def test_exclusao_de_ciclo_remove_registro_e_redireciona_para_sistema(self):
        sistema = self._criar_sistema(nome="Sistema Ciclos")
        entrega = self._criar_entrega(sistema, titulo="Sprint Excluir")

        response = self.client.post(reverse("acompanhamento_sistemas_entrega_delete", kwargs={"pk": entrega.pk}))

        self.assertRedirects(response, reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema.pk}))
        self.assertFalse(sistema.entregas.filter(pk=entrega.pk).exists())

    def test_nome_usuario_exibicao_prioriza_nome_do_ramal(self):
        usuario_fake = SimpleNamespace(
            ramal_perfil=SimpleNamespace(nome_display="JOSE EDUARDO SANTANA MARTINS"),
            get_full_name=lambda: "Nome Auth",
            first_name="Nome",
            username="usuario-auth",
        )

        self.assertEqual(nome_usuario_exibicao(usuario_fake), "JOSE EDUARDO SANTANA MARTINS")

    def test_tela_de_edicao_exibe_botao_de_excluir(self):
        sistema = self._criar_sistema()

        response = self.client.get(reverse("acompanhamento_sistemas_update", kwargs={"pk": sistema.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("acompanhamento_sistemas_delete", kwargs={"pk": sistema.pk}))
        self.assertContains(response, "Excluir sistema")

    def test_exclusao_de_sistema_remove_registro_e_redireciona(self):
        sistema = self._criar_sistema(nome="Sistema Excluir")

        response = self.client.post(reverse("acompanhamento_sistemas_delete", kwargs={"pk": sistema.pk}))

        self.assertRedirects(response, reverse("acompanhamento_sistemas_list"))
        self.assertFalse(Sistema.objects.filter(pk=sistema.pk).exists())
