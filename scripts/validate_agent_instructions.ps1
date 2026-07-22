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

function Get-MarkdownCellValue {
    param([string]$Cell)

    $value = $Cell.Trim()
    if ($value.Length -ge 2 -and $value.StartsWith("``") -and $value.EndsWith("``")) {
        return $value.Substring(1, $value.Length - 2)
    }
    return $value
}

if (Test-Path -LiteralPath $evidenceAnchor) {
    $anchorContent = Get-Content -Raw -LiteralPath $evidenceAnchor
    $pendingPatterns = @(
        "(?i)\b(?:pending|awaiting)\s+(?:independent\s+)?(?:verification|commit(?:ting)?|push(?:ing)?)\b",
        "(?i)\b(?:verification|commit|push)\s+(?:is|are)\s+pending\b",
        "(?i)\b(?:not\s+yet|to\s+be|will\s+be|remains?\s+to\s+be)\s+(?:verified|committed|pushed)\b"
    )
    foreach ($pattern in $pendingPatterns) {
        if ($anchorContent -match $pattern) {
            $failures.Add("Prospective pending-state wording in evidence-anchor ledger: '$($Matches[0])'")
        }
    }

    $anchorLines = @(Get-Content -LiteralPath $evidenceAnchor)
    $headerIndex = -1
    for ($index = 0; $index -lt $anchorLines.Count; $index++) {
        if ($anchorLines[$index] -match "^\s*\|\s*Phase\s*\|\s*Accepted commit\s*\|\s*Accepted tree\s*\|") {
            $headerIndex = $index
            break
        }
    }

    if ($headerIndex -lt 0) {
        $failures.Add("Missing evidence-anchor table header")
    }
    else {
        $rowCount = 0
        for ($index = $headerIndex + 1; $index -lt $anchorLines.Count; $index++) {
            $line = $anchorLines[$index]
            if ($line -notmatch "^\s*\|") {
                if ($rowCount -gt 0) { break }
                continue
            }
            if ($line -match "^\s*\|(?:\s*:?-+:?\s*\|)+\s*$") { continue }

            $rowCount++
            $cells = @($line.Trim().Trim("|").Split("|") | ForEach-Object { Get-MarkdownCellValue $_ })
            if ($cells.Count -ne 7) {
                $failures.Add("Malformed evidence-anchor row at line $($index + 1): expected 7 cells, found $($cells.Count)")
                continue
            }

            $commit = $cells[1]
            $tree = $cells[2]
            $record = $cells[3]
            $bytes = $cells[4]
            $sha256 = $cells[5]
            $finalized = $cells[6]

            if ([string]::IsNullOrWhiteSpace($cells[0])) {
                $failures.Add("Missing phase name in evidence-anchor row at line $($index + 1)")
            }

            if ($commit -notmatch "^[0-9a-f]{40}$") {
                $failures.Add("Malformed accepted commit in evidence-anchor row at line $($index + 1)")
            }
            if ($tree -notmatch "^[0-9a-f]{40}$") {
                $failures.Add("Malformed accepted tree in evidence-anchor row at line $($index + 1)")
            }

            $recordSegments = @($record.Split("/"))
            if (
                $record -notmatch "^\.local/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+$" -or
                $recordSegments -contains "." -or
                $recordSegments -contains ".."
            ) {
                $failures.Add("Malformed lifecycle record path in evidence-anchor row at line $($index + 1)")
            }

            [UInt64]$parsedBytes = 0
            if ($bytes -notmatch "^[1-9][0-9]*$" -or -not [UInt64]::TryParse($bytes, [ref]$parsedBytes)) {
                $failures.Add("Malformed positive byte count in evidence-anchor row at line $($index + 1)")
            }
            if ($sha256 -cnotmatch "^[0-9A-F]{64}$") {
                $failures.Add("Malformed uppercase SHA-256 in evidence-anchor row at line $($index + 1)")
            }

            [DateTimeOffset]$parsedTimestamp = [DateTimeOffset]::MinValue
            $timestampIsUtc = $finalized -match "^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,7})?Z$"
            $timestampParses = [DateTimeOffset]::TryParse(
                $finalized,
                [Globalization.CultureInfo]::InvariantCulture,
                [Globalization.DateTimeStyles]::AssumeUniversal,
                [ref]$parsedTimestamp
            )
            if (-not $timestampIsUtc -or -not $timestampParses -or $parsedTimestamp.Offset -ne [TimeSpan]::Zero) {
                $failures.Add("Malformed UTC finalization timestamp in evidence-anchor row at line $($index + 1)")
            }
        }
        if ($rowCount -eq 0) {
            $failures.Add("Evidence-anchor table has no data rows")
        }
    }
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
    $failures | ForEach-Object { Write-Output "ERROR: $_" }
    exit 1
}

Write-Host "Agent instruction validation passed."
