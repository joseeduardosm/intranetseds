# App `ramais`

## Descrição do propósito do app
O app `ramais` implementa o diretório interno de pessoas da organização,
centralizando dados de contato, informações funcionais e relações de hierarquia.
Ele também fornece a visualização de organograma com base na relação
superior/subordinados.

Na arquitetura do projeto Django, o app oferece:
- modelo de domínio para perfil de ramal;
- formulários com política de edição por permissão;
- views web (lista, detalhe, CRUD e organograma);
- templates para apresentação dos dados.

## Modelos existentes e o que representam
## `PessoaRamal`
Representa um perfil de pessoa no diretório institucional.

Campos e conceitos relevantes:
- vínculo opcional com conta de autenticação (`usuario`);
- dados cadastrais e de contato (`nome`, `ramal`, `email`, `foto`, `bio`);
- dados funcionais (`jornada_horas_semanais`, horários, regime de plantão);
- hierarquia organizacional via auto-relacionamento (`superior`);
- trilha de atualização (`atualizado_em`, `atualizado_por`).

Regras de negócio relevantes do model:
- sincronização de nome/e-mail com o usuário autenticado quando há vínculo;
- atualização de e-mail do `User` após salvar, quando necessário;
- captura do ator da alteração via integração com `auditoria.threadlocal`.

## Principais fluxos de negócio
1. Listagem de ramais com busca
- Endpoint lista ramais vinculados a usuário e permite busca textual ampla
  por nome, usuário, e-mail, setor, cargo e ramal.

2. Detalhe de ramal
- Exibe dados completos de uma pessoa, incluindo superior imediato.

3. Criação de ramal
- Exige permissão `ramais.add_pessoaramal`.
- Usa formulário com regras de campos condicionais por usuário.

4. Edição de ramal
- Staff/permissão global pode editar qualquer registro.
- Usuário comum pode editar apenas o próprio perfil (`usuario_id == request.user.id`).

5. Exclusão de ramal
- Exige permissão `ramais.delete_pessoaramal`.

6. Organograma
- Carrega conjunto de pessoas e monta árvore hierárquica em memória.
- Algoritmo usa mapa por id para montar a estrutura em O(n).

## Dependências com outros apps do projeto
- `auditoria`
  - Integração com `auditoria.threadlocal.get_current_user` para registrar
    `atualizado_por` automaticamente.
- `folha_ponto`
  - Permissões `folha_ponto.change_feriado` e
    `folha_ponto.change_feriasservidor` controlam edição de campos funcionais.
- `django.contrib.auth` / app de `usuarios`
  - Vínculo de `PessoaRamal` com conta `User` e regras de autenticação/autorização.
- Templates do app:
  - `templates/ramais/ramais_list.html`
  - `templates/ramais/ramais_detail.html`
  - `templates/ramais/ramais_form.html`
  - `templates/ramais/ramais_confirm_delete.html`
  - `templates/ramais/organograma.html`
  - `templates/ramais/organograma_node.html`

## Endpoints disponíveis
Considerando inclusão no roteador principal com prefixo `/ramais/`:

- `GET /ramais/` -> lista e busca de ramais (`name='ramais_list'`)
- `GET /ramais/organograma/` -> visualização de organograma (`name='organograma'`)
- `GET /ramais/novo/` -> formulário de criação (`name='ramais_create'`)
- `POST /ramais/novo/` -> cria ramal
- `GET /ramais/<int:pk>/` -> detalhe (`name='ramais_detail'`)
- `GET /ramais/<int:pk>/editar/` -> formulário de edição (`name='ramais_update'`)
- `POST /ramais/<int:pk>/editar/` -> atualiza ramal
- `GET /ramais/<int:pk>/excluir/` -> confirmação de exclusão (`name='ramais_delete'`)
- `POST /ramais/<int:pk>/excluir/` -> exclui ramal

