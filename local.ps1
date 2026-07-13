param(
    [ValidateSet("install", "bootstrap", "run", "test", "test-focused", "test-restore", "test-browser", "test-serial", "contract", "check", "runtime-check", "backup", "restore", "restore-status", "restore-resume", "restore-rollback", "restore-rehearsal", "artifact-inventory", "artifact-retention-assess", "prepare-fly-campaigns", "sync-fly", "deploy-fly")]
    [string]$Action = "run",
    [string]$PythonPath = "",
    [string]$TestPath = "",
    [string]$DbPath = "",
    [string]$BackupArchive = "",
    [string]$BackupDir = "",
    [string]$BackupLabel = "",
    [string[]]$ArtifactDataRoot = @(),
    [string[]]$ArtifactArchiveRoot = @(),
    [string[]]$ArtifactScratchRoot = @(),
    [double]$ArtifactAsOfEpoch = [double]::NaN,
    [string]$FlyApp = $(if ($env:PLAYER_WIKI_FLY_APP) { $env:PLAYER_WIKI_FLY_APP } else { "campaign-player-wiki-example" }),
    [string]$FlyMachineId = "",
    [string]$FlyctlPath = "",
    [string]$AdminEmail = "",
    [string]$AdminName = "Admin User",
    [string]$AdminPassword = "",
    [switch]$ForceRestore,
    [switch]$ForceSyncFromFly,
    [switch]$SkipPreSyncBackup,
    [switch]$PhysicalShortRoot,
    [string]$ShortRootBase = "",
    [switch]$RemoveShortRootOnSuccess
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
. (Join-Path $projectRoot "scripts\invoke_short_root_validation.ps1")
$sampleFlyApp = "campaign-player-wiki-example"
$persistedFlyApp = [Environment]::GetEnvironmentVariable("PLAYER_WIKI_FLY_APP", "User")
$pytestBaseTemp = ""
$pytestCacheDir = ""

if ($FlyApp -eq $sampleFlyApp -and -not [string]::IsNullOrWhiteSpace($persistedFlyApp)) {
    $FlyApp = $persistedFlyApp
}

if (-not [string]::IsNullOrWhiteSpace($DbPath)) {
    $env:PLAYER_WIKI_DB_PATH = $DbPath
}

function Set-LocalTempEnvironment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScopeName
    )

    $randomSuffix = [Guid]::NewGuid().ToString("N").Substring(0, 8)
    $scopePrefix = (($ScopeName.Split("-") | ForEach-Object { $_.Substring(0, 1) }) -join "")
    $runName = "$scopePrefix-$PID-$randomSuffix"
    $tempRoot = Join-Path $projectRoot ".local\tmp\$runName"
    $script:pytestBaseTemp = Join-Path $projectRoot ".local\pt\$runName"
    $script:pytestCacheDir = Join-Path $projectRoot ".local\pc\$runName"
    New-Item -ItemType Directory -Path $tempRoot,$script:pytestBaseTemp,$script:pytestCacheDir -Force | Out-Null

    $env:PLAYER_WIKI_TEMP_DIR = $tempRoot
    $env:TEMP = $tempRoot
    $env:TMP = $tempRoot
    $env:TMPDIR = $tempRoot
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

function Invoke-Pytest {
    param(
        [string[]]$PytestArguments = @()
    )

    $arguments = @(
        "-m",
        "pytest",
        "--basetemp", $script:pytestBaseTemp,
        "-o", "cache_dir=$script:pytestCacheDir"
    ) + $PytestArguments
    Push-Location $projectRoot
    try {
        Invoke-Python -Arguments $arguments
    } finally {
        Pop-Location
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

function Run-Tests {
    Write-Host "Running test suite..."
    Invoke-Pytest -PytestArguments @($projectRoot)
}

function Run-FocusedTests {
    $selectedTests = @(
        $TestPath.Split(",", [System.StringSplitOptions]::RemoveEmptyEntries) |
            ForEach-Object { $_.Trim() } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    if ($selectedTests.Count -eq 0) {
        throw "TestPath requires at least one explicit test file or node selector for test-focused."
    }
    Write-Host "Running focused test selection..."
    Invoke-Pytest -PytestArguments $selectedTests
}

function Run-RestoreTests {
    Write-Host "Running maintained backup, restore, lease, and SQLite safety lane..."
    $restoreTestFiles = @(
        "tests/test_backup_archive.py",
        "tests/test_operations.py",
        "tests/test_restore_transaction.py",
        "tests/test_runtime_lease.py",
        "tests/test_sqlite_safety.py"
    )
    Invoke-Pytest -PytestArguments $restoreTestFiles
}

function Run-BrowserTests {
    Write-Host "Running maintained real-browser and static-asset lane..."
    $browserTestFiles = @(
        "tests/test_character_read_shell_browser.py",
        "tests/test_combat_dm_controls_browser.py",
        "tests/test_static_assets.py"
    )
    Invoke-Pytest -PytestArguments $browserTestFiles
}

function Run-SerialSensitiveTests {
    Write-Host "Running serial shared-resource-sensitive test lane..."
    $serialTestFiles = @(
        "tests/test_app_metadata.py",
        "tests/test_backup_archive.py",
        "tests/test_character_read_shell_browser.py",
        "tests/test_combat_dm_controls_browser.py",
        "tests/test_login_throttle.py",
        "tests/test_migrations.py",
        "tests/test_operations.py",
        "tests/test_restore_transaction.py",
        "tests/test_runtime_baseline.py",
        "tests/test_runtime_lease.py",
        "tests/test_runtime_security.py",
        "tests/test_sqlite_safety.py",
        "tests/test_static_assets.py"
    )
    Invoke-Pytest -PytestArguments $serialTestFiles
}

function Run-ContractTests {
    Write-Host "Running fast contract suite..."
    Invoke-Pytest -PytestArguments @("-m", "contract", "-q")
}

function Run-Checks {
    Write-Host "Compiling project..."
    Invoke-Python -Arguments @(
        "-m",
        "compileall",
        $projectRoot
    )
    Run-Tests
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

function Invoke-SelectedLocalAction {
    switch ($Action) {
        "install" {
            Install-Dependencies
        }
        "bootstrap" {
            Install-Dependencies
            Initialize-Database
            Ensure-AdminUser
        }
        "run" {
            Run-App
        }
        "test" {
            Run-Tests
        }
        "test-focused" {
            Run-FocusedTests
        }
        "test-restore" {
            Run-RestoreTests
        }
        "test-browser" {
            Run-BrowserTests
        }
        "test-serial" {
            Run-SerialSensitiveTests
        }
        "contract" {
            Run-ContractTests
        }
        "check" {
            Run-Checks
        }
        "runtime-check" {
            Test-RuntimeContainer
        }
        "backup" {
            Backup-LocalState
        }
        "restore" {
            Restore-LocalState
        }
        "restore-status" {
            Get-RestoreStatus
        }
        "restore-resume" {
            Resume-RestoreTransaction
        }
        "restore-rollback" {
            Rollback-RestoreTransaction
        }
        "restore-rehearsal" {
            Test-RestoreRehearsal
        }
        "artifact-inventory" {
            Invoke-ArtifactReport -Command "artifact-inventory"
        }
        "artifact-retention-assess" {
            Invoke-ArtifactReport -Command "artifact-retention-assess"
        }
        "prepare-fly-campaigns" {
            Prepare-FlyCampaigns
        }
        "sync-fly" {
            Sync-FromFly
        }
        "deploy-fly" {
            Deploy-Fly
        }
        default {
            throw "Unknown action: $Action"
        }
    }
}

$shortRootActions = @(
    "test-focused",
    "test-restore",
    "test-browser",
    "test-serial",
    "test",
    "check"
)
$completeActions = @("test", "check")
if ((-not $PhysicalShortRoot) -and (
    -not [string]::IsNullOrWhiteSpace($ShortRootBase) -or $RemoveShortRootOnSuccess
)) {
    throw "ShortRootBase and RemoveShortRootOnSuccess require PhysicalShortRoot."
}
if ($PhysicalShortRoot) {
    if ($env:PLAYER_WIKI_SHORT_ROOT_ACTIVE -eq "1") {
        throw "Physical short-root validation cannot recursively create another short-root checkout."
    }
    if ($Action -notin $shortRootActions) {
        throw "PhysicalShortRoot is supported only for: $($shortRootActions -join ', ')."
    }
    Ensure-Python
    $shortRootInvocation = {
        Invoke-PhysicalShortRootValidation `
            -Source $projectRoot `
            -ValidationAction $Action `
            -ValidationPythonPath $PythonPath `
            -ValidationTestPath $TestPath `
            -ValidationShortRootBase $ShortRootBase `
            -RemoveOnSuccess:$RemoveShortRootOnSuccess
    }
    if ($Action -in $completeActions) {
        $shortRootExit = Invoke-WithCompleteValidationLock `
            -ProjectRoot $projectRoot `
            -ActionName $Action `
            -ScriptBlock $shortRootInvocation
    } else {
        $shortRootExit = & $shortRootInvocation
    }
    exit [int]$shortRootExit
}

if ($Action -in @("artifact-inventory", "artifact-retention-assess")) {
    $PythonPath = Resolve-PythonExecutable
    if (-not (Test-Path $PythonPath)) {
        [Console]::Error.WriteLine("The configured Python executable is unavailable.")
        exit 2
    }
} elseif ($Action -ne "runtime-check") {
    Ensure-Python
}
if ($Action -notin @("runtime-check", "artifact-inventory", "artifact-retention-assess")) {
    Set-LocalTempEnvironment -ScopeName $Action
}
if ($Action -in $completeActions) {
    Invoke-WithCompleteValidationLock `
        -ProjectRoot $projectRoot `
        -ActionName $Action `
        -ScriptBlock { Invoke-SelectedLocalAction }
} else {
    Invoke-SelectedLocalAction
}


<#
.SYNOPSIS
Runs local Campaign Player Wiki development, validation, recovery, and deployment actions.

.DESCRIPTION
Resolves the configured or shared workspace Python from the current Git worktree and assigns each
invocation unique ignored temp paths. Test actions remain serial unless a future verified policy
explicitly enables parallel execution. Selected test actions can re-run a clean committed tree in a
hash-verified detached physical short-root worktree for decisive Windows validation.

.PARAMETER Action
Selects the local action. Use contract for the fast contract lane, test-focused with TestPath for
an explicit selection, test-restore for recovery coverage, test-browser for the maintained real-browser
lane, test-serial for shared-resource-sensitive coverage, or test for the full suite.

.PARAMETER TestPath
A comma-separated list of explicit pytest files or node selectors accepted only by test-focused.

.PARAMETER PhysicalShortRoot
Runs test-focused, test-restore, test-browser, test-serial, test, or check from a unique detached
physical short-root worktree. The source must be clean and committed.

.PARAMETER ShortRootBase
Optional absolute physical directory for generated short-root worktrees. Defaults to
PLAYER_WIKI_SHORT_ROOT_BASE or <drive>:\cpwv.

.PARAMETER RemoveShortRootOnSuccess
Removes only the generated detached worktree after a successful short-root run and stringent identity
checks. Failed runs and successful runs without this switch retain their evidence checkout.

.EXAMPLE
.\local.ps1 -Action contract

.EXAMPLE
.\local.ps1 -Action test-focused -TestPath "tests/test_api_systems.py,tests/test_route_contract_manifest.py::test_committed_manifest_is_generated_byte_for_byte"

.EXAMPLE
.\local.ps1 -Action test-serial

.EXAMPLE
.\local.ps1 -Action test-restore -PhysicalShortRoot -RemoveShortRootOnSuccess
#>
