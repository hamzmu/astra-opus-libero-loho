$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $workspace '.venv-windows'
$repo = Join-Path $workspace 'LIBERO-LOHO'
New-Item -ItemType Directory -Path (Join-Path $workspace 'setup_logs') -Force | Out-Null
if (!(Test-Path -LiteralPath (Join-Path $repo 'setup.py'))) {
    git clone --depth 1 https://github.com/markli1hoshipu/LIBERO-LOHO.git $repo
    if ($LASTEXITCODE -ne 0) { throw 'Could not clone LIBERO-LoHo' }
}
if (!(Test-Path -LiteralPath (Join-Path $runtime 'Scripts\python.exe'))) {
    uv venv --python 3.8 $runtime
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Windows environment' }
}
$python = Join-Path $runtime 'Scripts\python.exe'
# Robomimic's training dependencies include a Linux-only egl-probe build.
# The LIBERO environment and benchmark imports do not require Robomimic.
$requirements = Join-Path $workspace 'setup_logs\requirements-windows-sim.txt'
Get-Content -LiteralPath (Join-Path $workspace 'requirements-sim.txt') | Where-Object { $_ -notmatch '^robomimic==' } | Set-Content -LiteralPath $requirements
uv pip install --python $python --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match -r $requirements
if ($LASTEXITCODE -ne 0) { throw 'Windows dependency installation failed' }
uv pip install --python $python -e (Join-Path $workspace 'LIBERO-LOHO')
if ($LASTEXITCODE -ne 0) { throw 'Windows source installation failed' }
# A short junction avoids the unusually long task-4 filenames on Windows.
$shortRepo = 'C:\loho-libero'
if (Test-Path -LiteralPath $shortRepo) {
    $item = Get-Item -LiteralPath $shortRepo
    if ($item.LinkType -ne 'Junction' -or $item.Target[0] -ne $repo) {
        throw "The short repository path $shortRepo already belongs to another directory"
    }
} else {
    New-Item -ItemType Junction -Path $shortRepo -Target $repo | Out-Null
}
& $python (Join-Path $PSScriptRoot 'patch_windows_runtime.py')
if ($LASTEXITCODE -ne 0) { throw 'Windows compatibility patch failed' }
uv pip check --python $python
if ($LASTEXITCODE -ne 0) { throw 'Windows dependency consistency check failed' }
uv pip freeze --python $python | Set-Content (Join-Path $workspace 'setup_logs\windows-freeze.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not record Windows dependency versions' }
exit 0
