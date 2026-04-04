# Client SGI Desktop (.NET)

Cliente Windows nativo para consumir a API desktop da intranet.

## Stack

- .NET 8
- Windows Forms
- NotifyIcon para bandeja
- popup próprio persistente no canto inferior direito
- DPAPI para proteger token e senha localmente
- log local em `%APPDATA%\ClientSGI\clientsgi.log`
- inicialização automática por padrão após o primeiro login
- ícone customizado opcional em `Assets\clientsgi.ico`

## Como rodar no Windows

```powershell
cd C:\intranet\desktop_client_dotnet
dotnet restore
dotnet run
```

Se quiser usar ícone próprio, coloque antes um arquivo em:

```text
desktop_client_dotnet\Assets\clientsgi.ico
```

## Como publicar um executável

Executável self-contained para Windows x64:

```powershell
dotnet publish -c Release -r win-x64 --self-contained true
```

Saída esperada:

```text
bin\Release\net8.0-windows\win-x64\publish\
```

Executável esperado:

```text
bin\Release\net8.0-windows\win-x64\publish\clientsgi.exe
```

## Instalação MVP

Depois do `publish`, use os scripts da pasta `installer`:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\installer\Install-ClientSgi.ps1 -PublishDir .\bin\Release\net8.0-windows\win-x64\publish
```

Isso copia o app para:

```text
%LOCALAPPDATA%\Programs\ClientSGI
```

E cria atalhos no menu iniciar e na área de trabalho.

Para remover:

```powershell
.\installer\Uninstall-ClientSgi.ps1
```

## Passo a passo de publicação no Windows

1. Copie a pasta `desktop_client_dotnet` para uma máquina Windows.
2. Instale o .NET 8 SDK.
3. Abra PowerShell dentro da pasta do projeto.
4. Rode:

```powershell
dotnet restore
dotnet build -c Release
dotnet publish -c Release -r win-x64 --self-contained true
```

5. Abra a pasta:

```text
bin\Release\net8.0-windows\win-x64\publish\
```

6. Execute `clientsgi.exe`.
7. No primeiro login, informe como base URL:

```text
http://sgi.seds.sp.gov.br
```

## Checklist de validação

- login concluído
- ícone visível na bandeja
- log sendo gravado em `%APPDATA%\ClientSGI\clientsgi.log`
- nova notificação aparecendo no painel da janela
- popup próprio aparecendo no canto inferior direito
- clique em `Abrir` abrindo a URL
- clique em `Fechar` dispensando apenas o popup
- item sendo marcado como lido no servidor

## Fluxos do MVP

- login manual com credenciais salvas localmente
- reautenticação automática ao reiniciar
- polling a cada 30 segundos
- popup próprio persistente até ação do usuário
- clique em `Abrir` abre a URL da intranet
- marcação de exibida e lida via API
