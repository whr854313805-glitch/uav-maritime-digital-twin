param([ValidateSet('run','check','verify','recover')][string]$Mode = 'run')
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
Set-Location -LiteralPath $projectDir
$launchMutex = $null
$ownsMutex = $false
try {
    # One complete startup pipeline per checkout, including extraction.
    $hash = [Security.Cryptography.SHA256]::Create()
    try { $key = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($projectDir.ToLowerInvariant()))).Replace('-','') } finally { $hash.Dispose() }
    $launchMutex = [Threading.Mutex]::new($false, ('Local\UAVStartup-' + $key))
    try { $ownsMutex = $launchMutex.WaitOne(240000) } catch [Threading.AbandonedMutexException] { $ownsMutex = $true }
    if (!$ownsMutex) { throw 'Another startup is still running for this project. No duplicate model was started.' }
    $localDir = Join-Path $projectDir '.local'
    New-Item -ItemType Directory -Path $localDir -Force | Out-Null
    $probe = Join-Path $localDir ('write-check-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try { [IO.File]::WriteAllText($probe, 'ok') } finally { if (Test-Path -LiteralPath $probe) { Remove-Item -LiteralPath $probe -Force } }
    $required = [long]104857600
    if (!(Test-Path -LiteralPath (Join-Path $projectDir 'runtime\python\python.exe'))) {
        $runtimeInfo = Get-Content -LiteralPath (Join-Path $projectDir 'runtime\packages\windows-python.manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $required += [long]$runtimeInfo.expanded_bytes + [long]$runtimeInfo.archive_bytes
    }
    if (!(Test-Path -LiteralPath (Join-Path $projectDir 'data\official'))) {
        $dataInfo = Get-Content -LiteralPath (Join-Path $projectDir 'runtime\data\current-data.manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $required += [long]$dataInfo.expanded_bytes
    }
    $volume = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($projectDir))
    if ($volume.AvailableFreeSpace -lt $required) { throw 'Not enough free disk space to prepare/run the project. Free space, then retry.' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'setup_runtime.ps1') -ProjectRoot $projectDir
    if ($LASTEXITCODE -ne 0) { throw 'Python setup failed.' }
    $pythonExe = Join-Path $projectDir 'runtime\python\python.exe'
    if ($Mode -eq 'recover') {
        & $pythonExe -B (Join-Path $PSScriptRoot 'bootstrap_project.py') --recover-latest
        exit $LASTEXITCODE
    }
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
} finally {
    if ($ownsMutex) { $launchMutex.ReleaseMutex() }
    if ($null -ne $launchMutex) { $launchMutex.Dispose() }
}
