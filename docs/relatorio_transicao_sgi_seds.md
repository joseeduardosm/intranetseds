# Relatório de Transição - SGI SEDS

Data-base: 07/05/2026

## 1. Objetivo

Este documento registra as informações críticas do SGI SEDS como plataforma institucional. O foco é arquitetura, stack, decisões estruturais, integrações, dados, segurança, riscos e recomendações estratégicas para continuidade.

Não é um manual funcional de cada tela. É um documento de passagem para orientar sustentação, governança e evolução do sistema como um todo.

## 2. Resumo Executivo

O SGI SEDS é uma intranet corporativa em Django que centraliza rotinas administrativas, operacionais e gerenciais da Secretaria de Desenvolvimento Social.

O sistema deixou de ser apenas um conjunto de páginas internas e passou a operar como plataforma institucional: autentica usuários, resolve permissões, audita ações, mantém dados operacionais, emite notificações, organiza documentos, apoia dashboards e concentra módulos críticos de acompanhamento.

Áreas mais sensíveis:

- autenticação AD/LDAP e contingência local;
- permissões por perfis, setores, herança e deny;
- banco MySQL/MariaDB;
- diretório `media/`;
- auditoria e rastreabilidade;
- notificações web, desktop e e-mail;
- Sala de Situação;
- Acompanhamento de Sistemas;
- Licitações/documentos;
- Administração, usuários e configurações globais.

## 3. Identificação

Nome funcional: Sistema de Gestão Integrada - SGI SEDS

Tipo: intranet institucional / plataforma administrativa interna

Arquitetura: monólito modular Django

Repositório: `https://github.com/joseeduardosm/intranetseds.git`

Domínio configurado: `sgi.seds.sp.gov.br`

Hosts previstos/configurados:

- `localhost`
- `127.0.0.1`
- `10.22.0.37`
- `200.144.29.245`
- `sgi.seds.sp.gov.br`

## 4. Arquitetura Geral

O SGI é um monólito modular. Existe uma única aplicação Django, organizada em apps por domínio.

Vantagens dessa decisão:

- menor complexidade de deploy;
- autenticação e autorização centralizadas;
- templates e identidade visual compartilhados;
- integração simples entre módulos;
- evolução rápida de funcionalidades internas;
- banco único para dados institucionais.

Trade-offs:

- arquivos globais afetam muitos módulos;
- context processors podem impactar todas as páginas;
- banco e aplicação são pontos únicos de falha;
- crescimento do monólito exige disciplina de código;
- mudanças em permissões podem ter efeitos amplos.

## 5. Stack Técnica

Backend:

- Python 3
- Django 5.2.10
- Django ORM
- Django Templates
- Django Admin
- Django Auth com backends customizados

Banco:

- MySQL/MariaDB no ambiente principal
- SQLite apenas para cenários locais ou testes simplificados
- charset `utf8mb4`

Frontend:

- HTML server-side renderizado pelo Django
- CSS modular em `static/css/`
- JavaScript vanilla
- sem framework SPA

Estáticos:

- WhiteNoise
- `CompressedManifestStaticFilesStorage`
- `collectstatic` necessário em produção

Documentos e planilhas:

- `python-docx`
- `openpyxl`

Integrações:

- `ldap3` para Active Directory/LDAP
- `pyodbc` em integrações de monitoramento quando aplicável
- `plotly` para visualizações

Client desktop:

- .NET 8
- Windows Forms
- tray icon
- DPAPI
- polling HTTP na API do SGI

## 6. Estrutura do Código

Diretórios críticos:

- `intranet/`: configurações, URLs, views base e context processors.
- `templates/`: templates HTML globais e por módulo.
- `static/`: CSS, JS e imagens estáticas.
- `media/`: uploads, anexos, imagens e evidências.
- `docs/`: documentação e artefatos administrativos.
- `desktop_client_dotnet/`: client Windows de notificações.
- `manage.py`: entrada administrativa Django.

Apps estratégicos:

- `administracao`
- `usuarios`
- `auditoria`
- `notificacoes`
- `acompanhamento_sistemas`
- `sala_situacao_v2`
- `sala_situacao`
- `diario_bordo`
- `licitacoes`
- `ramais`
- `reserva_salas`
- `lousa_digital`
- `monitoramento`
- `contratos`
- `folha_ponto`
- `rastreamento_navegacao`

## 7. Camadas da Aplicação

### Entrada HTTP

Arquivo central: `intranet/urls.py`

Responsável por rotear home, login/logout, admin, módulos funcionais e API desktop.

Rotas estratégicas:

- `/`
- `/admin/`
- `/login/`
- `/logout/`
- `/administracao/`
- `/usuarios/`
- `/auditoria/`
- `/acompanhamento-sistemas/`
- `/sala-de-situacao/`
- `/sala-de-situacao-old/`
- `/api/desktop/`

### Template Global

Arquivo crítico: `templates/base.html`

Concentra:

- layout base;
- navbar;
- mensagens globais;
- modal de login obrigatório;
- modais de notificações;
- sincronização de CSRF;
- regras globais de clique/link;
- alertas do Diário de Bordo;
- alertas do Acompanhamento de Sistemas.

Risco: qualquer alteração no `base.html` deve ser tratada como mudança global.

### Context Processors

Arquivo: `intranet/context_processors.py`

Fornece dados globais para templates:

- perfil/ramal;
- alertas do Diário de Bordo;
- alertas do Acompanhamento de Sistemas;
- acesso à Sala de Situação;
- identidade visual;
- navegação administrativa.

Risco: erro ou consulta pesada em context processor degrada várias páginas.

### Domínio

Cada app concentra seu domínio com:

- models;
- views;
- urls;
- forms;
- services;
- templates;
- tests;
- migrations.

Módulos com `services.py` tendem a concentrar regras de negócio importantes.

### Persistência

O acesso a dados é feito principalmente via Django ORM.

Há uso relevante de:

- migrations por app;
- relacionamentos Django;
- `JSONField`;
- `ContentType`;
- índices em tabelas de crescimento contínuo;
- modelos de histórico/timeline/auditoria.

## 8. Configurações Críticas

Arquivo: `intranet/settings.py`

Variáveis relevantes:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DJANGO_CSRF_COOKIE_SECURE`
- `DJANGO_SESSION_COOKIE_SECURE`
- `DJANGO_SECURE_SSL_REDIRECT`
- `DJANGO_USE_X_FORWARDED_HOST`
- `MYSQL_NAME`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_HOST`
- `MYSQL_PORT`
- `TZ`
- `DESKTOP_CLIENT_BASE_URL`

Recomendações:

- produção deve usar `DEBUG=False`;
- segredo Django deve vir de ambiente;
- `.env` não deve ser versionado;
- cookies seguros devem ser ativados em HTTPS;
- `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` devem acompanhar domínio/IP real;
- alteração de domínio deve ser testada também no client desktop.

## 9. Banco de Dados

Banco principal: MySQL/MariaDB

Configuração via variáveis `MYSQL_*`.

Dados críticos:

- usuários, grupos e permissões;
- setores e grants;
- auditoria;
- notificações;
- dados da Sala de Situação;
- dados do Acompanhamento de Sistemas;
- documentos e termos;
- ramais e dados de contato;
- reservas, contratos e registros administrativos.

Tabelas com crescimento esperado:

- auditoria;
- notificações;
- rastreamento de navegação;
- históricos e timelines;
- anexos.

Recomendações:

- backup antes de migrations;
- rotina de retenção para tabelas volumosas;
- monitoramento de tamanho do banco;
- teste de restauração periódico;
- nunca alterar migrations antigas já aplicadas.

## 10. Arquivos de Mídia

Diretório: `media/`

Contém anexos, fotos, documentos enviados, evidências, imagens de cards e arquivos operacionais.

Ponto crítico: backup somente do banco é insuficiente. Recuperação completa exige banco + `media/` + código + variáveis de ambiente.

## 11. Autenticação

Backends:

- `administracao.ldap_backend.LDAPBackend`
- `usuarios.auth_backends.SetorPermissionBackend`

Fluxo AD/LDAP:

1. usuário informa credenciais;
2. SGI consulta configuração AD persistida;
3. faz bind com conta de serviço;
4. localiza usuário no AD;
5. valida senha;
6. cria/atualiza usuário local;
7. atribui grupos/perfis básicos;
8. permissões efetivas são resolvidas localmente.

Riscos:

- indisponibilidade do AD;
- senha da conta de bind expirada;
- mudança de domínio/base DN;
- falha LDAP;
- ausência de superusuário local.

Recomendação: manter conta administrativa local de contingência.

## 12. Autorização e Permissões

O SGI não usa apenas o modelo simples de grupos do Django.

Há:

- permissões Django;
- perfis por módulo;
- grupos;
- setores;
- grants diretos;
- grants por setor;
- herança na árvore de setores;
- deny explícito com precedência;
- auditoria de resolução de permissão.

Arquivo estratégico: `usuarios/auth_backends.py`

Risco: mudanças em grants/perfis podem liberar ou bloquear áreas inteiras.

Recomendações:

- testar acesso com usuários de perfis diferentes;
- registrar mudanças de permissão;
- revisar usuários administrativos;
- usar auditoria de resolução para investigar acesso.

## 13. Auditoria

App: `auditoria`

Entidade central: `AuditLog`

Middleware crítico: `auditoria.middleware.CurrentUserMiddleware`

Função:

- registrar criação, alteração, exclusão e mudanças de relacionamento;
- preservar autoria;
- armazenar diffs simples;
- permitir rastreabilidade operacional.

Riscos:

- crescimento contínuo;
- perda de autoria se middleware for alterado;
- lentidão se não houver retenção.

Recomendação: política de retenção/exportação de auditoria.

## 14. Notificações

O SGI possui três canais:

- web modal;
- client desktop;
- e-mail.

App central: `notificacoes`

Modelo central: `NotificacaoUsuario`

Campos críticos:

- `user`
- `source_app`
- `event_type`
- `title`
- `body_short`
- `target_url`
- `dedupe_key`
- `payload_json`
- `created_at`
- `displayed_at`
- `read_at`

Comando de teste:

```bash
python manage.py simular_notificacao_desktop USUARIO
```

Riscos:

- acúmulo de notificações não lidas;
- fila antiga aparecendo ao usuário;
- divergência entre exibida/lida;
- domínio incorreto no `target_url`;
- cache/CSS interferindo em modais web.

Recomendação: criar painel técnico de volume, pendências e falhas de notificação.

## 15. Client Desktop

Diretório: `desktop_client_dotnet/`

Stack:

- .NET 8;
- Windows Forms;
- ícone na bandeja;
- popup persistente;
- DPAPI;
- polling a cada 30 segundos;
- log em `%APPDATA%\ClientSGI\clientsgi.log`.

Riscos:

- mudança de domínio;
- HTTPS/certificado;
- proxy de rede;
- token expirado;
- atualização do executável nas estações.

Recomendação: manter instalador versionado e checklist de validação em Windows.

## 16. Módulos Estratégicos

### Administração

Centro de configuração da plataforma: AD, SMTP, identidade visual, atalhos, cards e histórico de notificações.

### Usuários

Base de governança de acesso: perfis, setores, grants, grupos e auditoria de permissão.

### Acompanhamento de Sistemas

Governança de sistemas, ciclos, etapas, interessados, anexos, histórico e notificações.

### Sala de Situação V2

Rota oficial: `/sala-de-situacao/`

Controla processos, entregas, indicadores, monitoramento e dashboards.

### Sala de Situação Legado

Rota: `/sala-de-situacao-old/`

Ainda existe e deve ser diferenciada da v2.

### Licitações

Módulo documental com impacto administrativo e potencialmente jurídico.

### Diário de Bordo

Blocos de trabalho, incrementos, leitura explícita e acompanhamento operacional.

## 17. Frontend e CSS

O frontend é server-rendered.

Pontos críticos:

- `templates/base.html`;
- `static/css/styles.css`;
- `static/css/auth/auth.css`;
- CSS específico por módulo.

Riscos:

- CSS global afetar módulo distante;
- cache de estáticos em produção;
- alterações em modais afetarem home e fluxos globais;
- JavaScript inline dificultar testes.

Recomendações:

- testar home, login, administração e módulos operacionais após mudanças globais;
- rodar `collectstatic`;
- validar com cache limpo;
- evitar concentrar regra de negócio no JavaScript.

## 18. Deploy e Operação

Checklist mínimo:

1. backup do banco;
2. backup de `media/`;
3. atualizar código;
4. instalar dependências se houver mudança;
5. aplicar migrations;
6. rodar `collectstatic`;
7. reiniciar aplicação;
8. validar login;
9. validar home;
10. validar módulos críticos;
11. validar notificações;
12. verificar logs.

Comandos comuns:

```bash
python manage.py migrate
python manage.py collectstatic
python manage.py check
python manage.py test --settings=intranet.settings_test
```

## 19. Backup e Recuperação

Backup completo deve incluir:

- banco MySQL/MariaDB;
- diretório `media/`;
- variáveis de ambiente;
- configuração do servidor;
- versão do código.

Riscos:

- banco sem mídia gera anexos quebrados;
- mídia sem banco perde vínculo;
- código sem `.env` não sobe;
- schema incompatível com migrations causa falha.

Recomendação: testar restauração em ambiente separado.

## 20. Segurança

Pontos críticos:

- `DEBUG=False` em produção;
- `SECRET_KEY` fora do código;
- HTTPS e cookies seguros;
- proteção de `.env`;
- proteção de backups;
- controle do Django Admin;
- revisão de superusuários;
- revisão de tokens desktop;
- revisão de permissões;
- proteção de anexos sensíveis.

Recomendação: revisão trimestral de acessos administrativos e permissões críticas.

## 21. Observabilidade

O SGI possui auditoria de negócio, mas precisa de observabilidade técnica no ambiente.

Recomendações:

- logs centralizados;
- monitoramento de erro 500;
- monitoramento de tempo de resposta;
- monitoramento de disco;
- monitoramento de banco;
- monitoramento de falhas SMTP;
- monitoramento de falhas LDAP;
- contagem de notificações pendentes;
- logs do client desktop.

## 22. Riscos Estratégicos

Conhecimento concentrado:

- risco alto em transição de equipe;
- mitigar com documentação, testes e responsáveis por módulo.

Crescimento do monólito:

- arquitetura atual é adequada, mas requer disciplina;
- mitigar com services, testes e baixa dependência entre apps.

Dados institucionais críticos:

- SGI vem se tornando fonte de verdade;
- mitigar com backup, auditoria e governança.

Integrações:

- AD, SMTP, client desktop e bases externas podem falhar fora do código;
- mitigar com monitoramento e procedimentos de contingência.

Legado vs v2:

- Sala de Situação possui duas versões;
- mitigar com plano formal de convergência.

## 23. Recomendações Estratégicas

Prioridade alta:

- formalizar deploy e rollback;
- documentar ambiente de produção;
- documentar backup/restauração;
- revisar HTTPS, cookies e `DEBUG`;
- mapear superusuários;
- revisar AD e SMTP;
- definir retenção para auditoria, notificações e rastreamento;
- identificar dono funcional por módulo.

Prioridade média:

- ampliar testes dos fluxos críticos;
- criar painel técnico de saúde;
- revisar performance dos context processors;
- revisar queries da home e notificações;
- padronizar logs.

Prioridade estratégica:

- tratar SGI como plataforma institucional;
- criar ciclo de releases;
- criar ambiente de homologação;
- separar backlog técnico e funcional;
- versionar client desktop;
- planejar convergência da Sala de Situação.

## 24. Checklist de Passagem

- Acesso ao GitHub confirmado.
- Acesso ao servidor confirmado.
- Acesso ao banco confirmado.
- Localização do `.env` confirmada.
- Localização de backups confirmada.
- Backup de `media/` confirmado.
- Superusuário local validado.
- Configuração AD revisada.
- Configuração SMTP revisada.
- Rotina de deploy documentada.
- Rotina de `collectstatic` documentada.
- Donos funcionais identificados.
- Riscos comunicados.

## 25. Primeiros Passos para Nova Equipe

1. Subir o sistema localmente.
2. Ler `intranet/settings.py`.
3. Ler `intranet/urls.py`.
4. Ler `templates/base.html`.
5. Revisar `usuarios`, `administracao`, `auditoria` e `notificacoes`.
6. Validar login AD e login local administrativo.
7. Testar permissões com perfis diferentes.
8. Validar backup banco + `media/`.
9. Rodar testes com `intranet.settings_test`.
10. Mapear o deploy real de produção.

## 26. Comandos Úteis

Criar ambiente:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Executar local:

```bash
python manage.py runserver
```

Aplicar migrations:

```bash
python manage.py migrate
```

Gerar estáticos:

```bash
python manage.py collectstatic
```

Rodar testes:

```bash
python manage.py test --settings=intranet.settings_test
```

Gerar notificação:

```bash
python manage.py simular_notificacao_desktop USUARIO
```

Ver migrations:

```bash
python manage.py showmigrations
```

## 27. Configuração Real do Servidor: systemd, Gunicorn, Nginx e Apache

Esta seção foi levantada diretamente no servidor em 07/05/2026.

### Desenho Operacional Atual

O SGI está publicado com a seguinte cadeia:

```text
Cliente/Navegador
  -> Nginx em 0.0.0.0:80 e 0.0.0.0:443
  -> proxy reverso para Gunicorn em 127.0.0.1:8000
  -> Django WSGI intranet.wsgi:application
  -> MariaDB local em 127.0.0.1:3306
```

### Serviços systemd

Serviços relevantes encontrados:

- `intranet.service`: serviço Django/Gunicorn do SGI.
- `nginx.service`: proxy reverso HTTP/HTTPS.
- `mariadb.service`: banco MariaDB local.

Todos estavam `enabled` e `active` no momento da verificação.

Comandos úteis:

```bash
systemctl status intranet.service
systemctl status nginx.service
systemctl status mariadb.service
```

```bash
systemctl restart intranet.service
systemctl reload nginx.service
systemctl restart nginx.service
systemctl restart mariadb.service
```

Para logs:

```bash
journalctl -u intranet.service -f
journalctl -u nginx.service -f
journalctl -u mariadb.service -f
```

### Serviço da Aplicação: intranet.service

Arquivo:

```text
/etc/systemd/system/intranet.service
```

Configuração observada:

```ini
[Unit]
Description=Intranet Django Service
After=network.target

[Service]
Type=simple
User=jesmartins
Group=jesmartins
WorkingDirectory=/home/jesmartins/intranet
EnvironmentFile=/etc/default/intranet
ExecStart=/home/jesmartins/intranet/.venv/bin/gunicorn intranet.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 120
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Pontos importantes:

- executa com usuário/grupo `jesmartins`;
- diretório de trabalho: `/home/jesmartins/intranet`;
- usa o virtualenv local em `/home/jesmartins/intranet/.venv`;
- chama Gunicorn diretamente;
- bind interno em `127.0.0.1:8000`;
- usa 3 workers;
- timeout de 120 segundos;
- reinicia automaticamente em falha;
- lê variáveis de ambiente de `/etc/default/intranet`.

Após alteração no unit file:

```bash
systemctl daemon-reload
systemctl restart intranet.service
```

### Variáveis de Ambiente do Serviço

Arquivo:

```text
/etc/default/intranet
```

O arquivo existe e contém variáveis sensíveis. Não registrar valores em documentação ou commit.

Chaves observadas:

- `DB_ENGINE`
- `MYSQL_NAME`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_HOST`
- `MYSQL_PORT`
- `DJANGO_USE_X_FORWARDED_HOST`
- `DJANGO_SECURE_PROXY_SSL_HEADER_PROTO`

Recomendação: proteger este arquivo com permissão restrita e manter cópia segura em procedimento de recuperação.

### Gunicorn

Processo observado:

```text
/home/jesmartins/intranet/.venv/bin/gunicorn intranet.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 120
```

Processos em execução:

- 1 processo master;
- 3 workers;
- usuário `jesmartins`;
- porta local `127.0.0.1:8000`.

Como Gunicorn está atrás do Nginx e escuta apenas localhost, ele não deve ser exposto diretamente para rede externa.

Comandos úteis:

```bash
systemctl restart intranet.service
journalctl -u intranet.service -n 100 --no-pager
ss -ltnp | grep 8000
```

### Nginx

Serviço:

```text
nginx.service
```

Arquivo principal:

```text
/etc/nginx/nginx.conf
```

Virtual host do SGI:

```text
/etc/nginx/sites-available/intranet.conf
/etc/nginx/sites-enabled/intranet.conf -> /etc/nginx/sites-available/intranet.conf
```

Também existe o site padrão habilitado:

```text
/etc/nginx/sites-enabled/default -> /etc/nginx/sites-available/default
```

Configuração relevante do SGI:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name sgi.seds.sp.gov.br 200.144.29.245;

    client_max_body_size 25m;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
        default_type "text/plain";
        try_files $uri =404;
    }

    location /static/ {
        alias /home/jesmartins/intranet/staticfiles/;
        access_log off;
        expires 7d;
        add_header Cache-Control "public";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header Connection "";
        proxy_read_timeout 120s;
        proxy_connect_timeout 30s;
        proxy_redirect off;
    }
}
```

Há também bloco HTTPS:

```nginx
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name sgi.seds.sp.gov.br 200.144.29.245;

    ssl_certificate /etc/ssl/certs/sgi_seds_sp_gov_br-selfsigned.crt;
    ssl_certificate_key /etc/ssl/private/sgi_seds_sp_gov_br-selfsigned.key;

    client_max_body_size 25m;

    location /static/ {
        alias /home/jesmartins/intranet/staticfiles/;
        access_log off;
        expires 7d;
        add_header Cache-Control "public";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header Connection "";
        proxy_read_timeout 120s;
        proxy_connect_timeout 30s;
        proxy_redirect off;
    }
}
```

Pontos importantes:

- portas públicas: 80 e 443;
- `client_max_body_size` está em 25 MB;
- `/static/` é servido diretamente de `/home/jesmartins/intranet/staticfiles/`;
- aplicação Django recebe o restante via proxy para `127.0.0.1:8000`;
- headers `X-Forwarded-*` estão configurados;
- certificado HTTPS atual é self-signed no caminho `/etc/ssl/...`;
- desafio Let's Encrypt está previsto em `/.well-known/acme-challenge/`.

Comandos úteis:

```bash
nginx -t
nginx -T
systemctl reload nginx.service
systemctl restart nginx.service
journalctl -u nginx.service -n 100 --no-pager
```

Logs padrão:

```text
/var/log/nginx/access.log
/var/log/nginx/error.log
```

### Apache

Não há uso de Apache para servir o SGI neste servidor.

Verificação realizada:

```bash
systemctl status apache2.service
systemctl status httpd.service
```

Resultado observado:

```text
Unit apache2.service could not be found.
Unit httpd.service could not be found.
```

Existe apenas configuração residual comum em `/etc/apache2/conf-available/javascript-common.conf`, sem serviço Apache ativo para a aplicação.

### MariaDB

Serviço:

```text
mariadb.service
```

Estado observado:

- ativo;
- habilitado;
- escutando em `127.0.0.1:3306`;
- versão observada no status: MariaDB 10.11.14 em Ubuntu 24.04.

Comandos úteis:

```bash
systemctl status mariadb.service
journalctl -u mariadb.service -n 100 --no-pager
ss -ltnp | grep 3306
```

Ponto crítico: banco está local e não deve ser exposto em interface pública.

### Portas Observadas

Portas relevantes em escuta:

- `0.0.0.0:80`: Nginx HTTP;
- `0.0.0.0:443`: Nginx HTTPS;
- `127.0.0.1:8000`: Gunicorn/Django;
- `127.0.0.1:3306`: MariaDB.

### Fluxo de Deploy Recomendado Neste Servidor

Fluxo operacional sugerido, considerando a configuração real:

```bash
cd /home/jesmartins/intranet
source .venv/bin/activate
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check
systemctl restart intranet.service
systemctl reload nginx.service
```

Validações após deploy:

```bash
systemctl status intranet.service --no-pager
systemctl status nginx.service --no-pager
journalctl -u intranet.service -n 100 --no-pager
curl -I http://127.0.0.1:8000
curl -I http://sgi.seds.sp.gov.br
```

Observação: se houver alteração em `/etc/systemd/system/intranet.service`, executar `systemctl daemon-reload` antes de reiniciar o serviço.

### Pontos de Atenção Operacional

- O Nginx serve `/static/`, então alterações CSS/JS precisam de `collectstatic`.
- A configuração atual não mostrou bloco explícito para `/media/` no Nginx; validar se uploads/anexos estão sendo servidos pelo Django, por regra externa não listada, ou se é necessário adicionar regra controlada para mídia.
- O certificado HTTPS observado é self-signed; avaliar substituição por certificado institucional ou Let's Encrypt, conforme política da SEDS.
- O site `default` do Nginx está habilitado junto com `intranet.conf`; avaliar se deve permanecer assim ou ser desabilitado para reduzir ambiguidade.
- O Gunicorn está corretamente isolado em localhost.
- O MariaDB está corretamente isolado em localhost.
- Logs do Gunicorn ficam no journald via `intranet.service`.
- Logs do Nginx ficam em `/var/log/nginx/`.
- O arquivo `/etc/default/intranet` contém segredos e deve ser protegido.

## 28. Conclusão

O SGI SEDS deve ser mantido como plataforma estratégica da Secretaria. Ele integra autenticação, autorização, dados administrativos, auditoria, dashboards, documentos, notificações e fluxos operacionais em uma base comum.

A continuidade segura depende de:

1. sustentação técnica: deploy, banco, backups, logs, segurança e testes;
2. governança funcional: donos por módulo, regras de acesso e validação de mudanças;
3. evolução planejada: priorização, documentação e redução de riscos técnicos.

Componentes mais importantes para compreensão inicial:

- `intranet/settings.py`;
- `intranet/urls.py`;
- `templates/base.html`;
- `usuarios`;
- `administracao`;
- `auditoria`;
- `notificacoes`;
- `acompanhamento_sistemas`;
- `sala_situacao_v2`.

Com esses pontos compreendidos, a nova equipe terá base suficiente para operar, corrigir e evoluir o SGI com menor risco.
