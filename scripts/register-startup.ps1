param([string]$StartupFolder = [Environment]::GetFolderPath('Startup'))
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force -Path $StartupFolder | Out-Null
$shell = New-Object -ComObject WScript.Shell
$icon = Join-Path $root 'assets/ui/icon.ico'
$linkPath = Join-Path $StartupFolder 'ClaudeDesktopPet.lnk'
# WScript rejects assigning an empty IconLocation. Recreate only our link
# when artwork is missing, so a stale custom icon does not survive.
if (!(Test-Path -LiteralPath $icon -PathType Leaf) -and (Test-Path -LiteralPath $linkPath -PathType Leaf)) {
    Remove-Item -LiteralPath $linkPath -Force
}
$link = $shell.CreateShortcut($linkPath)
$link.TargetPath = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$link.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $root 'scripts/start.ps1') + '"'
$link.WorkingDirectory = $root
if (Test-Path -LiteralPath $icon -PathType Leaf) {
    $link.IconLocation = $icon + ',0'
}
$link.Save()
