import io
from pathlib import Path
import tempfile
from unittest.mock import patch
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.urls import reverse_lazy
from django.test import TestCase
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage

from administracao.forms import AtalhoAdministracaoForm
from administracao.models import AtalhoAdministracao, AtalhoServico, SMTPConfiguration
from administracao.views import Feedback
from administracao.views import SMTPConfigView
from administracao.views import SystemBackupDownloadView


class SMTPConfigViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@exemplo.gov.br",
            password="123456",
        )
        self.factory = RequestFactory()

    def test_salvar_configuracao_smtp(self):
        request = self.factory.post(
            "/administracao/configuracoes/smtp/",
            data={
                "host": "smtp.exemplo.gov.br",
                "port": 587,
                "use_tls": "on",
                "use_ssl": "",
                "username": "smtp-user",
                "password": "smtp-pass",
                "from_email": "noreply@exemplo.gov.br",
                "timeout": 15,
                "ativo": "on",
                "save": "1",
            },
        )
        request.user = self.user
        response = SMTPConfigView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SMTPConfiguration.objects.count(), 1)
        config = SMTPConfiguration.objects.first()
        self.assertEqual(config.host, "smtp.exemplo.gov.br")
        self.assertEqual(config.from_email, "noreply@exemplo.gov.br")

    @patch("administracao.views._test_smtp_connection", return_value=Feedback(level="success", message="ok"))
    def test_testar_conexao_smtp(self, mock_test):
        request = self.factory.post(
            "/administracao/configuracoes/smtp/",
            data={
                "host": "smtp.exemplo.gov.br",
                "port": 587,
                "use_tls": "on",
                "use_ssl": "",
                "username": "smtp-user",
                "password": "smtp-pass",
                "from_email": "noreply@exemplo.gov.br",
                "timeout": 15,
                "ativo": "on",
                "test": "1",
            },
        )
        request.user = self.user
        response = SMTPConfigView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ok", response.content)
        mock_test.assert_called_once()


class SystemBackupDownloadViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="backup-admin",
            email="backup@exemplo.gov.br",
            password="123456",
        )
        self.factory = RequestFactory()

    @patch("administracao.views._generate_database_sql_dump", return_value=b"CREATE TABLE teste;")
    @patch("administracao.views._iter_system_backup_sources")
    def test_download_zip_contem_sql_e_arquivos_essenciais(self, mock_sources, _mock_dump):
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_dir = Path(tmp_dir)
            app_dir = temp_dir / "app_teste"
            app_dir.mkdir(parents=True, exist_ok=True)
            root_file = temp_dir / "manage.py"
            app_file = app_dir / "views.py"
            root_file.write_text("print('ok')", encoding="utf-8")
            app_file.write_text("def view(): pass", encoding="utf-8")
            mock_sources.return_value = [root_file, app_dir]

            request = self.factory.get("/administracao/configuracoes/backup-sistema/")
            request.user = self.user

            with patch("administracao.views.settings.BASE_DIR", temp_dir):
                response = SystemBackupDownloadView.as_view()(request)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/zip")

            archive_bytes = b"".join(response.streaming_content)
            with ZipFile(io.BytesIO(archive_bytes)) as zip_file:
                names = set(zip_file.namelist())
                self.assertIn("manage.py", names)
                self.assertIn("app_teste/views.py", names)
                sql_entries = [name for name in names if name.startswith("database/") and name.endswith(".sql")]
                self.assertEqual(len(sql_entries), 1)
                self.assertIn(b"CREATE TABLE teste;", zip_file.read(sql_entries[0]))

    @patch("administracao.views._generate_database_sql_dump", side_effect=FileNotFoundError)
    def test_redireciona_com_erro_quando_dump_falha(self, _mock_dump):
        request = self.factory.get("/administracao/configuracoes/backup-sistema/")
        request.user = self.user
        request.session = self.client.session
        setattr(request, "_messages", FallbackStorage(request))

        response = SystemBackupDownloadView.as_view()(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse_lazy("administracao_configuracoes"))


class HomeAtalhosTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()

    def test_home_renderiza_duas_colunas_sem_bloco_de_noticias(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Administracao")
        self.assertContains(response, "Atalhos")
        self.assertNotContains(response, "Ultimas noticias")

    def test_home_mostra_todas_as_funcionalidades_administrativas_sem_login(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "Auditoria")
        self.assertContains(response, "Noticias")
        self.assertContains(response, "Reserva de Salas")
        self.assertContains(response, "Lousa Digital")
        self.assertContains(response, "data-login-popup")

    def test_home_mostra_apenas_cards_administrativos_cadastrados_e_ativos(self):
        AtalhoAdministracao.objects.filter(
            funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_AUDITORIA
        ).update(ativo=False)
        AtalhoAdministracao.objects.filter(
            funcionalidade=AtalhoAdministracao.FUNCIONALIDADE_CONTRATOS
        ).delete()

        response = self.client.get(reverse("home"))

        self.assertNotContains(response, "Auditoria")
        self.assertNotContains(response, "Contratos")

    def test_home_mostra_fallback_quando_card_administrativo_esta_sem_imagem(self):
        user = self.user_model.objects.create_user(
            username="fallback",
            email="fallback@exemplo.gov.br",
            password="123456",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertContains(response, "servico-card-media-fallback", html=False)

    def test_home_mantem_atalhos_livres_na_coluna_direita(self):
        AtalhoServico.objects.create(
            titulo="Portal Externo",
            imagem=SimpleUploadedFile("atalho.png", b"atalho", content_type="image/png"),
            url_destino="https://example.com",
            ativo=True,
        )

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Portal Externo")
        self.assertContains(response, "https://example.com")

    def test_home_remove_popup_de_login_quando_usuario_esta_autenticado(self):
        user = self.user_model.objects.create_user(
            username="editor",
            email="editor@exemplo.gov.br",
            password="123456",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Administracao")
        self.assertContains(response, "Noticias")
        self.assertNotContains(response, "data-login-popup")

    def test_seed_cria_cards_administrativos_padrao(self):
        funcionalidades = set(
            AtalhoAdministracao.objects.values_list("funcionalidade", flat=True)
        )

        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_CONFIGURACOES, funcionalidades)
        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_NOTICIAS, funcionalidades)
        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_RESERVA_SALAS, funcionalidades)
        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_RAMAIS, funcionalidades)
        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_EMPRESAS, funcionalidades)
        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_PREPOSTOS, funcionalidades)
        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_FOLHA_PONTO, funcionalidades)
        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_SALA_SITUACAO, funcionalidades)


class AtalhoAdministracaoFormTests(TestCase):
    def test_combobox_lista_todos_os_apps_configurados(self):
        form = AtalhoAdministracaoForm()
        values = [choice[0] for choice in form.fields["funcionalidade"].choices if choice[0]]

        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_RAMAIS, values)
        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_EMPRESAS, values)
        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_PREPOSTOS, values)
        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_FOLHA_PONTO, values)
        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_SALA_SITUACAO, values)
        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_ADMINISTRACAO, values)
        self.assertIn(AtalhoAdministracao.FUNCIONALIDADE_SALA_SITUACAO_OLD, values)


class AtalhoAdministracaoListViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="cards-admin",
            email="cards@exemplo.gov.br",
            password="123456",
        )

    def test_lista_admin_mostra_todas_as_funcionalidades_da_home(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("administracao_atalho_administracao_list"))

        self.assertContains(response, "Ramais")
        self.assertContains(response, "Empresas")
        self.assertContains(response, "Prepostos")
        self.assertContains(response, "Folha de Ponto")
        self.assertContains(response, "Sala de Situacao")
        self.assertContains(response, "Editar")
