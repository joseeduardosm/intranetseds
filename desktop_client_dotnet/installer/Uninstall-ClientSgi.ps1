$ErrorActionPreference = "Stop"

$installDir = "$env:LOCALAPPDATA\Programs\ClientSGI"
$startMenuShortcut = Join-Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs" "Client SGI.lnk"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Client SGI.lnk"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

if (Test-Path $installDir) {
    Remove-Item $installDir -Recurse -Force
}

if (Test-Path $startMenuShortcut) {
    Remove-Item $startMenuShortcut -Force
}

if (Test-Path $desktopShortcut) {
    Remove-Item $desktopShortcut -Force
}

if ((Get-ItemProperty -Path $runKey -Name "ClientSGI" -ErrorAction SilentlyContinue)) {
    Remove-ItemProperty -Path $runKey -Name "ClientSGI" -ErrorAction SilentlyContinue
}

Write-Host "Client SGI removido."
