# Diario de Bordo

## Propósito do app
O app `diario_bordo` gerencia blocos de trabalho e atualizações operacionais (incrementos), permitindo acompanhar status, histórico de evolução, participantes responsáveis e confirmação de ciência por usuário.

Na arquitetura Django do projeto, ele se integra principalmente com:
- `models.py`: persistência de blocos, incrementos e leituras;
- `views.py`: fluxos HTTP de listagem, detalhe, relatórios e CRUD;
- `forms.py`: formulários de criação/edição;
- templates `diario_bordo/*`: renderização de telas e relatórios.

## Modelos existentes
- `BlocoTrabalho`: unidade principal de acompanhamento (nome, descrição, status, participantes, vínculo opcional com contrato e metadados de atualização).
- `Incremento`: registro de atualização de um bloco (texto, anexo/imagem, autor e data).
- `IncrementoCiencia`: confirmação de leitura/ciência de um incremento por usuário.
- `BlocoLeitura`: cursor de leitura por usuário para cada bloco (último incremento visto).

## Principais fluxos de negócio
1. Criação de bloco:
- usuário cria o bloco;
- criador é automaticamente adicionado como participante;
- sistema gera incremento automático de criação.

2. Atualização de bloco:
- edição de dados e status;
- novos participantes recebem incremento automático de inclusão.

3. Inclusão de incremento:
- incremento é vinculado ao bloco e ao autor autenticado;
- se o bloco estiver `NOVO`, muda para `EM_ANDAMENTO`.

4. Ciência de incremento:
- participante registra ciência explícita;
- sistema evita duplicidade por usuário/incremento;
- leitura do bloco é atualizada.

5. Listagem/relatórios:
- filtros por status, termo e legenda de alerta;
- cálculo de "dias desde última atualização";
- classes visuais de criticidade para priorização.

## Dependências com outros apps do projeto
- `contratos`:
  - `BlocoTrabalho` possui `ForeignKey` opcional para `contratos.Contrato`.
- `auth` (Django):
  - participantes, autores, responsáveis de atualização e ciência.
- `auditoria` (indireta):
  - alguns fluxos do projeto usam usuário corrente em thread-local para rastreabilidade global.

## Endpoints disponíveis
Baseado em `diario_bordo/urls.py`:

- `GET /diario-bordo/` → `diario_bordo_list`
- `GET /diario-bordo/relatorio/` → `diario_bordo_relatorio`
- `GET /diario-bordo/relatorio/<pk>/` → `diario_bordo_relatorio_detalhe`
- `GET|POST /diario-bordo/novo/` → `diario_bordo_create`
- `GET /diario-bordo/<pk>/` → `diario_bordo_detail`
- `GET|POST /diario-bordo/<pk>/editar/` → `diario_bordo_update`
- `GET|POST /diario-bordo/<pk>/excluir/` → `diario_bordo_delete`
- `GET|POST /diario-bordo/<pk>/incrementos/novo/` → `diario_bordo_incremento_create`
- `POST /diario-bordo/incrementos/<pk>/ciente/` → `diario_bordo_incremento_ciente`
- `GET|POST /diario-bordo/incrementos/<pk>/editar/` → `diario_bordo_incremento_update`
- `GET|POST /diario-bordo/incrementos/<pk>/excluir/` → `diario_bordo_incremento_delete`

Observação: os prefixos reais dependem da inclusão deste `urls.py` no roteador principal do projeto.
