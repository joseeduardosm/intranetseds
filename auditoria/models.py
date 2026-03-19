"""
Modelos de dominio do app `auditoria`.

Este modulo concentra a persistencia de eventos de auditoria do sistema
em uma estrutura generica (`AuditLog`) baseada em `ContentType`, o que
permite rastrear mudancas de qualquer model de outros apps.
As views de auditoria consultam esta entidade para montar historico e
filtros de investigacao operacional.
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class AuditLog(models.Model):
    """
    Registro generico de auditoria para qualquer modelo do sistema.

    Entidade de negocio:
    - cada linha representa uma acao relevante (CRUD/M2M) sobre um objeto;
    - referencia o alvo auditado por chave generica (`content_type` + `object_id`);
    - armazena metadados minimos para rastreabilidade (usuario, data, diff).
    """

    class Action(models.TextChoices):
        """Enum de acoes auditaveis reconhecidas pelo sistema."""

        CREATE = "CREATE", "Criacao"
        UPDATE = "UPDATE", "Edicao"
        DELETE = "DELETE", "Exclusao"
        M2M_ADD = "M2M_ADD", "Relacionamento adicionado"
        M2M_REMOVE = "M2M_REMOVE", "Relacionamento removido"
        M2M_CLEAR = "M2M_CLEAR", "Relacionamento limpo"

    timestamp = models.DateTimeField(auto_now_add=True)
    # Usuario que executou a acao (pode ser nulo em tarefas automaticas).
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    # Ligacao generica com o objeto auditado.
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=64)
    content_object = GenericForeignKey("content_type", "object_id")
    object_repr = models.CharField(max_length=255)
    # Diff simples (antes/depois) ou detalhes de M2M.
    changes = models.JSONField(blank=True, null=True)

    class Meta:
        """Ordena do evento mais recente para o mais antigo."""

        ordering = ["-timestamp"]

    MODEL_LABELS = {
        "ramais.pessoaramal": "dados de contato",
        "diario_bordo.blocotrabalho": "bloco de trabalho",
        "diario_bordo.incremento": "incremento",
        "reserva_salas.reserva": "reserva de sala",
        "reserva_salas.sala": "sala",
        "contratos.contrato": "contrato",
        "noticias.noticia": "notícia",
        "prepostos.preposto": "preposto",
        "empresas.empresa": "empresa",
        "administracao.adconfiguration": "configuração de autenticação",
        "administracao.atalhoservico": "atalho de serviço",
        "folha_ponto.feriado": "feriado",
        "folha_ponto.feriasservidor": "férias de servidor",
        "folha_ponto.configuracaorh": "configuração de RH",
    }
    CONTACT_FIELD_LABELS = {
        "ramal": "ramal",
        "email": "e-mail",
        "setor": "setor",
        "cargo": "cargo",
        "bio": "bio",
        "foto": "foto",
        "rg": "RG",
    }

    def __str__(self) -> str:
        """
        Representacao compacta do log para interfaces administrativas.

        Retorno:
        - `str`: data/hora + tipo da acao + representacao do objeto.
        """

        return f"{self.timestamp:%d/%m/%Y %H:%M} - {self.action} - {self.object_repr}"

    def _model_key(self) -> str:
        """
        Monta chave canonica `app_label.model` do alvo auditado.

        Retorno:
        - `str`: chave completa para lookup de labels semanticos.
        """

        if not self.content_type_id:
            return ""
        return f"{self.content_type.app_label}.{self.content_type.model}"

    def _entity_label(self) -> str:
        """
        Resolve nome amigavel da entidade auditada.

        Retorno:
        - `str`: label de dominio para mensagens de resumo.

        Regra de negocio:
        - prioriza mapeamentos curados em `MODEL_LABELS`;
        - aplica fallback para nome tecnico quando nao mapeado.
        """

        key = self._model_key()
        if key in self.MODEL_LABELS:
            return self.MODEL_LABELS[key]
        if self.content_type_id:
            return self.content_type.model.replace("_", " ")
        return "registro"

    def _changed_fields(self):
        """
        Extrai lista de campos alterados a partir do payload `changes`.

        Retorno:
        - `list[str]`: nomes de campos alterados quando `changes` e dict.
        """

        if isinstance(self.changes, dict):
            return list(self.changes.keys())
        return []

    def _contact_update_detail(self) -> str:
        """
        Gera sufixo resumido para mudancas em cadastro de contato.

        Retorno:
        - `str`: texto com ate 4 labels de campos modificados.

        Regra de negocio:
        - limita quantidade exibida para manter leitura objetiva no feed.
        """

        all_labels = []
        has_more = False
        labels = []
        for field in self._changed_fields():
            label = self.CONTACT_FIELD_LABELS.get(field)
            if label:
                all_labels.append(label)
        if not all_labels:
            return ""
        if len(all_labels) > 4:
            labels = all_labels[:4]
            has_more = True
        else:
            labels = all_labels
        sufixo = "..." if has_more else ""
        return f" (campos: {', '.join(labels)}{sufixo})"

    @property
    def acao_resumo(self) -> str:
        """
        Gera frase legivel descrevendo a acao auditada.

        Retorno:
        - `str`: resumo textual orientado a usuario final.

        Regras de negocio:
        - aplica mensagens especializadas para entidades com vocabulário
          proprio (ramais e diario de bordo);
        - para updates, inclui amostra de campos alterados quando disponivel.
        """

        key = self._model_key()
        entity = self._entity_label()
        objeto = self.object_repr or entity

        if key == "ramais.pessoaramal":
            if self.action == self.Action.CREATE:
                return f"Criou cadastro de dados de contato para {objeto}."
            if self.action == self.Action.UPDATE:
                return f"Atualizou dados de contato de {objeto}{self._contact_update_detail()}."
            if self.action == self.Action.DELETE:
                return f"Excluiu cadastro de dados de contato de {objeto}."

        if key == "diario_bordo.blocotrabalho":
            if self.action == self.Action.CREATE:
                return f"Criou bloco de trabalho: {objeto}."
            if self.action == self.Action.UPDATE:
                return f"Atualizou bloco de trabalho: {objeto}."
            if self.action == self.Action.DELETE:
                return f"Excluiu bloco de trabalho: {objeto}."

        if key == "diario_bordo.incremento":
            if self.action == self.Action.CREATE:
                return f"Registrou incremento no Diário de Bordo: {objeto}."
            if self.action == self.Action.UPDATE:
                return f"Atualizou incremento do Diário de Bordo: {objeto}."
            if self.action == self.Action.DELETE:
                return f"Excluiu incremento do Diário de Bordo: {objeto}."

        if self.action == self.Action.CREATE:
            return f"Criou {entity}: {objeto}."
        if self.action == self.Action.UPDATE:
            if isinstance(self.changes, dict) and self.changes:
                campos = ", ".join(list(self.changes.keys())[:4])
                sufixo = "..." if len(self.changes.keys()) > 4 else ""
                return f"Atualizou {entity}: {objeto} (campos: {campos}{sufixo})."
            return f"Atualizou {entity}: {objeto}."
        if self.action == self.Action.DELETE:
            return f"Excluiu {entity}: {objeto}."
        if self.action == self.Action.M2M_ADD:
            return f"Adicionou relacionamento em {entity}: {objeto}."
        if self.action == self.Action.M2M_REMOVE:
            return f"Removeu relacionamento em {entity}: {objeto}."
        if self.action == self.Action.M2M_CLEAR:
            return f"Limpou relacionamentos em {entity}: {objeto}."
        return f"Executou ação em {entity}: {objeto}."
