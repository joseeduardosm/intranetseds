param(
    [Parameter(Mandatory = $true)]
    [string]$PublishDir,
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\ClientSGI",
    [switch]$NoDesktopShortcut
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $PublishDir)) {
    throw "Pasta de publish nao encontrada: $PublishDir"
}

$exePath = Join-Path $PublishDir "clientsgi.exe"
if (-not (Test-Path $exePath)) {
    throw "Nao encontrei clientsgi.exe em: $PublishDir"
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Copy-Item -Path (Join-Path $PublishDir "*") -Destination $InstallDir -Recurse -Force

$shell = New-Object -ComObject WScript.Shell
$startMenuShortcut = Join-Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs" "Client SGI.lnk"
$shortcut = $shell.CreateShortcut($startMenuShortcut)
$shortcut.TargetPath = (Join-Path $InstallDir "clientsgi.exe")
$shortcut.WorkingDirectory = $InstallDir
$shortcut.Save()

if (-not $NoDesktopShortcut) {
    $desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Client SGI.lnk"
    $desktop = $shell.CreateShortcut($desktopShortcut)
    $desktop.TargetPath = (Join-Path $InstallDir "clientsgi.exe")
    $desktop.WorkingDirectory = $InstallDir
    $desktop.Save()
}

Write-Host "Client SGI instalado em: $InstallDir"
Write-Host "Execute: $(Join-Path $InstallDir 'clientsgi.exe')"
