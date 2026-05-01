# Client SGI Desktop

Client Windows em Python para consumir a API desktop da intranet.

## MVP

- login manual com usuario e senha
- persistencia local de token e `since_id`
- polling de notificacoes
- popup via `QSystemTrayIcon`
- clique abre a URL no navegador

## Execucao local

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r desktop_client/requirements.txt
python desktop_client/app.py
```

## Empacotamento

```bash
pyinstaller --noconsole --name clientsgi desktop_client/app.py
```

