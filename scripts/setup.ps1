$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'install-common.ps1')
Assert-PetPrerequisites
$root = Split-Path $PSScriptRoot -Parent
$venv = Join-Path $root '.venv'
# A WSL venv cannot be reused by Windows. Keep it intact; use a Windows subfolder.
if ((Test-Path (Join-Path $venv 'bin/python')) -and !(Test-Path (Join-Path $venv 'Scripts/python.exe'))) {
    $venv = Join-Path $root '.venv/windows'
}
py -3.14 -m venv $venv
if ($LASTEXITCODE -ne 0) { throw 'Failed to create Python 3.14 environment' }
& (Join-Path $venv 'Scripts/python.exe') -m pip install -r (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Failed to install dependencies' }
