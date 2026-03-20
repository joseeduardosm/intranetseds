"""
Contém testes automatizados para validar comportamento esperado do app.

Leitura recomendada para iniciantes: comece pelos itens públicos deste arquivo,
siga para dependências chamadas e confira os testes para observar cenários reais.
"""

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import views as sala_views
from .forms import EntregaForm, MonitoramentoEntregaForm
from .models import (
    Entrega,
    IndicadorVariavelCicloMonitoramento,
    IndicadorCicloValor,
    IndicadorEstrategico,
    IndicadorTatico,
    IndicadorVariavel,
    Marcador,
    MarcadorVinculoAutomaticoGrupoItem,
    MarcadorVinculoItem,
    Processo,
)
from usuarios.models import SetorNode, UserSetorMembership


class SalaSituacaoAccessTests(TestCase):
    """Classe `SalaSituacaoAccessTests` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    def setUp(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.password = "senha-forte-123"
        self.user_autorizado = User.objects.create_user(username="autorizado", password=self.password)
        self.user_sem_permissao = User.objects.create_user(username="sem_permissao", password=self.password)
        permissao = Permission.objects.get(codename="view_salasituacaopainel")
        self.user_autorizado.user_permissions.add(permissao)

    def test_usuario_autorizado_acessa_modulo(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.client.login(username=self.user_autorizado.username, password=self.password)
        response = self.client.get(reverse("sala_situacao_home"))
        self.assertEqual(response.status_code, 200)

    def test_usuario_sem_permissao_nao_acessa_modulo(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.client.login(username=self.user_sem_permissao.username, password=self.password)
        response = self.client.get(reverse("sala_situacao_home"))
        self.assertEqual(response.status_code, 403)


    def test_usuario_de_grupo_monitoramento_acessa_modulo_sem_permissao_global(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        monitor_user = User.objects.create_user(username="monitor_grupo", password=self.password)
        grupo_monitor = Group.objects.create(name="DIVTI")
        monitor_user.groups.add(grupo_monitor)

        hoje = timezone.localdate()
        indicador = IndicadorEstrategico.objects.create(
            nome="Indicador monitoramento por grupo",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="X",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=60),
        )
        indicador.sincronizar_variaveis_da_formula()
        variavel = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="X",
        )
        variavel.periodicidade_monitoramento = "MENSAL"
        variavel.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        variavel.grupos_monitoramento.set([grupo_monitor])
        indicador.sincronizar_estrutura_processual_monitoramento()

        self.client.login(username=monitor_user.username, password=self.password)
        response = self.client.get(reverse("sala_situacao_home"))
        self.assertEqual(response.status_code, 200)

    def test_usuario_de_grupo_monitoramento_acessa_processos_e_entregas(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        monitor_user = User.objects.create_user(username="teste-divti", password=self.password)
        grupo_monitor = Group.objects.create(name="DCF")
        monitor_user.groups.add(grupo_monitor)

        hoje = timezone.localdate()
        indicador = IndicadorEstrategico.objects.create(
            nome="Execução DCF",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="teto_orcamentario + valor_executado",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=60),
        )
        indicador.sincronizar_variaveis_da_formula()
        for nome in ("teto_orcamentario", "valor_executado"):
            variavel = IndicadorVariavel.objects.get(
                content_type__model="indicadorestrategico",
                object_id=indicador.pk,
                nome=nome,
            )
            variavel.periodicidade_monitoramento = "MENSAL"
            variavel.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
            variavel.grupos_monitoramento.set([grupo_monitor])
        indicador.sincronizar_estrutura_processual_monitoramento()

        self.client.login(username=monitor_user.username, password=self.password)
        response_home = self.client.get(reverse("sala_situacao_home"))
        self.assertEqual(response_home.status_code, 200)
        self.assertContains(response_home, "Processos")
        self.assertContains(response_home, "Entregas")

        response_processos = self.client.get(reverse("sala_processo_list"))
        self.assertEqual(response_processos.status_code, 200)
        self.assertGreater(len(response_processos.context["processos"]), 0)

        response_entregas = self.client.get(reverse("sala_entrega_list"))
        self.assertEqual(response_entregas.status_code, 200)
        self.assertGreater(len(response_entregas.context["entregas"]), 0)

    def test_setor_pai_visualiza_itens_do_setor_filho(self):
        gestor_user = User.objects.create_user(username="gestor_pai", password=self.password)
        grupo_pai = Group.objects.create(name="Gabinete")
        grupo_filho = Group.objects.create(name="Assessoria Tecnica")
        setor_pai = SetorNode.objects.create(group=grupo_pai)
        setor_filho = SetorNode.objects.create(group=grupo_filho, parent=setor_pai)
        UserSetorMembership.objects.create(user=gestor_user, setor=setor_pai)

        hoje = timezone.localdate()
        indicador = IndicadorEstrategico.objects.create(
            nome="Indicador do filho",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="X",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=60),
        )
        indicador.sincronizar_variaveis_da_formula()
        variavel = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="X",
        )
        variavel.periodicidade_monitoramento = "MENSAL"
        variavel.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        variavel.grupos_monitoramento.set([grupo_filho])
        indicador.sincronizar_estrutura_processual_monitoramento()

        processo = Processo.objects.filter(
            nome__contains='Monitoramento de "X" do indicador'
        ).first()
        entrega = Entrega.objects.filter(variavel_monitoramento=variavel).order_by("id").first()

        self.client.login(username=gestor_user.username, password=self.password)

        response_home = self.client.get(reverse("sala_situacao_home"))
        self.assertEqual(response_home.status_code, 200)
        self.assertContains(response_home, "Indicador do filho")

        response_indicador = self.client.get(reverse("sala_indicador_estrategico_detail", kwargs={"pk": indicador.pk}))
        self.assertEqual(response_indicador.status_code, 200)

        response_processos = self.client.get(reverse("sala_processo_list"))
        self.assertEqual(response_processos.status_code, 200)
        self.assertIn(processo.id, list(response_processos.context["processos"].values_list("id", flat=True)))

        response_processo = self.client.get(reverse("sala_processo_detail", kwargs={"pk": processo.pk}))
        self.assertEqual(response_processo.status_code, 200)

        response_entregas = self.client.get(reverse("sala_entrega_list"))
        self.assertEqual(response_entregas.status_code, 200)
        self.assertIn(entrega.id, list(response_entregas.context["entregas"].values_list("id", flat=True)))

        response_entrega = self.client.get(reverse("sala_entrega_detail", kwargs={"pk": entrega.pk}))
        self.assertEqual(response_entrega.status_code, 200)

    def test_filtro_por_setor_na_lista_de_processos(self):
        gestor_user = User.objects.create_user(username="gestor_filtro", password=self.password)
        grupo_pai = Group.objects.create(name="Secretaria")
        grupo_filho_a = Group.objects.create(name="Setor A")
        grupo_filho_b = Group.objects.create(name="Setor B")
        setor_pai = SetorNode.objects.create(group=grupo_pai)
        setor_filho_a = SetorNode.objects.create(group=grupo_filho_a, parent=setor_pai)
        SetorNode.objects.create(group=grupo_filho_b, parent=setor_pai)
        UserSetorMembership.objects.create(user=gestor_user, setor=setor_pai)

        hoje = timezone.localdate()
        indicador_a = IndicadorEstrategico.objects.create(
            nome="Indicador setor A",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="XA",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=60),
        )
        indicador_a.sincronizar_variaveis_da_formula()
        variavel_a = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador_a.pk,
            nome="XA",
        )
        variavel_a.periodicidade_monitoramento = "MENSAL"
        variavel_a.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        variavel_a.grupos_monitoramento.set([grupo_filho_a])
        indicador_a.sincronizar_estrutura_processual_monitoramento()

        indicador_b = IndicadorEstrategico.objects.create(
            nome="Indicador setor B",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="XB",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=60),
        )
        indicador_b.sincronizar_variaveis_da_formula()
        variavel_b = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador_b.pk,
            nome="XB",
        )
        variavel_b.periodicidade_monitoramento = "MENSAL"
        variavel_b.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        variavel_b.grupos_monitoramento.set([grupo_filho_b])
        indicador_b.sincronizar_estrutura_processual_monitoramento()

        processo_a = Processo.objects.filter(nome__contains='Monitoramento de "XA" do indicador').first()
        processo_b = Processo.objects.filter(nome__contains='Monitoramento de "XB" do indicador').first()

        self.client.login(username=gestor_user.username, password=self.password)
        response = self.client.get(reverse("sala_processo_list"), {"setor": str(setor_filho_a.id)})
        self.assertEqual(response.status_code, 200)
        processos_ids = list(response.context["processos"].values_list("id", flat=True))
        self.assertIn(processo_a.id, processos_ids)
        self.assertNotIn(processo_b.id, processos_ids)

    def test_filtro_por_setor_na_lista_de_entregas(self):
        gestor_user = User.objects.create_user(username="gestor_entrega_filtro", password=self.password)
        grupo_pai = Group.objects.create(name="Secretaria Entregas")
        grupo_filho_a = Group.objects.create(name="Entrega Setor A")
        grupo_filho_b = Group.objects.create(name="Entrega Setor B")
        setor_pai = SetorNode.objects.create(group=grupo_pai)
        setor_filho_a = SetorNode.objects.create(group=grupo_filho_a, parent=setor_pai)
        SetorNode.objects.create(group=grupo_filho_b, parent=setor_pai)
        UserSetorMembership.objects.create(user=gestor_user, setor=setor_pai)

        hoje = timezone.localdate()
        indicador_a = IndicadorEstrategico.objects.create(
            nome="Indicador entrega A",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="EA",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=60),
        )
        indicador_a.sincronizar_variaveis_da_formula()
        variavel_a = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador_a.pk,
            nome="EA",
        )
        variavel_a.periodicidade_monitoramento = "MENSAL"
        variavel_a.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        variavel_a.grupos_monitoramento.set([grupo_filho_a])
        indicador_a.sincronizar_estrutura_processual_monitoramento()

        indicador_b = IndicadorEstrategico.objects.create(
            nome="Indicador entrega B",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="EB",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=60),
        )
        indicador_b.sincronizar_variaveis_da_formula()
        variavel_b = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador_b.pk,
            nome="EB",
        )
        variavel_b.periodicidade_monitoramento = "MENSAL"
        variavel_b.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        variavel_b.grupos_monitoramento.set([grupo_filho_b])
        indicador_b.sincronizar_estrutura_processual_monitoramento()

        entrega_a = Entrega.objects.filter(variavel_monitoramento=variavel_a).order_by("id").first()
        entrega_b = Entrega.objects.filter(variavel_monitoramento=variavel_b).order_by("id").first()

        self.client.login(username=gestor_user.username, password=self.password)
        response = self.client.get(reverse("sala_entrega_list"), {"setor": str(setor_filho_a.id)})
        self.assertEqual(response.status_code, 200)
        entregas_ids = list(response.context["entregas"].values_list("id", flat=True))
        self.assertIn(entrega_a.id, entregas_ids)
        self.assertNotIn(entrega_b.id, entregas_ids)

    def test_painel_consolidado_redireciona_para_home(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.client.login(username=self.user_autorizado.username, password=self.password)
        response = self.client.get(reverse("sala_painel_consolidado"))
        self.assertRedirects(response, reverse("sala_situacao_home"))

    def test_painel_consolidado_redireciona_para_home_mesmo_com_marcadores(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.client.login(username=self.user_autorizado.username, password=self.password)
        grupo = Group.objects.create(name="DIVTI")
        hoje = timezone.localdate()
        indicador = IndicadorEstrategico.objects.create(
            nome="Indicador Auto Marcador",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="X",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=60),
        )
        indicador.sincronizar_variaveis_da_formula()
        variavel = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="X",
        )
        variavel.periodicidade_monitoramento = "MENSAL"
        variavel.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        variavel.grupos_monitoramento.set([grupo])
        indicador.sincronizar_estrutura_processual_monitoramento()

        response = self.client.get(reverse("sala_painel_consolidado"))
        self.assertRedirects(response, reverse("sala_situacao_home"))


class EntregaFormTests(TestCase):
    def test_ordem_campos_da_entrega_prioriza_nome_descricao_processo_marcadores(self):
        form = EntregaForm()

        self.assertEqual(
            list(form.fields.keys())[:6],
            [
                "nome",
                "descricao",
                "processos",
                "marcadores_ids",
                "data_entrega_estipulada",
                "evolucao_manual",
            ],
        )


class SalaSituacaoCadeiaTests(TestCase):
    """Classe `SalaSituacaoCadeiaTests` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    def test_cadeia_indicador_processo_entrega(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        ie = IndicadorEstrategico.objects.create(nome="IE")
        it = IndicadorTatico.objects.create(nome="IT")
        it.indicadores_estrategicos.add(ie)
        processo = Processo.objects.create(nome="Processo")
        processo.indicadores_taticos.add(it)
        entrega = Entrega.objects.create(nome="Entrega", evolucao_manual=60)
        entrega.processos.add(processo)

        self.assertEqual(ie.indicadores_taticos_relacionados.count(), 1)
        self.assertEqual(it.processos.count(), 1)
        self.assertEqual(processo.entregas.count(), 1)
        self.assertEqual(entrega.processos.count(), 1)

    def test_progresso_cascata_sem_objetivos(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        hoje = timezone.localdate()
        prazo = hoje + timedelta(days=5)

        ie = IndicadorEstrategico.objects.create(nome="IE", data_entrega_estipulada=prazo)
        it = IndicadorTatico.objects.create(nome="IT", data_entrega_estipulada=prazo)
        it.indicadores_estrategicos.add(ie)

        processo = Processo.objects.create(nome="Processo", data_entrega_estipulada=prazo)
        processo.indicadores_taticos.add(it)

        entrega = Entrega.objects.create(nome="Entrega", data_entrega_estipulada=prazo, evolucao_manual=80)
        entrega.processos.add(processo)

        self.assertEqual(processo.progresso_percentual, 80)
        self.assertEqual(it.progresso_percentual, 80)
        self.assertEqual(ie.progresso_percentual, 80)

    def test_indicador_estrategico_reflete_progresso_de_processo_vinculado_diretamente(self):
        hoje = timezone.localdate()
        prazo = hoje + timedelta(days=5)

        ie = IndicadorEstrategico.objects.create(nome="IE Direto", data_entrega_estipulada=prazo)
        processo = Processo.objects.create(nome="Processo Direto", data_entrega_estipulada=prazo)
        processo.indicadores_estrategicos.add(ie)

        entrega = Entrega.objects.create(
            nome="Entrega Direta",
            data_entrega_estipulada=prazo,
            evolucao_manual=Decimal("25.00"),
        )
        entrega.processos.add(processo)

        self.assertTrue(ie.tem_filhos_relacionados)
        self.assertEqual(ie.processos.count(), 1)
        self.assertEqual(processo.progresso_percentual, 25.0)
        self.assertEqual(ie.progresso_percentual, 25.0)

    def test_entrega_manual_salva_periodo_mensal(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        ie = IndicadorEstrategico.objects.create(nome="IE Manual")
        it = IndicadorTatico.objects.create(nome="IT Manual")
        it.indicadores_estrategicos.add(ie)
        processo = Processo.objects.create(nome="Processo Manual")
        processo.indicadores_taticos.add(it)
        referencia = timezone.localdate() + timedelta(days=20)
        entrega = Entrega.objects.create(
            nome="Entrega Manual",
            data_entrega_estipulada=referencia,
        )
        entrega.processos.add(processo)
        entrega.refresh_from_db()
        self.assertEqual(entrega.periodo_inicio.day, 1)
        self.assertGreaterEqual(entrega.periodo_fim.day, 28)

    def test_processo_herda_marcador_do_indicador_via_entrega_monitoramento(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        hoje = timezone.localdate()
        ie = IndicadorEstrategico.objects.create(
            nome="IE monitoramento marcador",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="X",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=90),
        )
        marcador = Marcador.objects.create(
            nome="Contrato",
            nome_normalizado="contrato",
            cor="#1f77b4",
            ativo=True,
        )
        MarcadorVinculoItem.objects.create(
            content_type=ContentType.objects.get_for_model(IndicadorEstrategico),
            object_id=ie.pk,
            marcador=marcador,
        )

        ie.sincronizar_variaveis_da_formula()
        variavel = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=ie.pk,
            nome="X",
        )
        variavel.periodicidade_monitoramento = "MENSAL"
        variavel.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        ie.sincronizar_estrutura_processual_monitoramento()

        processo = Processo.objects.filter(nome__contains='Monitoramento de "X"').first()
        self.assertIsNotNone(processo)
        marcadores_efetivos_ids = {item.id for item in processo.marcadores_efetivos}
        self.assertIn(marcador.id, marcadores_efetivos_ids)

    def test_indicador_prefetch_mantem_marcador_automatico_local(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        hoje = timezone.localdate()
        grupo = Group.objects.create(name="Grupo Auto")
        indicador = IndicadorEstrategico.objects.create(
            nome="IE prefetch marcador",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="X",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=60),
        )
        indicador.sincronizar_variaveis_da_formula()
        variavel = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="X",
        )
        variavel.periodicidade_monitoramento = "MENSAL"
        variavel.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        variavel.grupos_monitoramento.set([grupo])
        indicador.sincronizar_estrutura_processual_monitoramento()

        indicador_prefetch = (
            IndicadorEstrategico.objects.prefetch_related("marcadores_vinculos__marcador")
            .get(pk=indicador.pk)
        )
        nomes = {marcador.nome for marcador in indicador_prefetch.marcadores_locais}
        self.assertIn("Grupo Auto", nomes)


class SalaSituacaoIndicadorMatematicoTests(TestCase):
    """Classe `SalaSituacaoIndicadorMatematicoTests` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    def test_indicador_matematico_acumulativo_soma_valores_por_ciclo(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        hoje = timezone.localdate()
        indicador = IndicadorEstrategico.objects.create(
            nome="Consumo Contrato",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO_ACUMULATIVO,
            formula_expressao="X",
            meta_valor=Decimal("10000"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=160),
        )
        indicador.sincronizar_variaveis_da_formula()
        variavel_x = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="X",
        )
        variavel_x.periodicidade_monitoramento = "MENSAL"
        variavel_x.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        variavel_x.gerar_ciclos_monitoramento()

        ciclos = list(
            IndicadorVariavelCicloMonitoramento.objects.filter(
                variavel=variavel_x,
            ).order_by("numero")
        )
        self.assertGreaterEqual(len(ciclos), 4)

        IndicadorCicloValor.objects.create(ciclo=ciclos[0], variavel=variavel_x, valor=Decimal("100"))
        IndicadorCicloValor.objects.create(ciclo=ciclos[3], variavel=variavel_x, valor=Decimal("200"))

        indicador.refresh_from_db()
        self.assertEqual(indicador.valor_atual, Decimal("300"))

    def test_edicao_formula_recalcula_valor_atual_de_indicador_em_andamento(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        hoje = timezone.localdate()
        indicador = IndicadorEstrategico.objects.create(
            nome="Indicador em andamento",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="X + Y",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=160),
        )
        indicador.sincronizar_variaveis_da_formula()
        variavel_x = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="X",
        )
        variavel_y = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="Y",
        )
        variavel_x.periodicidade_monitoramento = "MENSAL"
        variavel_y.periodicidade_monitoramento = "MENSAL"
        variavel_x.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        variavel_y.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        variavel_x.gerar_ciclos_monitoramento()
        variavel_y.gerar_ciclos_monitoramento()

        ciclo_x = IndicadorVariavelCicloMonitoramento.objects.filter(variavel=variavel_x).order_by("numero").first()
        ciclo_y = IndicadorVariavelCicloMonitoramento.objects.filter(variavel=variavel_y).order_by("numero").first()
        IndicadorCicloValor.objects.create(ciclo=ciclo_x, variavel=variavel_x, valor=Decimal("80"))
        IndicadorCicloValor.objects.create(ciclo=ciclo_y, variavel=variavel_y, valor=Decimal("30"))

        indicador.refresh_from_db()
        self.assertEqual(indicador.valor_atual, Decimal("110"))

        indicador.formula_expressao = "X - Y"
        indicador.save()

        indicador.refresh_from_db()
        self.assertEqual(indicador.valor_atual, Decimal("50"))

    def test_periodicidade_da_variavel_controla_entregas_geradas(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        hoje = timezone.localdate()
        indicador = IndicadorEstrategico.objects.create(
            nome="Indicador por variável",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="X",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=160),
        )
        indicador.sincronizar_variaveis_da_formula()
        variavel_x = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="X",
        )
        variavel_x.periodicidade_monitoramento = "TRIMESTRAL"
        variavel_x.full_clean()
        variavel_x.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])

        indicador.sincronizar_estrutura_processual_monitoramento()

        ciclos = list(
            IndicadorVariavelCicloMonitoramento.objects.filter(
                variavel=variavel_x,
            ).order_by("numero")
        )
        entregas = Entrega.objects.filter(variavel_monitoramento=variavel_x)
        self.assertEqual(entregas.count(), len(ciclos))

    def test_variavel_anual_cria_ciclo_inicial_obrigatorio(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        hoje = timezone.localdate()
        indicador = IndicadorEstrategico.objects.create(
            nome="Indicador anual",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="Y",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=430),
        )
        indicador.sincronizar_variaveis_da_formula()
        variavel_y = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="Y",
        )
        variavel_y.periodicidade_monitoramento = "ANUAL"
        variavel_y.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        variavel_y.gerar_ciclos_monitoramento()

        ciclos = list(IndicadorVariavelCicloMonitoramento.objects.filter(variavel=variavel_y).order_by("numero"))
        self.assertGreaterEqual(len(ciclos), 2)
        self.assertTrue(ciclos[0].eh_inicial)
        self.assertEqual(ciclos[0].periodo_inicio.day, 1)
        self.assertGreaterEqual(ciclos[0].periodo_fim.day, 28)

    def test_ie_matematico_nao_cria_indice_tatico_automatico_por_variavel(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        hoje = timezone.localdate()
        indicador = IndicadorEstrategico.objects.create(
            nome="Execução Contrato Very",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="X",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=200),
        )
        indicador.sincronizar_variaveis_da_formula()
        variavel_x = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="X",
        )
        variavel_x.periodicidade_monitoramento = "MENSAL"
        variavel_x.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        indicador.sincronizar_estrutura_processual_monitoramento()

        self.assertFalse(
            IndicadorTatico.objects.filter(
                nome__startswith='Índice de entregas da variável "',
                nome__contains=indicador.nome,
            ).exists()
        )

    def test_entrega_monitoramento_tem_periodo_mensal(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        hoje = timezone.localdate()
        indicador = IndicadorEstrategico.objects.create(
            nome="Indicador periodicidade longa",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="Z",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=240),
        )
        indicador.sincronizar_variaveis_da_formula()
        variavel_z = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="Z",
        )
        variavel_z.periodicidade_monitoramento = "TRIMESTRAL"
        variavel_z.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        indicador.sincronizar_estrutura_processual_monitoramento()

        entrega_inicial = (
            Entrega.objects.filter(variavel_monitoramento=variavel_z)
            .select_related("ciclo_monitoramento")
            .order_by("ciclo_monitoramento__numero")
            .first()
        )
        self.assertIsNotNone(entrega_inicial)
        self.assertEqual(entrega_inicial.periodo_inicio.day, 1)
        self.assertGreaterEqual(entrega_inicial.periodo_fim.day, 28)
        self.assertIn("(Inicial)", entrega_inicial.nome)
        self.assertTrue(entrega_inicial.ciclo_monitoramento.eh_inicial)

    def test_recalculo_nao_falha_quando_formula_esta_incompleta(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        hoje = timezone.localdate()
        indicador = IndicadorEstrategico.objects.create(
            nome="Indicador incompleto",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="(X / Y) * 100",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=90),
        )
        indicador.sincronizar_variaveis_da_formula()
        variavel_x = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="X",
        )
        variavel_y = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="Y",
        )
        variavel_x.periodicidade_monitoramento = "MENSAL"
        variavel_y.periodicidade_monitoramento = "MENSAL"
        variavel_x.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        variavel_y.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        variavel_x.gerar_ciclos_monitoramento()

    def test_monitoramento_entrega_salva_valor_e_evidencia(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        hoje = timezone.localdate()
        indicador = IndicadorEstrategico.objects.create(
            nome="Indicador monitorado",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="X",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=90),
        )
        indicador.sincronizar_variaveis_da_formula()
        variavel_x = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="X",
        )
        variavel_x.periodicidade_monitoramento = "MENSAL"
        variavel_x.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        indicador.sincronizar_estrutura_processual_monitoramento()
        entrega = Entrega.objects.filter(variavel_monitoramento=variavel_x).order_by("id").first()
        usuario = User.objects.create_user(username="monitor_user", password="senha-forte")

        form = MonitoramentoEntregaForm(
            data={"valor_monitoramento": "123.45"},
            files={"evidencia_monitoramento": SimpleUploadedFile("evidencia.txt", b"ok", content_type="text/plain")},
            instance=entrega,
            usuario=usuario,
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.save()

        entrega.refresh_from_db()
        self.assertEqual(entrega.valor_monitoramento, Decimal("123.45"))
        self.assertIsNotNone(entrega.evidencia_monitoramento)
        self.assertEqual(entrega.monitorado_por_id, usuario.id)
        self.assertIsNotNone(entrega.monitorado_em)


class SalaSituacaoMarcadorFluxosTests(TestCase):
    """Classe `SalaSituacaoMarcadorFluxosTests` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    def setUp(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.password = "senha-forte-123"
        self.usuario = User.objects.create_user(username="editor", password=self.password)
        permissao = Permission.objects.get(codename="change_processo")
        self.usuario.user_permissions.add(permissao)
        self.admin = User.objects.create_user(
            username="admin_validado",
            password=self.password,
            is_staff=True,
        )
        self.client.login(username=self.usuario.username, password=self.password)
        self.processo = Processo.objects.create(nome="Proc. Marcador")
        self.marcador = Marcador.objects.create(
            nome="Urgente",
            nome_normalizado="urgente",
            cor="#1f77b4",
            ativo=True,
        )
        MarcadorVinculoItem.objects.create(
            content_type=ContentType.objects.get_for_model(Processo),
            object_id=self.processo.pk,
            marcador=self.marcador,
        )

    def test_exclusao_global_exige_admin_valido(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        response = self.client.delete(
            reverse("sala_marcador_excluir_api", kwargs={"pk": self.marcador.pk}),
            data=json.dumps({
                "admin_username": "admin_inexistente",
                "admin_password": "qualquer",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.marcador.refresh_from_db()
        self.assertTrue(self.marcador.ativo)

    def test_exclusao_global_inativa_sem_remover_registro(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        response = self.client.delete(
            reverse("sala_marcador_excluir_api", kwargs={"pk": self.marcador.pk}),
            data=json.dumps({
                "admin_username": self.admin.username,
                "admin_password": self.password,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Marcador.objects.filter(pk=self.marcador.pk).exists())
        self.marcador.refresh_from_db()
        self.assertFalse(self.marcador.ativo)

    def test_desvincular_remove_apenas_vinculo_do_item(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        response = self.client.delete(
            reverse(
                "sala_item_marcador_desvincular_api",
                kwargs={
                    "tipo": "processo",
                    "pk": self.processo.pk,
                    "marcador_id": self.marcador.pk,
                },
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            MarcadorVinculoItem.objects.filter(
                marcador_id=self.marcador.pk,
                object_id=self.processo.pk,
            ).exists()
        )
        self.marcador.refresh_from_db()
        self.assertTrue(self.marcador.ativo)


class SalaSituacaoDeleteCascadeComplementarTests(TestCase):
    """Classe `SalaSituacaoDeleteCascadeComplementarTests` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    def test_resolver_cascata_ie_inclui_toda_cadeia_vinculada(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        ie = IndicadorEstrategico.objects.create(nome="IE")
        it_a = IndicadorTatico.objects.create(nome="IT A")
        it_b = IndicadorTatico.objects.create(nome="IT B")
        it_a.indicadores_estrategicos.add(ie)
        it_b.indicadores_estrategicos.add(ie)

        processo_compartilhado = Processo.objects.create(nome="Processo Compartilhado")
        processo_compartilhado.indicadores_taticos.add(it_a, it_b)
        processo_simples = Processo.objects.create(nome="Processo Simples")
        processo_simples.indicadores_taticos.add(it_a)

        entrega_compartilhada = Entrega.objects.create(nome="Entrega Compartilhada")
        entrega_compartilhada.processos.add(processo_compartilhado)
        entrega_simples = Entrega.objects.create(nome="Entrega Simples")
        entrega_simples.processos.add(processo_simples)

        cascata = sala_views._resolver_cascata_ie(ie)
        processos_ids = set(cascata["processos"].values_list("id", flat=True))
        entregas_ids = set(cascata["entregas"].values_list("id", flat=True))

        self.assertEqual(processos_ids, {processo_compartilhado.id, processo_simples.id})
        self.assertEqual(entregas_ids, {entrega_compartilhada.id, entrega_simples.id})


class SalaSituacaoChartPayloadTests(TestCase):
    def test_fallback_chart_payload_usa_snapshot_dict_do_indicador(self):
        indicador = IndicadorEstrategico.objects.create(
            nome="Indicador com fallback",
            descricao="teste",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="a / b * 100",
            meta_valor=Decimal("100"),
            meta_unidade_medida="%",
            data_lancamento=timezone.localdate(),
            data_entrega_estipulada=timezone.localdate() + timedelta(days=15),
        )
        indicador.sincronizar_variaveis_da_formula()
        variavel_a = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="a",
        )
        variavel_b = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=indicador.pk,
            nome="b",
        )
        for variavel in (variavel_a, variavel_b):
            variavel.periodicidade_monitoramento = IndicadorEstrategico.PeriodicidadeMonitoramento.QUINZENAL
            variavel.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        indicador.gerar_ciclos_monitoramento()
        ciclo_a = IndicadorVariavelCicloMonitoramento.objects.get(variavel=variavel_a, numero=1)
        ciclo_b = IndicadorVariavelCicloMonitoramento.objects.get(variavel=variavel_b, numero=1)
        IndicadorCicloValor.objects.create(ciclo=ciclo_a, variavel=variavel_a, valor=Decimal("50"))
        IndicadorCicloValor.objects.create(ciclo=ciclo_b, variavel=variavel_b, valor=Decimal("100"))
        indicador.valor_atual = Decimal("50")
        indicador.save(update_fields=["valor_atual", "atualizado_em"])

        payload = sala_views._chart_compare_payload(indicador)

        self.assertEqual(payload["type"], "bar_compare")
        self.assertEqual(payload["conclusao_label"], "Atingimento da Meta")
        self.assertEqual(payload["conclusao"], 50.0)
        self.assertGreaterEqual(payload["prazo"], 0.0)

    def test_indicador_acumulativo_usa_comparativo_horizontal(self):
        indicador = IndicadorEstrategico.objects.create(
            nome="Indicador acumulativo",
            descricao="teste",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO_ACUMULATIVO,
            formula_expressao="a",
            meta_valor=Decimal("100"),
            meta_unidade_medida="%",
            valor_atual=Decimal("80"),
            data_lancamento=timezone.localdate(),
            data_entrega_estipulada=timezone.localdate() + timedelta(days=15),
        )

        payload = sala_views._chart_payload_for_indicator(indicador, series_map={})

        self.assertEqual(payload["type"], "bar_compare")
        self.assertEqual(payload["conclusao_label"], "Atingimento da Meta")
        self.assertEqual(payload["conclusao"], 80.0)


class SalaSituacaoHierarquiaAcessoTests(TestCase):
    """Classe `SalaSituacaoHierarquiaAcessoTests` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    def setUp(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.password = "senha-forte-123"
        self.creator = User.objects.create_user(username="criador", password=self.password)
        self.other_user = User.objects.create_user(username="outro", password=self.password)
        self.admin_user = User.objects.create_user(
            username="admin-sala",
            password=self.password,
            is_staff=True,
        )
        self.monitor_user = User.objects.create_user(username="monitor-a", password=self.password)
        self.outsider_user = User.objects.create_user(username="monitor-fora", password=self.password)

        self.group_a = Group.objects.create(name="Grupo A")
        self.group_b = Group.objects.create(name="Grupo B")
        self.monitor_user.groups.add(self.group_a)

        self._grant(self.creator, [
            "view_indicadorestrategico",
            "change_indicadorestrategico",
            "delete_indicadorestrategico",
            "view_processo",
            "change_processo",
            "delete_processo",
            "view_entrega",
            "change_entrega",
            "delete_entrega",
            "monitorar_entrega",
        ])
        self._grant(self.other_user, [
            "view_indicadorestrategico",
            "change_indicadorestrategico",
            "delete_indicadorestrategico",
        ])
        self._grant(self.admin_user, [
            "view_indicadorestrategico",
            "change_indicadorestrategico",
            "delete_indicadorestrategico",
            "view_processo",
            "change_processo",
            "delete_processo",
            "view_entrega",
            "change_entrega",
            "delete_entrega",
            "monitorar_entrega",
        ])
        self._grant(self.monitor_user, ["monitorar_entrega"])
        self._grant(self.outsider_user, ["monitorar_entrega"])

        hoje = timezone.localdate()
        self.indicador = IndicadorEstrategico.objects.create(
            nome="Indicador Hierarquia",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="X + Y",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=120),
            criado_por=self.creator,
        )
        self.indicador.sincronizar_variaveis_da_formula()
        self.variavel_x = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=self.indicador.pk,
            nome="X",
        )
        self.variavel_y = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=self.indicador.pk,
            nome="Y",
        )
        self.variavel_x.periodicidade_monitoramento = "MENSAL"
        self.variavel_y.periodicidade_monitoramento = "MENSAL"
        self.variavel_x.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        self.variavel_y.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        self.variavel_x.grupos_monitoramento.set([self.group_a, self.group_b])
        self.variavel_y.grupos_monitoramento.set([self.group_b])
        self.indicador.sincronizar_estrutura_processual_monitoramento()

        self.processo_x = Processo.objects.filter(
            nome__contains='Monitoramento de "X" do indicador'
        ).first()
        self.entrega_x = (
            Entrega.objects.filter(variavel_monitoramento=self.variavel_x)
            .order_by("id")
            .first()
        )
        self.entrega_y = (
            Entrega.objects.filter(variavel_monitoramento=self.variavel_y)
            .order_by("id")
            .first()
        )

    def _grant(self, user, codenames):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        for codename in codenames:
            user.user_permissions.add(
                Permission.objects.get(
                    codename=codename,
                    content_type__app_label="sala_situacao",
                )
            )

    def test_propriedade_indicador_apenas_criador_ou_admin(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.client.login(username=self.creator.username, password=self.password)
        response = self.client.get(reverse("sala_indicador_estrategico_update", kwargs={"pk": self.indicador.pk}))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("sala_indicador_estrategico_delete", kwargs={"pk": self.indicador.pk}))
        self.assertEqual(response.status_code, 200)

        self.client.login(username=self.other_user.username, password=self.password)
        response = self.client.get(reverse("sala_indicador_estrategico_update", kwargs={"pk": self.indicador.pk}))
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse("sala_indicador_estrategico_delete", kwargs={"pk": self.indicador.pk}))
        self.assertEqual(response.status_code, 403)

        legado = IndicadorEstrategico.objects.create(
            nome="Legado sem dono",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.PROCESSUAL,
            meta_valor=Decimal("1"),
            criado_por=None,
        )
        self.client.login(username=self.admin_user.username, password=self.password)
        response = self.client.get(reverse("sala_indicador_estrategico_update", kwargs={"pk": legado.pk}))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("sala_indicador_estrategico_delete", kwargs={"pk": legado.pk}))
        self.assertEqual(response.status_code, 200)

    def test_variavel_persiste_multiplos_grupos_monitoramento(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        grupos_ids = set(self.variavel_x.grupos_monitoramento.values_list("id", flat=True))
        self.assertEqual(grupos_ids, {self.group_a.id, self.group_b.id})

    def test_monitorar_por_grupo_com_botao_visivel_somente_para_elegivel(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.client.login(username=self.monitor_user.username, password=self.password)
        response = self.client.get(reverse("sala_entrega_detail", kwargs={"pk": self.entrega_x.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Monitorar")
        self.assertNotContains(response, "Editar")
        self.assertNotContains(response, "Excluir")

        response = self.client.post(
            reverse("sala_entrega_monitorar", kwargs={"pk": self.entrega_x.pk}),
            data={"valor_monitoramento": "10.5"},
        )
        self.assertEqual(response.status_code, 302)
        self.entrega_x.refresh_from_db()
        self.assertEqual(self.entrega_x.valor_monitoramento, Decimal("10.5000"))

        self.client.login(username=self.outsider_user.username, password=self.password)
        response = self.client.post(
            reverse("sala_entrega_monitorar", kwargs={"pk": self.entrega_x.pk}),
            data={"valor_monitoramento": "22"},
        )
        self.assertEqual(response.status_code, 403)

    def test_lista_entregas_de_monitorador_mostra_apenas_grupo_permitido(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.client.login(username=self.monitor_user.username, password=self.password)
        response = self.client.get(reverse("sala_entrega_list"))
        self.assertEqual(response.status_code, 200)
        nomes = [entrega.nome for entrega in response.context["entregas"]]
        self.assertIn(self.entrega_x.nome, nomes)
        self.assertNotIn(self.entrega_y.nome, nomes)

    def test_lista_entregas_legada_expoe_api_de_calendario_legada(self):
        self.client.login(username=self.creator.username, password=self.password)

        response = self.client.get(reverse("sala_old_entrega_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["entregas_calendario_api_url"],
            reverse("sala_old_entrega_calendario_api"),
        )

    def test_fluxo_processos_do_indicador_filtra_processos_nao_visiveis(self):
        processo_y = Processo.objects.filter(
            nome__contains='Monitoramento de "Y" do indicador'
        ).first()
        self.assertIsNotNone(processo_y)
        self._grant(self.monitor_user, ["view_processo"])

        self.client.login(username=self.monitor_user.username, password=self.password)
        response = self.client.get(reverse("sala_fluxo_processos", kwargs={"pk": self.indicador.pk}))

        self.assertEqual(response.status_code, 200)
        processos_ids = list(response.context["processos"].values_list("id", flat=True))
        self.assertIn(self.processo_x.id, processos_ids)
        self.assertNotIn(processo_y.id, processos_ids)

    def test_usuario_com_permissao_global_sem_participacao_nao_visualiza_itens(self):
        self._grant(self.other_user, ["view_processo", "view_entrega"])

        self.client.login(username=self.other_user.username, password=self.password)
        indicadores_ids = list(
            sala_views._indicadores_estrategicos_queryset_para_usuario(self.other_user).values_list("id", flat=True)
        )
        self.assertIn(self.indicador.id, indicadores_ids)

        response_indicador_detail = self.client.get(
            reverse("sala_indicador_estrategico_detail", kwargs={"pk": self.indicador.pk})
        )
        self.assertEqual(response_indicador_detail.status_code, 200)

        response_processos = self.client.get(reverse("sala_processo_list"))
        self.assertEqual(response_processos.status_code, 200)
        processos_ids = list(response_processos.context["processos"].values_list("id", flat=True))
        self.assertNotIn(self.processo_x.id, processos_ids)

        response_entregas = self.client.get(reverse("sala_entrega_list"))
        self.assertEqual(response_entregas.status_code, 200)
        entregas_ids = list(response_entregas.context["entregas"].values_list("id", flat=True))
        self.assertNotIn(self.entrega_x.id, entregas_ids)

        response_processo_detail = self.client.get(reverse("sala_processo_detail", kwargs={"pk": self.processo_x.pk}))
        self.assertEqual(response_processo_detail.status_code, 404)
        response_entrega_detail = self.client.get(reverse("sala_entrega_detail", kwargs={"pk": self.entrega_x.pk}))
        self.assertEqual(response_entrega_detail.status_code, 404)

    def test_processo_automatico_bloqueado_para_nao_admin(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        self.client.login(username=self.creator.username, password=self.password)
        response = self.client.get(reverse("sala_processo_update", kwargs={"pk": self.processo_x.pk}))
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse("sala_processo_delete", kwargs={"pk": self.processo_x.pk}))
        self.assertEqual(response.status_code, 403)

        response = self.client.get(reverse("sala_processo_detail", kwargs={"pk": self.processo_x.pk}))
        self.assertEqual(response.status_code, 404)

    def test_marcador_automatico_por_grupo_sincroniza_sem_apagar_manual(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        marcador_manual = Marcador.objects.create(
            nome="Manual Processo",
            nome_normalizado="manual processo",
            cor="#1f77b4",
            ativo=True,
        )
        MarcadorVinculoItem.objects.create(
            content_type=ContentType.objects.get_for_model(Processo),
            object_id=self.processo_x.pk,
            marcador=marcador_manual,
        )
        self.assertTrue(
            MarcadorVinculoAutomaticoGrupoItem.objects.filter(
                object_id=self.processo_x.pk,
                grupo__in=[self.group_a, self.group_b],
            ).exists()
        )

        self.variavel_x.grupos_monitoramento.set([self.group_a])
        self.indicador.sincronizar_estrutura_processual_monitoramento()

        self.assertTrue(
            MarcadorVinculoAutomaticoGrupoItem.objects.filter(
                content_type=ContentType.objects.get_for_model(Processo),
                object_id=self.processo_x.pk,
                grupo=self.group_a,
            ).exists()
        )
        self.assertFalse(
            MarcadorVinculoAutomaticoGrupoItem.objects.filter(
                content_type=ContentType.objects.get_for_model(Processo),
                object_id=self.processo_x.pk,
                grupo=self.group_b,
            ).exists()
        )
        self.assertTrue(
            MarcadorVinculoItem.objects.filter(
                content_type=ContentType.objects.get_for_model(Processo),
                object_id=self.processo_x.pk,
                marcador=marcador_manual,
            ).exists()
        )


class SalaSituacaoDeleteCascadeTests(TestCase):
    """Classe `SalaSituacaoDeleteCascadeTests` do domínio Sala de Situação.

    Papel na arquitetura:
    - Encapsula comportamento coeso de modelo, formulário, view, admin ou teste
      conforme o módulo em que está definida.
    - Organiza regras de negócio e integração com ORM, permissões e templates.
    """

    def test_resolver_cascata_ie_inclui_monitoramento_por_variavel_sem_it(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        hoje = timezone.localdate()
        ie = IndicadorEstrategico.objects.create(
            nome="IE matemático sem IT",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="X",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=60),
        )
        ie.sincronizar_variaveis_da_formula()
        variavel_x = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=ie.pk,
            nome="X",
        )
        variavel_x.periodicidade_monitoramento = "MENSAL"
        variavel_x.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        ie.sincronizar_estrutura_processual_monitoramento()

        cascata = sala_views._resolver_cascata_ie(ie)
        self.assertGreater(cascata["processos"].count(), 0)
        self.assertGreater(cascata["entregas"].count(), 0)

    def test_exclusao_ie_remove_processos_monitoramento_sem_it(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        hoje = timezone.localdate()
        ie = IndicadorEstrategico.objects.create(
            nome="IE matemático sem IT para excluir",
            tipo_indicador=IndicadorEstrategico.TipoIndicador.MATEMATICO,
            formula_expressao="X",
            meta_valor=Decimal("100"),
            data_lancamento=hoje,
            data_entrega_estipulada=hoje + timedelta(days=60),
        )
        ie.sincronizar_variaveis_da_formula()
        variavel_x = IndicadorVariavel.objects.get(
            content_type__model="indicadorestrategico",
            object_id=ie.pk,
            nome="X",
        )
        variavel_x.periodicidade_monitoramento = "MENSAL"
        variavel_x.save(update_fields=["periodicidade_monitoramento", "atualizado_em"])
        ie.sincronizar_estrutura_processual_monitoramento()

        cascata = sala_views._resolver_cascata_ie(ie)
        processos_ids = list(cascata["processos"].values_list("id", flat=True))
        entregas_ids = list(cascata["entregas"].values_list("id", flat=True))
        indicadores_taticos_ids = list(cascata["indicadores_taticos"].values_list("id", flat=True))

        Entrega.objects.filter(id__in=entregas_ids).delete()
        Processo.objects.filter(id__in=processos_ids).delete()
        sala_views._limpar_recursos_genericos_do_indicador(IndicadorTatico, indicadores_taticos_ids)
        IndicadorTatico.objects.filter(id__in=indicadores_taticos_ids).delete()
        sala_views._limpar_recursos_genericos_do_indicador(IndicadorEstrategico, [ie.pk])
        ie.delete()

        self.assertFalse(Processo.objects.filter(id__in=processos_ids).exists())

    def test_resolver_cascata_it_inclui_processos_e_entregas_compartilhados(self):
        """Implementa parte do fluxo de negócio deste componente.

        Contexto arquitetural:
        - Centraliza uma etapa específica de validação, transformação, consulta
          ORM ou montagem de contexto para a interface.
        - Deve ser lido junto dos métodos que o invocam para entender o fluxo
          completo de execução.

        Parâmetros:
        - `self`.

        Retorno:
        - Valor ou estrutura esperada pelo chamador, preservando o contrato da classe.
        """

        it = IndicadorTatico.objects.create(nome="IT")
        outro_it = IndicadorTatico.objects.create(nome="Outro IT")

        processo_compartilhado = Processo.objects.create(nome="Processo Compartilhado")
        processo_compartilhado.indicadores_taticos.add(it, outro_it)
        processo_simples = Processo.objects.create(nome="Processo Simples")
        processo_simples.indicadores_taticos.add(it)

        entrega_compartilhada = Entrega.objects.create(nome="Entrega Compartilhada")
        entrega_compartilhada.processos.add(processo_compartilhado)
        entrega_simples = Entrega.objects.create(nome="Entrega Simples")
        entrega_simples.processos.add(processo_simples)

        cascata = sala_views._resolver_cascata_it(it)
        processos_ids = set(cascata["processos"].values_list("id", flat=True))
        entregas_ids = set(cascata["entregas"].values_list("id", flat=True))

        self.assertEqual(processos_ids, {processo_compartilhado.id, processo_simples.id})
        self.assertEqual(entregas_ids, {entrega_compartilhada.id, entrega_simples.id})
