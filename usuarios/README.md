# Usuários

## Descrição do propósito do app

O app `usuarios` centraliza a administração de contas e grupos da intranet,
utilizando os modelos nativos do Django (`auth.User`, `auth.Group`, `auth.Permission`) e adicionando regras de negócio específicas do projeto:

- gestão de perfis por módulo (Leitura, Edição, Administração);
- sincronização de privilégios do grupo `ADMIN` com flags nativas (`is_staff`, `is_superuser`);
- criação/edição de dados complementares de perfil de ramal (`ramais.PessoaRamal`);
- concessão automática de permissões iniciais para `reserva_salas` ao criar usuário.

Prefixo global de rota no projeto: **`/usuarios/`**.

## Modelos existentes e o que representam

O app **não define modelos próprios** em `usuarios/models.py`.

Ele opera sobre modelos de outros módulos:

- `django.contrib.auth.models.User`: conta de autenticação e permissões diretas;
- `django.contrib.auth.models.Group`: agrupamento de usuários e permissões coletivas;
- `django.contrib.auth.models.Permission`: permissões de baixo nível aplicadas por perfil;
- `ramais.models.PessoaRamal`: dados funcionais do usuário (ramal, cargo, setor, superior etc.);
- `auditoria.models.AuditLog`: utilizado no fluxo de exclusão de usuário para evitar conflito de integridade legado.

## Principais fluxos de negócio

1. **Gestão de usuários (CRUD)**
- criação e edição com formulário unificado (`UsuarioBaseForm` + variantes);
- definição de senha com hash seguro (`set_password`);
- aplicação de perfis e ajuste de grupo ADMIN;
- gravação de dados complementares no perfil de ramal.

2. **Gestão de grupos (CRUD)**
- associação de membros ao grupo;
- aplicação de permissões derivadas dos perfis selecionados;
- regra especial: grupo `ADMIN` recebe todas as permissões;
- proteção contra renomeação/exclusão indevida do grupo `ADMIN`.

3. **Sinais de automação**
- ao criar usuário, concessão automática de permissões padrão de `reserva_salas`;
- ao alterar vínculo usuário<->grupo, sincronização de `is_staff`/`is_superuser` com grupo `ADMIN`.

4. **Controle de acesso às telas do app**
- mixin `StaffOnlyMixin` restringe acesso a staff/superuser ou usuários com permissões de CRUD de `auth.User`.

## Dependências com outros apps do projeto

- `ramais`: persistência e leitura de `PessoaRamal` no formulário de usuário;
- `auditoria`: ajuste de vínculo de `AuditLog` durante exclusão de usuário;
- `reserva_salas`: permissões padrão concedidas na criação de usuário;
- `folha_ponto`: permissões específicas determinam edição de campos de jornada;
- `intranet` (projeto principal): inclusão das rotas sob `/usuarios/`.

## Endpoints disponíveis

### Usuários
- `GET /usuarios/` (`usuarios_list`)
- `GET|POST /usuarios/novo/` (`usuarios_create`)
- `GET|POST /usuarios/<pk>/editar/` (`usuarios_update`)
- `GET|POST /usuarios/<pk>/excluir/` (`usuarios_delete`)

### Grupos
- `GET /usuarios/grupos/` (`grupos_list`)
- `GET|POST /usuarios/grupos/novo/` (`grupos_create`)
- `GET|POST /usuarios/grupos/<pk>/editar/` (`grupos_update`)
- `GET|POST /usuarios/grupos/<pk>/excluir/` (`grupos_delete`)
