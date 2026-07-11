[CmdletBinding(DefaultParameterSetName = "Check")]
param(
    [Parameter(ParameterSetName = "Check")]
    [switch]$Check,

    [Parameter(Mandatory = $true, ParameterSetName = "Write")]
    [switch]$Write,

    [string]$UvPath = "uv",
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$versionFile = Join-Path $repoRoot ".python-version"
$expectedPython = (Get-Content -Raw $versionFile).Trim()

$uvCommand = Get-Command $UvPath -ErrorAction Stop
$uvVersion = (& $uvCommand.Source --version).Trim()

if ($uvVersion -notmatch '^uv 0\.9\.28(?:\s|$)') {
    throw "uv 0.9.28 is required to refresh dependency locks; found '$uvVersion'."
}

if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = (& $uvCommand.Source python find $expectedPython `
        --managed-python --no-python-downloads --no-project).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($PythonPath)) {
        throw "Could not find the managed Python $expectedPython interpreter."
    }
}

$pythonCommand = Get-Command $PythonPath -ErrorAction Stop
$actualPython = (& $pythonCommand.Source -c "import platform; print(platform.python_version())").Trim()

if ($actualPython -ne $expectedPython) {
    throw "Python $expectedPython is required to refresh dependency locks; found '$actualPython'."
}

$tempRoot = Join-Path $repoRoot ".local\tmp\runtime-baseline"
$runRoot = Join-Path $tempRoot ("locks-" + [Guid]::NewGuid().ToString("N"))
$publishArtifacts = @()
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null

function New-LockFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceName,

        [Parameter(Mandatory = $true)]
        [string]$OutputPath
    )

    $sourcePath = Join-Path $repoRoot $SourceName
    & $uvCommand.Source --quiet --no-progress pip compile `
        --python $pythonCommand.Source `
        --python-version 3.12 `
        --universal `
        --generate-hashes `
        --no-annotate `
        --no-header `
        --output-file $OutputPath `
        $sourcePath
    if ($LASTEXITCODE -ne 0) {
        throw "uv failed to compile $SourceName."
    }

    $content = [System.IO.File]::ReadAllText($OutputPath)
    $normalized = $content.Replace("`r`n", "`n").Replace("`r", "`n").TrimEnd("`n") + "`n"
    [System.IO.File]::WriteAllText(
        $OutputPath,
        $normalized,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Test-FilesEqual {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExpectedPath,

        [Parameter(Mandatory = $true)]
        [string]$ActualPath
    )

    if (-not (Test-Path -LiteralPath $ExpectedPath)) {
        return $false
    }

    $expectedBytes = [System.IO.File]::ReadAllBytes($ExpectedPath)
    $actualBytes = [System.IO.File]::ReadAllBytes($ActualPath)
    if ($expectedBytes.Length -ne $actualBytes.Length) {
        return $false
    }
    return [System.Convert]::ToBase64String($expectedBytes) -ceq `
        [System.Convert]::ToBase64String($actualBytes)
}

function Assert-LockFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -eq 0 -or $bytes[$bytes.Length - 1] -ne 10) {
        throw "$Path must be non-empty and end with a newline."
    }
    if ($bytes -contains 13) {
        throw "$Path must use LF line endings."
    }

    $entryCount = 0
    $hashCount = 0
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            throw "$Path contains an empty line."
        }

        if (-not [char]::IsWhiteSpace($line[0])) {
            if ($entryCount -gt 0 -and $hashCount -eq 0) {
                throw "$Path contains an unhashed requirement."
            }
            if ($line -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]*==[^ ;\s]+(?: ; .+)? \\$') {
                throw "$Path contains a non-exact requirement: $line"
            }
            $entryCount += 1
            $hashCount = 0
            continue
        }

        if ($entryCount -eq 0 -or $line -notmatch '^\s+--hash=sha256:[0-9a-f]{64}(?: \\)?$') {
            throw "$Path contains an unsupported lock continuation: $line"
        }
        $hashCount += 1
    }

    if ($entryCount -eq 0 -or $hashCount -eq 0) {
        throw "$Path does not contain a complete hashed requirement."
    }
}

function Get-LockEntryBlocks {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $entries = @{}
    $current = @()
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        if (-not [char]::IsWhiteSpace($line[0])) {
            if ($current.Count -gt 0) {
                $name = ($current[0] -split '==', 2)[0].ToLowerInvariant().Replace('_', '-').Replace('.', '-')
                if ($entries.ContainsKey($name)) {
                    throw "$Path pins $name more than once."
                }
                $entries[$name] = $current -join "`n"
            }
            $current = @($line)
        }
        else {
            $current += $line
        }
    }

    if ($current.Count -gt 0) {
        $name = ($current[0] -split '==', 2)[0].ToLowerInvariant().Replace('_', '-').Replace('.', '-')
        if ($entries.ContainsKey($name)) {
            throw "$Path pins $name more than once."
        }
        $entries[$name] = $current -join "`n"
    }
    return $entries
}

function Assert-LockPair {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProductionPath,

        [Parameter(Mandatory = $true)]
        [string]$DevelopmentPath
    )

    $production = Get-LockEntryBlocks -Path $ProductionPath
    $development = Get-LockEntryBlocks -Path $DevelopmentPath
    if ($development.Count -le $production.Count) {
        throw "The development lock must include dependencies beyond the production lock."
    }

    foreach ($name in $production.Keys) {
        if (-not $development.ContainsKey($name) -or `
            $development[$name] -cne $production[$name]) {
            throw "The production lock entry for $name is not an exact component of the development lock."
        }
    }
}

function Invoke-AtomicFileReplacement {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,

        [Parameter(Mandatory = $true)]
        [string]$TargetPath
    )

    if (-not (Test-Path -LiteralPath $TargetPath)) {
        [System.IO.File]::Move($SourcePath, $TargetPath)
        return
    }

    $targetDirectory = Split-Path -Parent $TargetPath
    $targetName = Split-Path -Leaf $TargetPath
    $replaceBackupPath = Join-Path $targetDirectory `
        (".$targetName.replace-" + [Guid]::NewGuid().ToString("N") + ".bak")
    $script:publishArtifacts += $replaceBackupPath
    try {
        [System.IO.File]::Replace($SourcePath, $TargetPath, $replaceBackupPath)
        return
    }
    catch [System.PlatformNotSupportedException] {
        # Use the byte-preserving fallback only where atomic replacement is unavailable.
    }
    catch [System.NotSupportedException] {
        # Use the byte-preserving fallback only where atomic replacement is unavailable.
    }

    [System.IO.File]::WriteAllBytes(
        $TargetPath,
        [System.IO.File]::ReadAllBytes($SourcePath)
    )
    Remove-Item -LiteralPath $SourcePath -Force
}

function Restore-LockTarget {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$State
    )

    if (-not $State.HadOriginal) {
        if (Test-Path -LiteralPath $State.TargetPath) {
            Remove-Item -LiteralPath $State.TargetPath -Force
        }
        return
    }

    $targetDirectory = Split-Path -Parent $State.TargetPath
    $targetName = Split-Path -Leaf $State.TargetPath
    $rollbackPath = Join-Path $targetDirectory `
        (".$targetName.rollback-" + [Guid]::NewGuid().ToString("N") + ".tmp")
    $script:publishArtifacts += $rollbackPath
    [System.IO.File]::WriteAllBytes(
        $rollbackPath,
        [System.IO.File]::ReadAllBytes($State.BackupPath)
    )
    Invoke-AtomicFileReplacement -SourcePath $rollbackPath -TargetPath $State.TargetPath
}

function Publish-LockFiles {
    param(
        [Parameter(Mandatory = $true)]
        [array]$Locks
    )

    $token = [Guid]::NewGuid().ToString("N")
    $states = @()

    foreach ($lock in $Locks) {
        $targetDirectory = Split-Path -Parent $lock.TargetPath
        $targetName = Split-Path -Leaf $lock.TargetPath
        $publishPath = Join-Path $targetDirectory ".$targetName.publish-$token.tmp"
        $backupPath = Join-Path $targetDirectory ".$targetName.backup-$token.bak"
        $hadOriginal = Test-Path -LiteralPath $lock.TargetPath
        $script:publishArtifacts += @($publishPath, $backupPath)

        [System.IO.File]::WriteAllBytes(
            $publishPath,
            [System.IO.File]::ReadAllBytes($lock.GeneratedPath)
        )
        if ($hadOriginal) {
            [System.IO.File]::WriteAllBytes(
                $backupPath,
                [System.IO.File]::ReadAllBytes($lock.TargetPath)
            )
        }

        $states += @{
            BackupPath = $backupPath
            HadOriginal = $hadOriginal
            PublishPath = $publishPath
            TargetName = $lock.Target
            TargetPath = $lock.TargetPath
        }
    }

    $attempted = @()
    try {
        foreach ($state in $states) {
            $attempted += $state
            Invoke-AtomicFileReplacement `
                -SourcePath $state.PublishPath `
                -TargetPath $state.TargetPath
            Write-Host "Updated $($state.TargetName)"
        }
    }
    catch {
        $publishError = $_
        $rollbackErrors = @()
        for ($index = $attempted.Count - 1; $index -ge 0; $index -= 1) {
            try {
                Restore-LockTarget -State $attempted[$index]
            }
            catch {
                $rollbackErrors += $_.Exception.Message
            }
        }

        if ($rollbackErrors.Count -gt 0) {
            throw "Lock publication failed ('$($publishError.Exception.Message)') and rollback failed: $($rollbackErrors -join '; ')"
        }
        throw $publishError
    }
}

try {
    $locks = @(
        @{ Source = "requirements-prod.txt"; Target = "requirements-prod.lock" },
        @{ Source = "requirements-dev.txt"; Target = "requirements-dev.lock" }
    )
    # Phase one: compile and validate every output before any tracked target changes.
    foreach ($lock in $locks) {
        $generatedPath = Join-Path $runRoot $lock.Target
        New-LockFile -SourceName $lock.Source -OutputPath $generatedPath
        Assert-LockFile -Path $generatedPath
        $lock.GeneratedPath = $generatedPath
        $lock.TargetPath = Join-Path $repoRoot $lock.Target
    }
    Assert-LockPair `
        -ProductionPath $locks[0].GeneratedPath `
        -DevelopmentPath $locks[1].GeneratedPath

    if ($Write) {
        Publish-LockFiles -Locks $locks
    }
    else {
        $stale = @()
        foreach ($lock in $locks) {
            if (-not (Test-FilesEqual `
                -ExpectedPath $lock.TargetPath `
                -ActualPath $lock.GeneratedPath)) {
                $stale += $lock.Target
            }
        }

        if ($stale.Count -gt 0) {
            throw "Dependency locks are stale: $($stale -join ', '). Run this script with -Write."
        }

        Write-Host "Dependency locks match their source requirements."
    }
}
finally {
    foreach ($artifactPath in $publishArtifacts) {
        if (Test-Path -LiteralPath $artifactPath) {
            Remove-Item -LiteralPath $artifactPath -Force
        }
    }
    if (Test-Path -LiteralPath $runRoot) {
        Remove-Item -LiteralPath $runRoot -Recurse -Force
    }
}
