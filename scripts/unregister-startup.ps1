param([string]$StartupFolder = [Environment]::GetFolderPath('Startup'))
$ErrorActionPreference = 'Stop'
$link = Join-Path $StartupFolder 'ClaudeDesktopPet.lnk'
if (Test-Path -LiteralPath $link) { Remove-Item -LiteralPath $link }
