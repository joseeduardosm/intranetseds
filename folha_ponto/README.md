# App `folha_ponto`

## Descricao do proposito do app
O app `folha_ponto` centraliza o fluxo de emissao de folha de ponto mensal para usuarios autenticados e oferece telas administrativas de RH para manter os dados que impactam essa emissao.

No dominio do negocio, o app resolve tres necessidades principais:
- consolidar calendario de trabalho por mes (dias uteis, sabados, domingos, feriados e ferias);
- manter cadastro de feriados institucionais;
- manter periodos de ferias por servidor e configuracao visual da folha (brasao).

## Modelos existentes e o que representam
- `Feriado`: representa um feriado oficial em data unica, usado para preencher automaticamente linhas de feriado na folha mensal.
- `FeriasServidor`: representa um intervalo de ferias de um servidor (`PessoaRamal`) com rastreabilidade de quem cadastrou.
- `ConfiguracaoRH`: configuracao global do modulo RH (atualmente, arquivo de brasao para impressao).

## Principais fluxos de negocio
- Emissao da folha mensal:
  - usuario acessa a tela de impressao com mes/ano;
  - sistema consolida por dia: feriado, ferias, sabado, domingo ou dia util;
  - sistema monta quadro de consolidacao (eventos do mes) e dados funcionais do servidor.
- Gestao de feriados:
  - RH lista, cria, edita e exclui feriados;
  - registros impactam imediatamente a geracao da folha.
- Gestao de ferias:
  - RH lista, cria, edita e exclui periodos de ferias;
  - validacao garante que `data_fim >= data_inicio`.
- Gestao de brasao:
  - RH faz upload/atualizacao do brasao institucional;
  - arquivo eh usado no template de impressao da folha.

## Dependencias com outros apps do projeto
- `ramais`:
  - usa `PessoaRamal` para vincular dados funcionais do servidor;
  - consulta atributos de jornada e horarios para preencher a folha.
- `administracao`:
  - fluxo de configuracao de brasao redireciona para a area administrativa de RH (`administracao_rh`).
- `usuarios`/auth do Django:
  - controle de acesso por login e permissoes (`add/change/delete` dos modelos do app).

## Endpoints disponiveis
Rotas definidas em `folha_ponto/urls.py` (normalmente sob prefixo do projeto):

- `GET /` -> `folha_ponto_home`
- `GET|POST /brasao/` -> `folha_ponto_brasao`
- `GET /imprimir/` -> `folha_ponto_print`

CRUD de feriados:
- `GET /feriados/` -> `folha_ponto_feriado_list`
- `GET|POST /feriados/novo/` -> `folha_ponto_feriado_create`
- `GET|POST /feriados/<pk>/editar/` -> `folha_ponto_feriado_update`
- `GET|POST /feriados/<pk>/excluir/` -> `folha_ponto_feriado_delete`

CRUD de ferias:
- `GET /ferias/` -> `folha_ponto_ferias_list`
- `GET|POST /ferias/novo/` -> `folha_ponto_ferias_create`
- `GET|POST /ferias/<pk>/editar/` -> `folha_ponto_ferias_update`
- `GET|POST /ferias/<pk>/excluir/` -> `folha_ponto_ferias_delete`
