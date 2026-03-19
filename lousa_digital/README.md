# App `lousa_digital`

## Descrição do propósito do app
O app `lousa_digital` implementa um quadro de acompanhamento de processos (SEI), com foco em visibilidade operacional, controle de encaminhamentos por destino e monitoramento de prazo (SLA).

Ele permite:
- cadastrar e editar processos;
- abrir e devolver encaminhamentos com prazo;
- registrar notas e eventos de timeline;
- acompanhar status (`EM_ABERTO` / `CONCLUIDO`) de forma automática com base nos encaminhamentos ativos.

## Modelos existentes e o que representam
- `Processo`:
  - entidade central da lousa;
  - armazena identificação SEI, assunto, caixa de origem, status e metadados de autoria/grupo.
- `Encaminhamento`:
  - representa envio do processo para um destino com data de prazo;
  - guarda início, conclusão e usuários responsáveis;
  - oferece cálculos de prazo (minutos totais/decorridos, percentual consumido).
- `EventoTimeline`:
  - histórico cronológico de ações do processo (criação, edição, encaminhamento, devolução, nota e mudança de status).

## Principais fluxos de negócio
- Listagem da lousa:
  - aplica filtro de visibilidade por usuário/grupo;
  - calcula prioridade por prazo do encaminhamento ativo;
  - permite busca textual e filtro por status.
- Ciclo de processo:
  - criação registra evento de timeline;
  - edição atualiza autor da alteração e registra evento;
  - exclusão remove processo (dentro da visibilidade permitida).
- Encaminhamentos:
  - criação mantém processo em aberto e registra evento;
  - devolução conclui encaminhamento, registra evento e recalcula status do processo.
- Timeline:
  - permite inclusão de notas livres e mantém histórico auditável por usuário/data.
- Importação em lote:
  - comando `importar_lousa_csv` cria/atualiza processos e encaminhamentos a partir de CSV.

## Dependências com outros apps do projeto
- Dependências internas:
  - usa `auth` do Django (`User`, `Group`) para autoria, visibilidade e permissões de acesso.
- Dependências externas ao app:
  - não depende diretamente de modelos de outros apps do projeto para regra principal da lousa.
- Infraestrutura Django:
  - `messages`, CBVs genéricas, ORM avançado (`Exists`, `Subquery`, `Prefetch`, `Q`).

## Endpoints disponíveis
Rotas definidas em `lousa_digital/urls.py` (normalmente sob prefixo do projeto, por exemplo `/lousa-digital/`):

- `GET /` -> `lousa_digital_list` (lista de processos)
- `GET|POST /novo/` -> `lousa_digital_create`
- `GET /<pk>/` -> `lousa_digital_detail`
- `GET|POST /<pk>/editar/` -> `lousa_digital_update`
- `GET|POST /<pk>/excluir/` -> `lousa_digital_delete`
- `POST /<pk>/encaminhar/` -> `lousa_digital_encaminhar`
- `POST /<pk>/encaminhamentos/<encaminhamento_id>/devolver/` -> `lousa_digital_devolver`
- `POST /<pk>/nota/` -> `lousa_digital_nota`

## Comando de gestão
- `python manage.py importar_lousa_csv --arquivo <caminho.csv> --username <usuario>`
  - importa dados de processos/encaminhamentos em lote com transação atômica.
- `python manage.py notificar_prazos_lousa`
  - envia alerta por e-mail para encaminhamentos ativos com prazo entre hoje e os próximos 3 dias;
  - envia para o e-mail do encaminhamento e também para usuários do grupo que cadastrou o processo (`grupo_insercao`), quando houver e-mails válidos;
  - registra no output da execução e na trilha de auditoria os envios realizados (processo, prazo e destinatários);
  - notifica apenas uma vez por encaminhamento (campo `notificado_72h_em`).

## Agendamento diário (cron)
- Exemplo de execução diária às 00:00:
  - `0 0 * * * /caminho/venv/bin/python /caminho/projeto/manage.py notificar_prazos_lousa`
- Timezone do projeto: `America/Sao_Paulo`.
