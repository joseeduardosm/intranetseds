"""
Modelos de domínio do app `ramais`.

Este módulo define a entidade principal de pessoas/ramais da intranet, com
dados de contato, vínculo com usuário do Django e hierarquia para organograma.
As classes aqui são usadas por views, formulários, admin e templates.
"""
from django.contrib.auth import get_user_model
from django.db import models


User = get_user_model()


class PessoaRamal(models.Model):
    """
    Entidade de domínio que representa uma pessoa no diretório de ramais.

    No negócio, cada registro centraliza dados de contato e posição
    organizacional de um servidor/colaborador, com suporte a:
    - vínculo opcional com conta de autenticação (`usuario`);
    - hierarquia (superior/subordinados) para organograma;
    - dados funcionais complementares (jornada, intervalos, regime).
    """
    usuario = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        null=True,
        related_name="ramal_perfil",
    )
    # Nome completo da pessoa.
    nome = models.CharField(max_length=200, blank=True)
    # Cargo/funcao na organizacao.
    cargo = models.CharField(max_length=120, blank=True, default="")
    # Setor/departamento.
    setor = models.CharField(max_length=120, blank=True, default="")
    # Numero do ramal telefonico.
    ramal = models.CharField(max_length=20, blank=True, default="")
    # Email corporativo.
    email = models.EmailField(blank=True)
    # Pequena bio exibida no detalhe do ramal.
    bio = models.TextField(blank=True)
    # Jornada de trabalho semanal (em horas).
    jornada_horas_semanais = models.PositiveIntegerField(null=True, blank=True)
    # Horario de trabalho padrao.
    horario_trabalho_inicio = models.TimeField(null=True, blank=True)
    horario_trabalho_fim = models.TimeField(null=True, blank=True)
    # Intervalo de almoco/descanso.
    intervalo_inicio = models.TimeField(null=True, blank=True)
    intervalo_fim = models.TimeField(null=True, blank=True)
    # Documento de identificacao.
    rg = models.CharField(max_length=30, blank=True, default="")
    # Marcadores funcionais.
    regime_plantao = models.BooleanField(default=False)
    horario_estudante = models.BooleanField(default=False)
    # Foto opcional para avatar.
    foto = models.ImageField(upload_to='ramais/', blank=True, null=True)
    # Referencia ao superior imediato (auto-relacionamento).
    superior = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinados',
    )
    # Timestamp de atualizacao automatica.
    atualizado_em = models.DateTimeField(auto_now=True)
    # Usuario responsavel pela ultima alteracao.
    atualizado_por = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ramais_atualizados',
    )

    class Meta:
        # Ordena os registros por nome.
        ordering = ['nome']
        # Permissão customizada para acesso ao organograma.
        permissions = [
            ("view_organograma", "Pode visualizar o organograma"),
        ]

    @property
    def nome_display(self) -> str:
        """
        Resolve o nome que deve ser exibido na interface.

        Regra de negócio:
        - Se existir usuário associado, prioriza os dados da conta para evitar
          divergência entre cadastro de ramal e perfil de autenticação.
        - Caso contrário, usa o valor manual do campo `nome`.

        Retorno:
            str: nome final para exibição em lista, detalhe e admin.
        """
        if self.usuario:
            return (
                self.usuario.get_full_name()
                or self.usuario.first_name
                or self.usuario.username
            )
        return self.nome

    @property
    def email_display(self) -> str:
        """
        Resolve o e-mail final de exibição.

        Regra de negócio:
        - Quando há usuário associado com e-mail preenchido, essa informação é
          tratada como fonte principal de verdade.

        Retorno:
            str: e-mail exibido ao usuário final.
        """
        if self.usuario and self.usuario.email:
            return self.usuario.email
        return self.email

    def _sync_from_user(self):
        """
        Sincroniza campos locais a partir da conta de usuário vinculada.

        Problema resolvido:
        - Evitar inconsistência entre dados do perfil de autenticação e registro
          de ramal, especialmente para nome e e-mail.

        Regras aplicadas:
        - Nome do usuário sobrescreve `nome` quando disponível.
        - E-mail do usuário preenche `email` apenas se o campo local estiver vazio.
        """
        if not self.usuario:
            return
        nome = self.usuario.get_full_name() or self.usuario.first_name or self.usuario.username
        if nome:
            self.nome = nome
        if self.usuario.email and not self.email:
            self.email = self.usuario.email

    def _sync_to_user(self):
        """
        Propaga alterações de e-mail do ramal para a conta de usuário.

        Problema resolvido:
        - Manter comunicação consistente entre módulos que leem e-mail direto do
          modelo de autenticação.

        Regra aplicada:
        - Atualiza apenas quando há diferença para evitar escrita desnecessária.
        """
        if not self.usuario:
            return
        if self.email and self.usuario.email != self.email:
            self.usuario.email = self.email
            self.usuario.save(update_fields=["email"])

    def save(self, *args, **kwargs):
        """
        Persiste o registro garantindo sincronização e trilha de auditoria.

        Parâmetros:
            *args: argumentos posicionais padrão do `models.Model.save`.
            **kwargs: argumentos nomeados padrão do `models.Model.save`.

        Fluxo de negócio:
        1. Sincroniza dados básicos a partir do usuário vinculado.
        2. Tenta identificar usuário corrente via `auditoria.threadlocal`.
        3. Registra esse usuário em `atualizado_por` quando autenticado.
        4. Salva a entidade no banco.
        5. Sincroniza e-mail de volta para o usuário, se necessário.

        Integração externa:
        - `auditoria.threadlocal.get_current_user`: mecanismo transversal para
          capturar o ator da requisição sem acoplamento direto com views.
        """
        self._sync_from_user()
        try:
            from auditoria.threadlocal import get_current_user
        except Exception:
            user = None
        else:
            user = get_current_user()
        if getattr(user, "is_authenticated", False):
            self.atualizado_por = user
        super().save(*args, **kwargs)
        self._sync_to_user()
        if self.usuario_id:
            try:
                from usuarios.models import UserAccessState

                UserAccessState.objects.filter(user_id=self.usuario_id).update(
                    force_profile_update=False
                )
            except Exception:
                pass

    def __str__(self) -> str:
        """
        Retorna representação textual da entidade.

        Retorno:
            str: nome exibível e ramal para identificação rápida.
        """
        return f'{self.nome_display} - {self.ramal}'
