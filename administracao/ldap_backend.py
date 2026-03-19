"""
Backend de autenticacao LDAP/AD para o app `administracao`.

Este modulo integra o Django Auth com Active Directory:
- valida credenciais no AD;
- cria/atualiza usuario local no banco Django;
- sincroniza metadados basicos (nome/email);
- garante grupos de leitura padrao no ecossistema da intranet.

Fluxo arquitetural:
- chamado pelo mecanismo de autenticacao (`AUTHENTICATION_BACKENDS`);
- consulta `ADConfiguration` em banco para parametros de conexao;
- comunica com servidor LDAP externo via `ldap3`.
"""

from __future__ import annotations

from typing import Optional
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import Group
from django.db.utils import OperationalError, ProgrammingError

from .models import ADConfiguration
from usuarios.permissions import PROFILE_DEFINITIONS, build_group_name, ensure_profiles


UserModel = get_user_model()
logger = logging.getLogger(__name__)


def _assign_read_groups(user):
    """
    Vincula o usuario aos grupos padrao de leitura entre os modulos.

    Parametros:
    - `user`: instancia do usuario Django autenticado/sincronizado.

    Retorno:
    - Nao retorna valor; aplica side-effect em M2M `user.groups`.

    Regra de negocio:
    - Todo usuario autenticado via AD recebe o baseline de acesso de leitura,
      incluindo excecao operacional para "Diario de Bordo / Edicao".
    """

    ensure_profiles()
    groups = []
    for app_label in PROFILE_DEFINITIONS.keys():
        # Consulta por nome canonico do grupo para manter compatibilidade com
        # padrao de perfis centralizado no modulo `usuarios.permissions`.
        group_name = build_group_name(app_label, "Leitura")
        group = Group.objects.filter(name=group_name).first()
        if group:
            groups.append(group)
    diario_edicao = Group.objects.filter(
        name=build_group_name("Diario de Bordo", "Edicao")
    ).first()
    if diario_edicao and diario_edicao not in groups:
        groups.append(diario_edicao)
    if groups:
        user.groups.add(*groups)


class LDAPBackend(BaseBackend):
    """Autentica via AD e clona o usuario para o banco local."""

    def authenticate(self, request, username: Optional[str] = None, password: Optional[str] = None, **kwargs):
        """
        Executa autenticacao no AD e materializa usuario local.

        Parametros:
        - `request`: request HTTP opcional do Django auth.
        - `username`: login informado pelo usuario.
        - `password`: senha informada.
        - `**kwargs`: parametros extras do pipeline de autenticacao.

        Retorno:
        - Instancia de usuario autenticado quando sucesso.
        - `None` quando qualquer etapa falha.

        Regras de negocio relevantes:
        - Nao autentica sem configuracao AD persistida.
        - Usa bind de servico para localizar DN do usuario.
        - Valida senha do usuario com multiplas estrategias de bind
          (DN -> UPN -> NTLM) para aumentar compatibilidade com AD.
        """

        if not username or not password:
            return None

        try:
            # Consulta unica de configuracao: o sistema opera com apenas um
            # endpoint AD ativo por ambiente.
            config = ADConfiguration.objects.first()
        except (OperationalError, ProgrammingError) as exc:
            logger.warning("Tabela de configuracao AD indisponivel: %s", exc)
            return None
        if not config:
            return None

        try:
            from ldap3 import Connection, Server, NONE, SUBTREE, NTLM
            from ldap3.core.exceptions import LDAPBindError
        except Exception:
            return None

        server = Server(
            config.server_host,
            port=config.server_port,
            use_ssl=config.use_ssl,
            connect_timeout=5,
            get_info=NONE,
        )
        try:
            connection = Connection(
                server,
                user=config.bind_dn,
                password=config.bind_password,
                auto_bind=True,
            )
        except Exception as exc:
            # Sem bind de servico nao ha como pesquisar o DN do usuario.
            logger.warning("LDAP bind com conta de servico falhou: %s", exc)
            return None

        try:
            # Se veio com @, tenta userPrincipalName; senao, sAMAccountName.
            if "@" in username:
                search_filter = f"(userPrincipalName={username})"
            else:
                search_filter = f"(sAMAccountName={username})"
            connection.search(
                search_base=config.base_dn,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=["distinguishedName", "givenName", "sn", "displayName", "mail", "sAMAccountName"],
            )
            # Resultado esperado: no maximo um usuario ativo para o login.
            if not connection.entries:
                logger.warning("LDAP nao encontrou usuario %s na base %s", username, config.base_dn)
                return None
            entry = connection.entries[0]
            user_dn = str(entry.distinguishedName)

            # Tenta bind com o usuario encontrado.
            try:
                user_conn = Connection(server, user=user_dn, password=password, auto_bind=True)
                user_conn.unbind()
            except LDAPBindError as exc:
                # Fallback: tenta UPN derivado do base_dn (dc=dominio,dc=local)
                domain_parts = []
                for part in config.base_dn.split(","):
                    part = part.strip()
                    if part.lower().startswith("dc="):
                        domain_parts.append(part.split("=", 1)[1])
                upn = None
                if domain_parts:
                    upn = f"{username}@{'.'.join(domain_parts)}"
                    try:
                        user_conn = Connection(server, user=upn, password=password, auto_bind=True)
                        user_conn.unbind()
                    except LDAPBindError as exc_upn:
                        # Fallback NTLM: DOMINIO\\usuario
                        domain = domain_parts[0] if domain_parts else ""
                        if domain:
                            ntlm_user = f"{domain}\\{username}"
                            try:
                                user_conn = Connection(
                                    server,
                                    user=ntlm_user,
                                    password=password,
                                    authentication=NTLM,
                                    auto_bind=True,
                                )
                                user_conn.unbind()
                            except LDAPBindError as exc_ntlm:
                                logger.warning(
                                    "LDAP bind falhou (DN/UPN/NTLM) para %s: %s | %s | %s",
                                    username,
                                    exc,
                                    exc_upn,
                                    exc_ntlm,
                                )
                                return None
                        else:
                            logger.warning(
                                "LDAP bind falhou (DN/UPN) para %s: %s | %s",
                                username,
                                exc,
                                exc_upn,
                            )
                            return None
                else:
                    logger.warning("LDAP bind falhou (DN) para %s: %s", username, exc)
                    return None

            username_value = str(entry.sAMAccountName) if entry.sAMAccountName else username
            email_value = str(entry.mail) if entry.mail else ""
            first_name = str(entry.givenName) if entry.givenName else ""
            last_name = str(entry.sn) if entry.sn else ""
            if not first_name and not last_name and entry.displayName:
                display = str(entry.displayName)
                parts = display.split(" ", 1)
                first_name = parts[0]
                if len(parts) > 1:
                    last_name = parts[1]

            user, created = UserModel.objects.get_or_create(
                username=username_value,
                defaults={
                    "email": email_value,
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_active": True,
                },
            )
            if not created:
                update_fields = []
                # Atualizacao parcial para minimizar escrita no banco e manter
                # sincronismo dos dados de identificacao vindos do AD.
                if email_value and user.email != email_value:
                    user.email = email_value
                    update_fields.append("email")
                if first_name and user.first_name != first_name:
                    user.first_name = first_name
                    update_fields.append("first_name")
                if last_name and user.last_name != last_name:
                    user.last_name = last_name
                    update_fields.append("last_name")
                if update_fields:
                    user.save(update_fields=update_fields)
            else:
                user.set_unusable_password()
                user.save()

            # Cria ramal vazio se ainda nao existir.
            try:
                from ramais.models import PessoaRamal
            except Exception:
                PessoaRamal = None
            if PessoaRamal and not hasattr(user, "ramal_perfil"):
                # Garante integracao com modulo de ramais para novos usuarios
                # autenticados via AD sem perfil local previo.
                PessoaRamal.objects.create(
                    usuario=user,
                    cargo="",
                    setor="",
                    ramal="",
                    email=user.email or "",
                )

            _assign_read_groups(user)
            return user
        finally:
            # Encerra conexao LDAP independente de sucesso/falha da autenticacao.
            connection.unbind()

    def get_user(self, user_id):
        """
        Resolve usuario por ID para sessao autenticada do Django.

        Parametros:
        - `user_id`: chave primaria do usuario.

        Retorno:
        - Usuario correspondente quando existe.
        - `None` quando removido/invalido.
        """

        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
