$ErrorActionPreference = "Stop"

function Invoke-ValidationGit {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $output = & git -C $Root @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed in $Root`: git $($Arguments -join ' ')`n$($output -join [Environment]::NewLine)"
    }
    return ($output -join "`n").Trim()
}

function Resolve-ValidationPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return [System.IO.Path]::GetFullPath($Path).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
}

function Get-ValidationGitCommonDir {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $commonDir = Invoke-ValidationGit -Root $Root -Arguments @(
        "rev-parse",
        "--path-format=absolute",
        "--git-common-dir"
    )
    return Resolve-ValidationPath $commonDir
}

function Read-CompleteValidationLockToken {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LockPath
    )

    $readerStream = [System.IO.File]::Open(
        $LockPath,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite
    )
    try {
        $reader = [System.IO.StreamReader]::new($readerStream, [System.Text.Encoding]::UTF8, $true, 1024, $true)
        try {
            return $reader.ReadToEnd().Trim()
        } finally {
            $reader.Dispose()
        }
    } finally {
        $readerStream.Dispose()
    }
}

function Invoke-WithCompleteValidationLock {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string]$ActionName,
        [Parameter(Mandatory = $true)]
        [scriptblock]$ScriptBlock
    )

    $commonDir = Get-ValidationGitCommonDir $ProjectRoot
    $lockPath = Join-Path $commonDir "campaign-player-wiki-complete-validation.lock"
    $hasGuardPath = -not [string]::IsNullOrWhiteSpace($env:PLAYER_WIKI_COMPLETE_VALIDATION_LOCK_PATH)
    $hasGuardToken = -not [string]::IsNullOrWhiteSpace($env:PLAYER_WIKI_COMPLETE_VALIDATION_LOCK_TOKEN)
    if ($hasGuardPath -ne $hasGuardToken) {
        throw "Complete-validation recursion guard is incomplete."
    }
    if ($hasGuardPath -and $hasGuardToken) {
        $expectedLockPath = Resolve-ValidationPath $env:PLAYER_WIKI_COMPLETE_VALIDATION_LOCK_PATH
        if ($expectedLockPath -eq (Resolve-ValidationPath $lockPath)) {
            if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf)) {
                throw "Complete-validation recursion guard lock file is missing."
            }
            $heldToken = Read-CompleteValidationLockToken $lockPath
            if ($heldToken -ne $env:PLAYER_WIKI_COMPLETE_VALIDATION_LOCK_TOKEN) {
                throw "Complete-validation recursion guard token is invalid."
            }
            return & $ScriptBlock
        }
    }

    $token = [Guid]::NewGuid().ToString("N")
    $stream = $null
    $previousPath = $env:PLAYER_WIKI_COMPLETE_VALIDATION_LOCK_PATH
    $previousToken = $env:PLAYER_WIKI_COMPLETE_VALIDATION_LOCK_TOKEN
    try {
        try {
            $stream = [System.IO.File]::Open(
                $lockPath,
                [System.IO.FileMode]::OpenOrCreate,
                [System.IO.FileAccess]::ReadWrite,
                [System.IO.FileShare]::Read
            )
        } catch [System.IO.IOException] {
            throw "Another complete validation is already running for this repository: $lockPath"
        }
        $stream.SetLength(0)
        $stream.Position = 0
        $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false), 1024, $true)
        try {
            $writer.Write($token)
            $writer.Flush()
            $stream.Flush()
        } finally {
            $writer.Dispose()
        }
        $env:PLAYER_WIKI_COMPLETE_VALIDATION_LOCK_PATH = $lockPath
        $env:PLAYER_WIKI_COMPLETE_VALIDATION_LOCK_TOKEN = $token
        Write-Host "Acquired complete-validation lock for $ActionName`: $lockPath"
        return & $ScriptBlock
    } finally {
        $env:PLAYER_WIKI_COMPLETE_VALIDATION_LOCK_PATH = $previousPath
        $env:PLAYER_WIKI_COMPLETE_VALIDATION_LOCK_TOKEN = $previousToken
        if ($null -ne $stream) {
            $stream.Dispose()
        }
    }
}

Export-ModuleMember -Function "Invoke-WithCompleteValidationLock"
