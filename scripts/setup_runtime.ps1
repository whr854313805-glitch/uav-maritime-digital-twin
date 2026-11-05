param(
    [string]$ProjectRoot = '',
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

function Get-Sha256([string]$LiteralFile) {
    $inputFile = [IO.File]::OpenRead($LiteralFile)
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
        Remove-Item -LiteralPath $absoluteTarget -Recurse -Force
    }
}

$runtimeLock = $null
$temporaryArchive = $null
$staging = $null
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
            if (!(Test-Path -LiteralPath $criticalPath -PathType Leaf) -or
                (Get-Item -LiteralPath $criticalPath).Length -ne $entry.bytes -or
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
        $runtimeLock = [IO.File]::Open((Join-Path $localRoot 'runtime-bootstrap.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch {
        throw 'Another project window is preparing Python. Wait for it to finish, then start again.'
    }
    Write-Output 'Preparing offline Python. This only runs on the first launch or after a runtime update.'
    $temporaryArchive = Join-Path $localRoot ('python-runtime-' + [Guid]::NewGuid().ToString('N') + '.zip')
    $combined = [IO.File]::Open($temporaryArchive, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        foreach ($part in $manifest.parts) {
            if ([IO.Path]::GetFileName($part.file) -ne $part.file -or $part.file -notmatch '^windows-python\.zip\.part[0-9]+$') {
                throw 'Unexpected offline runtime part filename.'
            }
            $partPath = Join-Path $packageRoot $part.file
            if (!(Test-Path -LiteralPath $partPath -PathType Leaf)) {
                throw ('Offline runtime part is missing: ' + $part.file + '. Download the complete repository.')
            }
            if ((Get-Item -LiteralPath $partPath).Length -ne $part.bytes -or (Get-Sha256 $partPath) -ne $part.sha256) {
                throw ('Offline runtime part is damaged: ' + $part.file + '. Download it again.')
            }
            $inputPart = [IO.File]::OpenRead($partPath)
            try { $inputPart.CopyTo($combined) } finally { $inputPart.Dispose() }
        }
    } finally {
        $combined.Dispose()
    }
    if ((Get-Item -LiteralPath $temporaryArchive).Length -ne $manifest.archive_bytes -or (Get-Sha256 $temporaryArchive) -ne $manifest.archive_sha256) {
        throw 'The combined offline runtime archive failed its integrity check.'
    }
    $staging = Join-Path $localRoot ('python-unpack-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $staging | Out-Null
    [AppContext]::SetSwitch('Switch.System.IO.UseLegacyPathHandling', $false)
    [AppContext]::SetSwitch('Switch.System.IO.BlockLongPaths', $false)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($temporaryArchive)
    try {
        $allowedPrefix = [IO.Path]::GetFullPath($staging).TrimEnd('\') + '\'
        foreach ($entry in $zip.Entries) {
            $target = [IO.Path]::GetFullPath((Join-Path $staging $entry.FullName))
            if (!$target.StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Offline runtime archive contains an unsafe path.'
            }
        }
    } finally {
        $zip.Dispose()
    }
    # Windows 10 (1803+) and Windows 11 include libarchive's tar.exe. Unlike
    # .NET Framework's ZIP extractor it supports deep Unicode project paths.
    $windowsTar = Join-Path $env:SystemRoot 'System32\tar.exe'
    if (Test-Path -LiteralPath $windowsTar -PathType Leaf) {
        & $windowsTar -xf $temporaryArchive -C $staging
        if ($LASTEXITCODE -ne 0) { throw 'Could not extract the offline Python archive.' }
    } else {
        try {
            [IO.Compression.ZipFile]::ExtractToDirectory($temporaryArchive, $staging)
        } catch {
            throw 'Windows ZIP extraction failed. Move the complete project to a shorter path, or use Windows 10 (1803+) / Windows 11.'
        }
    }
    if (!(Test-Path -LiteralPath (Join-Path $staging 'python.exe') -PathType Leaf)) {
        throw 'The offline runtime archive is incomplete.'
    }
    $env:PYTHONDONTWRITEBYTECODE = '1'
    & (Join-Path $staging 'python.exe') -I -c "import sys,numpy,shapely,pyproj,yaml,PIL,websockets,requests; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); p.stop(); print('Python '+sys.version.split()[0]+' and project dependencies are ready.')"
    if ($LASTEXITCODE -ne 0) {
        throw 'Offline Python validation failed. Check Windows security/quarantine history and the project startup log.'
    }
    [IO.File]::WriteAllText((Join-Path $staging '.runtime-manifest-sha256'), $manifestSha, [Text.Encoding]::ASCII)
    if (Test-Path -LiteralPath $runtimeRoot) {
        if (!(Test-Path -LiteralPath $stamp -PathType Leaf)) {
            throw 'runtime\python already exists but is not a managed runtime. Move it aside and start again.'
        }
        $backup = Join-Path $localRoot ('python-previous-' + [Guid]::NewGuid().ToString('N'))
        Assert-PathUnder $runtimeRoot (Join-Path $root 'runtime')
        Assert-PathUnder $backup $localRoot
        Move-Item -LiteralPath $runtimeRoot -Destination $backup
        Write-Output ('Previous managed runtime saved at ' + $backup)
    }
    Assert-PathUnder $staging $localRoot
    Assert-PathUnder $runtimeRoot (Join-Path $root 'runtime')
    Move-Item -LiteralPath $staging -Destination $runtimeRoot
    $staging = $null
    Write-Output 'Offline Python runtime prepared successfully.'
    exit 0
} catch {
    Write-Error $_.Exception.Message -ErrorAction Continue
    exit 1
} finally {
    if ($null -ne $runtimeLock) { $runtimeLock.Dispose() }
    if ($null -ne $temporaryArchive -and (Test-Path -LiteralPath $temporaryArchive)) {
        Remove-Item -LiteralPath $temporaryArchive -Force
    }
    if ($null -ne $staging) { Remove-Staging $staging $localRoot }
}
