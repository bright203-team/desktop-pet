$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root '.venv/Scripts/pythonw.exe'
if (!(Test-Path $python)) { $python = Join-Path $root '.venv/windows/Scripts/pythonw.exe' }
if (!(Test-Path $python)) { throw 'Run scripts/setup.ps1 first' }
Start-Process -FilePath $python -ArgumentList '-m desktop_pet' -WorkingDirectory $root
