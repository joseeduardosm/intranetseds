# Intranet SEDS

Sistema web interno da Secretaria de Desenvolvimento Social (SEDS), construído com Django, com módulos para gestão administrativa, indicadores, contratos, ramais, notícias, reserva de salas e outros fluxos institucionais.

## Tecnologias

- Python 3
- Django
- HTML + CSS + JavaScript
- SQLite (ambiente local)

## Módulos principais

- `usuarios`: gestão de usuários, setores e permissões
- `sala_situacao`: indicadores, processos e entregas
- `acompanhamento_sistemas`: governança do ciclo de vida de sistemas com ciclos, etapas, timeline e interessados
- `administracao`: configurações administrativas do sistema
- `ramais`: diretório de pessoas e estrutura organizacional
- `contratos`, `licitacoes`, `diario_bordo`, `noticias`, `reserva_salas`, `monitoramento`, `folha_ponto`, `empresas`, `prepostos`, `auditoria`, `lousa_digital`

## Destaques recentes

- nova infraestrutura de notificações desktop no app `notificacoes`, com caixa unificada por usuário, autenticação dedicada para client Windows e endpoints para listar, marcar exibida e marcar lida;
- integração inicial de `acompanhamento_sistemas` com a caixa unificada, cobrindo publicação de ciclo, mudanças de etapa e notas de sistema;
- novo client Windows nativo em `.NET` em `desktop_client_dotnet/`, com login manual, credenciais protegidas localmente, inicialização automática, polling e popup próprio no canto inferior direito;
- comando `python manage.py simular_notificacao_desktop <usuario>` para gerar notificações de teste sem depender do fluxo manual do sistema;
- ampliação da autonomia dos interessados internos em `acompanhamento_sistemas`, permitindo editar sistemas, ciclos, etapas e interessados dos itens em que já participam;
- exclusão de sistemas e ciclos limitada ao usuário que criou o registro, preservando a governança sem expor remoções amplas por permissão genérica;
- refinamento da visão executiva de `acompanhamento_sistemas`, com cards mais largos, títulos autoajustáveis, resumo compacto dos ciclos e melhor responsividade;
- ajuste da `sala_situacao` e da `sala_situacao_v2` para trabalhar apenas com grupos vinculados a setores ativos, incluindo filtros, formulários e monitoramento;
- ampliação do acesso global de leitura na `sala_situacao_v2` para usuários com permissões de visualização dos módulos legado e v2;
- proteção na geração automática de marcadores por grupo, evitando colisões e estouro de tamanho quando o nome do setor é muito longo;
- novo app `acompanhamento_sistemas` com cadastro de sistemas, ciclos e etapas fixas de acompanhamento;
- timeline consolidada por sistema e timeline específica por etapa, ambas com paginação de 6 eventos por navegação;
- progresso processual por sistema e por ciclo, seguindo a mesma lógica visual da `sala_situacao_v2`;
- indicador de `tempo de atendimento` (lead time) do sistema na listagem, calculado da criação até hoje ou até a última etapa concluída;
- gestão de interessados no nível do sistema, com reaproveitamento de usuários já cadastrados e notificações por e-mail;
- acesso contextual por interessado interno, dashboard executivo, marcadores de prazo e stepper horizontal do ciclo no `acompanhamento_sistemas`;
- modal de calendário na etapa com visão mensal de todas as etapas de todos os sistemas;
- transição automática entre etapas, com obrigatoriedade de anexo ao concluir `Requisitos`;
- integração do módulo à matriz de perfis do app `usuarios`, permitindo concessão de acesso por Leitura, Edição e Administração;
- integração do novo módulo com a área de atalhos administrativos.
- reorganização do `Termo de Referência 25` em `licitacoes`, com inserção de novos blocos técnicos de infraestrutura a partir de arquivos em `docs/`.

## Estrutura do projeto

- `intranet/`: configurações globais do Django (`settings.py`, `urls.py`)
- `notificacoes/`: caixa unificada de notificações desktop, tokens da API e endpoints do client
- `desktop_client_dotnet/`: client Windows nativo em `.NET` com popup próprio e scripts de instalação MVP
- `templates/`: templates HTML
- `static/`: arquivos estáticos (CSS, JS, imagens)
- `media/`: uploads de arquivos
- `manage.py`: utilitário principal Django

## Como executar localmente

### 1) Criar e ativar ambiente virtual

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2) Instalar dependências

```bash
pip install -r requirements.txt
```

### 3) Configurar variáveis de ambiente

Crie/ajuste o arquivo `.env` na raiz conforme o ambiente.

### 4) Executar migrações

```bash
python manage.py migrate
```

### 5) Subir servidor

```bash
python manage.py runserver
```

Acesse: `http://127.0.0.1:8000`

## Testes

Executar todos os testes:

```bash
python manage.py test
```

Executar testes de um app específico (exemplo `usuarios`):

```bash
python manage.py test usuarios
```

Executar os testes principais das notificações desktop:

```bash
python manage.py test notificacoes --settings=intranet.settings_test
python manage.py test acompanhamento_sistemas.tests.AcompanhamentoSistemasTests.test_publicacao_de_entrega_gera_notificacao_desktop_para_interessado_vinculado --settings=intranet.settings_test
```

## Notificações desktop

O backend expõe uma API dedicada para o client Windows:

- `POST /api/desktop/auth/login/`
- `POST /api/desktop/auth/logout/`
- `GET /api/desktop/notificacoes/`
- `POST /api/desktop/notificacoes/<id>/marcar-exibida/`
- `POST /api/desktop/notificacoes/<id>/marcar-lida/`

No `acompanhamento_sistemas`, o formato atual das notificações ficou:

- título: `Sistema: Nome do sistema`
- 1ª linha: `Ciclo: Nome do ciclo`
- 2ª linha: `Etapa: ...`
- 3ª linha: `Nome da pessoa, dd/mm/aaaa hh:mm`

Para simular uma notificação sem acionar o fluxo funcional:

```bash
python manage.py simular_notificacao_desktop jesmartins
```

O client Windows fica em `desktop_client_dotnet/README.md`.

## Versionamento (Git)

Fluxo básico recomendado:

```bash
git checkout -b feature/minha-alteracao
# ...edita arquivos...
git add .
git commit -m "feat: descreve a alteração"
git push -u origin feature/minha-alteracao
```

Para sincronizar a branch principal:

```bash
git checkout main
git pull
```

## Repositório remoto

Este projeto está versionado em:

- `origin`: `https://github.com/joseeduardosm/intranetseds.git`

## Observações

- Não versionar segredos (`.env`) nem bancos locais (`*.sqlite3`).
- O `.gitignore` já está configurado para arquivos temporários e artefatos de ambiente local.
