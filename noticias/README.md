# App `noticias`

## Descrição do propósito do app
O app `noticias` implementa a vitrine de comunicação da intranet. Ele fornece:
- listagem paginada de notícias na página inicial;
- visualização de detalhe por notícia;
- fluxo de criação, edição e exclusão para usuários com permissões apropriadas.

Na arquitetura do projeto, este app está montado na raiz de URLs (`/`) e funciona como porta de entrada da intranet para conteúdo institucional.

## Modelos existentes e o que representam
## `Noticia`
Representa uma notícia publicada na intranet.

Campos principais:
- `titulo`: título exibido em listagem e detalhe;
- `texto`: corpo completo da notícia;
- `data_publicacao`: data oficial da publicação;
- `categoria`: classificação temática;
- `imagem_destaque`: mídia opcional para destaque visual.

Regra de ordenação:
- padrão por `data_publicacao` decrescente e `id` decrescente.

## Principais fluxos de negócio
1. Home/listagem de notícias
- Endpoint `GET /`
- Usa `NoticiaListView` com paginação (`paginate_by = 6`).
- Também injeta no contexto os atalhos ativos de serviços via `AtalhoServico.objects.filter(ativo=True)`.

2. Detalhe da notícia
- Endpoint `GET /noticias/<pk>/`
- Usa `NoticiaDetailView` para exibir uma notícia específica.

3. Criação de notícia
- Endpoints `GET` e `POST /noticias/nova/`
- Usa `NoticiaCreateView`.
- Exige permissão `noticias.add_noticia`.

4. Edição de notícia
- Endpoints `GET` e `POST /noticias/<pk>/editar/`
- Usa `NoticiaUpdateView`.
- Exige permissão `noticias.change_noticia`.

5. Exclusão de notícia
- Endpoints `GET` e `POST /noticias/<pk>/excluir/`
- Usa `NoticiaDeleteView`.
- Exige permissão `noticias.delete_noticia`.

## Dependências com outros apps do projeto
- `administracao`:
  - Consome `administracao.models.AtalhoServico` para renderizar atalhos ativos na home.
- `usuarios`/autenticação Django:
  - Controle de acesso baseado em autenticação e permissões do Django (`PermissionRequiredMixin`).
- Templates:
  - `templates/noticias/noticia_list.html`
  - `templates/noticias/noticia_detail.html`
  - `templates/noticias/noticia_form.html`
  - `templates/noticias/noticia_confirm_delete.html`

## Endpoints disponíveis
- `GET /` -> lista notícias (`name='home'`)
- `GET /noticias/nova/` -> formulário de criação (`name='noticia_create'`)
- `POST /noticias/nova/` -> cria notícia
- `GET /noticias/<int:pk>/` -> detalhe (`name='noticia_detail'`)
- `GET /noticias/<int:pk>/editar/` -> formulário de edição (`name='noticia_update'`)
- `POST /noticias/<int:pk>/editar/` -> atualiza notícia
- `GET /noticias/<int:pk>/excluir/` -> confirmação de exclusão (`name='noticia_delete'`)
- `POST /noticias/<int:pk>/excluir/` -> exclui notícia

