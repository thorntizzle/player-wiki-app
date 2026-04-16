param(
    [ValidateSet("install", "bootstrap", "run", "test", "check", "backup", "restore", "prepare-fly-campaigns", "sync-fly", "deploy-fly")]
    [string]$Action = "run",
    [string]$PythonPath = (Join-Path (Split-Path $PSScriptRoot -Parent) ".venv\Scripts\python.exe"),
    [string]$DbPath = "",
    [string]$BackupArchive = "",
    [string]$BackupDir = "",
    [string]$BackupLabel = "",
    [string]$FlyApp = $(if ($env:PLAYER_WIKI_FLY_APP) { $env:PLAYER_WIKI_FLY_APP } else { "campaign-player-wiki-example" }),
    [string]$FlyMachineId = "",
    [string]$FlyctlPath = "",
    [string]$AdminEmail = "",
    [string]$AdminName = "Admin User",
    [string]$AdminPassword = "",
    [switch]$ForceRestore,
    [switch]$SkipPreRestoreBackup,
    [switch]$ForceSyncFromFly,
    [switch]$SkipPreSyncBackup
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$sampleFlyApp = "campaign-player-wiki-example"
$persistedFlyApp = [Environment]::GetEnvironmentVariable("PLAYER_WIKI_FLY_APP", "User")

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

    $tempRoot = Join-Path $projectRoot ".local\tmp\$ScopeName"
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

    $env:PLAYER_WIKI_TEMP_DIR = $tempRoot
    $env:TEMP = $tempRoot
    $env:TMP = $tempRoot
    $env:TMPDIR = $tempRoot
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
    Invoke-Python -Arguments @(
        "-m",
        "pytest",
        $projectRoot
    )
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
    if (-not [string]::IsNullOrWhiteSpace($BackupLabel)) {
        $arguments += @("--pre-restore-label", $BackupLabel)
    }
    if ($SkipPreRestoreBackup) {
        $arguments += "--skip-pre-restore-backup"
    }

    Invoke-Python -Arguments $arguments
}

function Prepare-FlyCampaigns {
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

Ensure-Python
Set-LocalTempEnvironment -ScopeName $Action

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
    "check" {
        Run-Checks
    }
    "backup" {
        Backup-LocalState
    }
    "restore" {
        Restore-LocalState
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
