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
    $baseUrl = "http://127.0.0.1:$($portMatch.Groups['port'].Value)"
    $livenessUrl = "$baseUrl/livez"
    $readinessUrl = "$baseUrl/readyz"
    $healthUrl = "$baseUrl/healthz"

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $liveness = $null
    do {
        try {
            $response = Invoke-WebRequest -Uri $livenessUrl -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                $candidate = $response.Content | ConvertFrom-Json
                if (
                    $candidate.status -eq "ok" -and
                    @($candidate.PSObject.Properties).Count -eq 1
                ) {
                    $liveness = $candidate
                    break
                }
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    } while ([DateTime]::UtcNow -lt $deadline)

    if ($null -eq $liveness) {
        throw "The disposable container did not return the expected liveness response within $TimeoutSeconds seconds."
    }

    $readinessResponse = Invoke-WebRequest -Uri $readinessUrl -UseBasicParsing -TimeoutSec 5
    $readiness = $readinessResponse.Content | ConvertFrom-Json
    if ($readinessResponse.StatusCode -ne 200 -or $readiness.status -ne "ready") {
        throw "The disposable container did not report ready after its real entrypoint completed."
    }

    $healthResponse = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
    $health = $healthResponse.Content | ConvertFrom-Json
    if ($healthResponse.StatusCode -ne 200 -or $health.status -ne "ok") {
        throw "The legacy health compatibility probe failed."
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
assert "/livez" in routes
assert "/readyz" in routes
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

    $unreadyProbe = @'
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

campaigns = Path(os.environ["PLAYER_WIKI_CAMPAIGNS_DIR"])
unready_campaigns = campaigns.with_name(f"{campaigns.name}-unready")
campaigns.rename(unready_campaigns)

with urlopen("http://127.0.0.1:8080/livez", timeout=5) as response:
    assert response.status == 200, response.status
    assert json.load(response) == {"status": "ok"}

try:
    urlopen("http://127.0.0.1:8080/readyz", timeout=5)
except HTTPError as exc:
    assert exc.code == 503, exc.code
    payload = json.load(exc)
else:
    raise AssertionError("readiness unexpectedly passed with a missing campaigns directory")

assert payload["status"] == "not_ready", payload
assert payload["reason"] == "campaigns_missing", payload
assert not campaigns.exists(), "readiness recreated the missing campaigns directory"
assert unready_campaigns.is_dir(), "disposable campaigns fixture was not preserved"
print("unready_liveness=ok unready_readiness=503 reason=campaigns_missing self_heal=false")
'@
    $unreadyOutput = Invoke-DockerWithInput -Arguments @(
        "exec", "-i", $containerName, "python", "-"
    ) -InputText $unreadyProbe
    $unreadyOutput | ForEach-Object { Write-Host $_ }

    Write-ContainerLogs
    Write-Host "Runtime container validation passed: liveness, readiness, legacy health, unready failure, metadata, pip check, WSGI, and one Gunicorn worker."
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
