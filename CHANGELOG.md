# Changelog

## 2026-03-31

### Acompanhamento de Sistemas
- criado o novo app `acompanhamento_sistemas`, com cadastro de sistemas, ciclos livres e cinco etapas fixas por ciclo;
- adicionadas telas de listagem, detalhe do sistema, detalhe do ciclo e detalhe da etapa, com visual alinhado ao restante da intranet;
- implementada timeline consolidada do sistema, priorizando eventos de negocio, notas livres e anexos;
- incluida a gestao de interessados no nivel do sistema, com selecao de usuarios existentes, cadastro manual e preenchimento automatico do e-mail ao escolher usuario;
- criado o indicador processual de progresso para sistemas e ciclos, com barras e cores no mesmo padrao da `sala_situacao_v2`;
- ajustado o fluxo de etapas para exigir justificativa em mudanca de status, exigir anexo ao concluir `Requisitos` e avancar automaticamente a proxima etapa para `Em andamento`;
- adicionados botoes de editar e excluir ciclo, com tela de confirmacao dedicada;
- integrado o novo modulo aos atalhos administrativos e a navegacao principal do projeto;
- ampliada a cobertura de testes do app para criacao, permissao, timeline, notificacao, anexos, progresso e exclusao.

## 2026-03-30

### Home, Atalhos e Noticias
- substituida a home baseada em noticias por uma home em duas colunas, com cards administrativos na esquerda e atalhos livres na direita;
- movida a listagem de noticias para a rota dedicada `/noticias/`, mantendo o CRUD e removendo noticias da raiz do site;
- criado o cadastro de `Cards administrativos` no modulo `administracao`, com upload de imagem por funcionalidade e uso da mesma identidade visual dos atalhos;
- alterada a home para exibir apenas os cards administrativos cadastrados e ativos em `atalhos-administracao`, sem itens fixos renderizados por fora desse cadastro;
- ampliado o catalogo de funcionalidades configuraveis para cobrir os apps do projeto, incluindo `Administracao`, `Ramais`, `Empresas`, `Prepostos`, `Folha de Ponto`, `Sala de Situacao`, `Sala de Situacao (Legado)` e modulos ja existentes;
- ajustada a tela administrativa de cards para refletir exatamente os itens cadastrados, e o formulario de criacao/edicao passou a listar todas as funcionalidades disponiveis no projeto;
- removido o dropdown `Administracao` da navbar, concentrando a navegacao dessas funcionalidades na tela inicial;
- alterado o comportamento da home para sempre exibir os cards administrativos cadastrados a usuarios anonimos, solicitando login apenas no clique;
- restaurado o tamanho anterior dos cards e ajustada a grade para preencher melhor a largura das colunas sem prender os atalhos em duas colunas internas;
- ordenados alfabeticamente os cards administrativos tanto na home quanto na tela de gestao;
- adicionadas migrations para o novo model `AtalhoAdministracao` e para a evolucao do catalogo de funcionalidades administrativas;
- ampliada a cobertura de testes para a nova home, listagem/edicao de cards administrativos e rotas de noticias.

## 2026-03-26

### Autenticacao e Navegacao
- adicionada `LoginView` customizada com `never_cache` e `ensure_csrf_cookie`, reduzindo falhas de CSRF em formularios reutilizados apos login, troca de aba ou navegação por cache;
- ampliado `CSRF_TRUSTED_ORIGINS` para contemplar o acesso publicado em `http` e `https`;
- sincronizado o campo `csrfmiddlewaretoken` com o cookie atual antes de envios de formulario na interface base;
- transformadas mensagens globais e erros de validacao em modal compartilhado, com suporte visual complementar no CSS de autenticacao;
- adicionados testes cobrindo emissao do cookie CSRF e headers sem cache na tela de login.

### Ramais e Usuarios
- reforcado o cadastro/edicao de ramais para exigir escolha explicita de setor e foto obrigatoria quando o perfil ainda nao possui imagem;
- aplicado o mesmo requisito de foto obrigatoria no formulario de atualizacao de usuarios;
- removido o usuario especial `admin` do fluxo obrigatorio de atualizacao de ramal e da exibicao na lista/organograma de ramais;
- atualizado o titulo da lista de ramais para exibir o total de contatos cadastrados;
- ampliada a cobertura de testes para selecao de setor, foto obrigatoria, excecao do `admin` e validacoes de formulario.

### Diario de Bordo
- enriquecido o historico automatico de edicoes de blocos, registrando alteracoes de nome, descricao, status, participantes e marcadores com comparacao entre valores anteriores e novos;
- adicionados testes de regressao para garantir a geracao correta desses incrementos ao editar blocos.

### Lousa Digital
- filtrado o dashboard por aba ativa, com cabecalho contextual, tabstrip com contadores por caixa e links consistentes para lista e criacao;
- corrigidas as contagens por aba para evitar duplicidades e refletir apenas os processos da origem selecionada;
- adicionados testes cobrindo o recorte do dashboard pela aba ativa.

### Sala de Situacao V2
- refinadas as regras de acesso para indicadores, processos e entregas, incluindo permissao por criador direto, grupos criadores, heranca da cadeia matematica e monitoramento por grupos da variavel;
- restringida a visibilidade de processos e entregas aos itens realmente relacionados ao usuario, inclusive na lista, detalhe e API de calendario;
- persistido `criado_por` em indicadores, processos e entregas, com nova migration e propagacao automatica para a estrutura monitorada gerada a partir dos indicadores matematicos;
- sincronizados grupos criadores e grupos responsaveis na cadeia automatica de monitoramento;
- ajustado o formulario de monitoramento de entregas com rotulos, campos e layout dedicados;
- reformulada a lista de entregas com visualizacoes em tabela, cards e calendario, incluindo ordenacao por colunas;
- melhorada a experiencia dos campos de data com abertura do calendario customizado tanto pelo botao quanto pelo clique direto no campo;
- ajustada a tela de detalhe da entrega para permitir monitoramento isolado por grupos da variavel, com mensagem explicativa quando edicao e exclusao seguem restritas;
- limitado o marcador de processos e entregas de monitoramento ao grupo que monitora a variavel, preservando `criado_por`, grupos criadores e os direitos de criacao;
- adicionadas periodicidades `Diario`, `Semanal` e `Quinzenal` para variaveis monitoradas, com ocultacao do dia de referencia quando ele nao se aplica;
- restringido o tipo matematico ao formato percentual `(x/y)*100`, com mensagens de validacao mais educativas e exemplos exibidos no formulario;
- desativado o tipo `Matematico Acumulativo` no fluxo de criacao e edicao, mantendo compatibilidade com registros antigos;
- adicionada a identificacao do usuario que monitorou cada entrega, com nova migration, exibicao do ultimo monitoramento por variavel no detalhe do indicador e link para o perfil de ramal quando disponivel;
- estendido o monitoramento para entregas ligadas a indicadores processuais, preservando o modal de anexos e exigindo nota obrigatoria para a equipe antes de concluir o registro;
- ajustado o comportamento do monitoramento processual para usar o percentual informado como evolucao da entrega, enquanto entregas de variaveis matematicas mantem o preenchimento como valor monitorado;
- transformados os marcadores da Sala de Situacao V2 em siglas automaticas dos setores, com tooltip exibindo o nome completo em listas, cards e telas de detalhe;
- atualizados testes de acesso, visibilidade, grupos de monitoramento, cadeia de criacao, ordenacao e monitoramento.

### Documentacao e Apoio
- adicionados materiais de apoio em `docs/`, incluindo textos de referencia e a planilha `Planilha Projetos CEI - Edital 20.03.2026.xlsx`.

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
