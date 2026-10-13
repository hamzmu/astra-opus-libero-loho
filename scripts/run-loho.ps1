param(
    [ValidateSet('wsl', 'windows')][string]$Platform = 'wsl',
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$RunnerArguments
)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
if (!$RunnerArguments) { $RunnerArguments = @('smoke') }
if ($Platform -eq 'wsl') {
    $linuxScript = ((wsl -d Ubuntu-24.04 --exec wslpath -a (Join-Path $PSScriptRoot 'run_wsl.sh')) | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not resolve WSL launcher path' }
    wsl -d Ubuntu-24.04 --exec bash $linuxScript @RunnerArguments
} else {
    $python = Join-Path $workspace '.venv-windows\Scripts\python.exe'
    # Task 4's filenames exceed MAX_PATH inside the OneDrive workspace.
    if (Test-Path -LiteralPath 'C:\loho-libero') {
        $junction = Get-Item -LiteralPath 'C:\loho-libero'
        if ($junction.LinkType -ne 'Junction' -or $junction.Target[0] -ne (Join-Path $workspace 'LIBERO-LOHO')) {
            throw 'C:\loho-libero points to a different repository'
        }
        $env:LOHO_REPO = 'C:\loho-libero'
    }
    & $python -u (Join-Path $workspace 'src\loho_frontier_eval.py') @RunnerArguments
}
exit $LASTEXITCODE
