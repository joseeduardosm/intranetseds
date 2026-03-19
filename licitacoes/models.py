"""
Modelos de domínio do app `licitacoes`.

Este arquivo concentra a estrutura persistida do Termo de Referência (TR) e integra-se com:
- `views.py`, que orquestra criação/edição/ordenação e montagem de árvore hierárquica;
- `forms.py`, que valida entrada textual e campos de tabela;
- templates do app, que exibem a hierarquia de sessões, itens e subitens.
"""

from django.db import models
from django.conf import settings


class TermoReferencia(models.Model):
    """Entidade raiz do domínio de TR.

    Cada registro representa um documento de referência de contratação, identificado por:
    - apelido operacional;
    - número do processo SEI e link opcional.
    """

    apelido = models.CharField(max_length=180)
    processo_sei = models.CharField("Processo SEI", max_length=120)
    link_processo_sei = models.URLField("Link do Processo SEI", max_length=500, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Define ordenação padrão para listagens e buscas no app."""

        ordering = ["apelido", "id"]

    def __str__(self):
        """Retorna descrição legível do TR para admin, selects e logs."""

        return f"{self.apelido} ({self.processo_sei})"


class SessaoTermo(models.Model):
    """Sessão de primeiro nível do Termo de Referência.

    Exemplo de domínio: "Condições Gerais", "Critérios de Pagamento".
    A ordem é controlada manualmente para refletir estrutura jurídica do documento.
    """

    termo = models.ForeignKey(TermoReferencia, on_delete=models.CASCADE, related_name="sessoes")
    titulo = models.CharField(max_length=300)
    ordem = models.PositiveIntegerField(default=1)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Ordena sessões por posição lógica dentro do termo."""

        ordering = ["ordem", "id"]

    def __str__(self):
        """Retorna sessão com índice de ordem para facilitar identificação."""

        return f"{self.ordem}. {self.titulo}"


class SubsessaoTermo(models.Model):
    """Subdivisão intermediária de uma sessão.

    É usada para agrupar itens relacionados dentro da mesma sessão principal.
    """

    sessao = models.ForeignKey(SessaoTermo, on_delete=models.CASCADE, related_name="subsessoes")
    titulo = models.CharField(max_length=300)
    ordem = models.PositiveIntegerField(default=1)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Ordena subseções de acordo com a posição definida pelo usuário."""

        ordering = ["ordem", "id"]

    def __str__(self):
        """Retorna título da subseção para composição de UI e seleção."""

        return self.titulo


class ItemSessao(models.Model):
    """Nó textual da estrutura do termo, com suporte a hierarquia recursiva.

    Regras de domínio:
    - pode pertencer diretamente à sessão ou a uma subseção;
    - pode ter um item pai (`parent`) para representar subitens;
    - suporta enumeração semântica para incisos/alíneas.
    """

    class EnumTipo(models.TextChoices):
        """Categoria de enumeração aplicada ao item no momento da exibição/exportação."""

        NENHUM = "", "Nenhum"
        INCISO = "INCISO", "Inciso"
        ALINEA = "ALINEA", "Alinea"

    sessao = models.ForeignKey(SessaoTermo, on_delete=models.CASCADE, related_name="itens")
    subsessao = models.ForeignKey(
        SubsessaoTermo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="itens",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subitens",
    )
    enum_tipo = models.CharField(max_length=10, choices=EnumTipo.choices, default="", blank=True)
    texto = models.TextField()
    ordem = models.PositiveIntegerField(default=1)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Ordena irmãos por posição para preservar narrativa jurídica do TR."""

        ordering = ["ordem", "id"]

    def __str__(self):
        """Retorna resumo do conteúdo textual para telas administrativas."""

        return self.texto[:80]


class TabelaItemLinha(models.Model):
    """Linha de item tabelado associada a um `ItemSessao`.

    Entidade voltada ao trecho de planilha do TR (descrição, códigos e quantidade).
    """

    item = models.ForeignKey(
        ItemSessao,
        on_delete=models.CASCADE,
        related_name="tabela_linhas",
    )
    ordem = models.PositiveIntegerField(default=1)
    descricao = models.TextField("Descricao")
    catmat_catser = models.CharField("CATMAT/CATSER", max_length=120, blank=True)
    siafisico = models.CharField("Siafisico", max_length=120, blank=True)
    unidade_fornecimento = models.CharField("Unidade de Fornecimento", max_length=120, blank=True)
    quantidade = models.DecimalField("Quantidade", max_digits=14, decimal_places=2)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Mantém ordenação estável das linhas da tabela vinculada ao item."""

        ordering = ["ordem", "id"]

    def __str__(self):
        """Retorna resumo de linha tabelada para debug e administração."""

        return f"{self.ordem} - {self.descricao[:60]}"


class EtpTic(models.Model):
    """Documento ETP TIC com preenchimento em múltiplas seções."""

    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        CONCLUIDO = "CONCLUIDO", "Concluido"

    DECLARACAO_PADRAO = "Esta equipe de planejamento declara viavel esta contratacao."

    titulo = models.CharField("Titulo", max_length=180, blank=True)
    numero_processo_servico = models.CharField("Numero do processo servico", max_length=120)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RASCUNHO)
    secao_atual = models.PositiveIntegerField(default=1)

    descricao_necessidade = models.TextField(blank=True)
    area_requisitante = models.CharField(max_length=180, blank=True)
    responsavel_area = models.CharField(max_length=180, blank=True)
    necessidades_negocio = models.TextField(blank=True)
    necessidades_tecnologicas = models.TextField(blank=True)
    demais_requisitos = models.TextField(blank=True)
    estimativa_demanda = models.TextField(blank=True)
    levantamento_solucoes = models.TextField(blank=True)
    analise_comparativa_solucoes = models.TextField(blank=True)
    solucoes_inviaveis = models.TextField(blank=True)
    analise_comparativa_custos_tco = models.TextField(blank=True)
    descricao_solucao_tic = models.TextField(blank=True)
    estimativa_custo_valor = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    estimativa_custo_texto = models.TextField(blank=True)
    justificativa_tecnica = models.TextField(blank=True)
    justificativa_economica = models.TextField(blank=True)
    beneficios_contratacao = models.TextField(blank=True)
    providencias_adotadas = models.TextField(blank=True)
    declaracao_viabilidade = models.TextField(default=DECLARACAO_PADRAO)
    justificativa_viabilidade = models.TextField(blank=True)

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etps_tic_criados",
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etps_tic_atualizados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-atualizado_em", "-id"]

    def __str__(self):
        base = self.titulo or self.numero_processo_servico
        return f"ETP TIC - {base}"
