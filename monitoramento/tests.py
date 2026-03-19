import importlib.util
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import (
    ConexaoBancoMonitoramento,
    ConsultaDashboardMonitoramento,
    DashboardMonitoramento,
    GraficoDashboardMonitoramento,
    ProjetoMonitoramento,
)
from .services import (
    build_plotly_payload,
    decrypt_secret,
    encrypt_secret,
    extract_sql_parameters,
    filter_rows_for_click,
    validate_read_only_sql,
)


class MonitoramentoServiceTests(TestCase):
    def test_encrypt_secret_roundtrip(self):
        encrypted = encrypt_secret("segredo-123")
        self.assertNotEqual(encrypted, "segredo-123")
        self.assertEqual(decrypt_secret(encrypted), "segredo-123")

    def test_extract_sql_parameters(self):
        params = extract_sql_parameters("SELECT * FROM tabela WHERE data BETWEEN @DataInicio AND @DataFim")
        self.assertEqual(params, ["DataInicio", "DataFim"])

    def test_validate_read_only_sql_rejeita_delete(self):
        with self.assertRaises(Exception):
            validate_read_only_sql("DELETE FROM tabela")

    def test_build_plotly_payload_ordena_linha_por_referencia(self):
        grafico = type(
            "GraficoStub",
            (),
            {
                "titulo": "Teste",
                "campo_x": "referencia",
                "campo_y": "total_familias",
                "campo_serie": "",
                "campo_data": "",
                "tipo_grafico": GraficoDashboardMonitoramento.TIPO_LINHA,
                "get_tipo_grafico_display": lambda self=None: "Linha",
            },
        )()
        payload = build_plotly_payload(
            grafico,
            [
                {"referencia": "2026-02", "total_familias": 376},
                {"referencia": "2025-09", "total_familias": 3},
                {"referencia": "2026-01", "total_familias": 213},
                {"referencia": "2025-12", "total_familias": 184},
            ],
        )
        self.assertEqual(
            payload["traces"][0]["x"],
            ["2025-09", "2025-12", "2026-01", "2026-02"],
        )

    def test_filter_rows_for_click_linha_nao_descarta_resultado_quando_tem_campo_detalhe(self):
        grafico = type(
            "GraficoStub",
            (),
            {
                "tipo_grafico": GraficoDashboardMonitoramento.TIPO_LINHA,
                "campo_x": "referencia",
                "campo_y": "total_familias",
                "campo_serie": "",
                "campo_detalhe": "referencia",
            },
        )()
        rows = [
            {"referencia": "2026-01", "total_familias": 213},
            {"referencia": "2026-02", "total_familias": 376},
        ]
        filtrado = filter_rows_for_click(
            grafico,
            rows,
            clicked_x="2026-02",
            clicked_y="376",
        )
        self.assertEqual(filtrado, [{"referencia": "2026-02", "total_familias": 376}])


class MonitoramentoViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="monitor-admin",
            email="monitor@exemplo.gov.br",
            password="123456",
        )
        self.user = User.objects.create_user(
            username="comum",
            password="123456",
        )
        self.client.force_login(self.admin)
        self.projeto = ProjetoMonitoramento.objects.create(
            nome="Projeto Monitor",
            descricao="Projeto de testes",
            criado_por=self.admin,
        )
        self.conexao = ConexaoBancoMonitoramento.objects.create(
            projeto=self.projeto,
            tipo_banco=ConexaoBancoMonitoramento.TIPO_MYSQL,
            host="127.0.0.1",
            porta=3306,
            database="analytics",
            usuario="root",
            senha_criptografada=encrypt_secret("senha"),
        )

    def test_home_exibe_monitoramento_para_admin(self):
        response = self.client.get(reverse("monitoramento_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Projeto Monitor")

    def test_home_bloqueia_usuario_sem_permissao(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("monitoramento_home"))
        self.assertEqual(response.status_code, 403)

    def test_home_libera_usuario_com_permissao_de_leitura_monitoramento(self):
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="monitoramento",
                codename="view_projetomonitoramento",
            )
        )
        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.client.force_login(self.user)
        response = self.client.get(reverse("monitoramento_home"))
        self.assertEqual(response.status_code, 200)

    @patch("monitoramento.views.test_external_connection")
    def test_testar_conexao_atualiza_status(self, mock_test):
        response = self.client.post(
            reverse("monitoramento_conexao", kwargs={"pk": self.projeto.pk}),
            data={
                "tipo_banco": ConexaoBancoMonitoramento.TIPO_MYSQL,
                "host": "10.0.0.2",
                "porta": 3306,
                "database": "analytics",
                "schema": "",
                "usuario": "root",
                "senha": "segredo",
                "testar": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.conexao.refresh_from_db()
        self.assertEqual(self.conexao.status_ultima_conexao, "ok")
        mock_test.assert_called_once()

    def test_dashboard_create_rejeita_sql_invalido(self):
        response = self.client.post(
            reverse("monitoramento_dashboard_create", kwargs={"pk": self.projeto.pk}),
            data={
                "titulo": "Dashboard inválido",
                "descricao": "",
                "nome": "Consulta inválida",
                "sql_texto": "DELETE FROM tabela_monitorada",
                "tipo_grafico": GraficoDashboardMonitoramento.TIPO_BARRA,
                "campo_x": "categoria",
                "campo_y": "total",
                "save": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "consulta deve iniciar com SELECT ou WITH", status_code=200, html=False)

    @patch("monitoramento.views.execute_monitoring_query")
    def test_dashboard_create_salva_modelos(self, mock_execute):
        mock_execute.return_value = {
            "columns": ["categoria", "total"],
            "rows": [{"categoria": "A", "total": 10}],
        }
        response = self.client.post(
            reverse("monitoramento_dashboard_create", kwargs={"pk": self.projeto.pk}),
            data={
                "titulo": "Painel principal",
                "descricao": "Descrição",
                "nome": "Consulta principal",
                "sql_texto": "SELECT categoria, total FROM tabela WHERE data BETWEEN @DataInicio AND @DataFim",
                "param_type_DataInicio": "date",
                "param_type_DataFim": "date",
                "param_label_DataInicio": "Data inicial",
                "param_label_DataFim": "Data final",
                "DataInicio": "2024-01-01",
                "DataFim": "2024-12-31",
                "tipo_grafico": GraficoDashboardMonitoramento.TIPO_BARRA,
                "campo_x": "categoria",
                "campo_y": "total",
                "save": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        dashboard = DashboardMonitoramento.objects.get()
        consulta = ConsultaDashboardMonitoramento.objects.get()
        grafico = GraficoDashboardMonitoramento.objects.get()
        self.assertEqual(dashboard.titulo, "Painel principal")
        self.assertEqual(consulta.dashboard, dashboard)
        self.assertEqual(grafico.dashboard, dashboard)
        self.assertEqual(len(consulta.parametros_json), 2)

    @patch("monitoramento.views.execute_monitoring_query")
    def test_dashboard_detail_exibe_legendas(self, mock_execute):
        dashboard = DashboardMonitoramento.objects.create(
            projeto=self.projeto,
            titulo="Painel detalhado",
            descricao="Teste",
            criado_por=self.admin,
        )
        consulta = ConsultaDashboardMonitoramento.objects.create(
            dashboard=dashboard,
            nome="Consulta",
            sql_texto="SELECT categoria, total FROM tabela",
            colunas_json=["categoria", "total"],
            parametros_json=[],
        )
        GraficoDashboardMonitoramento.objects.create(
            dashboard=dashboard,
            consulta=consulta,
            titulo="Grafico",
            tipo_grafico=GraficoDashboardMonitoramento.TIPO_BARRA,
            campo_x="categoria",
            campo_y="total",
        )
        mock_execute.return_value = {
            "columns": ["categoria", "total"],
            "rows": [{"categoria": "A", "total": 10}],
        }
        response = self.client.get(reverse("monitoramento_dashboard_detail", kwargs={"pk": dashboard.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Criado por")
        self.assertContains(response, "Última atualização")
        self.assertContains(response, "Editar dashboard")

    @patch("monitoramento.views.execute_monitoring_query")
    def test_dashboard_detail_habilita_periodo_e_subtitulo_em_grafico_temporal(self, mock_execute):
        dashboard = DashboardMonitoramento.objects.create(
            projeto=self.projeto,
            titulo="Painel temporal",
            descricao="Teste",
            criado_por=self.admin,
        )
        consulta = ConsultaDashboardMonitoramento.objects.create(
            dashboard=dashboard,
            nome="Linha temporal",
            sql_texto="""
SELECT referencia, total_registros
FROM periodo
WHERE @Periodo IS NOT NULL
""".strip(),
            colunas_json=["referencia", "total_registros"],
            parametros_json=[
                {"name": "DataInicio", "type": "date", "label": "Data inicial"},
                {"name": "DataFim", "type": "date", "label": "Data final"},
            ],
        )
        GraficoDashboardMonitoramento.objects.create(
            dashboard=dashboard,
            consulta=consulta,
            titulo="Evolução temporal",
            tipo_grafico=GraficoDashboardMonitoramento.TIPO_LINHA,
            campo_x="referencia",
            campo_y="total_registros",
            campo_data="referencia",
            campo_detalhe="data_referencia",
        )
        mock_execute.return_value = {
            "columns": ["referencia", "total_registros"],
            "rows": [{"referencia": "2026-03-10", "total_registros": 8}],
        }
        response = self.client.get(
            reverse("monitoramento_dashboard_detail", kwargs={"pk": dashboard.pk}),
            {"Periodo": "semana"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="Periodo"', html=False)
        self.assertContains(response, "Variável de tempo: data_referencia")
        self.assertEqual(response.context["parameter_values"].get("Periodo"), "semana")

    @patch("monitoramento.views.execute_monitoring_query")
    def test_dashboard_update_salva_alteracoes(self, mock_execute):
        dashboard = DashboardMonitoramento.objects.create(
            projeto=self.projeto,
            titulo="Painel antigo",
            descricao="Antes",
            criado_por=self.admin,
        )
        consulta = ConsultaDashboardMonitoramento.objects.create(
            dashboard=dashboard,
            nome="Consulta antiga",
            sql_texto="SELECT categoria, total FROM tabela",
            colunas_json=["categoria", "total"],
            parametros_json=[],
        )
        grafico = GraficoDashboardMonitoramento.objects.create(
            dashboard=dashboard,
            consulta=consulta,
            titulo="Grafico antigo",
            tipo_grafico=GraficoDashboardMonitoramento.TIPO_BARRA,
            campo_x="categoria",
            campo_y="total",
        )
        mock_execute.return_value = {
            "columns": ["referencia", "total_familias"],
            "rows": [{"referencia": "2026-01", "total_familias": 10}],
        }
        response = self.client.post(
            reverse("monitoramento_dashboard_update", kwargs={"pk": dashboard.pk}),
            data={
                "titulo": "Painel atualizado",
                "descricao": "Depois",
                "nome": "Consulta atualizada",
                "sql_texto": "SELECT referencia, total_familias FROM tabela WHERE data BETWEEN @DataInicio AND @DataFim",
                "param_type_DataInicio": "date",
                "param_type_DataFim": "date",
                "param_label_DataInicio": "Data inicial",
                "param_label_DataFim": "Data final",
                "DataInicio": "2026-01-01",
                "DataFim": "2026-03-31",
                "titulo": "Painel atualizado",
                "tipo_grafico": GraficoDashboardMonitoramento.TIPO_LINHA,
                "campo_x": "referencia",
                "campo_y": "total_familias",
                "campo_serie": "",
                "campo_data": "",
                "campo_detalhe": "",
                "save": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        dashboard.refresh_from_db()
        consulta.refresh_from_db()
        grafico.refresh_from_db()
        self.assertEqual(dashboard.titulo, "Painel atualizado")
        self.assertEqual(consulta.nome, "Consulta atualizada")
        self.assertEqual(grafico.tipo_grafico, GraficoDashboardMonitoramento.TIPO_LINHA)
        self.assertEqual(grafico.campo_x, "referencia")

    def test_dashboard_delete_remove_dashboard_por_completo(self):
        dashboard = DashboardMonitoramento.objects.create(
            projeto=self.projeto,
            titulo="Painel excluir",
            descricao="Teste",
            criado_por=self.admin,
        )
        consulta = ConsultaDashboardMonitoramento.objects.create(
            dashboard=dashboard,
            nome="Consulta excluir",
            sql_texto="SELECT categoria, total FROM tabela",
            colunas_json=["categoria", "total"],
            parametros_json=[],
        )
        grafico = GraficoDashboardMonitoramento.objects.create(
            dashboard=dashboard,
            consulta=consulta,
            titulo="Grafico excluir",
            tipo_grafico=GraficoDashboardMonitoramento.TIPO_BARRA,
            campo_x="categoria",
            campo_y="total",
        )

        response = self.client.post(
            reverse("monitoramento_dashboard_delete", kwargs={"pk": dashboard.pk}),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(GraficoDashboardMonitoramento.objects.filter(pk=grafico.pk).exists())
        self.assertFalse(ConsultaDashboardMonitoramento.objects.filter(pk=consulta.pk).exists())
        self.assertFalse(DashboardMonitoramento.objects.filter(pk=dashboard.pk).exists())

    @patch("monitoramento.views.execute_monitoring_query")
    def test_exportar_grafico_gera_xlsx(self, mock_execute):
        if importlib.util.find_spec("openpyxl") is None:
            self.skipTest("openpyxl não instalado no ambiente.")
        dashboard = DashboardMonitoramento.objects.create(
            projeto=self.projeto,
            titulo="Painel export",
            descricao="Teste",
            criado_por=self.admin,
        )
        consulta = ConsultaDashboardMonitoramento.objects.create(
            dashboard=dashboard,
            nome="Consulta",
            sql_texto="SELECT categoria, total FROM tabela",
            colunas_json=["categoria", "total"],
            parametros_json=[],
        )
        grafico = GraficoDashboardMonitoramento.objects.create(
            dashboard=dashboard,
            consulta=consulta,
            titulo="Grafico",
            tipo_grafico=GraficoDashboardMonitoramento.TIPO_BARRA,
            campo_x="categoria",
            campo_y="total",
        )
        mock_execute.return_value = {
            "columns": ["categoria", "total"],
            "rows": [
                {"categoria": "A", "total": 10},
                {"categoria": "B", "total": 20},
            ],
        }
        response = self.client.get(
            reverse("monitoramento_grafico_exportar", kwargs={"pk": grafico.pk}),
            {"clicked_x": "A"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            response["Content-Type"],
        )
        self.assertIn(".xlsx", response["Content-Disposition"])
