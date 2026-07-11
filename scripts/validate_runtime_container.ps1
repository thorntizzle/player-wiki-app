[CmdletBinding()]
param(
    [string]$DockerPath = "",
    [ValidateRange(15, 300)]
    [int]$TimeoutSeconds = 90,
    [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$token = [Guid]::NewGuid().ToString("N").ToLowerInvariant()
$imageTag = "campaign-player-wiki-runtime-check:$token"
$containerName = "campaign-player-wiki-runtime-check-$token"
$containerCreated = $false

function Resolve-DockerExecutable {
    if (-not [string]::IsNullOrWhiteSpace($DockerPath)) {
        if (-not (Test-Path -LiteralPath $DockerPath -PathType Leaf)) {
            throw "Docker executable not found at $DockerPath"
        }
        return (Resolve-Path -LiteralPath $DockerPath).Path
    }

    $command = Get-Command "docker" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker\resources\bin\docker.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }

    throw "Docker CLI not found. Install Docker Desktop or pass -DockerPath."
}

function Invoke-Docker {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$AllowFailure
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $script:dockerExecutable @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        $detail = ($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
        throw "Docker command failed (exit $exitCode): docker $($Arguments -join ' ')`n$detail"
    }
    return $output
}

function Invoke-DockerWithInput {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$InputText,
        [switch]$AllowFailure
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @($InputText | & $script:dockerExecutable @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        $detail = ($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
        throw "Docker command failed (exit $exitCode): docker $($Arguments -join ' ')`n$detail"
    }
    return $output
}

function New-DisposableSecret {
    $bytes = New-Object byte[] 48
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    } finally {
        $generator.Dispose()
    }
    return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
}

function Write-ContainerLogs {
    $logs = Invoke-Docker -Arguments @("logs", $containerName) -AllowFailure
    if ($logs.Count -gt 0) {
        Write-Host "Container logs:"
        $logs | ForEach-Object { Write-Host $_ }
    }
}

$dockerExecutable = Resolve-DockerExecutable

# Check the server before build/run so an unavailable engine cannot create or
# mutate any local image or container state.
$previousErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $serverProbe = @(& $dockerExecutable info --format "{{.ServerVersion}}" 2>&1)
    $serverExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousErrorActionPreference
}
if ($serverExitCode -ne 0) {
    $detail = ($serverProbe | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    throw "Docker server unavailable. Start Docker Desktop and wait for the engine before retrying. No image was built.`n$detail"
}

try {
    Write-Host "Building disposable runtime image $imageTag..."
    $buildOutput = Invoke-Docker -Arguments @(
        "build",
        "--pull",
        "--file", (Join-Path $projectRoot "Dockerfile"),
        "--tag", $imageTag,
        $projectRoot
    )
    $buildOutput | ForEach-Object { Write-Host $_ }

    $secret = New-DisposableSecret
    Write-Host "Starting disposable runtime container on an ephemeral localhost port..."
    $runOutput = Invoke-Docker -Arguments @(
        "run",
        "--rm",
        "--detach",
        "--name", $containerName,
        "--publish", "127.0.0.1::8080",
        "--env", "PLAYER_WIKI_SECRET_KEY=$secret",
        "--env", "PLAYER_WIKI_DB_PATH=/tmp/player-wiki-runtime-check.sqlite3",
        "--env", "PLAYER_WIKI_CAMPAIGNS_DIR=/tmp/player-wiki-runtime-check-campaigns",
        $imageTag
    )
    $containerCreated = $true
    $containerId = ($runOutput | Select-Object -Last 1).ToString().Trim()
    if ([string]::IsNullOrWhiteSpace($containerId)) {
        throw "Docker did not return a container id."
    }

    $portOutput = Invoke-Docker -Arguments @("port", $containerName, "8080/tcp")
    $portMatch = [regex]::Match((($portOutput | Select-Object -First 1).ToString()), ':(?<port>\d+)\s*$')
    if (-not $portMatch.Success) {
        throw "Could not resolve the ephemeral localhost port from: $($portOutput -join ' ')"
    }
    $healthUrl = "http://127.0.0.1:$($portMatch.Groups['port'].Value)/healthz"

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $health = $null
    do {
        try {
            $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                $candidate = $response.Content | ConvertFrom-Json
                if ($candidate.status -eq "ok") {
                    $health = $candidate
                    break
                }
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    } while ([DateTime]::UtcNow -lt $deadline)

    if ($null -eq $health) {
        throw "The disposable container did not return status=ok from $healthUrl within $TimeoutSeconds seconds."
    }

    $metadataProbe = @'
import importlib.metadata as metadata
import os
import platform

from flask import Flask
from wsgi import app

assert platform.python_version() == "3.12.12", platform.python_version()
assert metadata.version("gunicorn") == "23.0.0", metadata.version("gunicorn")
assert os.environ["PLAYER_WIKI_ENV"] == "production"
assert isinstance(app, Flask)
routes = {rule.rule for rule in app.url_map.iter_rules()}
assert "/healthz" in routes
assert "/api/v1/app" in routes
print("python=3.12.12 gunicorn=23.0.0 env=production wsgi=ok")
'@
    $metadataOutput = Invoke-DockerWithInput -Arguments @(
        "exec", "-i", $containerName, "python", "-"
    ) -InputText $metadataProbe
    $metadataOutput | ForEach-Object { Write-Host $_ }

    $pipCheckOutput = Invoke-Docker -Arguments @(
        "exec", $containerName, "python", "-m", "pip", "check"
    )
    $pipCheckOutput | ForEach-Object { Write-Host $_ }

    $processProbe = @'
from pathlib import Path

def cmdline(pid: int) -> str:
    return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()

master = cmdline(1)
children = [int(value) for value in Path("/proc/1/task/1/children").read_text().split()]
assert "gunicorn" in master and "wsgi:app" in master, master
assert len(children) == 1, children
worker = cmdline(children[0])
assert "gunicorn" in worker and "wsgi:app" in worker, worker
print(f"gunicorn_master=1 gunicorn_workers={len(children)} worker_pid={children[0]}")
'@
    $processOutput = Invoke-DockerWithInput -Arguments @(
        "exec", "-i", $containerName, "python", "-"
    ) -InputText $processProbe
    $processOutput | ForEach-Object { Write-Host $_ }

    Write-ContainerLogs
    Write-Host "Runtime container validation passed: health, metadata, pip check, WSGI, and one Gunicorn worker."
} catch {
    if ($containerCreated) {
        Write-ContainerLogs
    }
    throw
} finally {
    if ($KeepArtifacts) {
        Write-Host "Keeping disposable artifacts by request: container=$containerName image=$imageTag"
    } else {
        Invoke-Docker -Arguments @("rm", "--force", $containerName) -AllowFailure | Out-Null
        Invoke-Docker -Arguments @("image", "rm", "--force", $imageTag) -AllowFailure | Out-Null
    }
}
