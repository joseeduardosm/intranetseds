# Changelog

Este arquivo consolida as principais mudanças funcionais e estruturais do projeto `Intranet SEDS`.

## 2026-05-04

### Acompanhamento de Sistemas

- ajustada a regra de dependência das homologações para permitir reabrir/corrigir uma homologação já aprovada quando a etapa anterior foi retomada, mantendo o bloqueio para nova aprovação enquanto a etapa anterior não estiver concluída;
- corrigido o botão `Lançar nota` em etapas sem campo de data, como `Homologação de Requisitos`, garantindo abertura do modal e registro de anotações;
- adicionadas notificações web em formato de msgbox modal para atualizações do acompanhamento, reaproveitando a caixa `NotificacaoUsuario` já emitida junto com os e-mails;
- limitado o modal web do acompanhamento a notificações novas, evitando exibir em fila o histórico antigo de notificações não lidas;
- reorganizado o conteúdo das notificações do acompanhamento para exibir `data/hora - usuário` no cabeçalho e corpo resumido por `Processo` ou `Nota`, com suporte a anexos e áreas com scroll quando necessário;
- criado endpoint para marcar notificações do acompanhamento como lidas ao clicar em `OK` no modal.

### Diário de Bordo

- substituída a barra amarela global de atualização por msgbox modal bloqueante, exibindo uma atualização por vez;
- alterada a confirmação de leitura para ocorrer no clique em `OK`, com avanço automático para a próxima notificação pendente;
- incluídos nome do bloco, data/hora, usuário, conteúdo e anexos da atualização no modal;
- removida a marcação automática de leitura ao abrir o detalhe do bloco, preservando a leitura explícita via msgbox.

### Notificações Web

- padronizado o visual dos msgboxes globais de leitura obrigatória, com tamanho fixo, área de conteúdo/anexos reservada e botões em posição estável;
- adicionados timeout e recuperação visual no botão `OK` para evitar estado permanente de `Registrando...` quando a gravação da leitura falhar ou demorar.

### Home

- aplicado ajuste visual nos cards de atalhos para fixar o rodapé com o nome do serviço e evitar sobreposição com imagens.

### Manutenção

- adicionados ao `.gitignore` artefatos locais de build, distribuição, objetos do cliente `.NET`, executável gerado e cópia antiga de configurações.

## 2026-05-01

### Acompanhamento de Sistemas

- removido o fluxo separado de `Publicar ciclo`, incluindo botão, modal, rota, view e notificações específicas de publicação;
- ciclos novos passam a nascer ativos para acompanhamento, sem depender de uma ação posterior de publicação;
- liberadas atualizações de etapa, notas e anexos sem bloqueio por publicação do ciclo, mantendo validações de justificativa, data quando aplicável e anexo obrigatório em `Requisitos`;
- criação e edição de ciclo agora registram histórico do sistema e notificam os interessados pelo fluxo padrão de atualizações;
- edição do cadastro do sistema passou a registrar histórico e notificar interessados quando houver alteração;
- removidos elementos visuais sem função da tela de histórico global, como abas falsas e filtros rápidos apenas decorativos.

## 2026-04-08

### Documentação

- reestruturado o `README.md` para documentar o projeto como um todo, incluindo módulos, stack, execução local, testes, notificações desktop e fluxo de Git;
- consolidado este `CHANGELOG.md` como visão geral da evolução recente do sistema;
- adicionado em `docs/` o comparativo `TR 25 -> TR 26` com foco em mudanças relevantes de itens no módulo `licitacoes`.

### Licitações

- atualizada a versão `v6` do Termo de Referência 26 com revisões dirigidas em blocos técnicos;
- substituído o bloco `3.3.5. SWITCHES DE AGREGAÇÃO` por conteúdo técnico revisado a partir de arquivo-base em `docs/`;
- substituído o perfil `3.8.13.3. Arquiteto(a) de Soluções` e seus subitens por versão ampliada, com foco maior em arquitetura corporativa, segurança, governança e liderança técnica;
- substituídos e reorganizados os itens iniciais de `3.4. INFRAESTRUTURA REDUNDANTE`, incluindo `Escopo de Entrega de Poder Computacional`, `Política de Backup e Retenção`, `Sustentação e Disponibilidade` e `Conectividade e Redundância de Rede`;
- gerado changelog comparativo entre os Termos 25 e 26 em `docs/changelog-termo-25-26.md`.

### Home

- restaurado o rodapé visual com o nome dos atalhos na home para os cards de `Administracao` e `Atalhos`;
- ajustado o CSS dos cards para reservar área fixa para o footer, evitando que a imagem ou o fallback encubram o nome do atalho.

### Administração

- adicionada tela de acompanhamento de notificações na área de configurações;
- incluído card de acesso em `/administracao/configuracoes/` para consultar notificações já emitidas;
- criada listagem com status derivado de notificações (`Pendente`, `Exibida`, `Lida`) e filtros por texto e status.

### Reserva de Salas

- habilitada a ordenação client-side em todas as colunas da listagem de reservas;
- adicionada barra de pesquisa na tela `/reserva-salas/reservas/` para busca por evento, sala, data e responsável;
- ajustado o alinhamento da busca na barra de ações da listagem.

## 2026-04-04

### Notificações Desktop

- criado o novo app `notificacoes`, com persistência de notificações por usuário, deduplicação, tokens da API desktop e endpoints para login, listagem, marcação de exibida e marcação de lida;
- integrado `acompanhamento_sistemas` a essa caixa unificada, cobrindo publicação de ciclo, alterações de etapa e notas de sistema sem depender apenas de e-mail;
- padronizado o conteúdo das notificações de `acompanhamento_sistemas` para exibir `Sistema`, `Ciclo`, `Etapa` e `autor/data-hora` em formato mais legível para popup;
- adicionado comando `simular_notificacao_desktop` para gerar notificações de teste diretamente pelo terminal;
- criado o client Windows nativo em `.NET` em `desktop_client_dotnet`, com login manual, credenciais protegidas localmente, auto-start, polling de 30s, popup próprio no canto inferior direito e scripts MVP de instalação/desinstalação.

## 2026-04-02

### Acompanhamento de Sistemas

- ampliada a autonomia dos interessados internos, que agora podem editar sistemas, ciclos, etapas, notas e a lista de interessados dos sistemas em que participam;
- restringida a exclusão de sistemas e ciclos ao usuário criador do registro, evitando remoções amplas apenas por permissão de perfil;
- refinada a visão executiva com cards mais largos, container expandido, títulos autoajustáveis e resumo de ciclos limitado aos itens mais relevantes;
- reorganizada a grade de ciclos no detalhe do sistema para distribuir melhor os cards em telas amplas e manter responsividade em resoluções menores;
- atualizados os títulos das telas principais para destacar a proposta de `Visão Executiva`.

### Sala de Situação e Sala de Situação V2

- ampliado o acesso global de leitura da `sala_situacao_v2` para usuários com permissões de visualização do legado ou da v2, sem exigir perfil administrativo;
- ajustados formulários, filtros e opções de monitoramento para listar apenas grupos ligados a setores ativos, excluindo o grupo `admin`;
- removida a restrição que barrava a atribuição de grupos responsáveis fora da intersecção do usuário ao criar indicadores na v2, passando a confiar na lista filtrada do formulário;
- fortalecida a geração automática de marcadores por grupo no legado e na v2, com truncamento seguro e sufixo hash para nomes muito longos;
- ampliada a largura da home da Sala de Situação e refinada a grade dos cards para melhor aproveitamento horizontal.

## 2026-04-01

### Acompanhamento de Sistemas

- liberado acesso contextual de leitura para usuários internos vinculados como interessados, restringindo a visualização aos sistemas em que participam;
- adicionado dashboard executivo na listagem do módulo, com resumos operacionais para acompanhamento rápido dos sistemas;
- incluídos marcadores de prazo `Em dia`, `Atenção` e `Atrasado` ao lado do prazo relativo de etapas e ciclos;
- criado stepper horizontal no detalhe do ciclo, melhorando a leitura do fluxo atual e das transições entre etapas;
- refinado o comportamento das homologações, com comunicação visual de retomada, histórico de reprovações/aprovações e retorno controlado do fluxo;
- ajustada a timeline para espelhar eventos relevantes entre etapa anterior e homologação, removendo ruídos técnicos;
- tornado o envio de e-mails assíncrono no pós-commit, reduzindo o tempo de resposta em atualizações de etapa, notas e publicação de ciclo.

### Licitações

- reorganizado o `Termo de Referência 25` com inserção e renumeração de blocos técnicos de infraestrutura e continuidade;
- substituídos os subitens de `3.5.6.1 Sistema de Energia` pelo conteúdo técnico atualizado;
- inseridos os blocos `Storage`, `Servidor de Armazenamento`, `Switches de Agregação`, `Switches de Borda`, `FIREWALL`, `Ferramenta de Backup`, `Ferramenta de Replicação bidirecional do Banco de Dados`, `Política de Backup, Continuidade de Negócios e Recuperação de Desastres` e `Especificações e Volumetria de Servidores Virtuais`;
- ajustada a numeração dos itens subsequentes do termo para acomodar os novos blocos sem duplicidade de seções.

## 2026-03-31

### Acompanhamento de Sistemas

- criado o novo app `acompanhamento_sistemas`, com cadastro de sistemas, ciclos livres e cinco etapas fixas por ciclo;
- adicionadas telas de listagem, detalhe do sistema, detalhe do ciclo e detalhe da etapa, com visual alinhado ao restante da intranet;
- implementada timeline consolidada do sistema, priorizando eventos de negócio, notas livres e anexos;
- incluída a gestão de interessados no nível do sistema, com seleção de usuários existentes, cadastro manual e preenchimento automático do e-mail ao escolher usuário;
- criado o indicador processual de progresso para sistemas e ciclos, com barras e cores no mesmo padrão da `sala_situacao_v2`;
- ajustado o fluxo de etapas para exigir justificativa em mudança de status, exigir anexo ao concluir `Requisitos` e avançar automaticamente a próxima etapa para `Em andamento`;
- adicionados botões de editar e excluir ciclo, com tela de confirmação dedicada;
- integrado o novo módulo aos atalhos administrativos e à navegação principal do projeto;
- refinada a linguagem do domínio para `Ciclos`, com numeração `1/x`, cards próprios, detalhe dedicado e timeline de sistema separada da timeline da etapa;
- paginadas as timelines do módulo com limite de 6 eventos por página, mantendo consolidação no sistema e histórico específico na etapa;
- adicionado calendário modal na etapa, mostrando todas as etapas de todos os sistemas no mês, com tooltip de sistema, ciclo e etapa;
- implementado o `tempo de atendimento` (lead time) do sistema na listagem e reorganizado o card com rodapé de `Última ação`;
- reestruturado o corpo dos e-mails para destacar `Conteúdo` e `Justificativa`, e removido o log de destinatários da timeline;
- incluído `Acompanhamento de Sistemas` na matriz de perfis do módulo `usuarios`;
- ampliada a cobertura de testes do app para criação, permissão, timeline, notificação, anexos, progresso e exclusão.

## 2026-03-30

### Home, Atalhos e Notícias

- substituída a home baseada em notícias por uma home em duas colunas, com cards administrativos na esquerda e atalhos livres na direita;
- movida a listagem de notícias para a rota dedicada `/noticias/`, mantendo o CRUD e removendo notícias da raiz do site;
- criado o cadastro de `Cards administrativos` no módulo `administracao`, com upload de imagem por funcionalidade e uso da mesma identidade visual dos atalhos;
- alterada a home para exibir apenas os cards administrativos cadastrados e ativos em `atalhos-administracao`, sem itens fixos renderizados por fora desse cadastro;
- ampliado o catálogo de funcionalidades configuráveis para cobrir os apps do projeto, incluindo `Administracao`, `Ramais`, `Empresas`, `Prepostos`, `Folha de Ponto`, `Sala de Situacao`, `Sala de Situacao (Legado)` e módulos já existentes;
- ajustada a tela administrativa de cards para refletir exatamente os itens cadastrados, e o formulário de criação/edição passou a listar todas as funcionalidades disponíveis no projeto;
- removido o dropdown `Administracao` da navbar, concentrando a navegação dessas funcionalidades na tela inicial;
- alterado o comportamento da home para sempre exibir os cards administrativos cadastrados a usuários anônimos, solicitando login apenas no clique;
- restaurado o tamanho anterior dos cards e ajustada a grade para preencher melhor a largura das colunas sem prender os atalhos em duas colunas internas;
- ordenados alfabeticamente os cards administrativos tanto na home quanto na tela de gestão;
- adicionadas migrations para o novo model `AtalhoAdministracao` e para a evolução do catálogo de funcionalidades administrativas;
- ampliada a cobertura de testes para a nova home, listagem/edição de cards administrativos e rotas de notícias.

## 2026-03-26

### Autenticação e Navegação

- adicionada `LoginView` customizada com `never_cache` e `ensure_csrf_cookie`, reduzindo falhas de CSRF em formulários reutilizados após login, troca de aba ou navegação por cache;
- ampliado `CSRF_TRUSTED_ORIGINS` para contemplar o acesso publicado em `http` e `https`;
- sincronizado o campo `csrfmiddlewaretoken` com o cookie atual antes de envios de formulário na interface base;
- transformadas mensagens globais e erros de validação em modal compartilhado, com suporte visual complementar no CSS de autenticação;
- adicionados testes cobrindo emissão do cookie CSRF e headers sem cache na tela de login.

### Ramais e Usuários

- reforçado o cadastro/edição de ramais para exigir escolha explícita de setor e foto obrigatória quando o perfil ainda não possui imagem;
- aplicado o mesmo requisito de foto obrigatória no formulário de atualização de usuários;
- removido o usuário especial `admin` do fluxo obrigatório de atualização de ramal e da exibição na lista/organograma de ramais;
- atualizado o título da lista de ramais para exibir o total de contatos cadastrados;
- ampliada a cobertura de testes para seleção de setor, foto obrigatória, exceção do `admin` e validações de formulário.

### Diário de Bordo

- enriquecido o histórico automático de edições de blocos, registrando alterações de nome, descrição, status, participantes e marcadores com comparação entre valores anteriores e novos;
- adicionados testes de regressão para garantir a geração correta desses incrementos ao editar blocos.

### Lousa Digital

- filtrado o dashboard por aba ativa, com cabeçalho contextual, tabstrip com contadores por caixa e links consistentes para lista e criação;
- corrigidas as contagens por aba para evitar duplicidades e refletir apenas os processos da origem selecionada;
- adicionados testes cobrindo o recorte do dashboard pela aba ativa.

### Sala de Situação V2

- refinadas as regras de acesso para indicadores, processos e entregas, incluindo permissão por criador direto, grupos criadores, herança da cadeia matemática e monitoramento por grupos da variável;
- restringida a visibilidade de processos e entregas aos itens realmente relacionados ao usuário, inclusive na lista, detalhe e API de calendário;
- persistido `criado_por` em indicadores, processos e entregas, com nova migration e propagação automática para a estrutura monitorada gerada a partir dos indicadores matemáticos;
- sincronizados grupos criadores e grupos responsáveis na cadeia automática de monitoramento;
- ajustado o formulário de monitoramento de entregas com rótulos, campos e layout dedicados;
- reformulada a lista de entregas com visualizações em tabela, cards e calendário, incluindo ordenação por colunas;
- melhorada a experiência dos campos de data com abertura do calendário customizado tanto pelo botão quanto pelo clique direto no campo;
- ajustada a tela de detalhe da entrega para permitir monitoramento isolado por grupos da variável, com mensagem explicativa quando edição e exclusão seguem restritas;
- limitado o marcador de processos e entregas de monitoramento ao grupo que monitora a variável, preservando `criado_por`, grupos criadores e os direitos de criação;
- adicionadas periodicidades `Diario`, `Semanal` e `Quinzenal` para variáveis monitoradas, com ocultação do dia de referência quando ele não se aplica;
- restringido o tipo matemático ao formato percentual `(x/y)*100`, com mensagens de validação mais educativas e exemplos exibidos no formulário;
- desativado o tipo `Matematico Acumulativo` no fluxo de criação e edição, mantendo compatibilidade com registros antigos;
- adicionada a identificação do usuário que monitorou cada entrega, com nova migration, exibição do último monitoramento por variável no detalhe do indicador e link para o perfil de ramal quando disponível;
- estendido o monitoramento para entregas ligadas a indicadores processuais, preservando o modal de anexos e exigindo nota obrigatória para a equipe antes de concluir o registro;
- ajustado o comportamento do monitoramento processual para usar o percentual informado como evolução da entrega, enquanto entregas de variáveis matemáticas mantêm o preenchimento como valor monitorado;
- transformados os marcadores da Sala de Situação V2 em siglas automáticas dos setores, com tooltip exibindo o nome completo em listas, cards e telas de detalhe;
- atualizados testes de acesso, visibilidade, grupos de monitoramento, cadeia de criação, ordenação e monitoramento.

### Documentação e Apoio

- adicionados materiais de apoio em `docs/`, incluindo textos de referência e a planilha `Planilha Projetos CEI - Edital 20.03.2026.xlsx`.

## 2026-03-22

### Licitações

- evitado erro 404 em exclusão repetida de itens de sessão, com proteção contra duplo envio no formulário e tratamento idempotente no backend;
- adicionados testes cobrindo reenvio do `POST` de exclusão sem quebra do fluxo.

### Sala de Situação

- ajustado o fluxo de notas para aceitar anotações sem anexo e também múltiplos anexos reais no mesmo envio;
- reforçado o fallback de anexos em ambientes sem a tabela `NotaItemAnexo`, ocultando o campo e evitando consultas que quebravam as telas;
- tratado erro de permissão na gravação de anexos com retorno amigável ao formulário e rollback da nota, sem página 500;
- ampliada a cobertura de testes para notas com e sem anexo, múltiplos uploads e falha de escrita no storage.

## 2026-03-20

### Sala de Situação V2

- adicionada a configuração `dia_referencia_monitoramento` por variável matemática, com migration e ressincronização dos indicadores existentes;
- garantido ciclo inicial de monitoramento para toda variável, com prazos mensais calculados pelo dia de referência;
- ordenada a lista de entregas por `data_entrega_estipulada`;
- adicionada a visualização em calendário na tela `/sala-de-situacao/entregas/`;
- adicionados testes cobrindo ciclo inicial, prazo por referência, ordenação da lista e API de calendário;
- ajustada a exclusão de indicadores para remover em cascata processos, entregas, ciclos, valores e relações mesmo em ambientes com migration pendente;
- corrigida a tela de detalhe e os fluxos de criação/exclusão de indicadores matemáticos para não quebrarem quando a coluna `dia_referencia_monitoramento` ainda não existe no banco;
- refinada a experiência de monitoramento: entregas comuns não exibem bloco de monitoramento, entregas monitoradas passam a marcar `100%` ao salvar e o resultado reflete corretamente no indicador matemático;
- ocultado `evolucao_manual` em formulários de itens que passam a ter filhos, deixando a evolução sempre derivada da hierarquia;
- melhorado o histórico de auditoria de recálculos matemáticos, com mensagens mais claras, exibição de segundos e detalhes simplificados sem caixas extras;
- adicionada numeração automática de entregas manuais por processo no formato `1/x`, recalculada conforme o prazo;
- transformado o campo `data_entrega_estipulada` de indicador, processo e entrega em seletor visual com modal de calendário e preenchimento por clique;
- enriquecido o tooltip do calendário de entregas com processo, entrega e trecho curto da descrição.

### Sala de Situação

- adicionado suporte a anexar um ou vários arquivos nas notas, com novo modelo `NotaItemAnexo`, migration e exibição dos links nos históricos;
- reorganizados formulários e filtros da experiência legada, com busca por setor em listas e ajustes na ordem dos campos de entrega.

### Ramais

- removido o grupo `ADMIN` da seleção de setores no formulário de edição de ramais, com cobertura de teste.

### Lousa Digital e Monitoramento

- remodelado o dashboard para trabalhar com séries diárias dos últimos 30 dias, trocar o gráfico de destino atual para barras e remover o ranking de usuários com maior volume tratado;
- normalizada a serialização de timestamps e snapshots de schema para usar horário local.

### Auditoria e Acesso

- reforçado o log de alterações de relações many-to-many com identificação robusta do campo relacionado e serialização mais completa de itens vinculados;
- ampliado o acesso contextual à Sala de Situação V2 e incluído o trio `Indicador`, `Processo` e `Entrega` nas definições de permissão por perfil.
