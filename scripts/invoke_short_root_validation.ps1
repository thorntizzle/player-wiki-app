[CmdletBinding()]
param(
    [string]$SourceRoot = "",
    [string]$RequestedAction = "",
    [string]$RequestedPythonPath = "",
    [string]$RequestedTestPath = "",
    [string]$RequestedShortRootBase = "",
    [switch]$RequestedRemoveOnSuccess
)

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

function Test-ValidationGitQuiet {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & git -C $Root @Arguments *> $null
    return $LASTEXITCODE -eq 0
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

function Test-ValidationPathWithin {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Parent
    )

    $resolvedPath = Resolve-ValidationPath $Path
    $resolvedParent = Resolve-ValidationPath $Parent
    $prefix = $resolvedParent + [System.IO.Path]::DirectorySeparatorChar
    return $resolvedPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
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

function Get-CleanValidationSnapshot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $resolvedRoot = Resolve-ValidationPath $Root
    $status = Invoke-ValidationGit -Root $resolvedRoot -Arguments @(
        "status",
        "--porcelain=v1",
        "--untracked-files=all"
    )
    if (-not [string]::IsNullOrWhiteSpace($status)) {
        throw "Physical short-root validation requires a clean source checkout, including no nonignored untracked files.`n$status"
    }

    $commit = Invoke-ValidationGit -Root $resolvedRoot -Arguments @("rev-parse", "HEAD")
    $tree = Invoke-ValidationGit -Root $resolvedRoot -Arguments @("rev-parse", "$commit^{tree}")
    $indexTree = Invoke-ValidationGit -Root $resolvedRoot -Arguments @("write-tree")
    if ($indexTree -ne $tree) {
        throw "Source index tree $indexTree does not match HEAD tree $tree."
    }
    if (-not (Test-ValidationGitQuiet -Root $resolvedRoot -Arguments @("diff", "--quiet", "--"))) {
        throw "Source worktree differs from its index."
    }
    if (-not (Test-ValidationGitQuiet -Root $resolvedRoot -Arguments @("diff", "--cached", "--quiet", $commit, "--"))) {
        throw "Source index differs from commit $commit."
    }

    return [pscustomobject]@{
        Root = $resolvedRoot
        Commit = $commit
        Tree = $tree
        CommonDir = Get-ValidationGitCommonDir $resolvedRoot
    }
}

function Compare-ByteSensitiveValidationFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    $trackedFiles = @(
        Invoke-ValidationGit -Root $Source -Arguments @("ls-files") |
            ForEach-Object { $_ -split "`n" } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    foreach ($relativePath in $trackedFiles) {
        $attribute = Invoke-ValidationGit -Root $Source -Arguments @(
            "check-attr",
            "text",
            "--",
            $relativePath
        )
        if (-not $attribute.EndsWith(": text: unset", [System.StringComparison]::Ordinal)) {
            continue
        }

        $sourcePath = Join-Path $Source $relativePath
        $destinationPath = Join-Path $Destination $relativePath
        if (-not (Test-Path -LiteralPath $destinationPath -PathType Leaf)) {
            throw "Byte-sensitive tracked file is missing from the short-root checkout: $relativePath"
        }
        $sourceBytes = [System.IO.File]::ReadAllBytes($sourcePath)
        $destinationBytes = [System.IO.File]::ReadAllBytes($destinationPath)
        if (
            $sourceBytes.Length -ne $destinationBytes.Length -or
            [System.Convert]::ToBase64String($sourceBytes) -ne [System.Convert]::ToBase64String($destinationBytes)
        ) {
            throw "Byte-sensitive tracked file differs in the short-root checkout: $relativePath"
        }
    }
}

function Assert-ShortRootValidationIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Snapshot,
        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    $resolvedDestination = Resolve-ValidationPath $Destination
    $attributes = (Get-Item -LiteralPath $resolvedDestination).Attributes
    if (($attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Short-root checkout must be a physical directory, not a reparse point: $resolvedDestination"
    }

    $branchOutput = & git -C $resolvedDestination symbolic-ref -q HEAD 2>$null
    if ($LASTEXITCODE -eq 0 -or -not [string]::IsNullOrWhiteSpace($branchOutput)) {
        throw "Short-root checkout must remain detached."
    }
    $commit = Invoke-ValidationGit -Root $resolvedDestination -Arguments @("rev-parse", "HEAD")
    $tree = Invoke-ValidationGit -Root $resolvedDestination -Arguments @("rev-parse", "HEAD^{tree}")
    $indexTree = Invoke-ValidationGit -Root $resolvedDestination -Arguments @("write-tree")
    $commonDir = Get-ValidationGitCommonDir $resolvedDestination
    $status = Invoke-ValidationGit -Root $resolvedDestination -Arguments @(
        "status",
        "--porcelain=v1",
        "--untracked-files=all"
    )

    if ($commit -ne $Snapshot.Commit) {
        throw "Short-root commit $commit does not match frozen commit $($Snapshot.Commit)."
    }
    if ($tree -ne $Snapshot.Tree -or $indexTree -ne $Snapshot.Tree) {
        throw "Short-root tree/index identity does not match frozen tree $($Snapshot.Tree)."
    }
    if ($commonDir -ne $Snapshot.CommonDir) {
        throw "Short-root checkout belongs to an unexpected Git common directory."
    }
    if (-not [string]::IsNullOrWhiteSpace($status)) {
        throw "Short-root checkout is not clean.`n$status"
    }
    if (-not (Test-ValidationGitQuiet -Root $resolvedDestination -Arguments @("diff", "--quiet", "--"))) {
        throw "Short-root worktree differs from its index."
    }
    if (-not (Test-ValidationGitQuiet -Root $resolvedDestination -Arguments @("diff", "--cached", "--quiet", $commit, "--"))) {
        throw "Short-root index differs from frozen commit $commit."
    }

    Compare-ByteSensitiveValidationFiles -Source $Snapshot.Root -Destination $resolvedDestination
}

function Resolve-ShortRootValidationBase {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [string]$RequestedBase = ""
    )

    $candidate = $RequestedBase
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        $candidate = $env:PLAYER_WIKI_SHORT_ROOT_BASE
    }
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        $driveRoot = [System.IO.Path]::GetPathRoot((Resolve-ValidationPath $Source))
        $candidate = Join-Path $driveRoot "cpwv"
    }
    if (-not [System.IO.Path]::IsPathRooted($candidate)) {
        throw "ShortRootBase must be an absolute path."
    }

    $resolvedBase = Resolve-ValidationPath $candidate
    if ($resolvedBase -eq (Resolve-ValidationPath $Source) -or (Test-ValidationPathWithin -Path $resolvedBase -Parent $Source)) {
        throw "ShortRootBase must be outside the source checkout."
    }
    New-Item -ItemType Directory -Path $resolvedBase -Force | Out-Null
    $attributes = (Get-Item -LiteralPath $resolvedBase).Attributes
    if (($attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "ShortRootBase must be a physical directory, not a reparse point."
    }
    return $resolvedBase
}

function Test-RegisteredValidationWorktree {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    $expected = Resolve-ValidationPath $Destination
    $lines = (Invoke-ValidationGit -Root $Source -Arguments @("worktree", "list", "--porcelain")) -split "`n"
    foreach ($line in $lines) {
        if (-not $line.StartsWith("worktree ", [System.StringComparison]::Ordinal)) {
            continue
        }
        if ((Resolve-ValidationPath $line.Substring(9)) -eq $expected) {
            return $true
        }
    }
    return $false
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

function Assert-GeneratedShortRootValidationPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [Parameter(Mandatory = $true)]
        [string]$Base,
        [Parameter(Mandatory = $true)]
        [string]$GeneratedLeaf
    )

    $resolvedDestination = Resolve-ValidationPath $Destination
    $resolvedBase = Resolve-ValidationPath $Base
    if ($GeneratedLeaf -notmatch '^cpw-[0-9a-f]{7}-[0-9]+-[0-9a-f]{8}$') {
        throw "Refusing cleanup for a path that was not generated by this invocation."
    }
    $expectedDestination = Resolve-ValidationPath (Join-Path $resolvedBase $GeneratedLeaf)
    if (
        $resolvedDestination -ne $expectedDestination -or
        -not (Test-ValidationPathWithin -Path $resolvedDestination -Parent $resolvedBase)
    ) {
        throw "Refusing cleanup outside the exact generated leaf beneath the selected short-root base."
    }
    return $resolvedDestination
}

function Assert-NoValidationReparsePoints {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $resolvedRoot = Resolve-ValidationPath $Root
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($resolvedRoot)
    while ($pending.Count -gt 0) {
        $current = $pending.Pop()
        $currentItem = Get-Item -LiteralPath $current -Force
        if (($currentItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing cleanup because a reparse point is present: $current"
        }
        if (-not $currentItem.PSIsContainer) {
            throw "Refusing cleanup because the expected directory is not a directory: $current"
        }
        foreach ($child in @(Get-ChildItem -LiteralPath $current -Force)) {
            if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Refusing cleanup because a reparse point is present: $($child.FullName)"
            }
            if ($child.PSIsContainer) {
                $pending.Push($child.FullName)
            }
        }
    }
}

function Remove-GeneratedShortRootValidationResidual {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Snapshot,
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [Parameter(Mandatory = $true)]
        [string]$Base,
        [Parameter(Mandatory = $true)]
        [string]$GeneratedLeaf
    )

    $resolvedDestination = Assert-GeneratedShortRootValidationPath `
        -Destination $Destination `
        -Base $Base `
        -GeneratedLeaf $GeneratedLeaf
    if (Test-RegisteredValidationWorktree -Source $Snapshot.Root -Destination $resolvedDestination) {
        throw "Refusing residual cleanup because the generated path is still a registered worktree."
    }
    Assert-NoValidationReparsePoints -Root $resolvedDestination

    $files = [System.Collections.Generic.List[string]]::new()
    $directories = [System.Collections.Generic.List[string]]::new()
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($resolvedDestination)
    while ($pending.Count -gt 0) {
        $current = $pending.Pop()
        $directories.Add($current)
        foreach ($child in @(Get-ChildItem -LiteralPath $current -Force)) {
            if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Refusing residual cleanup because a reparse point appeared: $($child.FullName)"
            }
            if ($child.PSIsContainer) {
                $pending.Push($child.FullName)
            } else {
                $files.Add($child.FullName)
            }
        }
    }

    foreach ($file in $files) {
        if (-not (Test-ValidationPathWithin -Path $file -Parent $resolvedDestination)) {
            throw "Refusing residual cleanup for a file outside the generated root: $file"
        }
        $attributes = [System.IO.File]::GetAttributes($file)
        if (($attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing residual cleanup because a reparse point appeared: $file"
        }
        if (($attributes -band [System.IO.FileAttributes]::ReadOnly) -ne 0) {
            [System.IO.File]::SetAttributes(
                $file,
                ($attributes -band (-bnot [System.IO.FileAttributes]::ReadOnly))
            )
        }
        [System.IO.File]::Delete($file)
        if ([System.IO.File]::Exists($file)) {
            throw "Failed to remove generated validation file; retaining residual: $file"
        }
    }

    for ($index = $directories.Count - 1; $index -ge 0; $index--) {
        $directory = $directories[$index]
        if (
            $directory -ne $resolvedDestination -and
            -not (Test-ValidationPathWithin -Path $directory -Parent $resolvedDestination)
        ) {
            throw "Refusing residual cleanup for a directory outside the generated root: $directory"
        }
        $attributes = [System.IO.File]::GetAttributes($directory)
        if (($attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing residual cleanup because a reparse point appeared: $directory"
        }
        [System.IO.Directory]::Delete($directory, $false)
        if ([System.IO.Directory]::Exists($directory)) {
            throw "Failed to remove generated validation directory; retaining residual: $directory"
        }
    }
}

function Remove-VerifiedShortRootValidationWorktree {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Snapshot,
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [Parameter(Mandatory = $true)]
        [string]$Base,
        [Parameter(Mandatory = $true)]
        [string]$GeneratedLeaf
    )

    $resolvedDestination = Assert-GeneratedShortRootValidationPath `
        -Destination $Destination `
        -Base $Base `
        -GeneratedLeaf $GeneratedLeaf
    if (-not (Test-RegisteredValidationWorktree -Source $Snapshot.Root -Destination $resolvedDestination)) {
        throw "Refusing cleanup because the generated path is not a registered worktree."
    }
    Assert-ShortRootValidationIdentity -Snapshot $Snapshot -Destination $resolvedDestination
    Assert-NoValidationReparsePoints -Root $resolvedDestination

    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $gitOutput = & git -C $Snapshot.Root worktree remove $resolvedDestination 2>&1
    $gitExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    $gitOutput | ForEach-Object { Write-Host $_ }
    $stillRegistered = Test-RegisteredValidationWorktree -Source $Snapshot.Root -Destination $resolvedDestination
    if ($stillRegistered) {
        throw "Git refused to deregister the verified generated short-root worktree; retaining it."
    }
    if (Test-Path -LiteralPath $resolvedDestination) {
        Write-Host "Git deregistered the worktree but left generated validation files; removing only the exact generated path without following reparses."
        try {
            Remove-GeneratedShortRootValidationResidual `
                -Snapshot $Snapshot `
                -Destination $resolvedDestination `
                -Base $Base `
                -GeneratedLeaf $GeneratedLeaf
        } catch {
            throw "Generated short-root residual retained for separate manifest authority at $resolvedDestination. $($_.Exception.Message)"
        }
    }
    if (Test-Path -LiteralPath $resolvedDestination) {
        throw "Generated short-root path still exists after Git cleanup: $resolvedDestination"
    }
    Write-Host "Removed verified successful short-root checkout: $resolvedDestination"
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

function Invoke-PhysicalShortRootValidation {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$ValidationAction,
        [string]$ValidationPythonPath = "",
        [string]$ValidationTestPath = "",
        [string]$ValidationShortRootBase = "",
        [switch]$RemoveOnSuccess
    )

    $snapshot = Get-CleanValidationSnapshot $Source
    $base = Resolve-ShortRootValidationBase -Source $snapshot.Root -RequestedBase $ValidationShortRootBase
    $generatedLeaf = "cpw-$($snapshot.Commit.Substring(0, 7))-$PID-$([Guid]::NewGuid().ToString('N').Substring(0, 8))"
    $destination = Join-Path $base $generatedLeaf
    if (Test-Path -LiteralPath $destination) {
        throw "Generated short-root path already exists: $destination"
    }

    Write-Host "Frozen source commit: $($snapshot.Commit)"
    Write-Host "Frozen source tree: $($snapshot.Tree)"
    Write-Host "Git common directory: $($snapshot.CommonDir)"
    Write-Host "Creating detached physical short-root checkout: $destination"
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $gitOutput = & git -C $snapshot.Root worktree add --detach $destination $snapshot.Commit 2>&1
    $gitExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    $gitOutput | ForEach-Object { Write-Host $_ }
    if ($gitExitCode -ne 0) {
        throw "Git failed to create the detached short-root worktree."
    }

    Assert-ShortRootValidationIdentity -Snapshot $snapshot -Destination $destination
    Write-Host "Short-root identity verified: commit=$($snapshot.Commit) tree=$($snapshot.Tree) index=$($snapshot.Tree)"

    $shellPath = (Get-Process -Id $PID).Path
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        (Join-Path $destination "local.ps1"),
        "-Action",
        $ValidationAction
    )
    if (-not [string]::IsNullOrWhiteSpace($ValidationPythonPath)) {
        $arguments += @("-PythonPath", $ValidationPythonPath)
    }
    if (-not [string]::IsNullOrWhiteSpace($ValidationTestPath)) {
        $arguments += @("-TestPath", $ValidationTestPath)
    }

    $previousActive = $env:PLAYER_WIKI_SHORT_ROOT_ACTIVE
    try {
        $env:PLAYER_WIKI_SHORT_ROOT_ACTIVE = "1"
        Write-Host "Running short-root validation action '$ValidationAction' from $destination"
        $previousErrorPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $childOutput = & $shellPath @arguments 2>&1
        $exitCode = $LASTEXITCODE
        $ErrorActionPreference = $previousErrorPreference
        $childOutput | ForEach-Object { Write-Host $_ }
    } finally {
        $env:PLAYER_WIKI_SHORT_ROOT_ACTIVE = $previousActive
    }

    Write-Host "Short-root validation exit code: $exitCode"
    if ($exitCode -eq 0 -and $RemoveOnSuccess) {
        Remove-VerifiedShortRootValidationWorktree `
            -Snapshot $snapshot `
            -Destination $destination `
            -Base $base `
            -GeneratedLeaf $generatedLeaf
    } else {
        Write-Host "Short-root checkout retained: $destination"
    }
    return [int]$exitCode
}

if ($MyInvocation.InvocationName -ne ".") {
    try {
        if ([string]::IsNullOrWhiteSpace($SourceRoot) -or [string]::IsNullOrWhiteSpace($RequestedAction)) {
            throw "SourceRoot and RequestedAction are required."
        }
        $result = Invoke-PhysicalShortRootValidation `
            -Source $SourceRoot `
            -ValidationAction $RequestedAction `
            -ValidationPythonPath $RequestedPythonPath `
            -ValidationTestPath $RequestedTestPath `
            -ValidationShortRootBase $RequestedShortRootBase `
            -RemoveOnSuccess:$RequestedRemoveOnSuccess
        exit [int]$result
    } catch {
        Write-Error $_
        exit 1
    }
}
