# Changelog

## 2026-03-22

### Licitacoes
- evitado erro 404 em exclusao repetida de itens de sessao, com protecao contra duplo envio no formulario e tratamento idempotente no backend;
- adicionados testes cobrindo reenvio do `POST` de exclusao sem quebra do fluxo.

### Sala de Situacao
- ajustado o fluxo de notas para aceitar anotacoes sem anexo e tambem multiplos anexos reais no mesmo envio;
- reforcado o fallback de anexos em ambientes sem a tabela `NotaItemAnexo`, ocultando o campo e evitando consultas que quebravam as telas;
- tratado erro de permissao na gravacao de anexos com retorno amigavel ao formulario e rollback da nota, sem pagina 500;
- ampliada a cobertura de testes para notas com e sem anexo, multiplos uploads e falha de escrita no storage.

## 2026-03-20

### Sala de Situacao V2
- adicionada a configuracao `dia_referencia_monitoramento` por variavel matematica, com migration e ressincronizacao dos indicadores existentes;
- garantido ciclo inicial de monitoramento para toda variavel, com prazos mensais calculados pelo dia de referencia;
- ordenada a lista de entregas por `data_entrega_estipulada`;
- adicionada a visualizacao em calendario na tela `/sala-de-situacao/entregas/`;
- adicionados testes cobrindo ciclo inicial, prazo por referencia, ordenacao da lista e API de calendario.
- ajustada a exclusao de indicadores para remover em cascata processos, entregas, ciclos, valores e relacoes mesmo em ambientes com migration pendente;
- corrigida a tela de detalhe e os fluxos de criacao/exclusao de indicadores matematicos para nao quebrarem quando a coluna `dia_referencia_monitoramento` ainda nao existe no banco;
- refinada a experiencia de monitoramento: entregas comuns nao exibem bloco de monitoramento, entregas monitoradas passam a marcar `100%` ao salvar e o resultado reflete corretamente no indicador matematico;
- ocultado `evolucao_manual` em formularios de itens que passam a ter filhos, deixando a evolucao sempre derivada da hierarquia;
- melhorado o historico de auditoria de recalculos matematicos, com mensagens mais claras, exibicao de segundos e detalhes simplificados sem caixas extras;
- adicionada numeracao automatica de entregas manuais por processo no formato `1/x`, recalculada conforme o prazo;
- transformado o campo `data_entrega_estipulada` de indicador, processo e entrega em seletor visual com modal de calendario e preenchimento por clique;
- enriquecido o tooltip do calendario de entregas com processo, entrega e trecho curto da descricao.

### Sala de Situacao
- adicionado suporte a anexar um ou varios arquivos nas notas, com novo modelo `NotaItemAnexo`, migration e exibicao dos links nos historicos;
- reorganizados formularios e filtros da experiencia legada, com busca por setor em listas e ajustes na ordem dos campos de entrega.

### Ramais
- removido o grupo `ADMIN` da selecao de setores no formulario de edicao de ramais, com cobertura de teste.

### Lousa Digital e Monitoramento
- remodelado o dashboard para trabalhar com series diarias dos ultimos 30 dias, trocar o grafico de destino atual para barras e remover o ranking de usuarios com maior volume tratado;
- normalizada a serializacao de timestamps e snapshots de schema para usar horario local.

### Auditoria e Acesso
- reforcado o log de alteracoes de relacoes many-to-many com identificacao robusta do campo relacionado e serializacao mais completa de itens vinculados;
- ampliado o acesso contextual a Sala de Situacao V2 e incluido o trio `Indicador`, `Processo` e `Entrega` nas definicoes de permissao por perfil.
