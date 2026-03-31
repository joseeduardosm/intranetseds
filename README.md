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

- novo app `acompanhamento_sistemas` com cadastro de sistemas, ciclos e etapas fixas de acompanhamento;
- timeline consolidada por sistema com anotações, anexos e registro automático das transições mais relevantes;
- progresso processual por sistema e por ciclo, seguindo a mesma lógica visual da `sala_situacao_v2`;
- gestão de interessados no nível do sistema, com reaproveitamento de usuários já cadastrados e notificações por e-mail;
- integração do novo módulo com a área de atalhos administrativos.

## Estrutura do projeto

- `intranet/`: configurações globais do Django (`settings.py`, `urls.py`)
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
