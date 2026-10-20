$ErrorActionPreference = 'Stop'
function Assert-PetPrerequisites {
    $pythonHelp = 'Python 3.14 を https://www.python.org/downloads/windows/ から入れてください。Python Launcher (py) も必要です。導入後は PowerShell を開き直してください。'
    try { $pythonVersion = & py -3.14 --version } catch { throw $pythonHelp }
    if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch '^Python 3[.]14[.]') { throw $pythonHelp }
    $nodeHelp = 'Node.js 22 以上を https://nodejs.org/ から入れてください。導入後は PowerShell を開き直してください。'
    try { $nodeVersion = & node --version } catch { throw $nodeHelp }
    if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch '^v([0-9]+)[.]' -or [int]$Matches[1] -lt 22) { throw $nodeHelp }
}
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE). Fix the error and retry." }
}
function Confirm-PetChoice {
    param([string]$Question, [switch]$Yes, [switch]$Selected)
    if ($Selected) { return $true }
    if ($Yes) { return $false }
    return (Read-Host "$Question [y/N]") -match '^(y|yes)$'
}
function Update-PetHooks {
    param([string]$App, [string]$Action, [string]$Target, [string]$Kind, [string]$Previous)
    New-Item -ItemType Directory -Force -Path (Split-Path $Target -Parent) | Out-Null
    $utility = if ($Kind -eq 'claude') { 'settings.mjs' } else { 'codex-settings.mjs' }
    Invoke-Checked 'node' @((Join-Path $App "scripts/pet/$utility"), $Action, $Target, $Previous)
}
# A fixed shell program forwards positional arguments without evaluating them.
function Invoke-PetWslNode {
    param([string[]]$NodeArguments)
    $program = 'exec node "$@"'
    # Windows PowerShell's legacy native binder strips embedded quotes.
    # Escape only the fixed program; paths remain separate positional arguments.
    if ($PSVersionTable.PSVersion.Major -lt 7 -or $PSNativeCommandArgumentPassing -eq 'Legacy') {
        $program = $program.Replace('"', '\"')
    }
    Invoke-Checked 'wsl.exe' (@('--exec', 'bash', '-lc', $program, 'node') + $NodeArguments)
}
function Test-PetWslNode {
    $version = Invoke-PetWslNode @('--version')
    if ($version -notmatch '^v(2[2-9]|[3-9][0-9]|[1-9][0-9]{2,})\.') { throw 'Install Node 22+ in WSL first' }
}
function Update-PetWslHooks {
    param([string]$App, [string]$Action, [string]$Target, [string]$Previous)
    $utility = & wsl.exe --exec wslpath -u (Join-Path $App 'scripts/pet/codex-settings.mjs')
    if ($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed' }
    $old = ''
    if ($Previous) {
        $old = & wsl.exe --exec wslpath -u $Previous
        if ($LASTEXITCODE -ne 0) { throw 'WSL old path conversion failed' }
    }
    if (!$Target) {
        $wslHome = & wsl.exe --exec printenv HOME
        $Target = $wslHome.TrimEnd('/') + '/.codex/hooks.json'
        if ($LASTEXITCODE -ne 0) { throw 'Install Node 22+ in WSL first' }
    }
    # The settings tool requires its parent directory, normally created by Codex.
    Invoke-PetWslNode @($utility.Trim(), $Action, $Target.Trim(), $old)
    return $Target.Trim()
}
