param([switch]$Yes, [switch]$RemoveSettings)
. (Join-Path $PSScriptRoot 'install-common.ps1')
$base = Join-Path $env:USERPROFILE '.claude-desktop-pet'
$app = Join-Path $base 'app'
$manifestPath = Join-Path $base 'installation.json'
$remove = Confirm-PetChoice 'Also delete pet configuration and saved positions?' -Yes:$Yes -Selected:$RemoveSettings
if (!(Test-Path -LiteralPath (Join-Path $app '.installed-pet'))) { throw 'Installed app marker missing; refusing to delete an unknown directory.' }
if (!(Test-Path -LiteralPath $manifestPath)) { throw 'Installation manifest missing; cannot safely remove hooks. Reinstall first.' }
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
foreach ($target in $manifest.targets) {
    if ($target.kind -eq 'startup') {
        & (Join-Path $app 'scripts/unregister-startup.ps1') -StartupFolder $target.path
    } elseif ($target.kind -eq 'wsl') {
        $null = Update-PetWslHooks $app 'remove' $target.path ''
    } elseif ($target.kind -in @('claude','codex')) {
        Update-PetHooks $app 'remove' $target.path $target.kind ''
    } else { throw 'Unknown installation target; refusing partial deletion.' }
}
# Close the tray app before uninstalling; locked files cause a clear failure, never kill unrelated Python.
Remove-Item -LiteralPath $app -Recurse -Force
Remove-Item -LiteralPath $manifestPath
if ($remove) {
    Get-ChildItem -LiteralPath $base -File | Where-Object { $_.Name -eq 'config.json' -or $_.Name -match '^position(-[0-9a-f]+)?\.json$' } | Remove-Item -Force
}
Write-Output 'Pet removed. State files are disposable; user configuration is retained unless requested.'
