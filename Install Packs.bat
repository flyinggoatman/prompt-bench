@echo off
setlocal
set "PB_INSTALLER_PATH=%~f0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$raw=[IO.File]::ReadAllText($env:PB_INSTALLER_PATH);$marker='### POWERSHELL BELOW ###';$i=$raw.IndexOf($marker);if($i -lt 0){throw 'Installer payload missing.'};$code=$raw.Substring($i+$marker.Length);& ([ScriptBlock]::Create($code))"
set "PB_EXIT=%ERRORLEVEL%"
endlocal & exit /b %PB_EXIT%
### POWERSHELL BELOW ###
$ErrorActionPreference = 'Stop'

function Write-Info([string]$Message) { Write-Host "[Prompt Bench] $Message" }
function Write-Warn([string]$Message) { Write-Host "[Prompt Bench] WARNING: $Message" -ForegroundColor Yellow }
function Write-Good([string]$Message) { Write-Host "[Prompt Bench] $Message" -ForegroundColor Green }

function Get-ChildDirectoryCI {
    param([string]$Parent, [string]$Name)
    if (-not (Test-Path -LiteralPath $Parent -PathType Container)) { return $null }
    return Get-ChildItem -LiteralPath $Parent -Directory -Force | Where-Object { $_.Name -ieq $Name } | Select-Object -First 1
}

function Get-OrCreate-PacksRoot {
    param([string]$Root)
    $existing = Get-ChildDirectoryCI -Parent $Root -Name 'packs'
    if ($null -ne $existing) { return $existing.FullName }
    $path = Join-Path $Root 'packs'
    New-Item -ItemType Directory -Path $path -Force | Out-Null
    return $path
}

function Get-SafeExplicitDestination {
    param([object]$Json, [string]$PacksRoot)

    $candidate = $null
    foreach ($name in @('installPath','install_path','targetPath','target_path','destination','target')) {
        $prop = $Json.PSObject.Properties[$name]
        if ($null -ne $prop -and -not [string]::IsNullOrWhiteSpace([string]$prop.Value)) {
            $candidate = [string]$prop.Value
            break
        }
    }
    if ([string]::IsNullOrWhiteSpace($candidate)) { return $null }

    $candidate = $candidate.Trim().Replace('/', [IO.Path]::DirectorySeparatorChar).Replace('\', [IO.Path]::DirectorySeparatorChar)
    $candidate = $candidate.TrimStart([IO.Path]::DirectorySeparatorChar)
    if ($candidate -match '^(?i)packs([\\/]|$)') {
        $candidate = $candidate.Substring(5).TrimStart([IO.Path]::DirectorySeparatorChar)
    }
    if ([string]::IsNullOrWhiteSpace($candidate)) { return $PacksRoot }

    $packsFull = [IO.Path]::GetFullPath($PacksRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $full = [IO.Path]::GetFullPath((Join-Path $PacksRoot $candidate))
    $prefix = $packsFull + [IO.Path]::DirectorySeparatorChar
    if ($full -ne $packsFull -and -not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe install destination in JSON metadata: $candidate"
    }

    if ([IO.Path]::GetExtension($full) -ieq '.json') {
        return Split-Path -Parent $full
    }
    return $full
}

function Get-JsonDestination {
    param([object]$Json, [string]$PacksRoot)

    $explicit = Get-SafeExplicitDestination -Json $Json -PacksRoot $PacksRoot
    if ($null -ne $explicit) { return $explicit }

    $properties = @($Json.PSObject.Properties.Name)
    $pack = ''
    if ($properties -contains 'pack') { $pack = [string]$Json.pack }

    if ($pack -match '(?i)^DLC2\s*:') { return Join-Path $PacksRoot 'dlc2' }
    if ($pack -match '(?i)^DLC\s*:')  { return Join-Path $PacksRoot 'dlc' }

    if ($properties -contains 'masters' -or $properties -contains 'shared') { return Join-Path $PacksRoot 'masters' }
    if ($properties -contains 'people')  { return Join-Path $PacksRoot 'people' }

    $controlKeys = @('dials','variation','variations','fields','wording','settings','castFields','discipline','disciplines','controls')
    foreach ($key in $controlKeys) {
        if ($properties -contains $key) { return Join-Path $PacksRoot 'controls' }
    }
    if ($pack -match '(?i)^(Dials?|Variation|Fields?|Wording|Settings?|CastFields?|Discipline|Controls?)\b') {
        return Join-Path $PacksRoot 'controls'
    }

    if ($properties -contains 'categories') { return Join-Path $PacksRoot 'categories' }
    if ($pack -match '(?i)^Masters?\b') { return Join-Path $PacksRoot 'masters' }
    if ($pack -match '(?i)^(Cast|People)\b') { return Join-Path $PacksRoot 'people' }

    return $null
}

function Install-JsonFile {
    param([string]$Path, [string]$PacksRoot)

    try {
        $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
        $json = $raw | ConvertFrom-Json
        $destination = Get-JsonDestination -Json $json -PacksRoot $PacksRoot
        if ($null -eq $destination) {
            Write-Warn "Could not identify a Prompt Bench destination for '$([IO.Path]::GetFileName($Path))'. It was not moved."
            return $false
        }

        New-Item -ItemType Directory -Path $destination -Force | Out-Null
        $target = Join-Path $destination ([IO.Path]::GetFileName($Path))
        $sourceFull = [IO.Path]::GetFullPath($Path)
        $targetFull = [IO.Path]::GetFullPath($target)
        if ($sourceFull -eq $targetFull) {
            Write-Info "Already installed: $([IO.Path]::GetFileName($Path))"
            return $true
        }

        Move-Item -LiteralPath $Path -Destination $target -Force
        Write-Good "Installed $([IO.Path]::GetFileName($Path)) -> $($destination.Substring($ScriptRoot.Length).TrimStart([char[]]'\/'))"
        return $true
    }
    catch {
        Write-Warn "Could not install '$Path': $($_.Exception.Message)"
        return $false
    }
}

function Merge-Directory {
    param([string]$Source, [string]$Destination)

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    foreach ($item in @(Get-ChildItem -LiteralPath $Source -Force)) {
        $dest = Join-Path $Destination $item.Name
        if ($item.PSIsContainer) {
            Merge-Directory -Source $item.FullName -Destination $dest
            if (Test-Path -LiteralPath $item.FullName) {
                Remove-Item -LiteralPath $item.FullName -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        else {
            Move-Item -LiteralPath $item.FullName -Destination $dest -Force
        }
    }
}

function Assert-ZipSafe {
    param([string]$ZipPath)

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        foreach ($entry in $archive.Entries) {
            $name = $entry.FullName.Replace('/', '\')
            if ([IO.Path]::IsPathRooted($name)) { throw "ZIP contains an absolute path: $($entry.FullName)" }
            $parts = $name.Split([char]'\')
            if ($parts -contains '..') { throw "ZIP contains path traversal: $($entry.FullName)" }
        }
    }
    finally {
        $archive.Dispose()
    }
}

function Find-MatchingPackDirectories {
    param([string]$SearchRoot, [string]$PacksRoot)

    $known = @{}
    foreach ($dir in @(Get-ChildItem -LiteralPath $PacksRoot -Directory -Force -ErrorAction SilentlyContinue)) {
        $known[$dir.Name.ToLowerInvariant()] = $dir.FullName
    }

    $matches = @()
    foreach ($dir in @(Get-ChildItem -LiteralPath $SearchRoot -Directory -Recurse -Force -ErrorAction SilentlyContinue | Sort-Object { $_.FullName.Length })) {
        $key = $dir.Name.ToLowerInvariant()
        if ($known.ContainsKey($key)) {
            $matches += [PSCustomObject]@{ Source = $dir.FullName; Destination = $known[$key] }
        }
    }
    return $matches
}

function Install-ZipFile {
    param([string]$Path, [string]$PacksRoot, [string]$TempRoot)

    try {
        if (Test-Path -LiteralPath $TempRoot) { Remove-Item -LiteralPath $TempRoot -Recurse -Force }
        New-Item -ItemType Directory -Path $TempRoot -Force | Out-Null
        Assert-ZipSafe -ZipPath $Path
        Expand-Archive -LiteralPath $Path -DestinationPath $TempRoot -Force

        $topPacks = Get-ChildDirectoryCI -Parent $TempRoot -Name 'packs'
        if ($null -ne $topPacks) {
            Merge-Directory -Source $topPacks.FullName -Destination $PacksRoot
            Write-Good "Merged Packs from $([IO.Path]::GetFileName($Path))"
        }
        else {
            $usedSources = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
            foreach ($match in @(Find-MatchingPackDirectories -SearchRoot $TempRoot -PacksRoot $PacksRoot)) {
                if (-not (Test-Path -LiteralPath $match.Source -PathType Container)) { continue }

                $skip = $false
                foreach ($used in $usedSources) {
                    $prefix = $used.TrimEnd([char[]]'\') + '\'
                    if ($match.Source.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { $skip = $true; break }
                }
                if ($skip) { continue }

                Merge-Directory -Source $match.Source -Destination $match.Destination
                [void]$usedSources.Add($match.Source)
                Write-Good "Merged folder '$([IO.Path]::GetFileName($match.Source))' into packs."
            }

            foreach ($json in @(Get-ChildItem -LiteralPath $TempRoot -File -Filter '*.json' -Recurse -Force -ErrorAction SilentlyContinue)) {
                if (Test-Path -LiteralPath $json.FullName) {
                    [void](Install-JsonFile -Path $json.FullName -PacksRoot $PacksRoot)
                }
            }
        }

        $leftovers = @(Get-ChildItem -LiteralPath $TempRoot -File -Recurse -Force -ErrorAction SilentlyContinue)
        if ($leftovers.Count -eq 0) {
            Remove-Item -LiteralPath $Path -Force
            Write-Good "Finished $([IO.Path]::GetFileName($Path)); source ZIP removed after successful install."
            return $true
        }

        Write-Warn "$([IO.Path]::GetFileName($Path)) contained $($leftovers.Count) unrecognised file(s). The original ZIP was kept."
        return $false
    }
    catch {
        Write-Warn "Could not install ZIP '$Path': $($_.Exception.Message)"
        return $false
    }
    finally {
        if (Test-Path -LiteralPath $TempRoot) { Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue }
    }
}

$ScriptRoot = Split-Path -Parent $env:PB_INSTALLER_PATH
$PacksRoot = Get-OrCreate-PacksRoot -Root $ScriptRoot
$DropFolder = Join-Path $ScriptRoot 'Install Packs to Install'
$TempRoot = Join-Path $ScriptRoot 'Unpacked Content'
New-Item -ItemType Directory -Path $DropFolder -Force | Out-Null

$candidates = @()
foreach ($folder in @($ScriptRoot, $DropFolder)) {
    foreach ($file in @(Get-ChildItem -LiteralPath $folder -File -Force -ErrorAction SilentlyContinue)) {
        if ($file.Extension -ieq '.json' -or $file.Extension -ieq '.zip') {
            $candidates += $file
        }
    }
}
$candidates = @($candidates | Sort-Object FullName -Unique)

Write-Host ''
Write-Host 'Prompt Bench - Install Packs'
Write-Host '============================'
Write-Info "Prompt Bench root: $ScriptRoot"
Write-Info "Packs folder: $PacksRoot"
Write-Host ''

if ($candidates.Count -eq 0) {
    Write-Info "No .json or .zip packs were found beside this installer or in 'Install Packs to Install'."
    Write-Host ''
    Read-Host 'Press Enter to close' | Out-Null
    exit 0
}

for ($i = 0; $i -lt $candidates.Count; $i++) {
    $relative = $candidates[$i].FullName.Substring($ScriptRoot.Length).TrimStart([char[]]'\/')
    Write-Host ("[{0}] {1}" -f ($i + 1), $relative)
}
Write-Host '[A] Install all listed packs'
Write-Host '[Q] Quit'
Write-Host ''

$selected = @()
if ($env:PB_INSTALL_ALL -eq '1') {
    $selected = $candidates
}
else {
    $answer = (Read-Host 'Choose pack numbers separated by commas, or A for all').Trim()
    if ($answer -match '^(?i)q$') { exit 0 }
    if ($answer -match '^(?i)a$') {
        $selected = $candidates
    }
    else {
        $indexes = [System.Collections.Generic.HashSet[int]]::new()
        foreach ($piece in $answer.Split(',')) {
            $n = 0
            if ([int]::TryParse($piece.Trim(), [ref]$n) -and $n -ge 1 -and $n -le $candidates.Count) {
                [void]$indexes.Add($n - 1)
            }
        }
        foreach ($idx in $indexes) { $selected += $candidates[$idx] }
    }
}

if ($selected.Count -eq 0) {
    Write-Warn 'No valid pack selections were made.'
    if ($env:PB_INSTALL_ALL -ne '1') { Read-Host 'Press Enter to close' | Out-Null }
    exit 1
}

$ok = 0
$failed = 0
foreach ($item in $selected) {
    if (-not (Test-Path -LiteralPath $item.FullName -PathType Leaf)) { continue }
    if ($item.Extension -ieq '.json') {
        if (Install-JsonFile -Path $item.FullName -PacksRoot $PacksRoot) { $ok++ } else { $failed++ }
    }
    elseif ($item.Extension -ieq '.zip') {
        if (Install-ZipFile -Path $item.FullName -PacksRoot $PacksRoot -TempRoot $TempRoot) { $ok++ } else { $failed++ }
    }
}

Write-Host ''
Write-Host '============================'
Write-Info "Finished. Installed: $ok. Skipped/needs attention: $failed."
if ($env:PB_INSTALL_ALL -ne '1') { Read-Host 'Press Enter to close' | Out-Null }
if ($failed -gt 0) { exit 1 }
exit 0