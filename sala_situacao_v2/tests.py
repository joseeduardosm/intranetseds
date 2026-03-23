import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import resolve, reverse
from django.utils import timezone

from auditoria.models import AuditLog
from usuarios.models import SetorNode, UserSetorMembership

from .access import (
    user_can_delete_processo,
    user_can_manage_entrega,
    user_can_manage_indicador,
    user_can_manage_processo,
)
from .forms import EntregaForm, EntregaMonitoramentoForm, IndicadorForm, ProcessoForm
from .models import Entrega, Indicador, IndicadorCicloValor, Processo
from .views import _variaveis_queryset_para_detalhe
from sala_situacao.forms import NotaItemForm
from sala_situacao.models import NotaItem, NotaItemAnexo


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


class SalaSituacaoV2DateFieldWidgetTests(TestCase):
    def test_formularios_renderizam_data_entrega_com_widget_date(self):
        self.assertEqual(IndicadorForm().fields["data_entrega_estipulada"].widget.input_type, "date")
        self.assertEqual(ProcessoForm().fields["data_entrega_estipulada"].widget.input_type, "date")
        self.assertEqual(EntregaForm().fields["data_entrega_estipulada"].widget.input_type, "date")


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


class SalaSituacaoV2EvolucaoManualFormTests(TestCase):
    def test_indicador_com_filhos_nao_exibe_evolucao_manual_no_formulario(self):
        indicador = Indicador.objects.create(
            nome="Indicador com filhos",
            tipo_indicador=Indicador.TipoIndicador.PROCESSUAL,
        )
        processo = Processo.objects.create(nome="Processo filho")
        processo.indicadores.set([indicador])

        form = IndicadorForm(instance=indicador)

        self.assertNotIn("evolucao_manual", form.fields)

    def test_processo_com_filhos_nao_exibe_evolucao_manual_no_formulario(self):
        processo = Processo.objects.create(nome="Processo com entregas")
        entrega = Entrega.objects.create(nome="Entrega filha")
        entrega.processos.set([processo])

        form = ProcessoForm(instance=processo)

        self.assertNotIn("evolucao_manual", form.fields)


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

    def test_excluir_indicador_remove_processos_e_entregas_filhos(self):
        password = "senha-123"
        grupo_criador = Group.objects.create(name="Criador Indicador Exclusao")
        user_criador = User.objects.create_user(username="uiexclusao", password=password)
        user_criador.groups.add(grupo_criador)
        UserSetorMembership.objects.create(
            user=user_criador,
            setor=SetorNode.objects.create(group=grupo_criador),
        )
        perm = Permission.objects.get(codename="delete_indicador", content_type__app_label="sala_situacao_v2")
        user_criador.user_permissions.add(perm)

        indicador = Indicador.objects.create(nome="Indicador para excluir")
        indicador.grupos_responsaveis.set([grupo_criador])
        indicador.grupos_criadores.set([grupo_criador])

        processo = Processo.objects.create(nome="Processo filho")
        processo.indicadores.set([indicador])
        entrega = Entrega.objects.create(nome="Entrega filha")
        entrega.processos.set([processo])

        self.client.login(username=user_criador.username, password=password)
        response = self.client.post(reverse("sala_indicador_estrategico_delete", kwargs={"pk": indicador.pk}))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Indicador.objects.filter(pk=indicador.pk).exists())
        self.assertFalse(Processo.objects.filter(pk=processo.pk).exists())
        self.assertFalse(Entrega.objects.filter(pk=entrega.pk).exists())

    def test_excluir_indicador_remove_entregas_de_monitoramento_remanescentes(self):
        password = "senha-123"
        grupo_criador = Group.objects.create(name="Criador Indicador Exclusao Monitoramento")
        user_criador = User.objects.create_user(username="uiexclusaomonitor", password=password)
        user_criador.groups.add(grupo_criador)
        UserSetorMembership.objects.create(
            user=user_criador,
            setor=SetorNode.objects.create(group=grupo_criador),
        )
        perm = Permission.objects.get(codename="delete_indicador", content_type__app_label="sala_situacao_v2")
        user_criador.user_permissions.add(perm)

        indicador = Indicador.objects.create(
            nome="Indicador monitorado para excluir",
            tipo_indicador=Indicador.TipoIndicador.MATEMATICO,
            formula_expressao="parte",
            data_entrega_estipulada=date(2026, 12, 31),
        )
        indicador.grupos_responsaveis.set([grupo_criador])
        indicador.grupos_criadores.set([grupo_criador])
        indicador.sincronizar_variaveis_da_formula()
        variavel = indicador.variaveis.get(nome="parte")
        variavel.periodicidade_monitoramento = "MENSAL"
        variavel.dia_referencia_monitoramento = 10
        variavel.save(update_fields=["periodicidade_monitoramento", "dia_referencia_monitoramento", "atualizado_em"])
        variavel.grupos_monitoramento.set([grupo_criador])
        indicador.sincronizar_estrutura_processual_monitoramento()

        entrega_remanescente = Entrega.objects.create(
            nome="Entrega remanescente",
            ciclo_monitoramento=variavel.ciclos_monitoramento.first(),
            variavel_monitoramento=variavel,
        )

        self.client.login(username=user_criador.username, password=password)
        response = self.client.post(reverse("sala_indicador_estrategico_delete", kwargs={"pk": indicador.pk}))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Entrega.objects.filter(pk=entrega_remanescente.pk).exists())
        self.assertFalse(Indicador.objects.filter(pk=indicador.pk).exists())


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


class SalaSituacaoV2EntregaDetailMonitoramentoTests(TestCase):
    def test_entrega_comum_nao_exibe_bloco_de_monitoramento(self):
        password = "senha-123"
        user = User.objects.create_user(username="entrega-comum", password=password)
        grupo = Group.objects.create(name="Grupo Entrega Comum")
        user.groups.add(grupo)
        setor = SetorNode.objects.create(group=grupo)
        UserSetorMembership.objects.create(user=user, setor=setor)
        for codename in ("view_entrega", "monitorar_entrega"):
            perm = Permission.objects.get(codename=codename, content_type__app_label="sala_situacao_v2")
            user.user_permissions.add(perm)

        entrega = Entrega.objects.create(nome="Entrega comum")
        entrega.grupos_responsaveis.set([grupo])
        entrega.grupos_criadores.set([grupo])

        self.client.login(username=user.username, password=password)
        response = self.client.get(reverse("sala_entrega_detail", kwargs={"pk": entrega.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["pode_monitorar"])
        self.assertNotContains(response, "Salvar monitoramento")


class SalaSituacaoV2HistoricoIndicadorTests(TestCase):
    def test_log_de_recalculo_matematico_fica_mais_claro(self):
        user = User.objects.create_user(username="historico-ind", password="senha-123")
        indicador = Indicador.objects.create(
            nome="Indicador historico",
            tipo_indicador=Indicador.TipoIndicador.MATEMATICO,
            formula_expressao="(x/y)*100",
        )
        AuditLog.objects.create(
            user=user,
            action=AuditLog.Action.UPDATE,
            content_type=ContentType.objects.get_for_model(Indicador),
            object_id=str(indicador.pk),
            object_repr=indicador.nome,
            changes={
                "atualizado_em": {"from": "2026-03-20T14:41:00+00:00", "to": "2026-03-20T14:43:00+00:00"},
                "valor_atual": {"from": "83.3333", "to": "125.0"},
            },
        )

        self.client.force_login(user)
        response = self.client.get(reverse("sala_indicador_estrategico_detail", kwargs={"pk": indicador.pk}))

        self.assertEqual(response.status_code, 200)
        historico = response.context["historico_alteracoes_formatado"][0]
        self.assertEqual(historico["resumo"], "Recalculou o indicador matemático com base nos monitoramentos.")
        self.assertEqual(historico["detalhes"], ["Valor calculado: 83.3333 -> 125"])


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

    def test_entrega_concluida_congela_contagem_do_prazo(self):
        entrega = Entrega.objects.create(
            nome="Entrega concluida",
            data_lancamento=date(2026, 3, 1),
            data_entrega_estipulada=date(2026, 3, 20),
            evolucao_manual=100,
        )
        entrega.data_lancamento_em = timezone.make_aware(datetime(2026, 3, 1, 9, 0, 0))
        entrega.atualizado_em = timezone.make_aware(datetime(2026, 3, 10, 15, 0, 0))

        with patch("sala_situacao_v2.models.timezone.now", return_value=timezone.make_aware(datetime(2026, 3, 18, 18, 0, 0))), patch(
            "sala_situacao_v2.models.timezone.localdate", return_value=date(2026, 3, 18)
        ):
            self.assertEqual(entrega.dias_para_vencer, 10)
            self.assertEqual(entrega.texto_prazo, "Concluido com 10 dias de antecedencia")
            self.assertAlmostEqual(entrega.progresso_prazo, 47.13, places=2)


class SalaSituacaoV2NumeracaoEntregaTests(TestCase):
    def test_entrega_manual_recebe_numeracao_automatica_por_processo_e_prazo(self):
        processo = Processo.objects.create(nome="Processo Numerado")
        entrega_1 = Entrega.objects.create(
            nome="Entrega 1",
            data_entrega_estipulada=date(2026, 3, 10),
        )
        entrega_2 = Entrega.objects.create(
            nome="Entrega 2",
            data_entrega_estipulada=date(2026, 3, 20),
        )
        entrega_3 = Entrega.objects.create(
            nome="Entrega 3",
            data_entrega_estipulada=date(2026, 3, 20),
        )
        processo.entregas.set([entrega_1, entrega_2, entrega_3])

        self.assertEqual(entrega_1.rotulo_numeracao_no_processo(processo), "1/3")
        self.assertEqual(entrega_2.rotulo_numeracao_no_processo(processo), "2/3")
        self.assertEqual(entrega_3.rotulo_numeracao_no_processo(processo), "3/3")

    def test_edicao_de_prazo_revisa_indice_da_entrega_no_processo(self):
        processo = Processo.objects.create(nome="Processo Reordenado")
        entrega_1 = Entrega.objects.create(
            nome="Entrega A",
            data_entrega_estipulada=date(2026, 3, 10),
        )
        entrega_2 = Entrega.objects.create(
            nome="Entrega B",
            data_entrega_estipulada=date(2026, 3, 20),
        )
        entrega_3 = Entrega.objects.create(
            nome="Entrega C",
            data_entrega_estipulada=date(2026, 3, 25),
        )
        processo.entregas.set([entrega_1, entrega_2, entrega_3])

        entrega_3.data_entrega_estipulada = date(2026, 3, 5)
        entrega_3.save(update_fields=["data_entrega_estipulada", "atualizado_em"])

        self.assertEqual(entrega_3.rotulo_numeracao_no_processo(processo), "1/3")
        self.assertEqual(entrega_1.rotulo_numeracao_no_processo(processo), "2/3")
        self.assertEqual(entrega_2.rotulo_numeracao_no_processo(processo), "3/3")

    def test_entrega_de_monitoramento_nao_entra_na_numeracao_manual(self):
        processo = Processo.objects.create(nome="Processo Manual")
        indicador = Indicador.objects.create(
            nome="Indicador Monitorado",
            tipo_indicador=Indicador.TipoIndicador.MATEMATICO,
            formula_expressao="x",
            data_entrega_estipulada=date(2026, 12, 31),
        )
        indicador.sincronizar_variaveis_da_formula()
        variavel = indicador.variaveis.get(nome="x")
        variavel.gerar_ciclos_monitoramento()
        ciclo = variavel.ciclos_monitoramento.order_by("numero").first()

        entrega_manual = Entrega.objects.create(
            nome="Entrega Manual",
            data_entrega_estipulada=date(2026, 3, 10),
        )
        entrega_monitoramento = Entrega.objects.create(
            nome="Entrega Monitoramento",
            data_entrega_estipulada=date(2026, 3, 5),
            variavel_monitoramento=variavel,
            ciclo_monitoramento=ciclo,
        )
        processo.entregas.set([entrega_manual, entrega_monitoramento])

        self.assertEqual(entrega_manual.rotulo_numeracao_no_processo(processo), "1/1")
        self.assertEqual(entrega_monitoramento.rotulo_numeracao_no_processo(processo), "")


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
        self.assertEqual(indicador.progresso_percentual, 50.0)
        self.assertEqual(indicador.progresso_snapshot["titulo_conclusao"], "Atingimento da Meta")
        entrega_parte.refresh_from_db()
        entrega_total.refresh_from_db()
        self.assertEqual(entrega_parte.evolucao_manual, Decimal("100"))
        self.assertEqual(entrega_total.evolucao_manual, Decimal("100"))

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

    def test_queryset_de_variaveis_do_detalhe_nao_seleciona_dia_referencia(self):
        indicador = Indicador.objects.create(
            nome="Indicador detalhe compat",
            tipo_indicador=Indicador.TipoIndicador.MATEMATICO,
            formula_expressao="parte",
            data_entrega_estipulada=date(2026, 12, 31),
        )
        indicador.sincronizar_variaveis_da_formula()

        queryset = _variaveis_queryset_para_detalhe(indicador)
        sql = str(queryset.query)

        self.assertNotIn("dia_referencia_monitoramento", sql)
        self.assertEqual(list(queryset.values_list("nome", flat=True)), ["parte"])

    @patch("sala_situacao_v2.forms._db_tem_dia_referencia_monitoramento", return_value=False)
    def test_form_matematico_exibe_erro_amigavel_quando_coluna_ainda_nao_existe(self, _db_check):
        form = IndicadorForm(
            data={
                "nome": "Indicador bloqueado por migration",
                "descricao": "Descricao",
                "grupos_responsaveis": [self.group_a.id],
                "tipo_indicador": Indicador.TipoIndicador.MATEMATICO,
                "formula_expressao": "parte",
                "data_entrega_estipulada": "2026-12-31",
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

        self.assertFalse(form.is_valid())
        self.assertIn("variaveis_config_map", form.errors)


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
        processo = Processo.objects.create(nome="Processo Tooltip")
        entrega = Entrega.objects.create(
            nome="Entrega Calendario",
            descricao="Calendario",
            data_entrega_estipulada=date(2026, 3, 10),
            evolucao_manual=100,
        )
        entrega.processos.set([processo])

        response = self.client.get(reverse("sala_entrega_calendario_api"), {"ano": 2026, "mes": 3})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["id"], entrega.id)
        self.assertEqual(payload["results"][0]["data"], "2026-03-10")
        self.assertEqual(payload["results"][0]["processos"], [processo.nome])


class SalaSituacaoNotasAnexosTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="nota-v2", password="senha-123")
        self.indicador = Indicador.objects.create(nome="Indicador para nota")
        self.processo = Processo.objects.create(nome="Processo para nota")
        self.processo.indicadores.set([self.indicador])
        self.entrega = Entrega.objects.create(nome="Entrega para nota")
        self.entrega.processos.set([self.processo])

    def test_form_nota_salva_um_ou_varios_anexos(self):
        nota = NotaItem.objects.create(
            content_type=ContentType.objects.get_for_model(Indicador),
            object_id=self.indicador.pk,
            texto="Nota com anexos",
        )
        form = NotaItemForm(data={"texto": "Atualizada"})

        self.assertTrue(form.is_valid())
        arquivos = [
            SimpleUploadedFile("arquivo-1.txt", b"um"),
            SimpleUploadedFile("arquivo-2.txt", b"dois"),
        ]
        form.save_anexos(nota, arquivos)

        self.assertEqual(NotaItemAnexo.objects.filter(nota=nota).count(), 2)

    @patch("sala_situacao.forms.nota_item_anexo_storage_ready", return_value=False)
    def test_form_nota_omite_campo_e_ignora_salvar_anexos_sem_tabela(self, _storage_ready):
        indicador = Indicador.objects.create(nome="Indicador sem tabela de anexo")
        nota = NotaItem.objects.create(
            content_type=ContentType.objects.get_for_model(Indicador),
            object_id=indicador.pk,
            texto="Nota sem anexo persistente",
        )
        form = NotaItemForm(data={"texto": "Atualizada"})

        self.assertTrue(form.is_valid())
        self.assertNotIn("anexos", form.fields)
        form.save_anexos(nota, [SimpleUploadedFile("arquivo.txt", b"conteudo")])

        self.assertEqual(NotaItemAnexo.objects.filter(nota=nota).count(), 0)

    @patch("sala_situacao_v2.views.nota_item_anexo_storage_ready", return_value=False)
    def test_detail_de_indicador_funciona_sem_tabela_de_anexos(self, _storage_ready):
        user = User.objects.create_user(username="indicador-sem-anexo", password="senha-123")
        indicador = Indicador.objects.create(nome="Indicador sem anexo")
        NotaItem.objects.create(
            content_type=ContentType.objects.get_for_model(Indicador),
            object_id=indicador.pk,
            texto="Nota sem tabela de anexo",
            criado_por=user,
        )

        self.client.force_login(user)
        response = self.client.get(reverse("sala_indicador_estrategico_detail", kwargs={"pk": indicador.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nota sem tabela de anexo")

    def test_indicador_aceita_nota_sem_anexo(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("sala_indicador_estrategico_detail", kwargs={"pk": self.indicador.pk}),
            {"texto": "Nota sem arquivo"},
        )

        self.assertRedirects(
            response,
            reverse("sala_indicador_estrategico_detail", kwargs={"pk": self.indicador.pk}),
            fetch_redirect_response=False,
        )
        nota = NotaItem.objects.get(
            content_type=ContentType.objects.get_for_model(Indicador),
            object_id=self.indicador.pk,
        )
        self.assertEqual(nota.texto, "Nota sem arquivo")
        self.assertEqual(nota.criado_por, self.user)
        self.assertEqual(nota.anexos.count(), 0)

    def test_processo_aceita_nota_com_multiplos_anexos(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("sala_processo_detail", kwargs={"pk": self.processo.pk}),
            {
                "texto": "Nota com dois anexos",
                "anexos": [
                    SimpleUploadedFile("processo-1.txt", b"um"),
                    SimpleUploadedFile("processo-2.txt", b"dois"),
                ],
            },
        )

        self.assertRedirects(
            response,
            reverse("sala_processo_detail", kwargs={"pk": self.processo.pk}),
            fetch_redirect_response=False,
        )
        nota = NotaItem.objects.get(
            content_type=ContentType.objects.get_for_model(Processo),
            object_id=self.processo.pk,
        )
        self.assertEqual(nota.texto, "Nota com dois anexos")
        self.assertEqual(nota.anexos.count(), 2)

    def test_entrega_aceita_nota_sem_anexo(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("sala_entrega_detail", kwargs={"pk": self.entrega.pk}),
            {"texto": "Entrega sem anexo"},
        )

        self.assertRedirects(
            response,
            reverse("sala_entrega_detail", kwargs={"pk": self.entrega.pk}),
            fetch_redirect_response=False,
        )
        nota = NotaItem.objects.get(
            content_type=ContentType.objects.get_for_model(Entrega),
            object_id=self.entrega.pk,
        )
        self.assertEqual(nota.texto, "Entrega sem anexo")
        self.assertEqual(nota.anexos.count(), 0)

    @patch("sala_situacao.forms.NotaItemForm.save_anexos", side_effect=PermissionError("sem permissao"))
    def test_indicador_exibe_erro_quando_upload_falha_por_permissao(self, _save_anexos):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("sala_indicador_estrategico_detail", kwargs={"pk": self.indicador.pk}),
            {
                "texto": "Nota com anexo bloqueado",
                "anexos": [SimpleUploadedFile("bloqueado.txt", b"arquivo")],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nao foi possivel salvar o arquivo enviado")
        self.assertFalse(
            NotaItem.objects.filter(
                content_type=ContentType.objects.get_for_model(Indicador),
                object_id=self.indicador.pk,
                texto="Nota com anexo bloqueado",
            ).exists()
        )
