import shutil
import tempfile
from datetime import timedelta
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

from .models import (
    EtapaSistema,
    HistoricoEtapaSistema,
    InteressadoSistema,
    InteressadoSistemaManual,
    Sistema,
)
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

    def test_criacao_de_sistema_nao_gera_entrega_automatica(self):
        sistema = self._criar_sistema()

        self.assertEqual(sistema.entregas.count(), 0)

    def test_criacao_manual_de_entrega_gera_cinco_etapas(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="MVP", descricao="Primeira entrega")

        self.assertEqual(sistema.entregas.count(), 1)
        self.assertEqual(entrega.titulo, "MVP")
        self.assertEqual(entrega.etapas.count(), 5)
        self.assertEqual(
            list(entrega.etapas.order_by("ordem").values_list("status", flat=True)),
            [EtapaSistema.Status.PENDENTE] * 5,
        )
        self.assertEqual(
            list(entrega.etapas.order_by("ordem").values_list("data_etapa", flat=True)),
            [timezone.localdate()] * 5,
        )

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

    def test_alteracao_de_status_sem_justificativa_falha(self):
        sistema = self._criar_sistema()
        self._criar_entrega(sistema)
        etapa = sistema.entregas.get().etapas.order_by("ordem").first()

        response = self.client.post(
            reverse("acompanhamento_sistemas_etapa_update", kwargs={"pk": etapa.pk}),
            {
                "data_etapa": etapa.data_etapa.isoformat(),
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
                "data_etapa": etapa.data_etapa.isoformat(),
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
        self._criar_entrega(sistema)
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
        self.assertTrue(
            AuditLog.objects.filter(
                content_type__app_label="acompanhamento_sistemas",
                object_id=str(etapa.pk),
            ).exists()
        )
        self.assertEqual(mock_send.call_count, 1)

    def test_etapa_entregue_avanca_proxima_para_em_andamento_e_grava_historico(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
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
        self.assertContains(
            self.client.get(reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa_atual.pk})),
            "Status alterado automaticamente de Pendente para Em andamento apos conclusao da etapa anterior.",
        )

    @patch("acompanhamento_sistemas.services.EmailMessage.send", return_value=1)
    def test_anotacao_livre_aceita_multiplos_anexos(self, mock_send):
        sistema = self._criar_sistema()
        self._criar_entrega(sistema)
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

    def test_recalcula_tempo_entre_etapas(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema)
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
        etapa.data_etapa = timezone.localdate()
        self.assertEqual(etapa.expira_em_texto, "Expira hoje")
        etapa.data_etapa = timezone.localdate() - timedelta(days=3)
        self.assertEqual(etapa.expira_em_texto, "Expirou ha 3 dia(s)")

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
        self._criar_entrega(sistema)
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
                "data_etapa": etapa.data_etapa.isoformat(),
                "status": EtapaSistema.Status.EM_ANDAMENTO,
                "justificativa_status": "Teste",
                "texto_nota": "",
            },
        )

        self.assertEqual(response_get.status_code, 200)
        self.assertEqual(response_post.status_code, 404)

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
                "data_etapa": etapa_a.data_etapa.isoformat(),
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
                "data_etapa": etapa_b.data_etapa.isoformat(),
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

    def test_tela_da_etapa_renderiza_duas_colunas(self):
        sistema = self._criar_sistema()
        self._criar_entrega(sistema)
        etapa = sistema.entregas.get().etapas.order_by("ordem").first()

        response = self.client.get(reverse("acompanhamento_sistemas_etapa_detail", kwargs={"pk": etapa.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "acompanhamento-detail-grid")
        self.assertContains(response, "Timeline consolidada do sistema")
        self.assertContains(response, "Lançar nota")
        self.assertNotContains(response, "Anotação da etapa")
        self.assertContains(response, f'value="{etapa.data_etapa.isoformat()}"', html=False)
        self.assertContains(response, "A data já vem preenchida com o valor cadastrado.")

    def test_timeline_da_etapa_exibe_historico_consolidado_do_sistema(self):
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
        self.assertContains(response, "Ciclo Sprint 02 criado.")
        self.assertContains(response, "Ciclo Sprint 02: Criacao")
        self.assertContains(response, "Evento em outra etapa")
        self.assertNotContains(response, "Etapa criada automaticamente na abertura da entrega.")
        self.assertContains(response, outra_etapa.get_tipo_etapa_display())
        self.assertNotContains(response, "Interessados do sistema")
        self.assertNotContains(response, "Adicionar interessado")
        self.assertNotContains(response, "Auditoria complementar do sistema")

    def test_detalhe_do_sistema_exibe_timeline_consolidada_e_interessados_na_coluna_esquerda(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="Sprint 01", descricao="Resumo das tarefas que serão feitas na sprint 01")
        etapa = entrega.etapas.order_by("ordem").first()
        self.client.post(
            reverse("acompanhamento_sistemas_etapa_nota", kwargs={"pk": etapa.pk}),
            {"texto_nota": "Histórico do sistema"},
        )

        response = self.client.get(reverse("acompanhamento_sistemas_detail", kwargs={"pk": sistema.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Timeline consolidada do sistema")
        self.assertContains(response, "Ciclos")
        self.assertContains(response, "Novo Ciclo")
        self.assertNotContains(response, "Titulo:")
        self.assertNotContains(response, "Descricao:")
        self.assertContains(response, "Ciclo Sprint 01 criado.")
        self.assertContains(response, "Ciclo Sprint 01: Criacao")
        self.assertContains(response, "Histórico do sistema")
        self.assertNotContains(response, "Etapa criada automaticamente na abertura da entrega.")
        self.assertNotContains(response, "Auditoria complementar do sistema")
        self.assertContains(response, 'data-email="outro@exemplo.gov.br"', html=False)
        self.assertContains(response, "Evolução do Sistema")
        self.assertContains(response, "Evolução da Entrega")
        self.assertContains(response, reverse("acompanhamento_sistemas_entrega_detail", kwargs={"pk": entrega.pk}))
        self.assertNotContains(response, "Tempo entre etapas")

    def test_detalhe_da_entrega_exibe_tabela_de_etapas(self):
        sistema = self._criar_sistema()
        entrega = self._criar_entrega(sistema, titulo="Sprint 01", descricao="Resumo das tarefas que serão feitas na sprint 01")

        response = self.client.get(reverse("acompanhamento_sistemas_entrega_detail", kwargs={"pk": entrega.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resumo do ciclo")
        self.assertContains(response, "Tempo entre etapas")
        self.assertContains(response, "Requisitos")
        self.assertContains(response, "Homologacao de Requisitos")
        self.assertContains(response, "acompanhamento-row--pendente")
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
