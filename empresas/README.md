# Empresas

## Descrição do propósito do app
O app `empresas` centraliza o cadastro de empresas utilizadas no sistema (fornecedores/parceiros), servindo como base para relacionamentos com outros módulos.

Na arquitetura Django, ele integra:
- `models.py`: persistência da entidade `Empresa`;
- `views.py`: fluxos HTTP de CRUD;
- `urls.py`: roteamento dos endpoints;
- templates `empresas/*`: renderização das telas.

## Modelos existentes e o que representam
- `Empresa`:
  - representa uma pessoa jurídica cadastrada;
  - armazena `nome` (único) e `cnpj` opcional;
  - é referenciada por outros apps como `prepostos` e `contratos`.

## Principais fluxos de negócio
1. Listagem de empresas (`EmpresaListView`)
- exibe empresas para usuários autenticados;
- pré-carrega relação com prepostos para reduzir consultas adicionais.

2. Criação de empresa (`EmpresaCreateView`)
- cadastra nova empresa com nome e CNPJ.

3. Edição de empresa (`EmpresaUpdateView`)
- atualiza dados cadastrais;
- redireciona para o detalhe da empresa.

4. Detalhe de empresa (`EmpresaDetailView`)
- exibe dados da empresa;
- mostra prepostos e contratos relacionados.

5. Exclusão de empresa (`EmpresaDeleteView`)
- remove registro via fluxo de confirmação.

## Dependências com outros apps do projeto
- `prepostos`:
  - usa relacionamento reverso `empresa.prepostos` no detalhe.
- `contratos`:
  - usa relacionamento reverso `empresa.contratos` no detalhe.
- `auth` (Django):
  - controle de acesso via `LoginRequiredMixin`.

## Endpoints disponíveis
Baseado em `empresas/urls.py`:

- `GET /empresas/` → `empresas_list`
- `GET|POST /empresas/novo/` → `empresas_create`
- `GET /empresas/<pk>/` → `empresas_detail`
- `GET|POST /empresas/<pk>/editar/` → `empresas_update`
- `GET|POST /empresas/<pk>/excluir/` → `empresas_delete`

Observação: o prefixo real depende de como o `urls.py` do app é incluído nas rotas principais do projeto.
