"""Testes do app `licitacoes` para parser de importação e ETP TIC."""

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .forms import ItemSessaoForm
from .models import EtpTic, ItemSessao, SessaoTermo, SubsessaoTermo, TermoReferencia
from .views import IMPORT_COMMENT_PREFIX, _etp_render_sections, _importar_termo_texto


class ImportacaoTextoParserTests(TestCase):
    """Valida o parser deterministico da importacao por textarea."""

    def test_cria_arvore_numerica_por_profundidade(self):
        texto = """
1. SECAO TESTE
1.1. Item raiz
1.1.1. Item filho
1.1.1.1. Item neto
""".strip()
        termo, resumo = _importar_termo_texto(texto, "TR arvore")

        self.assertEqual(termo.sessoes.count(), 1)
        self.assertEqual(resumo["itens"], 3)
        raiz = ItemSessao.objects.get(texto="Item raiz")
        filho = ItemSessao.objects.get(texto="Item filho")
        neto = ItemSessao.objects.get(texto="Item neto")
        self.assertIsNone(raiz.parent)
        self.assertEqual(filho.parent_id, raiz.id)
        self.assertEqual(neto.parent_id, filho.id)

    def test_titulo_sem_numeracao_gera_subsessao(self):
        texto = """
1. REQUISITOS
Sustentabilidade
1.1. Item com titulo intermediario
""".strip()
        termo, _ = _importar_termo_texto(texto, "TR subsessao")

        sessao = SessaoTermo.objects.get(termo=termo)
        subsessao = SubsessaoTermo.objects.get(sessao=sessao)
        item = ItemSessao.objects.get(sessao=sessao)
        self.assertEqual(subsessao.titulo, "Sustentabilidade")
        self.assertEqual(item.subsessao_id, subsessao.id)

    def test_ou_e_bracket_viram_comentarios_no_mesmo_item_base(self):
        texto = """
1. CONDICOES
1.1. Texto base
OU
[segunda alternativa]
""".strip()
        _termo, resumo = _importar_termo_texto(texto, "TR comentarios")

        base = ItemSessao.objects.get(texto="Texto base")
        filhos = list(base.subitens.order_by("ordem", "id"))
        self.assertEqual(len(filhos), 2)
        self.assertTrue(filhos[0].texto.startswith(IMPORT_COMMENT_PREFIX))
        self.assertTrue(filhos[1].texto.startswith(IMPORT_COMMENT_PREFIX))
        self.assertEqual(resumo["comentarios"], 2)

    def test_incisos_e_alineas_com_parent_correto(self):
        texto = """
1. FUNDAMENTACAO
2. DESCRICAO
2.1. Texto numerico base
I) Primeiro inciso
a) Primeira alinea
""".strip()
        _termo, resumo = _importar_termo_texto(texto, "TR enum")

        base = ItemSessao.objects.get(texto="Texto numerico base")
        inciso = ItemSessao.objects.get(texto="Primeiro inciso")
        alinea = ItemSessao.objects.get(texto="Primeira alinea")
        self.assertEqual(inciso.parent_id, base.id)
        self.assertEqual(alinea.parent_id, inciso.id)
        self.assertEqual(inciso.enum_tipo, ItemSessao.EnumTipo.INCISO)
        self.assertEqual(alinea.enum_tipo, ItemSessao.EnumTipo.ALINEA)
        self.assertEqual(resumo["incisos"], 1)
        self.assertEqual(resumo["alineas"], 1)

    def test_tabela_entre_colchetes_vira_comentario(self):
        texto = """
1. CONDICOES
1.1. Item com tabela
[tabela]
""".strip()
        _termo, resumo = _importar_termo_texto(texto, "TR tabela")

        item = ItemSessao.objects.get(texto="Item com tabela")
        tabela = item.subitens.get()
        self.assertEqual(tabela.texto, f"{IMPORT_COMMENT_PREFIX}[tabela]")
        self.assertEqual(resumo["comentarios"], 1)

    def test_titulo_de_sessao_longo_e_truncado(self):
        titulo_longo = "X" * 380
        texto = f"1. {titulo_longo}\n1.1. Item" 
        termo, _ = _importar_termo_texto(texto, "TR truncado")

        sessao = SessaoTermo.objects.get(termo=termo)
        self.assertLessEqual(len(sessao.titulo), 300)

    def test_documento_grande_importa_sem_excecao_com_contagens_coerentes(self):
        linhas = ["1. SECAO 1", "1.1. Item 1.1", "1.1.1. Item 1.1.1", "OU", "[alternativa]"]
        for n in range(2, 11):
            linhas.extend(
                [
                    f"{n}. SECAO {n}",
                    f"{n}.1. Item {n}.1",
                    f"{n}.1.1. Item {n}.1.1",
                    f"{n}.1.1.1. Item {n}.1.1.1",
                ]
            )
        texto = "\n".join(linhas)

        termo, resumo = _importar_termo_texto(texto, "TR grande")

        self.assertEqual(termo.sessoes.count(), 10)
        self.assertGreaterEqual(resumo["itens"], 30)
        self.assertGreaterEqual(resumo["comentarios"], 2)
        self.assertEqual(ItemSessao.objects.filter(sessao__termo=termo).count(), resumo["itens"])


class ItemSessaoFormTests(TestCase):
    def setUp(self):
        self.termo = TermoReferencia.objects.create(
            apelido="TR teste",
            processo_sei="001/2026",
        )
        self.sessao = SessaoTermo.objects.create(
            termo=self.termo,
            titulo="Sessao teste",
            ordem=1,
        )

    def test_colapsa_quebras_de_linha_em_texto_corrido(self):
        form = ItemSessaoForm(
            data={
                "subsessao": "",
                "texto": (
                    "Visando o reestabelecimento imediato da continuidade dos servicos de\n"
                    "infraestrutura de TI local, redundante e dos Sistemas Vivaleite e Bom Prato, a\n"
                    "CONTRATADA devera executar em carater emergencial."
                ),
            },
            sessao=self.sessao,
        )

        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data["texto"],
            (
                "Visando o reestabelecimento imediato da continuidade dos servicos de "
                "infraestrutura de TI local, redundante e dos Sistemas Vivaleite e Bom Prato, "
                "a CONTRATADA devera executar em carater emergencial."
            ),
        )

    def test_preserva_quebra_entre_incisos_e_junta_continuacao(self):
        form = ItemSessaoForm(
            data={
                "subsessao": "",
                "texto": (
                    "Devera contemplar:\n"
                    "I) Primeiro requisito com descricao\n"
                    "complementar.\n"
                    "II) Segundo requisito."
                ),
            },
            sessao=self.sessao,
        )

        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data["texto"],
            "Devera contemplar:\nI) primeiro requisito com descricao complementar;\nII) segundo requisito.",
        )


class ItemSessaoDeleteViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="licit-user", password="123")
        perm = Permission.objects.get(codename="delete_itemsessao")
        self.user.user_permissions.add(perm)
        self.client.login(username="licit-user", password="123")

        self.termo = TermoReferencia.objects.create(
            apelido="TR exclusao",
            processo_sei="001/2026",
        )
        self.sessao = SessaoTermo.objects.create(
            termo=self.termo,
            titulo="Sessao teste",
            ordem=1,
        )
        self.item = ItemSessao.objects.create(
            sessao=self.sessao,
            texto="Item a excluir",
            ordem=1,
        )

    def test_post_repetido_redireciona_ao_invés_de_404(self):
        url = reverse("licitacoes_item_delete", args=[self.sessao.pk, self.item.pk])
        next_url = f"{reverse('licitacoes_termo_detail', args=[self.termo.pk])}#sessao-{self.sessao.pk}"

        first_response = self.client.post(url, {"next": next_url})
        self.assertRedirects(first_response, next_url, fetch_redirect_response=False)
        self.assertFalse(ItemSessao.objects.filter(pk=self.item.pk).exists())

        second_response = self.client.post(url, {"next": next_url})
        self.assertRedirects(second_response, next_url, fetch_redirect_response=False)


class EtpTicTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="etp-user", password="123")
        perm = Permission.objects.get(codename="view_termoreferencia")
        self.user.user_permissions.add(perm)
        self.client.login(username="etp-user", password="123")

    def test_criacao_minima_funciona(self):
        response = self.client.post(
            reverse("licitacoes_etp_tic_create"),
            {
                "titulo": "",
                "numero_processo_servico": "012.0001/2026",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(EtpTic.objects.count(), 1)
        etp = EtpTic.objects.first()
        self.assertEqual(etp.numero_processo_servico, "012.0001/2026")
        self.assertTrue(etp.declaracao_viabilidade)

    def test_permite_duplicidade_numero_processo(self):
        EtpTic.objects.create(numero_processo_servico="012.0001/2026")
        EtpTic.objects.create(numero_processo_servico="012.0001/2026")
        self.assertEqual(EtpTic.objects.filter(numero_processo_servico="012.0001/2026").count(), 2)

    def test_quebra_paragrafos_em_subitens(self):
        etp = EtpTic.objects.create(
            numero_processo_servico="012.0002/2026",
            descricao_necessidade="Paragrafo A\n\nParagrafo B",
        )
        secoes = _etp_render_sections(etp)
        secao_2 = next(secao for secao in secoes if secao["numero"] == 2)
        self.assertEqual(secao_2["entradas"][0], "2.1. Paragrafo A")
        self.assertEqual(secao_2["entradas"][1], "2.2. Paragrafo B")
