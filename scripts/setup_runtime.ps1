param(
    [string]$ProjectRoot = '',
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

[AppContext]::SetSwitch('Switch.System.IO.UseLegacyPathHandling', $false)
[AppContext]::SetSwitch('Switch.System.IO.BlockLongPaths', $false)
function Get-ExtendedPath([string]$LiteralPath) {
    $absolute = [IO.Path]::GetFullPath($LiteralPath)
    if ($absolute.StartsWith('\\?\')) { return $absolute }
    if ($absolute.StartsWith('\\')) { return '\\?\UNC\' + $absolute.Substring(2) }
    return '\\?\' + $absolute
}

function Get-FileLength([string]$LiteralFile) {
    $stream = [IO.File]::OpenRead((Get-ExtendedPath $LiteralFile))
    try { return $stream.Length } finally { $stream.Dispose() }
}

function Get-Sha256([string]$LiteralFile) {
    $inputFile = [IO.File]::OpenRead((Get-ExtendedPath $LiteralFile))
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($hasher.ComputeHash($inputFile)).Replace('-', '').ToLowerInvariant()
    } finally {
        $hasher.Dispose()
        $inputFile.Dispose()
    }
}

function Assert-PathUnder([string]$LiteralTarget, [string]$ExpectedParent) {
    $targetFull = [IO.Path]::GetFullPath($LiteralTarget)
    $parentPrefix = [IO.Path]::GetFullPath($ExpectedParent).TrimEnd('\') + '\'
    if (!$targetFull.StartsWith($parentPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing a filesystem operation outside the intended project directory.'
    }
}

function Move-ManagedRuntimeDirectory([string]$SourcePath, [string]$DestinationPath,
        [string]$SourceParent, [string]$DestinationParent, [int]$RetryCount = 80) {
    Assert-PathUnder $SourcePath $SourceParent
    Assert-PathUnder $DestinationPath $DestinationParent
    for ($attempt = 0; $attempt -le $RetryCount; $attempt++) {
        try {
            [IO.Directory]::Move((Get-ExtendedPath $SourcePath), (Get-ExtendedPath $DestinationPath))
            return
        } catch [IO.IOException] {
            $moveError = $_.Exception
        } catch [UnauthorizedAccessException] {
            $moveError = $_.Exception
        }
        if ($attempt -eq $RetryCount) {
            throw ('Runtime folder is still unavailable after bounded retries: ' + $SourcePath + '. ' + $moveError.Message)
        }
        Write-Verbose 'Runtime folder move is temporarily unavailable; retrying within the fixed limit.'
        Start-Sleep -Milliseconds 250
    }
}

function Remove-Staging([string]$LiteralTarget, [string]$LocalRoot) {
    $absoluteTarget = [IO.Path]::GetFullPath($LiteralTarget)
    $absoluteLocal = [IO.Path]::GetFullPath($LocalRoot).TrimEnd('\') + '\'
    if (!$absoluteTarget.StartsWith($absoluteLocal, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing to clean a temporary path outside this project.'
    }
    if ([IO.Path]::GetFileName($absoluteTarget) -notlike 'python-unpack-*') {
        throw 'Refusing to clean an unexpected temporary path.'
    }
    if (Test-Path -LiteralPath $absoluteTarget) {
        Remove-Item -LiteralPath (Get-ExtendedPath $absoluteTarget) -Recurse -Force
    }
}

$runtimeLock = $null
$temporaryArchive = $null
$staging = $null
$backup = $null
try {
    if (![Environment]::Is64BitOperatingSystem) {
        throw 'This project runtime requires 64-bit Windows 10 or Windows 11.'
    }
    if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
        if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'runtime\packages')) {
            $ProjectRoot = $PSScriptRoot
        } else {
            $ProjectRoot = Split-Path -Parent $PSScriptRoot
        }
    }
    $root = [IO.Path]::GetFullPath($ProjectRoot)
    $packageRoot = Join-Path $root 'runtime\packages'
    $manifestPath = Join-Path $packageRoot 'windows-python.manifest.json'
    if (!(Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw 'Offline runtime manifest is missing. Download and extract the complete GitHub project.'
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.platform -ne 'windows-x86_64' -or $manifest.schema_version -ne 1) {
        throw 'Unsupported offline runtime manifest.'
    }
    $runtimeRoot = Join-Path $root 'runtime\python'
    $pythonExe = Join-Path $runtimeRoot 'python.exe'
    $stamp = Join-Path $runtimeRoot '.runtime-manifest-sha256'
    $manifestSha = Get-Sha256 $manifestPath
    $ready = (Test-Path -LiteralPath $pythonExe -PathType Leaf) -and (Test-Path -LiteralPath $stamp -PathType Leaf)
    if ($ready) {
        $ready = (Get-Content -LiteralPath $stamp -Raw).Trim() -eq $manifestSha
    }
    if ($ready) {
        foreach ($entry in $manifest.critical_files) {
            $criticalPath = [IO.Path]::GetFullPath((Join-Path $runtimeRoot $entry.file))
            Assert-PathUnder $criticalPath $runtimeRoot
            if (![IO.File]::Exists((Get-ExtendedPath $criticalPath)) -or
                (Get-FileLength $criticalPath) -ne $entry.bytes -or
                (Get-Sha256 $criticalPath) -ne $entry.sha256) {
                $ready = $false
                break
            }
        }
    }
    if ($ready) {
        Write-Output 'Offline Python runtime is ready.'
        exit 0
    }
    if ($CheckOnly) {
        Write-Output 'Offline Python runtime has not been extracted for this version.'
        exit 2
    }
    $localRoot = Join-Path $root '.local'
    New-Item -ItemType Directory -Path $localRoot -Force | Out-Null
    try {
        $runtimeLock = [IO.File]::Open((Get-ExtendedPath (Join-Path $localRoot 'runtime-bootstrap.lock')), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch {
        throw 'Another project window is preparing Python. Wait for it to finish, then start again.'
    }
    Write-Output 'Preparing offline Python. This only runs on the first launch or after a runtime update.'
    $temporaryArchive = Join-Path $localRoot ('python-runtime-' + [Guid]::NewGuid().ToString('N') + '.zip')
    $combined = [IO.File]::Open((Get-ExtendedPath $temporaryArchive), [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        foreach ($part in $manifest.parts) {
            if ([IO.Path]::GetFileName($part.file) -ne $part.file -or $part.file -notmatch '^windows-python\.zip\.part[0-9]+$') {
                throw 'Unexpected offline runtime part filename.'
            }
            $partPath = Join-Path $packageRoot $part.file
            if (!(Test-Path -LiteralPath $partPath -PathType Leaf)) {
                throw ('Offline runtime part is missing: ' + $part.file + '. Download the complete repository.')
            }
            if ((Get-FileLength $partPath) -ne $part.bytes -or (Get-Sha256 $partPath) -ne $part.sha256) {
                throw ('Offline runtime part is damaged: ' + $part.file + '. Download it again.')
            }
            $inputPart = [IO.File]::OpenRead((Get-ExtendedPath $partPath))
            try { $inputPart.CopyTo($combined) } finally { $inputPart.Dispose() }
        }
    } finally {
        $combined.Dispose()
    }
    if ((Get-FileLength $temporaryArchive) -ne $manifest.archive_bytes -or (Get-Sha256 $temporaryArchive) -ne $manifest.archive_sha256) {
        throw 'The combined offline runtime archive failed its integrity check.'
    }
    $staging = Join-Path $localRoot ('python-unpack-' + [Guid]::NewGuid().ToString('N').Substring(0,12))
    [IO.Directory]::CreateDirectory((Get-ExtendedPath $staging)) | Out-Null
    [AppContext]::SetSwitch('Switch.System.IO.UseLegacyPathHandling', $false)
    [AppContext]::SetSwitch('Switch.System.IO.BlockLongPaths', $false)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    # .NET keeps UTF-16 paths end-to-end. Windows tar can replace Unicode names
    # with '?' on an English system, even though the archive itself is valid.
    $zip = [IO.Compression.ZipFile]::OpenRead((Get-ExtendedPath $temporaryArchive))
    try {
        $allowedPrefix = [IO.Path]::GetFullPath($staging).TrimEnd('\') + '\'
        foreach ($entry in $zip.Entries) {
            $target = [IO.Path]::GetFullPath((Join-Path $staging $entry.FullName))
            if (!$target.StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Offline runtime archive contains an unsafe path.'
            }
            if ([string]::IsNullOrEmpty($entry.Name)) {
                [IO.Directory]::CreateDirectory((Get-ExtendedPath $target)) | Out-Null
                continue
            }
            [IO.Directory]::CreateDirectory((Get-ExtendedPath ([IO.Path]::GetDirectoryName($target)))) | Out-Null
            $outputFile = [IO.FileStream]::new((Get-ExtendedPath $target), [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            try {
                $inputEntry = $entry.Open()
                try { $inputEntry.CopyTo($outputFile) } finally { $inputEntry.Dispose() }
            } finally { $outputFile.Dispose() }
        }
    } finally { $zip.Dispose() }
    if (![IO.File]::Exists((Get-ExtendedPath (Join-Path $staging 'python.exe')))) {
        throw 'The offline runtime archive is incomplete.'
    }
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $probeInfo = [Diagnostics.ProcessStartInfo]::new()
    $probeInfo.FileName = Join-Path $staging 'python.exe'
    $probeCode = "import sys,numpy,shapely,pyproj,yaml,PIL,websockets,requests; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); p.stop(); print('Python '+sys.version.split()[0]+' and project dependencies are ready.')"
    $probeInfo.Arguments = '-I -c "' + $probeCode + '"'
    $probeInfo.UseShellExecute = $false
    $probeInfo.CreateNoWindow = $true
    $probeInfo.RedirectStandardOutput = $true
    $probeInfo.RedirectStandardError = $true
    $probeProcess = [Diagnostics.Process]::new()
    $probeProcess.StartInfo = $probeInfo
    try {
        if (!$probeProcess.Start()) { throw 'Could not start bundled Python validation.' }
        $probeOutput = $probeProcess.StandardOutput.ReadToEndAsync()
        $probeErrors = $probeProcess.StandardError.ReadToEndAsync()
        if (!$probeProcess.WaitForExit(120000)) {
            $probeProcess.Kill()
            throw 'Offline Python validation timed out. Check Windows security/quarantine history.'
        }
        Write-Output $probeOutput.Result.Trim()
        if ($probeProcess.ExitCode -ne 0) {
            Write-Output $probeErrors.Result.Trim()
            throw 'Offline Python validation failed. Try a short writable project path such as C:\uav; check Windows security/quarantine history and the startup log.'
        }
    } finally { $probeProcess.Dispose() }
    [IO.File]::WriteAllText((Get-ExtendedPath (Join-Path $staging '.runtime-manifest-sha256')), $manifestSha, [Text.Encoding]::ASCII)
    if (Test-Path -LiteralPath $runtimeRoot) {
        if (!(Test-Path -LiteralPath $stamp -PathType Leaf)) {
            throw 'runtime\python already exists but is not a managed runtime. Move it aside and start again.'
        }
        $backup = Join-Path $localRoot ('python-previous-' + [Guid]::NewGuid().ToString('N'))
        Assert-PathUnder $runtimeRoot (Join-Path $root 'runtime')
        Assert-PathUnder $backup $localRoot
        Move-ManagedRuntimeDirectory $runtimeRoot $backup (Join-Path $root 'runtime') $localRoot
        Write-Output ('Previous managed runtime saved at ' + $backup)
    }
    Assert-PathUnder $staging $localRoot
    Assert-PathUnder $runtimeRoot (Join-Path $root 'runtime')
    try {
        Move-ManagedRuntimeDirectory $staging $runtimeRoot $localRoot (Join-Path $root 'runtime')
    } catch {
        $publishError = $_.Exception
        if ($null -ne $backup -and
                (Test-Path -LiteralPath $backup) -and !(Test-Path -LiteralPath $runtimeRoot)) {
            Move-ManagedRuntimeDirectory $backup $runtimeRoot $localRoot (Join-Path $root 'runtime')
        }
        throw $publishError
    }
    $staging = $null
    Write-Output 'Offline Python runtime prepared successfully.'
    exit 0
} catch {
    Write-Error $_.Exception.Message -ErrorAction Continue
    exit 1
} finally {
    if ($null -ne $runtimeLock) { $runtimeLock.Dispose() }
    if ($null -ne $temporaryArchive -and [IO.File]::Exists((Get-ExtendedPath $temporaryArchive))) {
        Assert-PathUnder $temporaryArchive $localRoot
        [IO.File]::Delete((Get-ExtendedPath $temporaryArchive))
    }
    if ($null -ne $staging) { Remove-Staging $staging $localRoot }
}
