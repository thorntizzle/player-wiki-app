param(
    [ValidateSet("install", "bootstrap", "run", "environment-check", "phase-closeout-anchor-render", "phase-closeout-anchor-write", "phase-closeout-anchor-verify", "runtime-check", "backup", "restore", "restore-status", "restore-resume", "restore-rollback", "restore-rehearsal", "artifact-inventory", "artifact-retention-assess", "player-wiki-reconciliation-dry-run", "player-wiki-reconciliation-apply", "prepare-fly-campaigns", "sync-fly", "deploy-fly")]
    [string]$Action = "run",
    [string]$PythonPath = "",
    [string]$DbPath = "",
    [string]$BackupArchive = "",
    [string]$BackupDir = "",
    [string]$BackupLabel = "",
    [string]$PhaseCloseoutSourceRoot = "",
    [string]$PhaseCloseoutCanonicalRoot = "",
    [string]$PhaseCloseoutLedgerRoot = "",
    [string]$PhaseCloseoutSourceRef = "",
    [string]$PhaseCloseoutCanonicalRef = "",
    [string]$PhaseCloseoutLedgerRef = "",
    [string]$PhaseCloseoutSourcePath = "",
    [string]$PhaseCloseoutCanonicalPath = "",
    [string]$PhaseCloseoutLedgerPath = "",
    [string]$PhaseCloseoutFrozenIdentity = "",
    [string]$PhaseCloseoutClassificationReceipt = "",
    [string]$PhaseCloseoutPhase = "",
    [string]$PhaseCloseoutFinalizedUtc = "",
    [string]$PhaseCloseoutPlan = "",
    [string]$PhaseCloseoutOutput = "",
    [switch]$PhaseCloseoutReplaceExisting,
    [string[]]$ArtifactDataRoot = @(),
    [string[]]$ArtifactArchiveRoot = @(),
    [string[]]$ArtifactScratchRoot = @(),
    [double]$ArtifactAsOfEpoch = [double]::NaN,
    [ValidateSet("all", "publication", "deletion")]
    [string]$ReconciliationKind = "all",
    [string]$ReconciliationCampaignSlug = "",
    [string]$ReconciliationPageRef = "",
    [ValidateSet("", "prepared", "repository_pending", "conflict")]
    [string]$ReconciliationState = "",
    [string]$ReconciliationOperationId = "",
    [ValidateSet("", "abandon-precommit", "resume-forward", "retry-refresh-cleanup")]
    [string]$ReconciliationApplyAction = "",
    [switch]$ConfirmReconciliationApply,
    [string]$FlyApp = $(if ($env:PLAYER_WIKI_FLY_APP) { $env:PLAYER_WIKI_FLY_APP } else { "campaign-player-wiki-example" }),
    [string]$FlyMachineId = "",
    [string]$FlyctlPath = "",
    [string]$AdminEmail = "",
    [string]$AdminName = "Admin User",
    [string]$AdminPassword = "",
    [switch]$ForceRestore,
    [switch]$ForceSyncFromFly,
    [switch]$SkipPreSyncBackup
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
Import-Module -Name (Join-Path $projectRoot "scripts\evidence_lock.psm1") -Force -ErrorAction Stop
$sampleFlyApp = "campaign-player-wiki-example"
$persistedFlyApp = [Environment]::GetEnvironmentVariable("PLAYER_WIKI_FLY_APP", "User")
$localTempRoot = ""
$localTempRunRoots = @()

if ($FlyApp -eq $sampleFlyApp -and -not [string]::IsNullOrWhiteSpace($persistedFlyApp)) {
    $FlyApp = $persistedFlyApp
}
if (-not [string]::IsNullOrWhiteSpace($DbPath)) {
    $env:PLAYER_WIKI_DB_PATH = $DbPath
}

function Set-LocalTempEnvironment {
    param([Parameter(Mandatory = $true)][string]$ScopeName)
    $randomSuffix = [Guid]::NewGuid().ToString("N").Substring(0, 8)
    $scopePrefix = (($ScopeName.Split("-") | ForEach-Object { $_.Substring(0, 1) }) -join "")
    $runName = "$scopePrefix-$PID-$randomSuffix"
    $script:localTempRoot = Join-Path $projectRoot ".local\tmp\$runName"
    $script:localTempRunRoots = @(@{
        Target = $script:localTempRoot
        Anchor = Join-Path $projectRoot ".local\tmp"
    })
    New-Item -ItemType Directory -Path $script:localTempRoot -Force | Out-Null
    $env:PLAYER_WIKI_TEMP_DIR = $script:localTempRoot
    $env:TEMP = $script:localTempRoot
    $env:TMP = $script:localTempRoot
    $env:TMPDIR = $script:localTempRoot
}

function Assert-DeployTempRootHasNoReparseDescendants {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $pendingDirectories = [System.Collections.Generic.Stack[string]]::new()
    $pendingDirectories.Push($Root)
    while ($pendingDirectories.Count -gt 0) {
        $currentDirectory = $pendingDirectories.Pop()
        foreach ($child in Get-ChildItem -LiteralPath $currentDirectory -Force -ErrorAction Stop) {
            if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "reparse point"
            }
            if ($child.PSIsContainer) {
                $pendingDirectories.Push($child.FullName)
            }
        }
    }
}

function Remove-DeployRunTempRoots {
    if ($null -eq $script:localTempRunRoots -or $script:localTempRunRoots.Count -eq 0) {
        return
    }

    $validatedRoots = @()

    foreach ($entry in $script:localTempRunRoots) {
        try {
            $target = [System.IO.Path]::GetFullPath([string]$entry.Target)
            $anchor = [System.IO.Path]::GetFullPath([string]$entry.Anchor).TrimEnd(
                [System.IO.Path]::DirectorySeparatorChar,
                [System.IO.Path]::AltDirectorySeparatorChar
            )
            $targetParent = [System.IO.Path]::GetDirectoryName($target).TrimEnd(
                [System.IO.Path]::DirectorySeparatorChar,
                [System.IO.Path]::AltDirectorySeparatorChar
            )
            if (-not [string]::Equals(
                $targetParent,
                $anchor,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
                throw "invalid parent"
            }
            if (Test-Path -LiteralPath $target -ErrorAction Stop) {
                $targetItem = Get-Item -LiteralPath $target -Force -ErrorAction Stop
                if (($targetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                    throw "reparse point"
                }
                Assert-DeployTempRootHasNoReparseDescendants -Root $target
            }
            $validatedRoots += $target
        } catch {
            throw "Deploy temporary directory cleanup failed safety validation."
        }
    }

    $cleanupFailed = $false
    foreach ($target in $validatedRoots) {
        try {
            if (Test-Path -LiteralPath $target -ErrorAction Stop) {
                $targetItem = Get-Item -LiteralPath $target -Force -ErrorAction Stop
                if (($targetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                    throw "reparse point"
                }
                Assert-DeployTempRootHasNoReparseDescendants -Root $target

                if (Test-Path -LiteralPath $target -ErrorAction Stop) {
                    $targetItem = Get-Item -LiteralPath $target -Force -ErrorAction Stop
                    if (($targetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                        throw "reparse point"
                    }
                    Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction Stop
                }
            }
        } catch {
            $cleanupFailed = $true
        }
        try {
            if (Test-Path -LiteralPath $target -ErrorAction Stop) {
                $cleanupFailed = $true
            }
        } catch {
            $cleanupFailed = $true
        }
    }
    if ($cleanupFailed) {
        throw "Deploy temporary directory cleanup failed."
    }
}

function Resolve-PythonExecutable {
    if (-not [string]::IsNullOrWhiteSpace($PythonPath)) {
        return $PythonPath
    }
    if (-not [string]::IsNullOrWhiteSpace($env:PLAYER_WIKI_PYTHON_PATH)) {
        return $env:PLAYER_WIKI_PYTHON_PATH
    }

    $candidates = @(
        (Join-Path (Split-Path $projectRoot -Parent) ".venv\Scripts\python.exe"),
        (Join-Path $projectRoot ".venv\Scripts\python.exe")
    )
    $gitCommand = Get-Command "git" -ErrorAction SilentlyContinue
    if ($gitCommand) {
        $commonDir = & $gitCommand.Source -C $projectRoot rev-parse --path-format=absolute --git-common-dir 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($commonDir)) {
            $primaryRepoRoot = Split-Path $commonDir.Trim() -Parent
            $candidates += Join-Path (Split-Path $primaryRepoRoot -Parent) ".venv\Scripts\python.exe"
        }
    }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    return $candidates[0]
}

function Invoke-Python {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $PythonPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $PythonPath $($Arguments -join ' ')"
    }
}

function Ensure-Python {
    $script:PythonPath = Resolve-PythonExecutable
    if (-not (Test-Path $PythonPath)) {
        throw "Python executable not found at $PythonPath"
    }
}

function Resolve-FlyctlExecutable {
    if (-not [string]::IsNullOrWhiteSpace($FlyctlPath)) {
        if (-not (Test-Path $FlyctlPath)) {
            throw "flyctl executable not found at $FlyctlPath"
        }
        return $FlyctlPath
    }

    $command = Get-Command "flyctl" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $defaultFlyctl = Join-Path $HOME ".fly\bin\flyctl.exe"
    if (Test-Path $defaultFlyctl) {
        return $defaultFlyctl
    }

    throw "flyctl executable not found. Pass -FlyctlPath or install flyctl."
}

function Get-SavedFlyAccessToken {
    $configPath = Join-Path $HOME ".fly\config.yml"
    if (-not (Test-Path $configPath)) {
        return $null
    }

    try {
        $configContent = Get-Content $configPath -Raw -ErrorAction Stop
    } catch {
        return $null
    }

    $match = [regex]::Match($configContent, '(?m)^access_token:\s*(.+?)\s*$')
    if (-not $match.Success) {
        return $null
    }

    $token = $match.Groups[1].Value.Trim().Trim("'").Trim('"')
    if ([string]::IsNullOrWhiteSpace($token)) {
        return $null
    }

    return $token
}

function Ensure-FlyAccessToken {
    if (-not [string]::IsNullOrWhiteSpace($env:FLY_ACCESS_TOKEN)) {
        return
    }

    if (-not [string]::IsNullOrWhiteSpace($env:FLYCTL_ACCESS_TOKEN)) {
        return
    }

    $savedToken = Get-SavedFlyAccessToken
    if ([string]::IsNullOrWhiteSpace($savedToken)) {
        return
    }

    $env:FLY_ACCESS_TOKEN = $savedToken
    Write-Host "Using saved Fly access token from local config for this process."
}

function Resolve-GitExecutable {
    $command = Get-Command "git" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        "C:\Program Files\Git\cmd\git.exe",
        "C:\Program Files\Git\bin\git.exe",
        (Join-Path $HOME "AppData\Local\Programs\Git\cmd\git.exe"),
        (Join-Path $HOME "AppData\Local\Programs\Git\bin\git.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Get-DeployBuildMetadata {
    $buildId = Get-Date -Format "yyyyMMdd-HHmmss"
    $gitSha = "unknown"
    $gitDirty = "false"
    $gitExecutable = Resolve-GitExecutable

    if ($gitExecutable) {
        $shaOutput = & $gitExecutable -C $projectRoot rev-parse HEAD 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($shaOutput)) {
            $gitSha = $shaOutput.Trim()
        }

        $statusOutput = & $gitExecutable -C $projectRoot status --short 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($statusOutput)) {
            $gitDirty = "true"
        }
    }

    return @{
        BuildId = $buildId
        GitSha = $gitSha
        GitDirty = $gitDirty
    }
}

function Install-Dependencies {
    Write-Host "Installing development dependencies..."
    Invoke-Python -Arguments @(
        "-m",
        "pip",
        "install",
        "-r",
        (Join-Path $projectRoot "requirements-dev.txt")
    )
}

function Initialize-Database {
    Write-Host "Initializing local database..."
    Invoke-Python -Arguments @(
        (Join-Path $projectRoot "manage.py"),
        "init-db"
    )
}

function Ensure-AdminUser {
    if ([string]::IsNullOrWhiteSpace($AdminEmail)) {
        Write-Host "Skipping admin bootstrap. Pass -AdminEmail and -AdminPassword to create or confirm an admin user."
        return
    }
    if ([string]::IsNullOrWhiteSpace($AdminPassword)) {
        throw "AdminPassword is required when AdminEmail is provided."
    }

    Write-Host "Ensuring local admin user exists..."
    Invoke-Python -Arguments @(
        (Join-Path $projectRoot "manage.py"),
        "ensure-admin",
        $AdminEmail,
        $AdminName,
        "--password",
        $AdminPassword
    )
}

function Run-App {
    Write-Host "Starting Campaign Player Wiki..."
    Invoke-Python -Arguments @(
        (Join-Path $projectRoot "run.py")
    )
}

function Test-RuntimeContainer {
    Write-Host "Validating the pinned production container..."
    & (Join-Path $projectRoot "scripts\validate_runtime_container.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime container validation failed."
    }
}

function Backup-LocalState {
    Write-Host "Creating local backup archive..."
    $arguments = @(
        (Join-Path $projectRoot "ops.py"),
        "backup"
    )
    if (-not [string]::IsNullOrWhiteSpace($BackupDir)) {
        $arguments += @("--output-dir", $BackupDir)
    }
    if (-not [string]::IsNullOrWhiteSpace($BackupLabel)) {
        $arguments += @("--label", $BackupLabel)
    }

    Invoke-Python -Arguments $arguments
}

function Restore-LocalState {
    if ([string]::IsNullOrWhiteSpace($BackupArchive)) {
        throw "BackupArchive is required for restore."
    }
    if (-not [string]::IsNullOrWhiteSpace($BackupLabel)) {
        throw "BackupLabel is not accepted for restore; mandatory prebackup names are transaction-correlated."
    }
    if (-not $ForceRestore) {
        throw "Restore is destructive. Re-run with -ForceRestore."
    }

    Write-Host "Restoring local backup archive..."
    $arguments = @(
        (Join-Path $projectRoot "ops.py"),
        "restore",
        $BackupArchive,
        "--yes"
    )
    if (-not [string]::IsNullOrWhiteSpace($BackupDir)) {
        $arguments += @("--output-dir", $BackupDir)
    }

    Invoke-Python -Arguments $arguments
}

function Get-RestoreStatus {
    Write-Host "Inspecting restore recovery state..."
    Invoke-Python -Arguments @(
        (Join-Path $projectRoot "ops.py"),
        "restore-status"
    )
}

function Resume-RestoreTransaction {
    if (-not $ForceRestore) {
        throw "Restore recovery mutates local state. Re-run with -ForceRestore."
    }

    Write-Host "Resuming interrupted restore transaction..."
    Invoke-Python -Arguments @(
        (Join-Path $projectRoot "ops.py"),
        "restore-resume",
        "--yes"
    )
}

function Rollback-RestoreTransaction {
    if (-not $ForceRestore) {
        throw "Restore recovery mutates local state. Re-run with -ForceRestore."
    }

    Write-Host "Rolling back interrupted restore transaction..."
    Invoke-Python -Arguments @(
        (Join-Path $projectRoot "ops.py"),
        "restore-rollback",
        "--yes"
    )
}

function Test-RestoreRehearsal {
    if ([string]::IsNullOrWhiteSpace($BackupArchive)) {
        throw "BackupArchive is required for restore rehearsal."
    }

    Write-Host "Rehearsing restore in a disposable workspace..."
    Invoke-Python -Arguments @(
        (Join-Path $projectRoot "ops.py"),
        "restore-rehearsal",
        $BackupArchive
    )
}

function Prepare-FlyCampaigns {
    Ensure-FlyAccessToken
    Write-Host "Preparing Fly campaigns volume..."
    $arguments = @(
        (Join-Path $projectRoot "ops.py"),
        "prepare-fly-campaigns",
        "--app",
        $FlyApp
    )
    if (-not [string]::IsNullOrWhiteSpace($FlyMachineId)) {
        $arguments += @("--machine-id", $FlyMachineId)
    }
    if (-not [string]::IsNullOrWhiteSpace($FlyctlPath)) {
        $arguments += @("--flyctl-path", $FlyctlPath)
    }

    Invoke-Python -Arguments $arguments
}

function Sync-FromFly {
    if (-not $ForceSyncFromFly) {
        throw "Sync is destructive. Re-run with -ForceSyncFromFly."
    }

    Ensure-FlyAccessToken
    Write-Host "Mirroring live Fly state into the local app..."
    $arguments = @(
        (Join-Path $projectRoot "ops.py"),
        "sync-from-fly",
        "--app",
        $FlyApp,
        "--yes"
    )
    if (-not [string]::IsNullOrWhiteSpace($FlyMachineId)) {
        $arguments += @("--machine-id", $FlyMachineId)
    }
    if (-not [string]::IsNullOrWhiteSpace($FlyctlPath)) {
        $arguments += @("--flyctl-path", $FlyctlPath)
    }
    if (-not [string]::IsNullOrWhiteSpace($BackupDir)) {
        $arguments += @("--output-dir", $BackupDir)
    }
    if (-not [string]::IsNullOrWhiteSpace($BackupLabel)) {
        $arguments += @("--pre-sync-label", $BackupLabel)
    }
    if ($SkipPreSyncBackup) {
        $arguments += "--skip-pre-sync-backup"
    }

    Invoke-Python -Arguments $arguments
}

function Deploy-Fly {
    if ([string]::IsNullOrWhiteSpace($FlyApp) -or $FlyApp -eq $sampleFlyApp) {
        throw "Set PLAYER_WIKI_FLY_APP or pass -FlyApp with the real Fly app name before deploying."
    }

    Ensure-FlyAccessToken
    $resolvedFlyctl = Resolve-FlyctlExecutable
    $configPath = Join-Path $projectRoot "fly.toml"
    $metadata = Get-DeployBuildMetadata

    Write-Host "Deploying to Fly app $FlyApp..."
    Write-Host "Using build id $($metadata.BuildId), git sha $($metadata.GitSha), dirty=$($metadata.GitDirty)."

    $arguments = @(
        "deploy",
        "--config", $configPath,
        "--app", $FlyApp,
        "--build-arg", "PLAYER_WIKI_BUILD_ID=$($metadata.BuildId)",
        "--build-arg", "PLAYER_WIKI_GIT_SHA=$($metadata.GitSha)",
        "--build-arg", "PLAYER_WIKI_GIT_DIRTY=$($metadata.GitDirty)"
    )

    & $resolvedFlyctl @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Fly deploy failed."
    }
}

function Invoke-ArtifactReport {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("artifact-inventory", "artifact-retention-assess")]
        [string]$Command
    )

    if (($ArtifactDataRoot.Count + $ArtifactArchiveRoot.Count + $ArtifactScratchRoot.Count) -eq 0) {
        [Console]::Error.WriteLine("At least one explicit artifact root is required.")
        exit 2
    }

    $arguments = @((Join-Path $projectRoot "ops.py"), $Command)
    foreach ($root in $ArtifactDataRoot) {
        $arguments += @("--data-root", $root)
    }
    foreach ($root in $ArtifactArchiveRoot) {
        $arguments += @("--archive-root", $root)
    }
    foreach ($root in $ArtifactScratchRoot) {
        $arguments += @("--scratch-root", $root)
    }
    if (-not [double]::IsNaN($ArtifactAsOfEpoch)) {
        $arguments += @("--as-of-epoch", $ArtifactAsOfEpoch.ToString(
            [System.Globalization.CultureInfo]::InvariantCulture
        ))
    }

    & $PythonPath @arguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Invoke-PlayerWikiReconciliationDryRun {
    $arguments = @(
        (Join-Path $projectRoot "ops.py"),
        "player-wiki-reconciliation-dry-run",
        "--kind",
        $ReconciliationKind
    )
    if (-not [string]::IsNullOrWhiteSpace($ReconciliationCampaignSlug)) {
        $arguments += @("--campaign-slug", $ReconciliationCampaignSlug)
    }
    if (-not [string]::IsNullOrWhiteSpace($ReconciliationPageRef)) {
        $arguments += @("--page-ref", $ReconciliationPageRef)
    }
    if (-not [string]::IsNullOrWhiteSpace($ReconciliationState)) {
        $arguments += @("--state", $ReconciliationState)
    }
    if (-not [string]::IsNullOrWhiteSpace($ReconciliationOperationId)) {
        $arguments += @("--operation-id", $ReconciliationOperationId)
    }

    & $PythonPath @arguments
    exit $LASTEXITCODE
}

function Invoke-PlayerWikiReconciliationApply {
    if ($ReconciliationKind -notin @("publication", "deletion")) {
        throw "ReconciliationKind must be publication or deletion for apply."
    }
    if ([string]::IsNullOrWhiteSpace($ReconciliationOperationId)) {
        throw "ReconciliationOperationId is required for apply."
    }
    if ([string]::IsNullOrWhiteSpace($ReconciliationApplyAction)) {
        throw "ReconciliationApplyAction is required for apply."
    }
    $arguments = @(
        (Join-Path $projectRoot "ops.py"),
        "player-wiki-reconciliation-apply",
        "--kind",
        $ReconciliationKind,
        "--operation-id",
        $ReconciliationOperationId,
        "--action",
        $ReconciliationApplyAction
    )
    if (-not [string]::IsNullOrWhiteSpace($BackupDir)) {
        $arguments += @("--output-dir", $BackupDir)
    }
    if ($ConfirmReconciliationApply) {
        $arguments += "--yes"
    }

    & $PythonPath @arguments
    exit $LASTEXITCODE
}

function Invoke-PhaseCloseoutAnchor {
    foreach ($required in @(
        @{ Name = "PhaseCloseoutSourceRoot"; Value = $PhaseCloseoutSourceRoot },
        @{ Name = "PhaseCloseoutCanonicalRoot"; Value = $PhaseCloseoutCanonicalRoot },
        @{ Name = "PhaseCloseoutLedgerRoot"; Value = $PhaseCloseoutLedgerRoot },
        @{ Name = "PhaseCloseoutOutput"; Value = $PhaseCloseoutOutput }
    )) {
        if ([string]::IsNullOrWhiteSpace([string]$required.Value)) {
            throw "$($required.Name) is required for $Action."
        }
    }

    $command = $Action.Replace("phase-closeout-anchor-", "")
    $arguments = @(
        "-B",
        (Join-Path $projectRoot "scripts\phase_closeout_anchor.py"),
        $command,
        "--source-root", $PhaseCloseoutSourceRoot,
        "--canonical-root", $PhaseCloseoutCanonicalRoot,
        "--ledger-root", $PhaseCloseoutLedgerRoot
    )
    if ($command -eq "render") {
        foreach ($required in @(
            @{ Name = "PhaseCloseoutSourceRef"; Value = $PhaseCloseoutSourceRef },
            @{ Name = "PhaseCloseoutCanonicalRef"; Value = $PhaseCloseoutCanonicalRef },
            @{ Name = "PhaseCloseoutLedgerRef"; Value = $PhaseCloseoutLedgerRef },
            @{ Name = "PhaseCloseoutSourcePath"; Value = $PhaseCloseoutSourcePath },
            @{ Name = "PhaseCloseoutCanonicalPath"; Value = $PhaseCloseoutCanonicalPath },
            @{ Name = "PhaseCloseoutLedgerPath"; Value = $PhaseCloseoutLedgerPath },
            @{ Name = "PhaseCloseoutFrozenIdentity"; Value = $PhaseCloseoutFrozenIdentity },
            @{ Name = "PhaseCloseoutClassificationReceipt"; Value = $PhaseCloseoutClassificationReceipt },
            @{ Name = "PhaseCloseoutPhase"; Value = $PhaseCloseoutPhase },
            @{ Name = "PhaseCloseoutFinalizedUtc"; Value = $PhaseCloseoutFinalizedUtc }
        )) {
            if ([string]::IsNullOrWhiteSpace([string]$required.Value)) {
                throw "$($required.Name) is required for $Action."
            }
        }
        $arguments += @(
            "--source-ref", $PhaseCloseoutSourceRef,
            "--canonical-ref", $PhaseCloseoutCanonicalRef,
            "--ledger-ref", $PhaseCloseoutLedgerRef,
            "--source-path", $PhaseCloseoutSourcePath,
            "--canonical-path", $PhaseCloseoutCanonicalPath,
            "--ledger-path", $PhaseCloseoutLedgerPath,
            "--frozen-identity", $PhaseCloseoutFrozenIdentity,
            "--classification-receipt", $PhaseCloseoutClassificationReceipt,
            "--phase", $PhaseCloseoutPhase,
            "--finalized-utc", $PhaseCloseoutFinalizedUtc
        )
        if ($PhaseCloseoutReplaceExisting) {
            $arguments += "--replace-existing"
        }
    } elseif ($command -in @("write", "verify")) {
        if ([string]::IsNullOrWhiteSpace($PhaseCloseoutPlan)) {
            throw "PhaseCloseoutPlan is required for $Action."
        }
        $arguments += @("--plan", $PhaseCloseoutPlan)
    } else {
        throw "Unsupported phase closeout anchor action: $Action"
    }
    $arguments += @("--output", $PhaseCloseoutOutput)

    # PowerShell transports scalar paths and values only. Python owns receipt
    # parsing, hashes, row construction, and target writes. Child stdout is
    # host output so exactly one integer crosses the wrapper/lock boundary.
    & $PythonPath @arguments |
        ForEach-Object { [Console]::Out.WriteLine([string]$_) }
    $anchorExitCode = [int]$LASTEXITCODE
    return $anchorExitCode
}

function Invoke-SelectedLocalAction {
    switch ($Action) {
        "install" { Install-Dependencies }
        "bootstrap" { Install-Dependencies; Initialize-Database; Ensure-AdminUser }
        "run" { Run-App }
        "environment-check" { Assert-CanonicalEnvironment }
        "phase-closeout-anchor-render" { exit [int](Invoke-PhaseCloseoutAnchor) }
        "phase-closeout-anchor-write" { exit [int](Invoke-WithCompleteValidationLock -ProjectRoot $projectRoot -ActionName $Action -ScriptBlock { Invoke-PhaseCloseoutAnchor }) }
        "phase-closeout-anchor-verify" { exit [int](Invoke-PhaseCloseoutAnchor) }
        "runtime-check" { Test-RuntimeContainer }
        "backup" { Backup-LocalState }
        "restore" { Restore-LocalState }
        "restore-status" { Get-RestoreStatus }
        "restore-resume" { Resume-RestoreTransaction }
        "restore-rollback" { Rollback-RestoreTransaction }
        "restore-rehearsal" { Test-RestoreRehearsal }
        "artifact-inventory" { Invoke-ArtifactReport -Command "artifact-inventory" }
        "artifact-retention-assess" { Invoke-ArtifactReport -Command "artifact-retention-assess" }
        "player-wiki-reconciliation-dry-run" { Invoke-PlayerWikiReconciliationDryRun }
        "player-wiki-reconciliation-apply" { Invoke-PlayerWikiReconciliationApply }
        "prepare-fly-campaigns" { Prepare-FlyCampaigns }
        "sync-fly" { Sync-FromFly }
        "deploy-fly" { Deploy-Fly }
        default { throw "Unknown action: $Action" }
    }
}

function Assert-CanonicalEnvironment {
    Invoke-Python -Arguments @(
        (Join-Path $projectRoot "scripts\verify_environment.py"),
        "--project-root", $projectRoot
    )
}

if ($Action -ne "runtime-check") {
    Ensure-Python
}
if ($Action -eq "deploy-fly") {
    $deployFailed = $false
    try {
        Set-LocalTempEnvironment -ScopeName $Action
        Invoke-SelectedLocalAction
    } catch {
        $deployFailed = $true
    }
    $cleanupFailed = $false
    try {
        Remove-DeployRunTempRoots
    } catch {
        $cleanupFailed = $true
    }
    if ($deployFailed -and $cleanupFailed) {
        [Console]::Error.WriteLine("Fly deploy/invocation failed, and deploy temporary directory cleanup failed.")
        exit 1
    }
    if ($deployFailed) {
        [Console]::Error.WriteLine("Fly deploy/invocation failed.")
        exit 1
    }
    if ($cleanupFailed) {
        [Console]::Error.WriteLine("Fly deploy completed, but deploy temporary directory cleanup failed.")
        exit 1
    }
} else {
    if ($Action -notin @("runtime-check", "environment-check", "phase-closeout-anchor-render", "phase-closeout-anchor-write", "phase-closeout-anchor-verify", "artifact-inventory", "artifact-retention-assess", "player-wiki-reconciliation-dry-run")) {
        Set-LocalTempEnvironment -ScopeName $Action
    }
    Invoke-SelectedLocalAction
}
