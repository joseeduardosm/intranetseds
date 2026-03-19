# Reserva de Salas

## Descrição do propósito do app

O app `reserva_salas` gerencia o ciclo completo de agendamento de salas na intranet:

- cadastro de salas e seus recursos (infraestrutura disponível);
- criação, edição, consulta e exclusão de reservas;
- prevenção de conflitos de horário na mesma sala;
- suporte a reservas recorrentes (diária, semanal, quinzenal e mensal);
- rastreabilidade de quem registrou cada reserva.

Na arquitetura Django do projeto, este app segue o padrão MVT:

- **Models** (`models.py`): entidades `Sala` e `Reserva`.
- **Forms** (`forms.py`): validações de negócio e recorrência.
- **Views** (`views.py`): fluxos HTTP com CBVs (CRUD e listagens).
- **Templates** (`templates/reserva_salas/`): renderização das telas.
- **URLs** (`urls.py`): roteamento local incluído no projeto principal.

## Modelos existentes e o que representam

### `Sala`
Representa um ambiente físico reservável.

Campos principais:
- identificação: `nome`, `localizacao`, `cor`;
- restrição operacional: `capacidade`;
- recursos disponíveis: `televisao`, `projetor`, `som`, `microfone_evento`, `som_evento`, `mesa_som_evento`, `videowall`, `wifi`.

Regras relevantes:
- cor é atribuída automaticamente (paleta interna) para uso visual no calendário;
- ordenação padrão por nome.

### `Reserva`
Representa um agendamento de evento em uma sala e intervalo de tempo.

Campos principais:
- vínculo: `sala` (FK para `Sala`);
- agenda: `data`, `hora_inicio`, `hora_fim`;
- negócio: `nome_evento`, `responsavel_evento`, `quantidade_pessoas`;
- recursos solicitados para o evento (mesmos booleanos de `Sala`);
- auditoria: `criado_em`, `registrado_por` (usuário), `serie_id` (grupo de recorrência).

Regras relevantes:
- ordenação por data decrescente e hora de início;
- em reservas recorrentes, todas as ocorrências compartilham o mesmo `serie_id`.

## Principais fluxos de negócio

1. **Cadastro de sala**
- usuário com permissão cria/edita salas e define recursos disponíveis.

2. **Criação de reserva**
- formulário valida:
  - capacidade da sala vs. quantidade de pessoas;
  - recursos solicitados vs. recursos da sala;
  - intervalo de horário válido (`hora_fim > hora_inicio`);
  - inexistência de sobreposição com reservas existentes.

3. **Recorrência de reserva**
- ao criar, usuário pode definir recorrência e data fim;
- sistema gera uma reserva por data de ocorrência e associa todas ao mesmo `serie_id`.

4. **Edição/Exclusão em lote de série**
- para reservas com `serie_id`, usuário pode aplicar ação na ocorrência atual ou em toda a série (`apply_scope`).

5. **Rastreabilidade de autoria**
- `registrado_por` é preenchido com usuário autenticado (quando disponível), inclusive via integração com `auditoria.threadlocal`.

## Dependências com outros apps do projeto

- **`intranet` (projeto principal)**:
  - inclui as rotas do app sob o prefixo `/reserva-salas/`.

- **`auditoria`**:
  - integração opcional via `auditoria.threadlocal.get_current_user` para preencher `registrado_por` automaticamente.

- **`ramais` / perfil do usuário**:
  - views consultam `user.ramal_perfil` para exibir ramal e e-mail do usuário que registrou a reserva.

- **`django.contrib.auth`**:
  - autenticação e permissões (`UserPassesTestMixin` e `PermissionRequiredMixin`).

## Endpoints disponíveis

Prefixo global do app no projeto: **`/reserva-salas/`**

### Salas
- `GET /reserva-salas/` - listagem de salas + dados de agenda (`salas_list`)
- `GET|POST /reserva-salas/nova/` - criar sala (`salas_create`)
- `GET /reserva-salas/<pk>/` - detalhe da sala (`salas_detail`)
- `GET|POST /reserva-salas/<pk>/editar/` - editar sala (`salas_update`)
- `GET|POST /reserva-salas/<pk>/excluir/` - excluir sala (`salas_delete`)

### Reservas
- `GET /reserva-salas/reservas/` - listagem de reservas (`reservas_list`)
- `GET|POST /reserva-salas/reservas/nova/` - criar reserva (`reservas_create`)
- `GET /reserva-salas/reservas/<pk>/` - detalhe da reserva (`reservas_detail`)
- `GET|POST /reserva-salas/reservas/<pk>/editar/` - editar reserva (`reservas_update`)
- `GET|POST /reserva-salas/reservas/<pk>/excluir/` - excluir reserva (`reservas_delete`)

## Observações operacionais

- Não há endpoints de API REST no app atualmente; o fluxo é orientado a páginas HTML.
- O app utiliza CBVs do Django e templates server-side para renderização.
- O módulo `tests.py` está como estrutura base e pode ser expandido para cobrir validações de conflito e recorrência.
