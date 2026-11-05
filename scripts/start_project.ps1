param([ValidateSet('run','check','verify')][string]$Mode = 'run')
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
Set-Location -LiteralPath $projectDir
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'setup_runtime.ps1') -ProjectRoot $projectDir
    if ($LASTEXITCODE -ne 0) { throw 'Python setup failed.' }
    $pythonExe = Join-Path $projectDir 'runtime\python\python.exe'
    & $pythonExe -B (Join-Path $PSScriptRoot 'bootstrap_project.py')
    if ($LASTEXITCODE -ne 0) { throw 'Offline data setup failed.' }
    if ($Mode -eq 'verify') {
        & $pythonExe -B (Join-Path $PSScriptRoot 'verify_project.py')
    } elseif ($Mode -eq 'check') {
        & $pythonExe -B (Join-Path $projectDir 'start_full_demo.py') --check
    } else {
        & $pythonExe -B (Join-Path $projectDir 'start_full_demo.py')
    }
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host 'See README.md. AnyLogic 8.9.10 PLE must be installed separately.'
    exit 1
}
