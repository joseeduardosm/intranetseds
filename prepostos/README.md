# App `prepostos`

## Descrição do propósito do app
O app `prepostos` gerencia o cadastro de prepostos vinculados a empresas no sistema.
No domínio do projeto, um preposto representa a pessoa de contato/responsável
associada a uma empresa cadastrada.

Na arquitetura Django do projeto, este app fornece CRUD web com autenticação,
utilizando:
- model para persistência;
- views baseadas em classe para fluxo HTTP;
- templates HTML para interface;
- URLs próprias incluídas no roteador principal.

## Modelos existentes e o que representam
## `Preposto`
Entidade que armazena dados cadastrais do preposto.

Campos:
- `nome`: identificação principal da pessoa;
- `cpf`: documento civil;
- `telefone`: contato telefônico (opcional);
- `email`: contato eletrônico (opcional);
- `empresa`: referência obrigatória para `empresas.Empresa`.

Regra relevante:
- `empresa` usa `on_delete=PROTECT`, impedindo excluir empresa que possua
  prepostos vinculados (integridade referencial).

## Principais fluxos de negócio
1. Listagem de prepostos
- Exibe todos os prepostos cadastrados para usuário autenticado.

2. Criação de preposto
- Permite cadastrar um novo preposto já associado a uma empresa existente.

3. Edição de preposto
- Permite atualizar os dados cadastrais.
- Após salvar, redireciona para o detalhe do registro atualizado.

4. Detalhe de preposto
- Mostra informações completas de um preposto específico.

5. Exclusão de preposto
- Exige confirmação e remove o registro.
- Restrições de banco podem bloquear exclusão indireta de empresa vinculada
  devido ao `PROTECT` no relacionamento.

## Dependências com outros apps do projeto
- `empresas`
  - Dependência direta via `ForeignKey` para `empresas.models.Empresa`.
- Autenticação Django (`django.contrib.auth`)
  - Todas as views utilizam `LoginRequiredMixin`.
- Templates do app
  - `templates/prepostos/preposto_list.html`
  - `templates/prepostos/preposto_form.html`
  - `templates/prepostos/preposto_detail.html`
  - `templates/prepostos/preposto_confirm_delete.html`

## Endpoints disponíveis
Considerando inclusão em `intranet/urls.py` com prefixo `/prepostos/`:

- `GET /prepostos/` -> lista prepostos (`name='prepostos_list'`)
- `GET /prepostos/novo/` -> formulário de criação (`name='prepostos_create'`)
- `POST /prepostos/novo/` -> cria preposto
- `GET /prepostos/<int:pk>/` -> detalhe (`name='prepostos_detail'`)
- `GET /prepostos/<int:pk>/editar/` -> formulário de edição (`name='prepostos_update'`)
- `POST /prepostos/<int:pk>/editar/` -> atualiza preposto
- `GET /prepostos/<int:pk>/excluir/` -> confirmação de exclusão (`name='prepostos_delete'`)
- `POST /prepostos/<int:pk>/excluir/` -> exclui preposto

