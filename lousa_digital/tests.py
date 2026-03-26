from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from django.test import RequestFactory
from django.test import TestCase
from django.utils import timezone

from auditoria.models import AuditLog
from administracao.models import SMTPConfiguration
from ramais.models import PessoaRamal
from .forms import EncaminhamentoForm
from .models import Encaminhamento, EventoTimeline, Processo
from .views import (
    CriarEncaminhamentoView,
    ProcessoCreateView,
    ProcessoListView,
    ProcessoUpdateView,
    _arquivar_processos_sem_encaminhamento,
    _processos_visiveis_para_usuario,
)


class EncaminhamentoFormTests(TestCase):
    def test_email_notificacao_opcional(self):
        hoje = timezone.localdate()
        form = EncaminhamentoForm(
            data={
                "destino": "COETIC",
                "prazo_data": (hoje + timedelta(days=1)).isoformat(),
                "email_notificacao": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_email_notificacao_invalido_rejeitado(self):
        hoje = timezone.localdate()
        form = EncaminhamentoForm(
            data={
                "destino": "COETIC",
                "prazo_data": (hoje + timedelta(days=1)).isoformat(),
                "email_notificacao": "invalido",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email_notificacao", form.errors)


class NotificarPrazosLousaCommandTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="tester", password="123456")
        self.processo = Processo.objects.create(
            numero_sei="012.00000001/2026-00",
            assunto="Processo teste",
            caixa_origem="SGC",
            criado_por=user,
            atualizado_por=user,
            status=Processo.Status.EM_ABERTO,
        )
        SMTPConfiguration.objects.create(
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

    @patch("lousa_digital.management.commands.notificar_prazos_lousa.EmailMessage.send", return_value=1)
    def test_envia_apenas_elegiveis_e_marca_notificado(self, mock_send):
        hoje = timezone.localdate()
        elegivel = Encaminhamento.objects.create(
            processo=self.processo,
            destino="Destino A",
            prazo_data=hoje + timedelta(days=2),
            email_notificacao="a@exemplo.gov.br",
        )
        Encaminhamento.objects.create(
            processo=self.processo,
            destino="Sem email",
            prazo_data=hoje + timedelta(days=2),
            email_notificacao="",
        )
        Encaminhamento.objects.create(
            processo=self.processo,
            destino="Fora janela",
            prazo_data=hoje + timedelta(days=4),
            email_notificacao="b@exemplo.gov.br",
        )
        Encaminhamento.objects.create(
            processo=self.processo,
            destino="Devolvido",
            prazo_data=hoje + timedelta(days=1),
            email_notificacao="c@exemplo.gov.br",
            data_conclusao=timezone.now(),
        )
        Encaminhamento.objects.create(
            processo=self.processo,
            destino="Ja notificado",
            prazo_data=hoje + timedelta(days=1),
            email_notificacao="d@exemplo.gov.br",
            notificado_72h_em=timezone.now(),
        )

        call_command("notificar_prazos_lousa")

        elegivel.refresh_from_db()
        self.assertIsNotNone(elegivel.notificado_72h_em)
        self.assertEqual(mock_send.call_count, 1)
        evento = EventoTimeline.objects.get(encaminhamento=elegivel)
        self.assertEqual(evento.tipo, EventoTimeline.Tipo.EMAIL_72H_ENVIADO)
        self.assertIn("Notificação automática de prazo (3 dias) enviada", evento.descricao)

    @patch(
        "lousa_digital.management.commands.notificar_prazos_lousa.EmailMessage.send",
        side_effect=[Exception("erro"), 1],
    )
    def test_continua_processando_quando_um_envio_falha(self, mock_send):
        hoje = timezone.localdate()
        primeiro = Encaminhamento.objects.create(
            processo=self.processo,
            destino="Destino 1",
            prazo_data=hoje + timedelta(days=1),
            email_notificacao="1@exemplo.gov.br",
        )
        segundo = Encaminhamento.objects.create(
            processo=self.processo,
            destino="Destino 2",
            prazo_data=hoje + timedelta(days=1),
            email_notificacao="2@exemplo.gov.br",
        )

        call_command("notificar_prazos_lousa")

        primeiro.refresh_from_db()
        segundo.refresh_from_db()
        self.assertIsNone(primeiro.notificado_72h_em)
        self.assertIsNotNone(segundo.notificado_72h_em)
        self.assertEqual(mock_send.call_count, 2)
        self.assertFalse(EventoTimeline.objects.filter(encaminhamento=primeiro).exists())
        self.assertTrue(
            EventoTimeline.objects.filter(
                encaminhamento=segundo,
                tipo=EventoTimeline.Tipo.EMAIL_72H_ENVIADO,
            ).exists()
        )

    @patch("lousa_digital.management.commands.notificar_prazos_lousa.EmailMessage.send", return_value=1)
    def test_envia_apenas_para_email_do_encaminhamento(self, mock_send):
        hoje = timezone.localdate()
        grupo = Group.objects.create(name="Grupo Lousa")
        self.processo.grupo_insercao = grupo
        self.processo.save(update_fields=["grupo_insercao"])

        user_grupo = get_user_model().objects.create_user(
            username="membro1",
            password="123456",
            first_name="Membro",
            last_name="Um",
            email="membro1@exemplo.gov.br",
        )
        grupo.user_set.add(user_grupo)
        PessoaRamal.objects.create(
            usuario=user_grupo,
            ramal="1234",
            email="membro1@exemplo.gov.br",
            setor="TI",
            cargo="Analista",
        )

        encaminhamento = Encaminhamento.objects.create(
            processo=self.processo,
            destino="Destino A",
            prazo_data=hoje + timedelta(days=3),
            email_notificacao="destino@exemplo.gov.br",
        )

        out = StringIO()
        call_command("notificar_prazos_lousa", stdout=out)

        self.assertEqual(mock_send.call_count, 1)

        encaminhamento.refresh_from_db()
        self.assertIsNotNone(encaminhamento.notificado_72h_em)
        evento = EventoTimeline.objects.get(encaminhamento=encaminhamento)
        self.assertIn("Destinatários:", evento.descricao)
        self.assertIn("destino@exemplo.gov.br", evento.descricao)
        self.assertNotIn("membro1@exemplo.gov.br", evento.descricao)
        self.assertNotIn("ramal", evento.descricao.lower())

        self.assertTrue(
            AuditLog.objects.filter(
                object_repr="Execucao do comando notificar_prazos_lousa",
            ).exists()
        )
        self.assertIn("Email enviado: Processo", out.getvalue())

    @patch("lousa_digital.management.commands.notificar_prazos_lousa.Command._acquire_lock", return_value=False)
    @patch("lousa_digital.management.commands.notificar_prazos_lousa.EmailMessage.send", return_value=1)
    def test_nao_executa_quando_outra_instancia_ja_esta_rodando(self, mock_send, mock_lock):
        hoje = timezone.localdate()
        Encaminhamento.objects.create(
            processo=self.processo,
            destino="Destino bloqueado por lock",
            prazo_data=hoje + timedelta(days=1),
            email_notificacao="lock@exemplo.gov.br",
        )

        out = StringIO()
        call_command("notificar_prazos_lousa", stdout=out)

        self.assertTrue(mock_lock.called)
        self.assertEqual(mock_send.call_count, 0)
        self.assertFalse(EventoTimeline.objects.filter(tipo=EventoTimeline.Tipo.EMAIL_72H_ENVIADO).exists())
        self.assertIn("já está em andamento", out.getvalue())


class CriarEncaminhamentoViewEmailTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_user(username="operador", password="123456")
        self.processo = Processo.objects.create(
            numero_sei="012.00000002/2026-00",
            assunto="Teste encaminhamento imediato",
            caixa_origem="SGC",
            criado_por=self.user,
            atualizado_por=self.user,
            status=Processo.Status.EM_ABERTO,
        )

    @patch("lousa_digital.views.messages.success")
    def test_nao_envia_email_imediato_no_ato_do_encaminhamento(self, mock_success):
        SMTPConfiguration.objects.create(
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
        request = self.factory.post(
            f"/lousa-digital/{self.processo.pk}/encaminhar/",
            data={
                "destino": "DESTINO TESTE",
                "prazo_data": (timezone.localdate() + timedelta(days=1)).isoformat(),
                "email_notificacao": "destino@exemplo.gov.br",
            },
        )
        request.user = self.user

        response = CriarEncaminhamentoView.as_view()(request, pk=self.processo.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Encaminhamento.objects.count(), 1)
        self.assertTrue(mock_success.called)

    @patch("lousa_digital.views.messages.error")
    def test_bloqueia_encaminhamento_para_processo_arquivo_morto(self, mock_error):
        self.processo.arquivo_morto = True
        self.processo.save(update_fields=["arquivo_morto"])

        request = self.factory.post(
            f"/lousa-digital/{self.processo.pk}/encaminhar/",
            data={
                "destino": "DESTINO BLOQUEADO",
                "prazo_data": (timezone.localdate() + timedelta(days=1)).isoformat(),
                "email_notificacao": "destino@exemplo.gov.br",
            },
        )
        request.user = self.user

        response = CriarEncaminhamentoView.as_view()(request, pk=self.processo.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Encaminhamento.objects.count(), 0)
        self.assertTrue(mock_error.called)


class ProcessoUpdateArquivoMortoTimelineTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_user(username="editor", password="123456")
        self.processo = Processo.objects.create(
            numero_sei="012.00000003/2026-00",
            assunto="Teste arquivo morto",
            caixa_origem="SGC",
            criado_por=self.user,
            atualizado_por=self.user,
            status=Processo.Status.EM_ABERTO,
            arquivo_morto=False,
        )

    @patch("lousa_digital.views.messages.success")
    def test_registra_evento_quando_enviado_para_arquivo_morto(self, mock_success):
        request = self.factory.post(
            f"/lousa-digital/{self.processo.pk}/editar/",
            data={
                "numero_sei": self.processo.numero_sei,
                "assunto": self.processo.assunto,
                "link_sei": self.processo.link_sei,
                "caixa_origem": self.processo.caixa_origem,
                "arquivo_morto": "on",
            },
        )
        request.user = self.user

        response = ProcessoUpdateView.as_view()(request, pk=self.processo.pk)
        self.assertEqual(response.status_code, 302)
        self.processo.refresh_from_db()
        self.assertTrue(self.processo.arquivo_morto)
        self.assertTrue(
            EventoTimeline.objects.filter(
                processo=self.processo,
                descricao="Enviado para arquivo morto.",
            ).exists()
        )
        self.assertTrue(mock_success.called)


class ProcessoCreateAbasTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_user(username="criador_aba", password="123456")

    @patch("lousa_digital.views.messages.success")
    def test_cria_processo_com_origem_da_aba(self, mock_success):
        request = self.factory.post(
            reverse("lousa_digital_create"),
            data={
                "numero_sei": "012.00000030/2026-00",
                "assunto": "Cadastro por aba",
                "link_sei": "",
                "caixa_origem": "",
            },
            QUERY_STRING="aba=TCE",
        )
        request.user = self.user

        response = ProcessoCreateView.as_view()(request)

        self.assertEqual(response.status_code, 302)
        processo = Processo.objects.get(numero_sei="012.00000030/2026-00")
        self.assertEqual(processo.caixa_origem, "TCE")
        self.assertTrue(mock_success.called)

    def test_arquiva_automaticamente_processo_com_20_dias_sem_encaminhamento(self):
        processo = Processo.objects.create(
            numero_sei="012.00000003/2026-01",
            assunto="Auto arquivo morto",
            caixa_origem="SGC",
            criado_por=self.user,
            atualizado_por=self.user,
            status=Processo.Status.EM_ABERTO,
            arquivo_morto=False,
        )
        Processo.objects.filter(pk=processo.pk).update(
            criado_em=timezone.now() - timedelta(days=20),
        )

        total = _arquivar_processos_sem_encaminhamento()

        processo.refresh_from_db()
        self.assertEqual(total, 1)
        self.assertTrue(processo.arquivo_morto)
        self.assertTrue(
            EventoTimeline.objects.filter(
                processo=processo,
                descricao="Enviado automaticamente para arquivo morto após 20 dias sem encaminhamento.",
            ).exists()
        )

    def test_nao_arquiva_automaticamente_quando_ha_encaminhamento(self):
        processo = Processo.objects.create(
            numero_sei="012.00000003/2026-02",
            assunto="Nao arquivar",
            caixa_origem="SGC",
            criado_por=self.user,
            atualizado_por=self.user,
            status=Processo.Status.EM_ABERTO,
            arquivo_morto=False,
        )
        Processo.objects.filter(pk=processo.pk).update(
            criado_em=timezone.now() - timedelta(days=25),
        )
        Encaminhamento.objects.create(
            processo=processo,
            destino="DAS",
            prazo_data=timezone.localdate() + timedelta(days=2),
            criado_por=self.user,
        )

        total = _arquivar_processos_sem_encaminhamento()

        processo.refresh_from_db()
        self.assertEqual(total, 0)
        self.assertFalse(processo.arquivo_morto)


class ProcessoListAlertaPrazoTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="viewer", password="123456")
        self.factory = RequestFactory()
        self.processo = Processo.objects.create(
            numero_sei="012.00000004/2026-00",
            assunto="Processo com alerta visual",
            caixa_origem="SGC",
            criado_por=self.user,
            atualizado_por=self.user,
            status=Processo.Status.EM_ABERTO,
        )

    def test_lista_exibe_alerta_quando_prazo_esta_nos_tres_dias_finais(self):
        Encaminhamento.objects.create(
            processo=self.processo,
            destino="DAS",
            prazo_data=timezone.localdate() + timedelta(days=3),
            criado_por=self.user,
        )

        request = self.factory.get(reverse("lousa_digital_list"))
        request.user = self.user
        response = ProcessoListView.as_view()(request)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Faltam 3 dias")
        self.assertContains(response, "lousa-progress-note")

    def test_lista_exibe_alerta_mesmo_quando_prazo_esta_mais_distante(self):
        Encaminhamento.objects.create(
            processo=self.processo,
            destino="DAS",
            prazo_data=timezone.localdate() + timedelta(days=10),
            criado_por=self.user,
        )

        request = self.factory.get(reverse("lousa_digital_list"))
        request.user = self.user
        response = ProcessoListView.as_view()(request)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Faltam 10 dias")
        self.assertContains(response, "lousa-progress-note")


class ProcessoListAbasTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="abas", password="123456")
        self.factory = RequestFactory()
        self.processo_sgc = Processo.objects.create(
            numero_sei="012.00000020/2026-00",
            assunto="Processo SGC",
            caixa_origem="SGC",
            criado_por=self.user,
            atualizado_por=self.user,
        )
        self.processo_cei = Processo.objects.create(
            numero_sei="012.00000021/2026-00",
            assunto="Processo CEI",
            caixa_origem="CEI",
            criado_por=self.user,
            atualizado_por=self.user,
        )
        self.processo_tce = Processo.objects.create(
            numero_sei="012.00000022/2026-00",
            assunto="Processo TCE",
            caixa_origem="TCE",
            criado_por=self.user,
            atualizado_por=self.user,
        )

    def test_lista_filtra_pela_aba_informada(self):
        request = self.factory.get(reverse("lousa_digital_list"), {"aba": "CEI"})
        request.user = self.user
        response = ProcessoListView.as_view()(request)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CEI - 1 processo")
        self.assertContains(response, self.processo_cei.numero_sei)
        self.assertNotContains(response, self.processo_sgc.numero_sei)
        self.assertNotContains(response, self.processo_tce.numero_sei)

    def test_lista_exibe_contadores_das_abas(self):
        request = self.factory.get(reverse("lousa_digital_list"), {"aba": "SGC"})
        request.user = self.user
        response = ProcessoListView.as_view()(request)
        response.render()

        self.assertContains(response, "SGC")
        self.assertContains(response, "(1)")
        self.assertContains(response, "CEI")
        self.assertContains(response, "TCE")


class ProcessoVisibilidadePorGrupoTests(TestCase):
    def setUp(self):
        self.grupo_a = Group.objects.create(name="Grupo A")
        self.grupo_b = Group.objects.create(name="Grupo B")
        self.criador = get_user_model().objects.create_user(username="criador", password="123456")
        self.membro_a = get_user_model().objects.create_user(username="membro_a", password="123456")
        self.outro = get_user_model().objects.create_user(username="outro", password="123456")
        self.criador.groups.add(self.grupo_a)
        self.membro_a.groups.add(self.grupo_a)
        self.outro.groups.add(self.grupo_b)

    def test_membro_do_mesmo_grupo_atual_do_criador_ve_processo(self):
        processo = Processo.objects.create(
            numero_sei="012.10000001/2026-00",
            assunto="Visível por grupo",
            caixa_origem="SGC",
            criado_por=self.criador,
            atualizado_por=self.criador,
            grupo_insercao=self.grupo_a,
            status=Processo.Status.EM_ABERTO,
        )

        visiveis = _processos_visiveis_para_usuario(self.membro_a)
        self.assertIn(processo, visiveis)

    def test_visibilidade_muda_quando_criador_muda_de_grupo(self):
        processo = Processo.objects.create(
            numero_sei="012.10000002/2026-00",
            assunto="Dinâmica por grupo atual",
            caixa_origem="SGC",
            criado_por=self.criador,
            atualizado_por=self.criador,
            grupo_insercao=self.grupo_a,
            status=Processo.Status.EM_ABERTO,
        )
        self.criador.groups.set([self.grupo_b])

        visiveis_membro_a = _processos_visiveis_para_usuario(self.membro_a)
        visiveis_outro = _processos_visiveis_para_usuario(self.outro)
        self.assertNotIn(processo, visiveis_membro_a)
        self.assertIn(processo, visiveis_outro)

    def test_usuario_de_outro_grupo_nao_ve_processo(self):
        processo = Processo.objects.create(
            numero_sei="012.10000003/2026-00",
            assunto="Restrito por grupo",
            caixa_origem="SGC",
            criado_por=self.criador,
            atualizado_por=self.criador,
            grupo_insercao=self.grupo_a,
            status=Processo.Status.EM_ABERTO,
        )

        visiveis = _processos_visiveis_para_usuario(self.outro)
        self.assertNotIn(processo, visiveis)


class ProcessoDashboardViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dash",
            password="123456",
            first_name="Ana",
            last_name="Gestora",
        )
        self.factory = RequestFactory()

        hoje = timezone.localdate()
        self.processo_a = Processo.objects.create(
            numero_sei="012.00000010/2026-00",
            assunto="Processo A",
            caixa_origem="SGC",
            criado_por=self.user,
            atualizado_por=self.user,
            status=Processo.Status.EM_ABERTO,
        )
        self.processo_b = Processo.objects.create(
            numero_sei="012.00000011/2026-00",
            assunto="Processo B",
            caixa_origem="SGC",
            criado_por=self.user,
            atualizado_por=self.user,
            status=Processo.Status.EM_ABERTO,
        )
        self.processo_cei = Processo.objects.create(
            numero_sei="012.00000012/2026-00",
            assunto="Processo CEI",
            caixa_origem="CEI",
            criado_por=self.user,
            atualizado_por=self.user,
            status=Processo.Status.EM_ABERTO,
        )

        enc_critico = Encaminhamento.objects.create(
            processo=self.processo_a,
            destino="DAS",
            prazo_data=hoje + timedelta(days=2),
            criado_por=self.user,
        )
        enc_concluido = Encaminhamento.objects.create(
            processo=self.processo_b,
            destino="SPP",
            prazo_data=hoje + timedelta(days=8),
            criado_por=self.user,
            concluido_por=self.user,
        )
        enc_concluido.data_conclusao = timezone.now()
        enc_concluido.save(update_fields=["data_conclusao", "concluido_por"])

        EventoTimeline.objects.create(
            processo=self.processo_a,
            encaminhamento=enc_critico,
            tipo=EventoTimeline.Tipo.EMAIL_72H_ENVIADO,
            descricao="Alerta enviado.",
            usuario=None,
        )

    def test_dashboard_exibe_metricas_principais(self):
        from .views import ProcessoDashboardView

        request = self.factory.get(reverse("lousa_digital_dashboard"))
        request.user = self.user
        response = ProcessoDashboardView.as_view()(request)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard da Lousa Digital")
        self.assertContains(response, "100,00%")
        self.assertContains(response, "Alertas enviados")
        self.assertContains(response, "Processos por destino atual")
        self.assertContains(response, "Processos com encaminhamento ativo")
        self.assertNotContains(response, "Usuários com maior volume tratado")
        self.assertContains(response, "Evolução diária, sempre dos últimos 30 dias.")
        self.assertContains(response, "grafico-processos-destino-atual")

    def test_dashboard_filtra_metricas_pela_aba_ativa(self):
        from .views import ProcessoDashboardView

        request = self.factory.get(reverse("lousa_digital_dashboard"), {"aba": "CEI"})
        request.user = self.user
        response = ProcessoDashboardView.as_view()(request)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard da Lousa Digital - CEI")
        self.assertEqual(response.context_data["active_aba"], "CEI")
        self.assertEqual(response.context_data["total_processos_monitorados"], 1)
        self.assertEqual(response.context_data["total_processos_com_destino_ativo"], 0)
