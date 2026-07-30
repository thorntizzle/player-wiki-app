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

try {
    Import-Module `
        -Name (Join-Path $PSScriptRoot "short_root_validation.psm1") `
        -Force `
        -ErrorAction Stop
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
