import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import resolve, reverse

from usuarios.models import SetorNode, UserSetorMembership

from .access import (
    user_can_delete_processo,
    user_can_manage_entrega,
    user_can_manage_indicador,
    user_can_manage_processo,
)
from .forms import EntregaForm, EntregaMonitoramentoForm, IndicadorForm, ProcessoForm
from .models import Entrega, Indicador, IndicadorCicloValor, Processo


class SalaSituacaoV2AccessTests(TestCase):
    def setUp(self):
        self.password = "senha-forte-123"
        self.parent_user = User.objects.create_user(username="parent", password=self.password)
        self.child_user = User.objects.create_user(username="child", password=self.password)
        self.outsider_user = User.objects.create_user(username="outsider", password=self.password)

        self.group_parent = Group.objects.create(name="Grupo Pai V2")
        self.group_child = Group.objects.create(name="Grupo Filho V2")
        self.child_user.groups.add(self.group_child)

        setor_parent = SetorNode.objects.create(group=self.group_parent)
        SetorNode.objects.create(group=self.group_child, parent=setor_parent)
        UserSetorMembership.objects.create(user=self.parent_user, setor=setor_parent)

        self.indicador = Indicador.objects.create(nome="Indicador V2")
        self.indicador.grupos_responsaveis.set([self.group_child])
        self.processo = Processo.objects.create(nome="Processo V2")
        self.processo.grupos_responsaveis.set([self.group_child])
        self.processo.indicadores.set([self.indicador])
        self.entrega = Entrega.objects.create(nome="Entrega V2")
        self.entrega.grupos_responsaveis.set([self.group_child])
        self.entrega.processos.set([self.processo])

        for codename in ("view_indicador", "view_processo", "view_entrega", "change_processo"):
            perm = Permission.objects.get(codename=codename, content_type__app_label="sala_situacao_v2")
            self.parent_user.user_permissions.add(perm)
            self.outsider_user.user_permissions.add(perm)

    def test_cutover_routes_points_to_v2(self):
        match = resolve("/sala-de-situacao/")
        self.assertEqual(match.url_name, "sala_situacao_home")
        self.assertIn("sala_situacao_v2", match._func_path)

    def test_authenticated_user_reads_all_items(self):
        self.client.login(username=self.outsider_user.username, password=self.password)
        response_ind = self.client.get(reverse("sala_indicador_estrategico_list"))
        response_proc = self.client.get(reverse("sala_processo_list"))
        response_ent = self.client.get(reverse("sala_entrega_list"))

        self.assertEqual(response_ind.status_code, 200)
        self.assertEqual(response_proc.status_code, 200)
        self.assertEqual(response_ent.status_code, 200)
        self.assertContains(response_ind, self.indicador.nome)
        self.assertContains(response_proc, self.processo.nome)
        self.assertContains(response_ent, self.entrega.nome)

    def test_parent_sector_can_edit_item(self):
        self.client.login(username=self.parent_user.username, password=self.password)
        response = self.client.get(reverse("sala_processo_update", kwargs={"pk": self.processo.pk}))
        self.assertEqual(response.status_code, 200)

    def test_outsider_with_permission_cannot_edit(self):
        self.client.login(username=self.outsider_user.username, password=self.password)
        response = self.client.get(reverse("sala_processo_update", kwargs={"pk": self.processo.pk}))
        self.assertEqual(response.status_code, 403)


class SalaSituacaoV2MarcadoresTests(TestCase):
    def setUp(self):
        self.group_a = Group.objects.create(name="Setor A")
        self.group_b = Group.objects.create(name="Setor B")

        self.indicador = Indicador.objects.create(nome="Indicador M")
        self.indicador.grupos_responsaveis.set([self.group_a])

        self.processo = Processo.objects.create(nome="Processo M")
        self.processo.indicadores.set([self.indicador])
        self.processo.grupos_responsaveis.set([self.group_b])

        self.entrega = Entrega.objects.create(nome="Entrega M")
        self.entrega.processos.set([self.processo])

    def test_item_cria_marcador_automatico_por_setor_responsavel(self):
        nomes = {marcador.nome for marcador in self.indicador.marcadores_locais}
        self.assertIn(self.group_a.name, nomes)

    def test_processo_herda_marcador_de_indicador(self):
        nomes = {marcador.nome for marcador in self.processo.marcadores_efetivos}
        self.assertIn(self.group_a.name, nomes)
        self.assertIn(self.group_b.name, nomes)

    def test_entrega_herda_marcadores_de_processo_e_indicador(self):
        nomes = {marcador.nome for marcador in self.entrega.marcadores_efetivos}
        self.assertIn(self.group_a.name, nomes)
        self.assertIn(self.group_b.name, nomes)


class SalaSituacaoV2HierarquiaDatasTests(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name="Setor Datas V2")

    def test_processo_nao_pode_ter_data_apos_indicador(self):
        indicador = Indicador.objects.create(
            nome="Indicador Pai",
            data_entrega_estipulada="2026-03-20",
        )
        form = ProcessoForm(
            data={
                "nome": "Processo Filho",
                "descricao": "",
                "data_entrega_estipulada": "2026-03-21",
                "evolucao_manual": "0",
                "grupos_responsaveis": [self.group.id],
                "indicadores": [indicador.id],
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("data_entrega_estipulada", form.errors)

    def test_entrega_nao_pode_ter_data_apos_processo(self):
        processo = Processo.objects.create(
            nome="Processo Pai",
            data_entrega_estipulada="2026-03-20",
        )
        form = EntregaForm(
            data={
                "nome": "Entrega Filha",
                "descricao": "",
                "data_entrega_estipulada": "2026-03-21",
                "evolucao_manual": "0",
                "grupos_responsaveis": [self.group.id],
                "processos": [processo.id],
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("data_entrega_estipulada", form.errors)

    def test_data_valida_no_limite_superior(self):
        indicador = Indicador.objects.create(
            nome="Indicador Pai Limite",
            data_entrega_estipulada="2026-03-20",
        )
        form = ProcessoForm(
            data={
                "nome": "Processo Ok",
                "descricao": "Descricao teste",
                "data_entrega_estipulada": "2026-03-20",
                "evolucao_manual": "0",
                "grupos_responsaveis": [self.group.id],
                "indicadores": [indicador.id],
            }
        )
        self.assertTrue(form.is_valid())


class SalaSituacaoV2EntregaFormOrderTests(TestCase):
    def test_entrega_form_renderiza_processos_antes_de_grupos_data_e_evolucao(self):
        form = EntregaForm()

        self.assertEqual(
            list(form.fields.keys()),
            [
                "nome",
                "descricao",
                "processos",
                "grupos_responsaveis",
                "data_entrega_estipulada",
                "evolucao_manual",
            ],
        )


class SalaSituacaoV2ProcessoGruposHerdadosTests(TestCase):
    def test_grupos_do_indicador_entram_automaticamente_no_processo(self):
        grupo_herdado = Group.objects.create(name="Setor Herdado")
        grupo_extra = Group.objects.create(name="Setor Extra")
        indicador = Indicador.objects.create(nome="Indicador Setorial")
        indicador.grupos_responsaveis.set([grupo_herdado])

        form = ProcessoForm(
            data={
                "nome": "Processo com heranca",
                "descricao": "Descricao teste",
                "data_entrega_estipulada": "2026-03-20",
                "evolucao_manual": "0",
                "grupos_responsaveis": [grupo_extra.id],
                "indicadores": [indicador.id],
            }
        )
        self.assertTrue(form.is_valid())
        grupos_ids = set(form.cleaned_data["grupos_responsaveis"].values_list("id", flat=True))
        self.assertIn(grupo_herdado.id, grupos_ids)
        self.assertIn(grupo_extra.id, grupos_ids)


class SalaSituacaoV2DeleteProcessoTests(TestCase):
    def test_somente_grupo_criador_pode_excluir(self):
        password = "senha-123"
        grupo_criador = Group.objects.create(name="Criador")
        grupo_outro = Group.objects.create(name="Outro")
        user_criador = User.objects.create_user(username="ucriador", password=password)
        user_outro = User.objects.create_user(username="uoutro", password=password)
        user_criador.groups.add(grupo_criador)
        user_outro.groups.add(grupo_outro)

        setor_criador = SetorNode.objects.create(group=grupo_criador)
        setor_outro = SetorNode.objects.create(group=grupo_outro)
        UserSetorMembership.objects.create(user=user_criador, setor=setor_criador)
        UserSetorMembership.objects.create(user=user_outro, setor=setor_outro)

        processo = Processo.objects.create(nome="Proc Excluir")
        processo.grupos_responsaveis.set([grupo_criador, grupo_outro])
        processo.grupos_criadores.set([grupo_criador])

        self.assertTrue(user_can_delete_processo(user_criador, processo))
        self.assertFalse(user_can_delete_processo(user_outro, processo))
        self.assertTrue(user_can_manage_processo(user_criador, processo))
        self.assertFalse(user_can_manage_processo(user_outro, processo))


class SalaSituacaoV2ManageIndicadorTests(TestCase):
    def test_somente_grupo_criador_pode_gerenciar_indicador(self):
        password = "senha-123"
        grupo_criador = Group.objects.create(name="Criador Indicador")
        grupo_outro = Group.objects.create(name="Outro Indicador")
        user_criador = User.objects.create_user(username="uicriador", password=password)
        user_outro = User.objects.create_user(username="uioutro", password=password)
        user_criador.groups.add(grupo_criador)
        user_outro.groups.add(grupo_outro)

        setor_criador = SetorNode.objects.create(group=grupo_criador)
        setor_outro = SetorNode.objects.create(group=grupo_outro)
        UserSetorMembership.objects.create(user=user_criador, setor=setor_criador)
        UserSetorMembership.objects.create(user=user_outro, setor=setor_outro)

        indicador = Indicador.objects.create(nome="Indicador Excluir")
        indicador.grupos_responsaveis.set([grupo_criador, grupo_outro])
        indicador.grupos_criadores.set([grupo_criador])

        self.assertTrue(user_can_manage_indicador(user_criador, indicador))
        self.assertFalse(user_can_manage_indicador(user_outro, indicador))


class SalaSituacaoV2ManageEntregaTests(TestCase):
    def test_somente_grupo_criador_pode_gerenciar_entrega(self):
        password = "senha-123"
        grupo_criador = Group.objects.create(name="Criador Entrega")
        grupo_outro = Group.objects.create(name="Outro Entrega")
        user_criador = User.objects.create_user(username="uecriador", password=password)
        user_outro = User.objects.create_user(username="ueoutro", password=password)
        user_criador.groups.add(grupo_criador)
        user_outro.groups.add(grupo_outro)

        setor_criador = SetorNode.objects.create(group=grupo_criador)
        setor_outro = SetorNode.objects.create(group=grupo_outro)
        UserSetorMembership.objects.create(user=user_criador, setor=setor_criador)
        UserSetorMembership.objects.create(user=user_outro, setor=setor_outro)

        entrega = Entrega.objects.create(nome="Entrega Excluir")
        entrega.grupos_responsaveis.set([grupo_criador, grupo_outro])
        entrega.grupos_criadores.set([grupo_criador])

        self.assertTrue(user_can_manage_entrega(user_criador, entrega))
        self.assertFalse(user_can_manage_entrega(user_outro, entrega))


class SalaSituacaoV2EntregaGruposHerdadosTests(TestCase):
    def test_grupos_do_processo_entram_automaticamente_na_entrega(self):
        grupo_herdado = Group.objects.create(name="Setor Herdado Entrega")
        grupo_extra = Group.objects.create(name="Setor Extra Entrega")
        processo = Processo.objects.create(nome="Processo Herdado Entrega")
        processo.grupos_responsaveis.set([grupo_herdado])

        form = EntregaForm(
            data={
                "nome": "Entrega com heranca",
                "descricao": "Descricao teste",
                "data_entrega_estipulada": "2026-03-20",
                "evolucao_manual": "0",
                "grupos_responsaveis": [grupo_extra.id],
                "processos": [processo.id],
            }
        )
        self.assertTrue(form.is_valid())
        grupos_ids = set(form.cleaned_data["grupos_responsaveis"].values_list("id", flat=True))
        self.assertIn(grupo_herdado.id, grupos_ids)
        self.assertIn(grupo_extra.id, grupos_ids)


class SalaSituacaoV2ProgressoProcessualTests(TestCase):
    def test_entrega_concluida_reflete_no_processo_e_indicador_processual(self):
        indicador = Indicador.objects.create(
            nome="Teste indicador processual",
            tipo_indicador=Indicador.TipoIndicador.PROCESSUAL,
        )
        processo = Processo.objects.create(nome="Teste Indicador Processual - Processo")
        processo.indicadores.set([indicador])

        entrega_1 = Entrega.objects.create(
            nome="Teste Indicador Processual - Processo - Entrega 1",
            evolucao_manual=0,
        )
        entrega_2 = Entrega.objects.create(
            nome="Teste Indicador Processual - Processo - Entrega 2",
            evolucao_manual=0,
        )
        entrega_3 = Entrega.objects.create(
            nome="Teste Indicador Processual - Processo - Entrega 3",
            evolucao_manual=100,
        )
        processo.entregas.set([entrega_1, entrega_2, entrega_3])

        self.assertEqual(processo.progresso_percentual, 33.33)
        self.assertEqual(indicador.progresso_percentual, 33.33)


class SalaSituacaoV2IndicadorMatematicoTests(TestCase):
    def setUp(self):
        self.group_a = Group.objects.create(name="Grupo A Mat")
        self.group_b = Group.objects.create(name="Grupo B Mat")

    def test_indicador_matematico_cria_variaveis_processos_e_entregas(self):
        form = IndicadorForm(
            data={
                "nome": "Indicador Matematico V2",
                "descricao": "Descricao",
                "grupos_responsaveis": [self.group_a.id],
                "tipo_indicador": Indicador.TipoIndicador.MATEMATICO,
                "formula_expressao": "(parte/total)*100",
                "data_entrega_estipulada": "2026-12-31",
                "evolucao_manual": "0",
                "variaveis_config_map": json.dumps(
                    {
                        "parte": {
                            "periodicidade_monitoramento": "MENSAL",
                            "dia_referencia_monitoramento": 10,
                            "grupos_monitoramento_ids": [self.group_a.id],
                        },
                        "total": {
                            "periodicidade_monitoramento": "TRIMESTRAL",
                            "dia_referencia_monitoramento": 15,
                            "grupos_monitoramento_ids": [self.group_b.id],
                        },
                    }
                ),
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        indicador = form.save()

        variaveis = {item.nome: item for item in indicador.variaveis.all()}
        self.assertEqual(set(variaveis.keys()), {"parte", "total"})
        self.assertEqual(variaveis["parte"].periodicidade_monitoramento, "MENSAL")
        self.assertEqual(variaveis["parte"].dia_referencia_monitoramento, 10)
        self.assertEqual(set(variaveis["parte"].grupos_monitoramento.values_list("id", flat=True)), {self.group_a.id})
        self.assertEqual(variaveis["total"].periodicidade_monitoramento, "TRIMESTRAL")
        self.assertEqual(variaveis["total"].dia_referencia_monitoramento, 15)
        self.assertEqual(set(variaveis["total"].grupos_monitoramento.values_list("id", flat=True)), {self.group_b.id})

        processos = list(indicador.processos.order_by("nome"))
        self.assertEqual(len(processos), 2)
        self.assertTrue(any('Monitoramento de "parte"' in item.nome for item in processos))
        self.assertTrue(any('Monitoramento de "total"' in item.nome for item in processos))
        self.assertTrue(Entrega.objects.filter(variavel_monitoramento__indicador=indicador).exists())

    def test_monitoramento_de_entrega_grava_valor_da_variavel_e_recalcula_indicador(self):
        indicador = Indicador.objects.create(
            nome="Indicador monitorado",
            descricao="Descricao",
            tipo_indicador=Indicador.TipoIndicador.MATEMATICO,
            formula_expressao="(parte/total)*100",
            meta_valor=Decimal("100"),
            data_entrega_estipulada=date(2026, 12, 31),
        )
        indicador.sincronizar_variaveis_da_formula()
        parte = indicador.variaveis.get(nome="parte")
        total = indicador.variaveis.get(nome="total")
        parte.periodicidade_monitoramento = "MENSAL"
        total.periodicidade_monitoramento = "MENSAL"
        parte.dia_referencia_monitoramento = 10
        total.dia_referencia_monitoramento = 10
        parte.save(update_fields=["periodicidade_monitoramento", "dia_referencia_monitoramento", "atualizado_em"])
        total.save(update_fields=["periodicidade_monitoramento", "dia_referencia_monitoramento", "atualizado_em"])
        parte.grupos_monitoramento.set([self.group_a])
        total.grupos_monitoramento.set([self.group_a])
        indicador.sincronizar_estrutura_processual_monitoramento()

        entrega_parte = Entrega.objects.filter(variavel_monitoramento=parte).order_by("id").first()
        entrega_total = Entrega.objects.filter(variavel_monitoramento=total).order_by("id").first()

        form_parte = EntregaMonitoramentoForm(
            data={"valor_monitoramento": "25", "evidencia_monitoramento": ""},
            instance=entrega_parte,
        )
        self.assertTrue(form_parte.is_valid(), form_parte.errors)
        form_parte.save()

        form_total = EntregaMonitoramentoForm(
            data={"valor_monitoramento": "50", "evidencia_monitoramento": ""},
            instance=entrega_total,
        )
        self.assertTrue(form_total.is_valid(), form_total.errors)
        form_total.save()

        indicador.refresh_from_db()
        self.assertEqual(entrega_parte.variavel_monitoramento.valores_ciclo.count(), 1)
        self.assertEqual(
            IndicadorCicloValor.objects.filter(variavel__indicador=indicador).count(),
            2,
        )
        self.assertEqual(indicador.valor_atual, Decimal("50"))

    def test_monitoramento_cria_ciclo_inicial_e_prazos_por_dia_referencia(self):
        form = IndicadorForm(
            data={
                "nome": "Indicador com referencia",
                "descricao": "Descricao",
                "grupos_responsaveis": [self.group_a.id],
                "tipo_indicador": Indicador.TipoIndicador.MATEMATICO,
                "formula_expressao": "parte",
                "data_entrega_estipulada": "2026-06-30",
                "evolucao_manual": "0",
                "variaveis_config_map": json.dumps(
                    {
                        "parte": {
                            "periodicidade_monitoramento": "MENSAL",
                            "dia_referencia_monitoramento": 10,
                            "grupos_monitoramento_ids": [self.group_a.id],
                        }
                    }
                ),
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        indicador = form.save()

        variavel = indicador.variaveis.get(nome="parte")
        entregas = list(Entrega.objects.filter(variavel_monitoramento=variavel).order_by("data_entrega_estipulada", "id"))

        self.assertGreaterEqual(len(entregas), 2)
        self.assertTrue(entregas[0].ciclo_monitoramento.eh_inicial)
        self.assertEqual(entregas[0].data_entrega_estipulada, date(2026, 3, 20))
        self.assertEqual(entregas[1].data_entrega_estipulada, date(2026, 4, 10))


class SalaSituacaoV2EntregaListTests(TestCase):
    def test_lista_entregas_ordena_por_prazo_e_expoe_api_calendario(self):
        entrega_b = Entrega.objects.create(
            nome="Entrega B",
            descricao="Depois",
            data_entrega_estipulada=date(2026, 3, 20),
        )
        entrega_a = Entrega.objects.create(
            nome="Entrega A",
            descricao="Antes",
            data_entrega_estipulada=date(2026, 3, 10),
        )

        response = self.client.get(reverse("sala_entrega_list"))

        self.assertEqual(response.status_code, 302)

        user = User.objects.create_user(username="lista-entregas", password="senha-forte-123")
        self.client.login(username=user.username, password="senha-forte-123")
        response = self.client.get(reverse("sala_entrega_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["entregas"]), [entrega_a, entrega_b])
        self.assertEqual(
            response.context["entregas_calendario_api_url"],
            reverse("sala_entrega_calendario_api"),
        )

    def test_api_calendario_retorna_entregas_do_mes(self):
        user = User.objects.create_user(username="cal-v2", password="senha-forte-123")
        self.client.login(username=user.username, password="senha-forte-123")
        entrega = Entrega.objects.create(
            nome="Entrega Calendario",
            descricao="Calendario",
            data_entrega_estipulada=date(2026, 3, 10),
            evolucao_manual=100,
        )

        response = self.client.get(reverse("sala_entrega_calendario_api"), {"ano": 2026, "mes": 3})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["id"], entrega.id)
        self.assertEqual(payload["results"][0]["data"], "2026-03-10")
