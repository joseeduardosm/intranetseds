# Changelog de RFs

Este arquivo e atualizado pela equipe de implementacao a cada iteracao (nova funcionalidade, ajuste ou correcao).

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
