[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateSet("codex", "claude", "both")]
    [string]$Agent = "both",

    [ValidateSet("user", "project")]
    [string]$Scope = "user",

    [string]$ProjectRoot = (Get-Location).Path
)

$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceRoot = Join-Path $repositoryRoot "skills"

if (-not (Test-Path -LiteralPath $sourceRoot)) {
    throw "Skills directory not found: $sourceRoot"
}

$destinations = @()

if ($Scope -eq "user") {
    if (-not $env:USERPROFILE) {
        throw "USERPROFILE is not set."
    }

    if ($Agent -in @("codex", "both")) {
        $destinations += Join-Path $env:USERPROFILE ".agents\skills"
    }
    if ($Agent -in @("claude", "both")) {
        $destinations += Join-Path $env:USERPROFILE ".claude\skills"
    }
}
else {
    $resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
    if ($Agent -in @("codex", "both")) {
        $destinations += Join-Path $resolvedProjectRoot ".agents\skills"
    }
    if ($Agent -in @("claude", "both")) {
        $destinations += Join-Path $resolvedProjectRoot ".claude\skills"
    }
}

$skills = Get-ChildItem -LiteralPath $sourceRoot -Directory | Sort-Object Name

foreach ($destinationRoot in $destinations) {
    if ($PSCmdlet.ShouldProcess($destinationRoot, "Install $($skills.Count) skills")) {
        New-Item -ItemType Directory -Path $destinationRoot -Force | Out-Null

        foreach ($skill in $skills) {
            $destinationSkill = Join-Path $destinationRoot $skill.Name
            New-Item -ItemType Directory -Path $destinationSkill -Force | Out-Null
            Copy-Item -Path (Join-Path $skill.FullName "*") -Destination $destinationSkill -Recurse -Force
        }

        Write-Host "Installed $($skills.Count) skills to $destinationRoot"
    }
}
