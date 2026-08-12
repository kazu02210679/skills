[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateSet("codex", "claude", "both")]
    [string]$Agent = "both",

    [ValidateSet("user", "project")]
    [string]$Scope = "user",

    [string]$ProjectRoot = (Get-Location).Path,

    [Alias("Skill")]
    [string[]]$RequestedSkill = @(),

    [switch]$All,

    [switch]$List,

    [Alias("Replace")]
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Test-PathEntry {
    param([Parameter(Mandatory)][string]$LiteralPath)
    return Test-Path -LiteralPath $LiteralPath
}

function Assert-TreesEqual {
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][string]$Staged
    )

    $sourceFiles = @(
        Get-ChildItem -LiteralPath $Source -Recurse -Force -File |
            Where-Object {
                $_.Extension -notin @(".pyc", ".pyo") -and
                $_.FullName -notmatch '[\\/]__pycache__[\\/]'
            } |
            Sort-Object { $_.FullName.Substring($Source.Length) }
    )
    $stagedFiles = @(
        Get-ChildItem -LiteralPath $Staged -Recurse -Force -File |
            Where-Object {
                $_.Extension -notin @(".pyc", ".pyo") -and
                $_.FullName -notmatch '[\\/]__pycache__[\\/]'
            } |
            Sort-Object { $_.FullName.Substring($Staged.Length) }
    )
    if ($sourceFiles.Count -ne $stagedFiles.Count) {
        throw "Staged copy verification failed for $Source (file count differs)."
    }

    for ($index = 0; $index -lt $sourceFiles.Count; $index++) {
        $sourceRelative = $sourceFiles[$index].FullName.Substring($Source.Length)
        $stagedRelative = $stagedFiles[$index].FullName.Substring($Staged.Length)
        if ($sourceRelative -ne $stagedRelative) {
            throw "Staged copy verification failed for $Source (paths differ)."
        }
        $sourceHash = (Get-FileHash -LiteralPath $sourceFiles[$index].FullName -Algorithm SHA256).Hash
        $stagedHash = (Get-FileHash -LiteralPath $stagedFiles[$index].FullName -Algorithm SHA256).Hash
        if ($sourceHash -ne $stagedHash) {
            throw "Staged copy verification failed for $($sourceFiles[$index].FullName)."
        }
    }
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceRoot = Join-Path $repositoryRoot "skills"
$noticesRoot = Join-Path $repositoryRoot "third_party"
$compatibilitySource = Join-Path $repositoryRoot "docs\host-compatibility.md"

if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
    throw "Skills directory not found: $sourceRoot"
}

$skills = @(Get-ChildItem -LiteralPath $sourceRoot -Directory | Sort-Object Name)
if ($skills.Count -eq 0) {
    throw "No Skill directories found in $sourceRoot"
}
foreach ($skill in $skills) {
    $skillFile = Join-Path $skill.FullName "SKILL.md"
    if (-not (Test-Path -LiteralPath $skillFile -PathType Leaf)) {
        throw "Invalid source Skill $($skill.Name): missing SKILL.md"
    }
}

$requestedNames = New-Object System.Collections.Generic.List[string]
$seenNames = @{}
foreach ($rawName in $RequestedSkill) {
    foreach ($name in $rawName.Split(",", [System.StringSplitOptions]::RemoveEmptyEntries)) {
        if (-not $seenNames.ContainsKey($name)) {
            $seenNames[$name] = $true
            $requestedNames.Add($name)
        }
    }
}
if ($All -and $requestedNames.Count -gt 0) {
    throw "-All and -Skill are mutually exclusive."
}
if ($List -and ($All -or $requestedNames.Count -gt 0)) {
    throw "-List cannot be combined with -All or -Skill."
}
if ($List) {
    $skills.Name | Write-Output
    return
}
if ($requestedNames.Count -gt 0) {
    $available = @{}
    foreach ($candidate in $skills) { $available[$candidate.Name] = $candidate }
    foreach ($name in $requestedNames) {
        if (-not $available.ContainsKey($name)) {
            throw "Unknown Skill: $name"
        }
    }
    $skills = @($requestedNames | ForEach-Object { $available[$_] })
}

foreach ($sourceName in @("handoff-gist")) {
    foreach ($filename in @("LICENSE", "source.json", "SHA256SUMS")) {
        $noticeSource = Join-Path $noticesRoot "$sourceName\$filename"
        if (-not (Test-Path -LiteralPath $noticeSource -PathType Leaf)) {
            throw "Required notice file is missing: $sourceName/$filename"
        }
    }
}
if (-not (Test-Path -LiteralPath $compatibilitySource -PathType Leaf)) {
    throw "Required compatibility notice is missing: $compatibilitySource"
}

$destinations = @()
if ($Scope -eq "user") {
    if (-not $env:USERPROFILE) {
        throw "USERPROFILE is not set."
    }
    $baseRoot = $env:USERPROFILE
}
else {
    if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
        throw "Project root does not exist: $ProjectRoot"
    }
    $baseRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
}

if ($Agent -in @("codex", "both")) {
    $destinations += Join-Path $baseRoot ".agents\skills"
}
if ($Agent -in @("claude", "both")) {
    $destinations += Join-Path $baseRoot ".claude\skills"
}

$targetNames = @($skills.Name) + @(".third-party-notices")
foreach ($destinationRoot in $destinations) {
    foreach ($targetName in $targetNames) {
        $target = Join-Path $destinationRoot $targetName
        if ($targetName -eq ".third-party-notices") {
            continue
        }
        if ((Test-PathEntry -LiteralPath $target) -and -not $Force) {
            throw "Installation conflict: $target already exists. Re-run with -Force to replace managed directories."
        }
    }
}

$transactions = New-Object System.Collections.Generic.List[object]
$completedDestinations = New-Object System.Collections.Generic.List[string]
try {
    foreach ($destinationRoot in $destinations) {
        $destinationParent = Split-Path -Parent $destinationRoot
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
        $transactionRoot = Join-Path $destinationParent (
            ".skills-install-" + [Guid]::NewGuid().ToString("N").Substring(0, 12)
        )
        $stage = Join-Path $transactionRoot "stage"
        $backup = Join-Path $transactionRoot "backup"
        New-Item -ItemType Directory -Path $stage -Force | Out-Null
        New-Item -ItemType Directory -Path $backup -Force | Out-Null
        $transaction = [PSCustomObject]@{
            Destination = $destinationRoot
            Root = $transactionRoot
            Stage = $stage
            Backup = $backup
            Touched = (New-Object System.Collections.Generic.List[object])
        }
        $transactions.Add($transaction)

        foreach ($skill in $skills) {
            $stagedSkill = Join-Path $stage $skill.Name
            New-Item -ItemType Directory -Path $stagedSkill -Force | Out-Null
            Get-ChildItem -LiteralPath $skill.FullName -Force |
                Where-Object {
                    $_.Name -ne "__pycache__" -and
                    $_.Extension -notin @(".pyc", ".pyo")
                } |
                Copy-Item -Destination $stagedSkill -Recurse -Force `
                    -Exclude "__pycache__", "*.pyc", "*.pyo"
            Assert-TreesEqual -Source $skill.FullName -Staged $stagedSkill
        }

        $noticeStage = Join-Path $stage ".third-party-notices"
        foreach ($sourceName in @("handoff-gist")) {
            $noticeDestination = Join-Path $noticeStage $sourceName
            New-Item -ItemType Directory -Path $noticeDestination -Force | Out-Null
            foreach ($filename in @("LICENSE", "source.json", "SHA256SUMS")) {
                $noticeSource = Join-Path $noticesRoot "$sourceName\$filename"
                Copy-Item -LiteralPath $noticeSource -Destination (
                    Join-Path $noticeDestination $filename
                ) -Force
            }
            Assert-TreesEqual -Source (
                Join-Path $noticesRoot $sourceName
            ) -Staged $noticeDestination
        }
        Copy-Item -LiteralPath $compatibilitySource -Destination (
            Join-Path $noticeStage "HOST-COMPATIBILITY.md"
        ) -Force
        $compatibilityHash = (Get-FileHash -LiteralPath $compatibilitySource -Algorithm SHA256).Hash
        $stagedCompatibilityHash = (Get-FileHash -LiteralPath (
            Join-Path $noticeStage "HOST-COMPATIBILITY.md"
        ) -Algorithm SHA256).Hash
        if ($compatibilityHash -ne $stagedCompatibilityHash) {
            throw "Staged compatibility notice verification failed."
        }
    }

    foreach ($transaction in $transactions) {
        $noticeTarget = Join-Path $transaction.Destination ".third-party-notices"
        $noticeStage = Join-Path $transaction.Stage ".third-party-notices"
        if ((Test-PathEntry -LiteralPath $noticeTarget) -and -not $Force) {
            try {
                Assert-TreesEqual -Source $noticeStage -Staged $noticeTarget
            }
            catch {
                throw "Installation conflict: $noticeTarget differs from the retained notices. Re-run with -Force to replace it."
            }
        }
    }

    $mutationCount = 0
    $backupAttemptCount = 0
    foreach ($transaction in $transactions) {
        if (-not $PSCmdlet.ShouldProcess(
            $transaction.Destination,
            "Install $($skills.Count) Skills and retained provenance notices"
        )) {
            continue
        }
        New-Item -ItemType Directory -Path $transaction.Destination -Force | Out-Null
        foreach ($targetName in $targetNames) {
            $target = Join-Path $transaction.Destination $targetName
            $stagedTarget = Join-Path $transaction.Stage $targetName
            $backupTarget = Join-Path $transaction.Backup $targetName
            $targetExists = Test-PathEntry -LiteralPath $target
            if ($targetName -eq ".third-party-notices" -and $targetExists -and -not $Force) {
                continue
            }
            $transaction.Touched.Add([PSCustomObject]@{
                Name = $targetName
                CreatedNew = (-not $targetExists)
            })
            if ($targetExists) {
                $backupAttemptCount++
                if (
                    $env:SKILLS_INSTALL_TEST_FAIL_BEFORE_BACKUP_AFTER -and
                    $backupAttemptCount -ge [int]$env:SKILLS_INSTALL_TEST_FAIL_BEFORE_BACKUP_AFTER
                ) {
                    throw "Injected installer failure before backup $backupAttemptCount."
                }
                Move-Item -LiteralPath $target -Destination $backupTarget
            }
            Move-Item -LiteralPath $stagedTarget -Destination $target
            $mutationCount++
            if (
                $env:SKILLS_INSTALL_TEST_FAIL_AFTER -and
                $mutationCount -ge [int]$env:SKILLS_INSTALL_TEST_FAIL_AFTER
            ) {
                throw "Injected installer failure after $mutationCount target(s)."
            }
        }
        $completedDestinations.Add($transaction.Destination)
    }
}
catch {
    for ($transactionIndex = $transactions.Count - 1; $transactionIndex -ge 0; $transactionIndex--) {
        $transaction = $transactions[$transactionIndex]
        for ($targetIndex = $transaction.Touched.Count - 1; $targetIndex -ge 0; $targetIndex--) {
            $targetState = $transaction.Touched[$targetIndex]
            $targetName = $targetState.Name
            $target = Join-Path $transaction.Destination $targetName
            $backupTarget = Join-Path $transaction.Backup $targetName
            if (Test-PathEntry -LiteralPath $backupTarget) {
                if (Test-PathEntry -LiteralPath $target) {
                    Remove-Item -LiteralPath $target -Recurse -Force
                }
                Move-Item -LiteralPath $backupTarget -Destination $target
            }
            elseif (
                $targetState.CreatedNew -and
                (Test-PathEntry -LiteralPath $target)
            ) {
                Remove-Item -LiteralPath $target -Recurse -Force
            }
        }
    }
    Write-Error "Installation failed; all touched targets were rolled back. $($_.Exception.Message)"
    throw
}
finally {
    foreach ($transaction in $transactions) {
        if (Test-PathEntry -LiteralPath $transaction.Root) {
            Remove-Item -LiteralPath $transaction.Root -Recurse -Force
        }
    }
}

foreach ($destinationRoot in $completedDestinations) {
    Write-Host "Installed $($skills.Count) skills and retained provenance notices to $destinationRoot"
}
