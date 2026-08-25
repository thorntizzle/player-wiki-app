param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [Parameter(Mandatory = $true)]
    [string]$PythonPath,
    [string]$DockerPath = "",
    [string]$GitPath = ""
)

$ErrorActionPreference = "Stop"

$windowsHostTests = @(
    "tests/test_agent_instruction_anchor_validation.py",
    "tests/test_file_publication.py",
    "tests/test_generate_publisher_manifest.py",
    "tests/test_measure_character_read_performance.py",
    "tests/test_operations.py",
    "tests/test_phase_closeout_anchor.py",
    "tests/test_program_continuation_policy.py",
    "tests/test_publisher_closeout.py",
    "tests/test_publisher_focused_validation.py",
    "tests/test_runtime_lease.py",
    "tests/test_short_root_validation.py",
    "tests/test_candidate_gate.py"
)

function Resolve-RequiredExecutable {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$ConfiguredPath,
        [Parameter(Mandatory = $true)]
        [string]$CommandName
    )

    if (-not [string]::IsNullOrWhiteSpace($ConfiguredPath)) {
        if (-not (Test-Path -LiteralPath $ConfiguredPath -PathType Leaf)) {
            throw "$CommandName executable not found at $ConfiguredPath"
        }
        return (Resolve-Path -LiteralPath $ConfiguredPath).Path
    }

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "$CommandName executable is required for candidate-gate."
    }
    return $command.Source
}

function Invoke-RecordedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [string]$Executable,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host "candidate-gate stage: $Label"
    & $Executable @Arguments |
        ForEach-Object { [Console]::Out.WriteLine([string]$_) }
    $exitCode = [int]$LASTEXITCODE
    if ($exitCode -ne 0) {
        [Console]::Error.WriteLine("candidate-gate stage failed ($exitCode): $Label")
    }
    return $exitCode
}

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Canonical Python executable not found at $PythonPath"
}

$failureCount = 0
try {
    $resolvedDocker = Resolve-RequiredExecutable -ConfiguredPath $DockerPath -CommandName "docker"
    $resolvedGit = Resolve-RequiredExecutable -ConfiguredPath $GitPath -CommandName "git"
    $dockerPlatform = (& $resolvedDocker info --format '{{.OSType}}/{{.Architecture}}').Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "candidate-gate could not query the Docker server."
    }
    if ($dockerPlatform -ne "linux/x86_64" -and $dockerPlatform -ne "linux/amd64") {
        throw "candidate-gate requires a Linux/amd64 Docker server; found '$dockerPlatform'."
    }

    $lockPath = Join-Path $ProjectRoot "requirements-dev.lock"
    $lockHash = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $cacheTag = "cpw-candidate-gate:$($lockHash.Substring(0, 16))"
    $contextStager = Join-Path $ProjectRoot "scripts\stage_candidate_build_context.py"
    $buildContext = Join-Path $ProjectRoot ".local\candidate-gate\build-context"
    $buildManifest = Join-Path $ProjectRoot ".local\candidate-gate\build-context-manifest.json"
    $stageArguments = @(
        $contextStager, "stage",
        "--project-root", $ProjectRoot,
        "--context-root", $buildContext,
        "--manifest", $buildManifest,
        "--git", $resolvedGit
    )
    if ((Invoke-RecordedCommand -Label "stage Git-authoritative build context" -Executable $PythonPath -Arguments $stageArguments) -ne 0) {
        throw "candidate-gate build context staging failed."
    }
    $dockerfile = Join-Path $buildContext "deploy\candidate-gate.Dockerfile"
    $dockerignore = "$dockerfile.dockerignore"
    $gitMetadataRoot = Join-Path $ProjectRoot ".local\candidate-gate\git-metadata"
    $gitMetadataJson = & $PythonPath $contextStager git-metadata `
        --project-root $ProjectRoot `
        --metadata-root $gitMetadataRoot `
        --git $resolvedGit
    if ($LASTEXITCODE -ne 0) {
        throw "candidate-gate Git metadata staging failed."
    }
    $gitMetadata = $gitMetadataJson | ConvertFrom-Json
    Write-Host "candidate-gate Git metadata: $gitMetadataJson"

    $buildArguments = @(
        "build",
        "--platform", "linux/amd64",
        "--file", $dockerfile,
        "--tag", $cacheTag,
        $buildContext
    )
    $buildExit = Invoke-RecordedCommand -Label "build cached validation image" -Executable $resolvedDocker -Arguments $buildArguments
    if ($buildExit -ne 0) {
        $failureCount += 1
    } else {
        $imageReceiptPath = Join-Path $ProjectRoot ".local\candidate-gate\image-receipt.json"
        $receiptArguments = @(
            $contextStager, "image-receipt",
            "--manifest", $buildManifest,
            "--dockerfile", $dockerfile,
            "--dockerignore", $dockerignore,
            "--lock", $lockPath,
            "--platform", "linux/amd64",
            "--output", $imageReceiptPath,
            "--docker", $resolvedDocker,
            "--image", $cacheTag
        )
        $imageReceiptJson = & $PythonPath @receiptArguments
        $imageReceiptExitCode = [int]$LASTEXITCODE
        if ($imageReceiptExitCode -ne 0) {
            throw "candidate-gate could not create the stable image receipt."
        }
        $imageReceiptResult = $imageReceiptJson | ConvertFrom-Json
        $imageReceipt = $imageReceiptResult.receipt
        $imageIdentity = @(
            $imageReceiptResult.image_identity.id,
            $imageReceiptResult.image_identity.os,
            $imageReceiptResult.image_identity.architecture
        )
        $imageIdentityText = $imageIdentity -join "|"
        if (
            $imageIdentity.Count -ne 3 -or
            $imageIdentity[0] -notmatch '^sha256:[0-9a-f]{64}$' -or
            $imageIdentity[1] -ne "linux" -or
            $imageIdentity[2] -ne "amd64"
        ) {
            throw "candidate-gate built image identity is invalid: '$imageIdentityText'."
        }
        Write-Host "candidate-gate image: id=$($imageIdentity[0]) os=$($imageIdentity[1]) arch=$($imageIdentity[2]) tag=$cacheTag"
        if ($imageReceipt.stable_sha256 -notmatch '^[0-9a-f]{64}$') {
            throw "candidate-gate stable image receipt is invalid."
        }
        Write-Host "candidate-gate receipt: stable_sha256=$($imageReceipt.stable_sha256) raw_image_id=$($imageReceipt.diagnostics.raw_image_id) created=$($imageReceipt.diagnostics.created)"

        $containerBase = @(
            "run", "--rm",
            "--platform", "linux/amd64",
            "--network", "none",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--shm-size", "1gb",
            "--tmpfs", "/tmp:rw,exec,nosuid,nodev",
            "--tmpfs", "/workspace/.local:rw,exec,nosuid,nodev",
            "--mount", "type=bind,src=$($gitMetadata.metadata),dst=/workspace/.git,readonly",
            "--mount", "type=bind,src=$($gitMetadata.objects),dst=/candidate-git-objects,readonly",
            "--mount", "type=bind,src=$buildManifest,dst=/candidate-build-context-manifest.json,readonly",
            "--env", "GIT_CONFIG_COUNT=1",
            "--env", "GIT_CONFIG_KEY_0=safe.directory",
            "--env", "GIT_CONFIG_VALUE_0=/workspace",
            "--env", "TEMP=/tmp",
            "--env", "TMP=/tmp",
            "--env", "TMPDIR=/tmp",
            $cacheTag
        )

        $linuxStages = @(
            @{
                Label = "Linux exact image inventory"
                Command = @(
                    "python", "scripts/stage_candidate_build_context.py", "verify-image",
                    "--root", "/workspace",
                    "--manifest", "/candidate-build-context-manifest.json"
                )
            },
            @{
                Label = "Linux writable temporary roots"
                Command = @(
                    "python", "scripts/stage_candidate_build_context.py", "verify-temp",
                    "--path", "/tmp",
                    "--path", "/workspace/.local/candidate-gate/linux-pytest",
                    "--path", "/workspace/.local/candidate-gate/linux-cache"
                )
            },
            @{
                Label = "Linux canonical environment"
                Command = @("python", "scripts/verify_validation_environment.py", "--project-root", "/workspace")
            },
            @{
                Label = "Linux dependency consistency"
                Command = @("python", "-m", "pip", "check")
            },
            @{
                Label = "Linux real Chromium launch"
                Command = @("python", "scripts/smoke_playwright_chromium.py")
            },
            @{
                Label = "Linux pytest"
                Command = @(
                    "python", "scripts/stage_candidate_build_context.py", "run-pytest", "--",
                    "--require-browser",
                    "-m", "not windows_host",
                    "/workspace"
                )
            }
        )

        foreach ($stage in $linuxStages) {
            $arguments = $containerBase + @($stage.Command)
            if ((Invoke-RecordedCommand -Label $stage.Label -Executable $resolvedDocker -Arguments $arguments) -ne 0) {
                $failureCount += 1
            }
        }
    }
} catch {
    $failureCount += 1
    [Console]::Error.WriteLine("candidate-gate Linux lane could not run: $($_.Exception.Message)")
}

if ([Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    $failureCount += 1
    [Console]::Error.WriteLine(
        "candidate-gate Windows host lane requires Win32NT; found '$([Environment]::OSVersion.Platform)'."
    )
} else {
    $hostArguments = @(
        "-m", "pytest",
        "-m", "windows_host",
        "--basetemp", (Join-Path $ProjectRoot ".local\candidate-gate\windows-pytest"),
        "-o", "cache_dir=$(Join-Path $ProjectRoot '.local\candidate-gate\windows-cache')"
    ) + $windowsHostTests
    if ((Invoke-RecordedCommand -Label "Windows host pytest" -Executable $PythonPath -Arguments $hostArguments) -ne 0) {
        $failureCount += 1
    }
}

if ($failureCount -ne 0) {
    [Console]::Error.WriteLine("candidate-gate failed $failureCount stage(s); both platform lanes were attempted.")
    exit 1
}

Write-Host "candidate-gate passed all Linux and Windows host stages."
exit 0
