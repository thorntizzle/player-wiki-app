[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$SkillRoot = (Join-Path $HOME ".codex\skills"),
    [int]$MaxLineLength = 500,
    [int]$SkillWarningLineLength = 2000
)

$ErrorActionPreference = "Stop"
$RepoRoot = if ($RepoRoot) { $RepoRoot } else { Split-Path -Parent $PSScriptRoot }
$failures = [System.Collections.Generic.List[string]]::new()

$required = @(
    "AGENTS.md",
    "docs/workflows/INDEX.md",
    "docs/workflows/agent-roles.md",
    "docs/workflows/authority-lanes.md",
    "docs/workflows/context-loading.md",
    "docs/workflows/worktrees.md",
    "docs/workflows/flask-rewrite-program.md",
    "docs/contracts/phase-closeout-evidence-anchors.md"
)

foreach ($relative in $required) {
    $path = Join-Path $RepoRoot $relative
    if (-not (Test-Path -LiteralPath $path)) {
        $failures.Add("Missing required workflow file: $relative")
    }
}

$scanFiles = @()
if (Test-Path -LiteralPath (Join-Path $RepoRoot "AGENTS.md")) {
    $scanFiles += Get-Item -LiteralPath (Join-Path $RepoRoot "AGENTS.md")
}
if (Test-Path -LiteralPath (Join-Path $RepoRoot "docs\workflows")) {
    $scanFiles += Get-ChildItem -LiteralPath (Join-Path $RepoRoot "docs\workflows") -File -Filter "*.md"
}
$evidenceAnchor = Join-Path $RepoRoot "docs\contracts\phase-closeout-evidence-anchors.md"
if (Test-Path -LiteralPath $evidenceAnchor) {
    $scanFiles += Get-Item -LiteralPath $evidenceAnchor
}

foreach ($file in $scanFiles) {
    $lineNumber = 0
    foreach ($line in Get-Content -LiteralPath $file.FullName) {
        $lineNumber++
        if ($line.Length -gt $MaxLineLength) {
            $failures.Add("Oversized line ($($line.Length) chars): $($file.FullName):$lineNumber")
        }
        if ($line -match "[A-Za-z]:\\Users\\[^\\]+") {
            $failures.Add("Personal absolute path: $($file.FullName):$lineNumber")
        }
    }

    $content = Get-Content -Raw -LiteralPath $file.FullName
    foreach ($match in [regex]::Matches($content, "\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")) {
        $target = $match.Groups[1].Value
        if ($target -notmatch "^(https?|mailto):" -and $target -notmatch "^[A-Za-z]:\\") {
            $resolved = [IO.Path]::GetFullPath((Join-Path $file.DirectoryName $target))
            if (-not (Test-Path -LiteralPath $resolved)) {
                $failures.Add("Broken relative link in $($file.FullName): $target")
            }
        }
    }
}

if (Test-Path -LiteralPath $SkillRoot) {
    $canonicalLive = Join-Path $SkillRoot "campaign-player-wiki-live"
    $obsoleteLive = Join-Path $SkillRoot "campaign-player-wiki-live-ops"
    if (-not (Test-Path -LiteralPath $canonicalLive)) {
        $failures.Add("Missing canonical skill: campaign-player-wiki-live")
    }
    if (Test-Path -LiteralPath $obsoleteLive) {
        $failures.Add("Obsolete duplicate skill directory exists: campaign-player-wiki-live-ops")
    }

    foreach ($directory in Get-ChildItem -LiteralPath $SkillRoot -Directory -Filter "campaign-player-wiki-*") {
        $skillFile = Join-Path $directory.FullName "SKILL.md"
        if (-not (Test-Path -LiteralPath $skillFile)) {
            $failures.Add("Missing SKILL.md: $($directory.FullName)")
            continue
        }
        $nameLine = Get-Content -LiteralPath $skillFile | Where-Object { $_ -match "^name:" } | Select-Object -First 1
        $declared = ($nameLine -replace "^name:\s*", "").Trim()
        if ($declared -ne $directory.Name) {
            $failures.Add("Skill name mismatch: directory '$($directory.Name)', manifest '$declared'")
        }

        foreach ($markdown in Get-ChildItem -LiteralPath $directory.FullName -Recurse -File -Filter "*.md") {
            $lineNumber = 0
            foreach ($line in Get-Content -LiteralPath $markdown.FullName) {
                $lineNumber++
                if ($line.Length -gt $SkillWarningLineLength) {
                    Write-Warning "Legacy oversized skill line ($($line.Length) chars): $($markdown.FullName):$lineNumber"
                }
                if ($markdown.FullName -eq $skillFile -and $line -match "[A-Za-z]:\\Users\\[^\\]+") {
                    $failures.Add("Personal absolute path in skill adapter: $($markdown.FullName):$lineNumber")
                }
            }

            $content = Get-Content -Raw -LiteralPath $markdown.FullName
            foreach ($match in [regex]::Matches($content, "\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")) {
                $target = $match.Groups[1].Value
                if ($target -notmatch "^(https?|mailto):" -and $target -notmatch "^[A-Za-z]:\\") {
                    $resolved = [IO.Path]::GetFullPath((Join-Path $markdown.DirectoryName $target))
                    if (-not (Test-Path -LiteralPath $resolved)) {
                        $failures.Add("Broken relative skill link in $($markdown.FullName): $target")
                    }
                }
            }
        }
    }
}

if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host "Agent instruction validation passed."
