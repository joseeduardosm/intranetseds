# App `licitacoes`

## Descrição do propósito do app
O app `licitacoes` gerencia a elaboração de Termos de Referência (TR) em estrutura hierárquica, com suporte a:
- cadastro e manutenção de termos;
- organização por seções, subseções, itens e subitens;
- duplicação de termos;
- importação estruturada por DOCX ou texto colado;
- exportação do documento final para DOCX.

Na arquitetura Django do projeto, ele se integra principalmente com `models`, `forms`, `views`, `templates` e permissões nativas do auth.

## Modelos existentes e o que representam
- `TermoReferencia`: entidade raiz do TR, contendo identificação (`apelido`) e referência ao processo SEI.
- `SessaoTermo`: seção principal do termo (ex.: "Condições Gerais"), com ordenação explícita.
- `SubsessaoTermo`: subdivisão opcional dentro de cada sessão.
- `ItemSessao`: nó de conteúdo textual recursivo (item/subitem), com suporte a enumeração (`INCISO`, `ALINEA`).
- `TabelaItemLinha`: linha de planilha vinculada a um item (descrição, códigos e quantidade).

## Principais fluxos de negócio
- Criação e edição de TR:
  - usuário cria metadados do termo;
  - adiciona sessões/subseções;
  - estrutura itens e subitens com ordenação manual.
- Edição de conteúdo:
  - formulário de item normaliza texto com remoção de índices redundantes e padronização de incisos/alíneas.
- Reordenação hierárquica:
  - endpoints de subir/descer para sessões, subseções e itens preservam consistência de ordem.
- Duplicação de termo:
  - clona transacionalmente toda a árvore (sessões, subseções, itens e tabela).
- Importação:
  - DOCX: leitura por estilos/regex para montar hierarquia;
  - Texto colado: parser determinístico por tokens (`1.`, `1.1.`, `I)`, `a)`, `OU`, colchetes);
  - alternativas/comentários recebem prefixo de revisão obrigatório.
- Exportação DOCX:
  - gera documento institucional com título, metadados, estrutura numerada e tabela de itens.

## Dependências com outros apps do projeto
- Dependência principal:
  - não depende diretamente de modelos de outros apps para a estrutura de TR.
- Dependências de plataforma Django:
  - `django.contrib.auth` (permissões e controle de acesso nas views);
  - templates do próprio app em `templates/licitacoes/*`.
- Dependência externa opcional:
  - `python-docx` para importação/exportação DOCX.

## Endpoints disponíveis
Rotas definidas em `licitacoes/urls.py` (normalmente sob prefixo do projeto, por exemplo `/licitacoes/`):

- `GET /` -> home do módulo
- `GET /termos/` -> lista de termos
- `GET|POST /termos/novo/` -> criação de termo
- `GET|POST /termos/importar/` -> importação por DOCX/texto
- `GET /termos/<pk>/` -> detalhe do termo
- `GET /termos/<pk>/exportar-docx/` -> exportação DOCX
- `GET|POST /termos/<pk>/editar/` -> edição de termo
- `GET|POST /termos/<pk>/excluir/` -> exclusão de termo
- `GET|POST /termos/<pk>/duplicar/` -> duplicação de termo

Sessões:
- `GET|POST /termos/<termo_pk>/sessoes/nova/`
- `GET|POST /termos/<termo_pk>/sessoes/<pk>/editar/`
- `GET|POST /termos/<termo_pk>/sessoes/<pk>/excluir/`
- `POST /termos/<termo_pk>/sessoes/<pk>/subir/`
- `POST /termos/<termo_pk>/sessoes/<pk>/descer/`

Subseções:
- `GET|POST /sessoes/<sessao_pk>/subsessoes/nova/`
- `GET|POST /sessoes/<sessao_pk>/subsessoes/<pk>/editar/`
- `GET|POST /sessoes/<sessao_pk>/subsessoes/<pk>/excluir/`
- `POST /sessoes/<sessao_pk>/subsessoes/<pk>/subir/`
- `POST /sessoes/<sessao_pk>/subsessoes/<pk>/descer/`

Itens e subitens:
- `GET|POST /sessoes/<sessao_pk>/itens/novo/`
- `GET|POST /sessoes/<sessao_pk>/subsessoes/<subsessao_pk>/itens/novo/`
- `GET|POST /sessoes/<sessao_pk>/itens/<parent_pk>/subitem/novo/`
- `GET|POST /sessoes/<sessao_pk>/itens/<pk>/editar/`
- `GET|POST /sessoes/<sessao_pk>/itens/<pk>/excluir/`
- `POST /sessoes/<sessao_pk>/itens/<pk>/subir/`
- `POST /sessoes/<sessao_pk>/itens/<pk>/descer/`

Tabela de itens:
- `GET|POST /sessoes/<sessao_pk>/itens/<item_pk>/tabela/novo/`
- `GET|POST /sessoes/<sessao_pk>/itens/<item_pk>/tabela/<pk>/editar/`
- `GET|POST /sessoes/<sessao_pk>/itens/<item_pk>/tabela/<pk>/excluir/`
