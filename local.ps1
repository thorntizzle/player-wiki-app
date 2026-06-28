param(
    [ValidateSet("install", "bootstrap", "run", "test", "check", "ts-api-check", "ts-api-container-proof", "backup", "restore", "prepare-fly-campaigns", "sync-fly", "deploy-fly")]
    [string]$Action = "run",
    [string]$PythonPath = (Join-Path (Split-Path $PSScriptRoot -Parent) ".venv\Scripts\python.exe"),
    [string]$NodePath = "",
    [string]$NpmPath = "",
    [string]$NodeRoot = "",
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
    [switch]$SkipPreSyncBackup,
    [switch]$SkipTsApiInstall,
    [switch]$SkipRouteSnapshotCheck
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$sampleFlyApp = "campaign-player-wiki-example"
$persistedFlyApp = [Environment]::GetEnvironmentVariable("PLAYER_WIKI_FLY_APP", "User")
$script:ResolvedPythonPath = $null

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

function Resolve-ExistingPath {
    param(
        [string]$PathValue
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $null
    }
    if (-not (Test-Path $PathValue)) {
        return $null
    }

    return (Resolve-Path -LiteralPath $PathValue).Path
}

function Resolve-PythonExecutable {
    $candidates = New-Object System.Collections.Generic.List[string]

    if (-not [string]::IsNullOrWhiteSpace($PythonPath)) {
        $candidates.Add($PythonPath)
    }
    if (-not [string]::IsNullOrWhiteSpace($env:PLAYER_WIKI_PYTHON)) {
        $candidates.Add($env:PLAYER_WIKI_PYTHON)
    }
    if (-not [string]::IsNullOrWhiteSpace($env:CPW_PYTHON_BIN)) {
        $candidates.Add($env:CPW_PYTHON_BIN)
    }
    if (-not [string]::IsNullOrWhiteSpace($env:VIRTUAL_ENV)) {
        $candidates.Add((Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"))
    }

    $candidates.Add((Join-Path (Split-Path $projectRoot -Parent) ".venv\Scripts\python.exe"))
    $candidates.Add((Join-Path $HOME "Documents\my_scripts\.venv\Scripts\python.exe"))

    foreach ($candidate in $candidates) {
        $resolved = Resolve-ExistingPath -PathValue $candidate
        if ($resolved) {
            return $resolved
        }
    }

    throw "Python executable not found. Pass -PythonPath or set PLAYER_WIKI_PYTHON/CPW_PYTHON_BIN."
}

function Ensure-Python {
    if ([string]::IsNullOrWhiteSpace($script:ResolvedPythonPath)) {
        $script:ResolvedPythonPath = Resolve-PythonExecutable
    }
}

function Invoke-Python {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Ensure-Python
    & $script:ResolvedPythonPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $script:ResolvedPythonPath $($Arguments -join ' ')"
    }
}

function Resolve-NodeFromRoot {
    param(
        [string]$RootPath
    )

    if ([string]::IsNullOrWhiteSpace($RootPath)) {
        return $null
    }

    $nodeCandidates = @(
        (Join-Path $RootPath "node.exe"),
        (Join-Path $RootPath "bin\node.exe")
    )

    foreach ($candidate in $nodeCandidates) {
        $resolved = Resolve-ExistingPath -PathValue $candidate
        if ($resolved) {
            return $resolved
        }
    }

    return $null
}

function Resolve-NpmFromRoot {
    param(
        [string]$RootPath
    )

    if ([string]::IsNullOrWhiteSpace($RootPath)) {
        return $null
    }

    $npmCandidates = @(
        @{ Path = (Join-Path $RootPath "npm.cmd"); Mode = "cmd" },
        @{ Path = (Join-Path $RootPath "bin\npm.cmd"); Mode = "cmd" },
        @{ Path = (Join-Path $RootPath "node_modules\npm\bin\npm-cli.js"); Mode = "node-cli" },
        @{ Path = (Join-Path $RootPath "lib\node_modules\npm\bin\npm-cli.js"); Mode = "node-cli" }
    )

    foreach ($candidate in $npmCandidates) {
        $resolved = Resolve-ExistingPath -PathValue $candidate.Path
        if ($resolved) {
            return @{
                Path = $resolved
                Mode = $candidate.Mode
            }
        }
    }

    return $null
}

function Add-NodeRootCandidate {
    param(
        [System.Collections.Generic.List[string]]$Candidates,
        [string]$Candidate
    )

    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        return
    }
    if ($Candidates.Contains($Candidate)) {
        return
    }

    $Candidates.Add($Candidate)
}

function Resolve-NodeToolchain {
    $explicitNode = if (-not [string]::IsNullOrWhiteSpace($NodePath)) { $NodePath } else { $env:CPW_NODE_BIN }
    $explicitNpm = if (-not [string]::IsNullOrWhiteSpace($NpmPath)) { $NpmPath } else { $env:CPW_NPM_BIN }
    $explicitRoot = if (-not [string]::IsNullOrWhiteSpace($NodeRoot)) { $NodeRoot } else { $env:CPW_NODE_ROOT }

    $resolvedExplicitNode = Resolve-ExistingPath -PathValue $explicitNode
    $resolvedExplicitNpm = Resolve-ExistingPath -PathValue $explicitNpm
    if ($resolvedExplicitNode -and $resolvedExplicitNpm) {
        $npmMode = if ($resolvedExplicitNpm.EndsWith(".js", [StringComparison]::OrdinalIgnoreCase)) { "node-cli" } else { "cmd" }
        return @{
            NodePath = $resolvedExplicitNode
            NpmPath = $resolvedExplicitNpm
            NpmMode = $npmMode
        }
    }

    $rootCandidates = New-Object System.Collections.Generic.List[string]
    Add-NodeRootCandidate -Candidates $rootCandidates -Candidate $explicitRoot
    if ($resolvedExplicitNode) {
        Add-NodeRootCandidate -Candidates $rootCandidates -Candidate (Split-Path $resolvedExplicitNode -Parent)
    }
    if ($resolvedExplicitNpm) {
        Add-NodeRootCandidate -Candidates $rootCandidates -Candidate (Split-Path $resolvedExplicitNpm -Parent)
    }

    Add-NodeRootCandidate -Candidates $rootCandidates -Candidate (Join-Path $projectRoot ".local\node")
    Add-NodeRootCandidate -Candidates $rootCandidates -Candidate (Join-Path $projectRoot ".local\node-v22.12.0-win-x64")
    Add-NodeRootCandidate -Candidates $rootCandidates -Candidate (Join-Path $projectRoot ".task-temp\node-v22.12.0-win-x64")
    Add-NodeRootCandidate -Candidates $rootCandidates -Candidate (Join-Path $HOME ".cache\codex-runtimes\codex-primary-runtime\dependencies\node")

    $sharedTaskTemp = Join-Path $HOME "Documents\my_scripts\.task-temp"
    if (Test-Path $sharedTaskTemp) {
        $discoveredNodeRoots = Get-ChildItem -Path $sharedTaskTemp -Directory -Filter "node-v*-win-x64" -Recurse -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 10
        foreach ($nodeRootCandidate in $discoveredNodeRoots) {
            Add-NodeRootCandidate -Candidates $rootCandidates -Candidate $nodeRootCandidate.FullName
        }
    }

    foreach ($candidateRoot in $rootCandidates) {
        $node = Resolve-NodeFromRoot -RootPath $candidateRoot
        $npm = Resolve-NpmFromRoot -RootPath $candidateRoot
        if ($node -and $npm) {
            return @{
                NodePath = $node
                NpmPath = $npm.Path
                NpmMode = $npm.Mode
            }
        }
    }

    $pathNodeCommand = Get-Command "node" -ErrorAction SilentlyContinue
    $pathNpmCommand = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    if (-not $pathNpmCommand) {
        $pathNpmCommand = Get-Command "npm" -ErrorAction SilentlyContinue
    }
    if ($pathNodeCommand -and $pathNpmCommand) {
        return @{
            NodePath = $pathNodeCommand.Source
            NpmPath = $pathNpmCommand.Source
            NpmMode = "cmd"
        }
    }

    throw "Node/npm toolchain not found. Pass -NodeRoot, -NodePath/-NpmPath, or set CPW_NODE_ROOT/CPW_NODE_BIN/CPW_NPM_BIN."
}

function Invoke-Npm {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Toolchain,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $previousPath = $env:PATH
    $nodeDir = Split-Path $Toolchain.NodePath -Parent
    $env:PATH = "$nodeDir;$previousPath"
    try {
        if ($Toolchain.NpmMode -eq "node-cli") {
            & $Toolchain.NodePath $Toolchain.NpmPath @Arguments
        } else {
            & $Toolchain.NpmPath @Arguments
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed: npm $($Arguments -join ' ')"
        }
    } finally {
        $env:PATH = $previousPath
    }
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

function Run-TypeScriptApiChecks {
    $apiRoot = Join-Path $projectRoot "apps\api"
    $packageJson = Join-Path $apiRoot "package.json"
    if (-not (Test-Path $packageJson)) {
        throw "TypeScript API package not found at $packageJson"
    }

    $toolchain = Resolve-NodeToolchain
    Write-Host "Using Node: $($toolchain.NodePath)"
    Write-Host "Using npm: $($toolchain.NpmPath)"

    Ensure-Python
    $previousCpwPythonPath = $env:CPW_PYTHON_PATH
    $env:CPW_PYTHON_PATH = $script:ResolvedPythonPath

    try {
        if (-not $SkipTsApiInstall) {
            Write-Host "Installing TypeScript API dependencies with npm ci..."
            Invoke-Npm -Toolchain $toolchain -Arguments @("--prefix", $apiRoot, "ci")
        }

        if (-not $SkipRouteSnapshotCheck) {
            Write-Host "Checking Flask route snapshot..."
            Invoke-Python -Arguments @(
                (Join-Path $projectRoot "scripts\route_snapshots.py"),
                "--check"
            )
        }

        Write-Host "Running TypeScript API typecheck..."
        Invoke-Npm -Toolchain $toolchain -Arguments @("--prefix", $apiRoot, "run", "typecheck")

        Write-Host "Building TypeScript API..."
        Invoke-Npm -Toolchain $toolchain -Arguments @("--prefix", $apiRoot, "run", "build")

        Write-Host "Checking TypeScript API SQLite startup posture..."
        Invoke-Npm -Toolchain $toolchain -Arguments @("--prefix", $apiRoot, "run", "test:sqlite-startup-posture")

        Write-Host "Checking TypeScript API SQLite schema command..."
        Invoke-Npm -Toolchain $toolchain -Arguments @("--prefix", $apiRoot, "run", "test:sqlite-schema-check")

        Write-Host "Checking TypeScript API SQLite migration proof command..."
        Invoke-Npm -Toolchain $toolchain -Arguments @("--prefix", $apiRoot, "run", "test:sqlite-migrate-proof")

        Write-Host "Checking TypeScript API route parity..."
        Invoke-Npm -Toolchain $toolchain -Arguments @("--prefix", $apiRoot, "run", "test:route-parity")
    } finally {
        if ($null -eq $previousCpwPythonPath) {
            Remove-Item Env:\CPW_PYTHON_PATH -ErrorAction SilentlyContinue
        } else {
            $env:CPW_PYTHON_PATH = $previousCpwPythonPath
        }
    }
}

function Run-TypeScriptApiContainerProof {
    $apiRoot = Join-Path $projectRoot "apps\api"
    $packageJson = Join-Path $apiRoot "package.json"
    if (-not (Test-Path $packageJson)) {
        throw "TypeScript API package not found at $packageJson"
    }

    $toolchain = Resolve-NodeToolchain
    Write-Host "Using Node: $($toolchain.NodePath)"
    Write-Host "Using npm: $($toolchain.NpmPath)"

    Ensure-Python
    $previousCpwPythonPath = $env:CPW_PYTHON_PATH
    $env:CPW_PYTHON_PATH = $script:ResolvedPythonPath

    try {
        if (-not $SkipTsApiInstall) {
            Write-Host "Installing TypeScript API dependencies with npm ci..."
            Invoke-Npm -Toolchain $toolchain -Arguments @("--prefix", $apiRoot, "ci")
        }

        Write-Host "Running TypeScript API container/runtime proof..."
        Invoke-Npm -Toolchain $toolchain -Arguments @("--prefix", $apiRoot, "run", "test:container-runtime-proof")
    } finally {
        if ($null -eq $previousCpwPythonPath) {
            Remove-Item Env:\CPW_PYTHON_PATH -ErrorAction SilentlyContinue
        } else {
            $env:CPW_PYTHON_PATH = $previousCpwPythonPath
        }
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

if ($Action -ne "ts-api-check" -or -not $SkipRouteSnapshotCheck) {
    Ensure-Python
}
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
    "ts-api-check" {
        Run-TypeScriptApiChecks
    }
    "ts-api-container-proof" {
        Run-TypeScriptApiContainerProof
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
