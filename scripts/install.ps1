param(
    [switch]$Yes, [switch]$NoCodex, [switch]$CodexWindows, [switch]$CodexWsl,
    [switch]$Autostart, [switch]$NoStart,
    [string]$ClaudeSettingsPath = (Join-Path $env:USERPROFILE '.claude/settings.json'),
    [string]$CodexSettingsPath = (Join-Path $env:USERPROFILE '.codex/hooks.json'),
    [string]$WslSettingsPath = '',
    [string]$StartupFolder = [Environment]::GetFolderPath('Startup')
)
. (Join-Path $PSScriptRoot 'install-common.ps1')
$source = Split-Path $PSScriptRoot -Parent
$base = Join-Path $env:USERPROFILE '.claude-desktop-pet'
$app = Join-Path $base 'app'
# Check prerequisites before changing anything.
Assert-PetPrerequisites
$windows = !$NoCodex -and (Confirm-PetChoice 'Register Windows Codex hooks?' -Yes:$Yes -Selected:$CodexWindows)
$wsl = !$NoCodex -and (Confirm-PetChoice 'Register default WSL Codex hooks?' -Yes:$Yes -Selected:$CodexWsl)
$startup = Confirm-PetChoice 'Start the pet at login?' -Yes:$Yes -Selected:$Autostart
if ($wsl) { Test-PetWslNode }
New-Item -ItemType Directory -Force -Path $app | Out-Null
if ([IO.Path]::GetFullPath($source).TrimEnd('\') -ne [IO.Path]::GetFullPath($app).TrimEnd('\')) {
    # Explicit allowlist: never copy .git, credentials, development environments or harness.
    foreach ($folder in @('desktop_pet', 'assets')) {
        Copy-Item -LiteralPath (Join-Path $source $folder) -Destination $app -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $app 'scripts') | Out-Null
    Copy-Item -LiteralPath (Join-Path $source 'scripts/pet') -Destination (Join-Path $app 'scripts') -Recurse -Force
    Get-ChildItem -LiteralPath (Join-Path $source 'scripts') -Filter '*.ps1' | Copy-Item -Destination (Join-Path $app 'scripts') -Force
    foreach ($file in @('requirements.txt', 'INSTALL.md')) { Copy-Item -LiteralPath (Join-Path $source $file) -Destination $app -Force }
    # Migrate development configuration once; later updates preserve installed user data.
    Get-ChildItem -LiteralPath $source -File | Where-Object { $_.Name -eq 'config.json' -or $_.Name -match '^position(-[0-9a-f]+)?\.json$' } | ForEach-Object {
        $destination = Join-Path $base $_.Name
        if (!(Test-Path -LiteralPath $destination)) { Copy-Item -LiteralPath $_.FullName -Destination $destination }
    }
}
# Remove only retired bundled Flan assets when the replacement is present.
# User configuration and custom character folders are outside this directory.
$flan = Join-Path $app 'assets/pets/flan'
if (Test-Path -LiteralPath (Join-Path $flan 'scenes.json')) {
    foreach ($retired in @('spritesheet.webp', 'idle_smile.png', 'idle_angry.png')) {
        $retiredPath = Join-Path $flan $retired
        if (Test-Path -LiteralPath $retiredPath -PathType Leaf) { Remove-Item -LiteralPath $retiredPath -Force }
    }
}
Set-Content -LiteralPath (Join-Path $app '.installed-pet') -Value '1'
& (Join-Path $app 'scripts/setup.ps1')
# Preserve previous optional registrations in the manifest for uninstall.
$manifestPath = Join-Path $base 'installation.json'
$targets = @()
if (Test-Path -LiteralPath $manifestPath) { $targets = @((Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json).targets) }
function Save-Target($kind, $path) {
    $script:targets = @($script:targets | Where-Object { !($_.kind -eq $kind -and $_.path -eq $path) }) + @(@{kind=$kind;path=$path})
    @{targets=$script:targets} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
}
Update-PetHooks $app 'add' $ClaudeSettingsPath 'claude' (Join-Path $source 'scripts/pet/state-hook.mjs')
Save-Target 'claude' $ClaudeSettingsPath
if ($windows) {
    Update-PetHooks $app 'add' $CodexSettingsPath 'codex' (Join-Path $source 'scripts/pet/codex-hook.mjs')
    Save-Target 'codex' $CodexSettingsPath
}
if ($wsl) {
    $target = Update-PetWslHooks $app 'add' $WslSettingsPath (Join-Path $source 'scripts/pet/codex-hook.mjs')
    Save-Target 'wsl' $target
}
if ($startup) {
    & (Join-Path $app 'scripts/register-startup.ps1') -StartupFolder $StartupFolder
}
# Remember the cleanup target even when the user enables startup later in Settings.
Save-Target 'startup' $StartupFolder
if (!$NoStart) { & (Join-Path $app 'scripts/start.ps1') }
Write-Output "Installed: $app. Restart Claude Code sessions; trust Codex hooks again when enabled."
