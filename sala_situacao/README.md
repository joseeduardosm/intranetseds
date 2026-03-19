# Sala de Situação

## Descrição do propósito do app

O app `sala_situacao` é o módulo de monitoramento estratégico/tático da intranet.
Ele organiza indicadores, processos e entregas em uma hierarquia de gestão,
permitindo acompanhar metas, evolução, ciclos de monitoramento, variáveis
matemáticas e anotações operacionais.

Além de telas de CRUD, o app oferece endpoints auxiliares para interface (sugestões,
marcadores e dados de gráfico) e fluxos de monitoramento periódico de resultados.

Prefixo de rotas no projeto: **`/sala-de-situacao/`**.

## Modelos existentes e o que representam

- `SalaSituacaoPainel`: configuração geral/identidade do painel.
- `Marcador`: etiqueta temática reutilizável para classificar itens.
- `MarcadorVinculoItem`: vínculo manual entre marcador e item do domínio (relação genérica via ContentType).
- `MarcadorVinculoAutomaticoGrupoItem`: vínculo automático de marcador com base em grupos.
- `ItemHierarquicoBase` (abstrato): base comum de metadados e comportamento hierárquico.
- `IndicadorBase` (abstrato): base comum para indicadores com regra de fórmula/monitoramento.
- `IndicadorEstrategico`: indicador de nível estratégico (topo da cadeia).
- `IndicadorTatico`: indicador de nível tático, relacionado a indicadores estratégicos.
- `Processo`: processo operacional que consolida entregas e monitoramento.
- `ProcessoMarcador`: vínculo específico entre processo e marcadores.
- `Entrega`: item executável/entregável dentro do processo, com evolução e prazos.
- `IndicadorVariavel`: variável numérica utilizada em fórmulas e monitoramento.
- `IndicadorVariavelCicloMonitoramento`: ciclo de monitoramento por variável.
- `IndicadorCicloMonitoramento`: ciclo agregado de monitoramento por indicador.
- `IndicadorCicloValor`: valor lançado para uma variável em determinado ciclo.
- `IndicadorCicloHistorico`: trilha histórica das alterações de valores monitorados.
- `NotaItem`: nota textual genérica vinculável a qualquer item do domínio.

## Principais fluxos de negócio

1. **Gestão hierárquica**
- manutenção de indicadores estratégicos;
- desdobramento em indicadores táticos;
- associação de processos e entregas.

2. **Indicadores matemáticos e variáveis**
- definição de fórmula;
- sincronização de variáveis derivadas da expressão;
- cálculo/recálculo de resultado conforme ciclos e valores registrados.

3. **Monitoramento periódico**
- criação e evolução de ciclos por periodicidade;
- registro de valores por variável;
- consolidação de resultado no ciclo do indicador.

4. **Classificação por marcadores**
- criação/sugestão de marcadores;
- vínculo e desvínculo de marcadores em itens de diferentes tipos;
- suporte a vínculos automáticos por grupo.

5. **Controle de acesso**
- permissões Django por modelo/ação;
- acesso complementar para grupos de monitoramento;
- regras específicas para edição/exclusão de indicadores e monitoramento de entregas.

## Dependências com outros apps do projeto

- `intranet` (projeto principal): inclui as URLs do app em `/sala-de-situacao/`.
- `auditoria`: uso de `AuditLog` para histórico de alterações na interface.
- `usuarios`: usa constante `ADMIN_GROUP_NAME` para regras administrativas do módulo.
- `django.contrib.auth`: autenticação, grupos e permissões.
- `django.contrib.contenttypes`: relações genéricas (marcadores, notas e variáveis associadas a tipos diferentes).

## Endpoints disponíveis

### APIs auxiliares e marcadores
- `GET /sala-de-situacao/variaveis/sugestoes/` (`sala_variavel_sugestoes_api`)
- `GET /sala-de-situacao/painel-consolidado/grafico-variaveis/` (`sala_painel_consolidado_grafico_variaveis_api`)
- `GET /sala-de-situacao/marcadores/sugestoes/` (`sala_marcador_sugestoes_api`)
- `POST /sala-de-situacao/marcadores/criar/` (`sala_marcador_criar_api`)
- `POST /sala-de-situacao/marcadores/<pk>/cor/` (`sala_marcador_cor_api`)
- `POST /sala-de-situacao/marcadores/<pk>/excluir/` (`sala_marcador_excluir_api`)
- `GET /sala-de-situacao/marcadores/<tipo>/<pk>/` (`sala_item_marcadores_api`)
- `POST /sala-de-situacao/marcadores/<tipo>/<pk>/vincular/` (`sala_item_marcador_vincular_api`)
- `POST /sala-de-situacao/marcadores/<tipo>/<pk>/<marcador_id>/` (`sala_item_marcador_desvincular_api`)

### Home e painel consolidado
- `GET /sala-de-situacao/` (`sala_situacao_home`)
- `GET /sala-de-situacao/painel-consolidado/` (`sala_painel_consolidado`)

### Fluxos hierárquicos
- `GET /sala-de-situacao/indicadores-estrategicos/<pk>/indicadores-taticos/` (`sala_fluxo_indicadores_taticos_por_ie`)
- `GET /sala-de-situacao/indicadores-taticos/<pk>/processos/` (`sala_fluxo_processos`)
- `GET /sala-de-situacao/processos/<pk>/entregas/` (`sala_fluxo_entregas`)

### CRUD de indicadores estratégicos
- `GET /sala-de-situacao/indicadores-estrategicos/` (`sala_indicador_estrategico_list`)
- `GET|POST /sala-de-situacao/indicadores-estrategicos/novo/` (`sala_indicador_estrategico_create`)
- `GET /sala-de-situacao/indicadores-estrategicos/<pk>/` (`sala_indicador_estrategico_detail`)
- `GET|POST /sala-de-situacao/indicadores-estrategicos/<pk>/editar/` (`sala_indicador_estrategico_update`)
- `GET|POST /sala-de-situacao/indicadores-estrategicos/<pk>/excluir/` (`sala_indicador_estrategico_delete`)

### Variáveis de indicadores
- `GET|POST /sala-de-situacao/indicadores/<tipo>/<pk>/variaveis/nova/` (`sala_indicador_variavel_create`)

### CRUD de indicadores táticos
- `GET /sala-de-situacao/indicadores-taticos/` (`sala_indicador_tatico_list`)
- `GET|POST /sala-de-situacao/indicadores-taticos/novo/` (`sala_indicador_tatico_create`)
- `GET /sala-de-situacao/indicadores-taticos/<pk>/` (`sala_indicador_tatico_detail`)
- `GET|POST /sala-de-situacao/indicadores-taticos/<pk>/editar/` (`sala_indicador_tatico_update`)
- `GET|POST /sala-de-situacao/indicadores-taticos/<pk>/excluir/` (`sala_indicador_tatico_delete`)

### CRUD de processos
- `GET /sala-de-situacao/processos/` (`sala_processo_list`)
- `GET|POST /sala-de-situacao/processos/novo/` (`sala_processo_create`)
- `GET /sala-de-situacao/processos/<pk>/` (`sala_processo_detail`)
- `GET|POST /sala-de-situacao/processos/<pk>/editar/` (`sala_processo_update`)
- `GET|POST /sala-de-situacao/processos/<pk>/excluir/` (`sala_processo_delete`)

### CRUD e monitoramento de entregas
- `GET /sala-de-situacao/entregas/` (`sala_entrega_list`)
- `GET /sala-de-situacao/entregas/calendario/eventos/` (`sala_entrega_calendario_api`)
- `GET|POST /sala-de-situacao/entregas/nova/` (`sala_entrega_create`)
- `GET /sala-de-situacao/entregas/<pk>/` (`sala_entrega_detail`)
- `GET|POST /sala-de-situacao/entregas/<pk>/editar/` (`sala_entrega_update`)
- `GET|POST /sala-de-situacao/entregas/<pk>/monitorar/` (`sala_entrega_monitorar`)
- `GET|POST /sala-de-situacao/entregas/<pk>/excluir/` (`sala_entrega_delete`)
