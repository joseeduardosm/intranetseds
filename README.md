# Intranet SEDS

Sistema web interno da Secretaria de Desenvolvimento Social (SEDS), desenvolvido em Django, voltado à operação administrativa e ao apoio de áreas como contratos, licitações, ramais, indicadores, folha de ponto, notícias, reserva de salas e acompanhamento de sistemas.

## Visão Geral

O projeto reúne, em uma única intranet:

- autenticação e navegação institucional;
- gestão de usuários, perfis, setores e permissões;
- módulos administrativos e operacionais com CRUDs, dashboards, relatórios e fluxos internos;
- recursos de auditoria, rastreabilidade e documentação;
- integrações com notificações desktop e client Windows dedicado.

## Stack Principal

- `Python 3`
- `Django`
- `MySQL/MariaDB` no ambiente principal
- `SQLite` em cenários locais simplificados
- `HTML`, `CSS` e `JavaScript`
- `python-docx` para fluxos documentais em `licitacoes`
- client Windows em `.NET` no diretório `desktop_client_dotnet/`

## Módulos do Projeto

- `administracao`: configurações gerais, SMTP, identidade visual, atalhos e apoio administrativo
- `acompanhamento_sistemas`: governança do ciclo de vida de sistemas, etapas, ciclos, timeline e interessados
- `auditoria`: trilha de alterações e histórico de ações
- `contratos`: gestão contratual com status, vencimentos e filtros operacionais
- `diario_bordo`: blocos de trabalho, incrementos e histórico de execução
- `empresas`: cadastro e consulta de empresas
- `folha_ponto`: RH, feriados, férias e configurações correlatas
- `licitacoes`: termos de referência, ETP TIC e estruturação documental
- `lousa_digital`: gestão visual de processos e dashboard por caixas
- `monitoramento`: dashboards e conexões para análise de dados
- `noticias`: publicação e gestão de notícias internas
- `notificacoes`: caixa unificada de notificações desktop, tokens e endpoints do client
- `prepostos`: gestão de prepostos
- `ramais`: diretório institucional, organograma e perfis de contato
- `rastreamento_navegacao`: métricas de acesso e navegação
- `reserva_salas`: agenda, reservas, dashboard e gestão de salas
- `sala_situacao` e `sala_situacao_v2`: indicadores, processos, entregas e monitoramento
- `usuarios`: usuários, grupos, perfis e auditoria de permissões

## Estrutura do Repositório

- `administracao/`, `usuarios/`, `licitacoes/`, `reserva_salas/` etc.: apps Django por domínio
- `intranet/`: configuração global do projeto (`settings.py`, `urls.py`, views compartilhadas)
- `templates/`: templates HTML
- `static/`: CSS, JS e assets estáticos
- `media/`: uploads
- `docs/`: materiais auxiliares, textos-base e changelogs de apoio
- `desktop_client_dotnet/`: client Windows para notificações desktop
- `manage.py`: ponto de entrada de administração Django

## Funcionalidades de Destaque

- home em duas colunas com cards administrativos e atalhos livres
- matriz de perfis e permissões por módulo
- dashboards executivos e operacionais em múltiplos apps
- importação, edição e exportação de Termos de Referência e ETP TIC
- notificações desktop persistidas por usuário, com marcação de exibida e lida
- acompanhamento de sistemas com timeline, ciclos, etapas e interessados internos
- reserva de salas com agenda, calendário e listagem tabular
- módulos de indicadores em operação simultânea: legado e v2

## Configuração Local

### 1. Criar ambiente virtual

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente

Crie ou ajuste o arquivo `.env` na raiz do projeto.

Exemplo de variáveis utilizadas no ambiente principal:

```env
DB_ENGINE=mysql
MYSQL_NAME=intranet
MYSQL_USER=intranet
MYSQL_PASSWORD=******
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
TZ=America/Sao_Paulo
```

## Banco de Dados

O projeto pode operar com bases diferentes conforme o ambiente:

- ambiente principal: `MySQL/MariaDB`
- ambiente local simplificado: `SQLite`, quando configurado

Após configurar o banco:

```bash
python manage.py migrate
```

## Execução Local

```bash
python manage.py runserver
```

Acesso padrão local:

- `http://127.0.0.1:8000`

## Testes

Executar toda a suíte:

```bash
python manage.py test
```

Executar um app específico:

```bash
python manage.py test usuarios
python manage.py test licitacoes
python manage.py test notificacoes
```

Exemplos úteis:

```bash
python manage.py test notificacoes --settings=intranet.settings_test
python manage.py test acompanhamento_sistemas.tests.AcompanhamentoSistemasTests.test_publicacao_de_entrega_gera_notificacao_desktop_para_interessado_vinculado --settings=intranet.settings_test
```

## Notificações Desktop

O backend expõe uma API para o client Windows:

- `POST /api/desktop/auth/login/`
- `POST /api/desktop/auth/logout/`
- `GET /api/desktop/notificacoes/`
- `POST /api/desktop/notificacoes/<id>/marcar-exibida/`
- `POST /api/desktop/notificacoes/<id>/marcar-lida/`

Fluxo funcional atual:

- persistência por usuário em `notificacoes.NotificacaoUsuario`
- deduplicação por janela de tempo
- autenticação por token para o client desktop
- integração inicial com `acompanhamento_sistemas`

Para gerar uma notificação de teste:

```bash
python manage.py simular_notificacao_desktop <usuario>
```

Documentação do client:

- [desktop_client_dotnet/README.md](/home/jesmartins/intranet/desktop_client_dotnet/README.md)

## Documentação Interna

O diretório `docs/` concentra:

- textos auxiliares para montagem e revisão de TRs
- anexos técnicos e conteúdo-base de licitações
- comparativos e changelogs específicos de termos
- artefatos de apoio para evolução funcional do sistema

## Git e Fluxo de Trabalho

Fluxo básico recomendado:

```bash
git checkout -b feature/minha-alteracao
git add <arquivos>
git commit -m "feat: descreve a alteração"
git push -u origin feature/minha-alteracao
```

Sincronização da branch principal:

```bash
git checkout main
git pull
```

Repositório remoto configurado:

- `origin`: `https://github.com/joseeduardosm/intranetseds.git`

## Boas Práticas

- não versionar segredos do `.env`
- não versionar bancos locais e artefatos temporários
- revisar alterações em `templates/` e `static/` em conjunto para evitar regressões visuais
- em alterações de domínio, atualizar documentação e changelog quando fizer sentido

## Changelog

O histórico consolidado do projeto está em [CHANGELOG.md](/home/jesmartins/intranet/CHANGELOG.md).
