# Changelog de RFs

Este arquivo e atualizado pela equipe de implementacao a cada iteracao (nova funcionalidade, ajuste ou correcao).

## 01/05/2026 12:40:47
- Sistema: Plataforma (geral)
- Alteracao: Lancamento consolidado de acompanhamento de requisitos, notificacoes, rastreamento e permissoes.
- Detalhes:
  - Acompanhamento de Sistemas: criado fluxo de processos de requisitos com etapas `AS IS`, `Diagnostico` e `TO BE`, historico, anexos, bloqueios por dependencia e transformacao em ciclo ou novo sistema.
  - Acompanhamento de Sistemas: revisado ciclo de entregas para permitir criacao de cronograma inicial, controlar publicacao conforme datas obrigatorias e exibir historico consolidado.
  - Notificacoes: adicionada pagina administrativa para acompanhar notificacoes enviadas, exibidas, lidas ou pendentes.
  - Diario de Bordo: participantes passaram a receber notificacoes de incrementos, inclusoes/remocoes no bloco e registros de ciencia.
  - Rastreamento de Navegacao: criado painel administrativo com agregacao diaria de visitas por pagina, filtros por periodo, ordenacao e detalhe por rota.
  - Permissoes e acesso: ampliada matriz de perfis para Lousa Digital, Usuarios, Notificacoes e Rastreamento; ajustados acessos de atalhos administrativos, ramais e reserva de salas para respeitar perfis somente leitura.
  - Interface: atualizados layouts de usuarios, reservas, acompanhamento de sistemas, atalhos, empresas, prepostos e lousa digital para refletir novos controles, buscas e historicos.
  - Configuracao: parametrizados hosts, CSRF, cookies, proxy SSL e chave do Django via variaveis de ambiente, mantendo valores padrao para o ambiente atual.
  - Cliente desktop: ajustado popup de notificacoes para melhor leitura de titulo e linhas de conteudo.

## 23/03/2026 18:45:00
- Sistema: Lousa Digital
- Alteracao: Listagem de processos segmentada por abas `SGC`, `CEI` e `TCE`.
- Detalhes:
  - A tela principal passou a exibir um tabstrip com contadores por aba no formato `SGC (n)`, `CEI (n)` e `TCE (n)`.
  - O cadastro de processo passou a assumir automaticamente a origem conforme a aba ativa, removendo a necessidade de preenchimento manual de `caixa_origem`.
  - A navegacao de criar, editar, detalhar, alternar cards/tabela e aplicar filtros passou a preservar a aba selecionada.
  - Mantidos os RFs existentes de cadastro, encaminhamentos e identidade visual.

## 23/02/2026 13:35:00
- Sistema: Administracao
- Alteracao: Criada pagina `Administracao > RFs`.
- Detalhes: Inclusao de rota, permissao, card em Configuracoes e estrutura inicial de historico de mudancas.

## 23/02/2026 13:37:06
- Sistema: Administracao
- Alteracao: Ajuste para modo somente leitura.
- Detalhes: Removida entrada manual na tela. A pagina `Administracao > RFs` passou a exibir somente o conteudo deste arquivo `docs/CHANGELOG_RF.md`.

## 23/02/2026 13:39:15
- Sistema: Plataforma (geral)
- Alteracao: Lancamento consolidado das iteracoes do dia.
- Detalhes:
  - Infra/seguranca: Ajustado `ALLOWED_HOSTS` para incluir `sgi.seds.sp.gov.br` e alinhadas configuracoes CSRF para ambiente HTTP.
  - Operacao: Validado reload do Gunicorn e teste de resposta com host de producao.
  - Diario de Bordo: Ajustada exibicao de pessoas envolvidas no card para formato de lista (um item por linha).
  - Documentacao de requisitos: Gerado `docs/RF_site.md` com mapeamento sistematizado de RFs por modulo.
  - Administracao: Criada navegacao `Administracao > RFs` com pagina dedicada de changelog.
  - Administracao: Pagina `RFs` convertida para modo somente leitura, consumindo `docs/CHANGELOG_RF.md`.

## 23/02/2026 13:47:00
- Sistema: Plataforma (timezone)
- Alteracao: Padronizacao para `America/Sao_Paulo` no comportamento da aplicacao.
- Detalhes:
  - Contratos: substituido uso de `date.today()` por `timezone.localdate()`.
  - Reserva de Salas: substituido uso de `datetime.now()` por horario local do Django.
  - Changelog: horarios anteriores ajustados de UTC para horario local de Sao Paulo.

## 23/02/2026 13:49:54
- Sistema: Administracao
- Alteracao: Pagina `Administracao > RFs` com layout em duas colunas.
- Detalhes:
  - Coluna esquerda: leitura de `docs/CHANGELOG_RF.md` (changelog).
  - Coluna direita: leitura de `docs/RF_site.md` (RFs atuais e futuros).
  - Mantida pagina em modo somente consulta, sem formulario de entrada manual.

## 23/02/2026 13:51:59
- Sistema: Administracao
- Alteracao: Correcao de renderizacao dos RFs na pagina `Administracao > RFs`.
- Detalhes:
  - Implementado renderizador Markdown basico no backend para converter tabelas em HTML.
  - Tabelas dos RFs passaram a usar layout `.table table-fulltext`, eliminando quebra visual do formato texto bruto.
