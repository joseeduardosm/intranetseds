Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$venvPath = Join-Path $PSScriptRoot ".venv"
$activate = Join-Path $venvPath "Scripts\\Activate.ps1"

if (-not (Test-Path $venvPath)) {
  Write-Host "Criando venv em $venvPath"
  python -m venv $venvPath
}

if (-not (Test-Path $activate)) {
  throw "Ativador do venv não encontrado: $activate"
}

Write-Host "Ativando venv"
& $activate

Write-Host "Instalando dependências"
python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")

Write-Host "Iniciando servidor"
python (Join-Path $PSScriptRoot "manage.py") runserver @Args
