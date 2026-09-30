$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Installer = Join-Path $RepoRoot 'Install Packs.bat'
$Fixture = Join-Path $PSScriptRoot 'fixtures\valid-variation-pack.json'
$Sandbox = Join-Path ([IO.Path]::GetTempPath()) ('prompt-bench-installer-' + [guid]::NewGuid().ToString('N'))

try {
    New-Item -ItemType Directory -Path $Sandbox -Force | Out-Null
    Copy-Item -LiteralPath $Installer -Destination (Join-Path $Sandbox 'Install Packs.bat')
    Copy-Item -LiteralPath $Fixture -Destination (Join-Path $Sandbox 'valid-variation-pack.json')

    $env:PB_INSTALL_ALL = '1'
    & (Join-Path $Sandbox 'Install Packs.bat')
    if ($LASTEXITCODE -ne 0) {
        throw "Installer exited with code $LASTEXITCODE."
    }

    $Installed = Join-Path $Sandbox 'packs\controls\valid-variation-pack.json'
    if (-not (Test-Path -LiteralPath $Installed -PathType Leaf)) {
        throw "Expected fixture at packs/controls/valid-variation-pack.json."
    }

    $Expected = (Get-Content -LiteralPath $Fixture -Raw -Encoding UTF8).Trim()
    $Actual = (Get-Content -LiteralPath $Installed -Raw -Encoding UTF8).Trim()
    if ($Actual -ne $Expected) {
        throw 'Installed JSON differs from the source fixture.'
    }

    if (Test-Path -LiteralPath (Join-Path $Sandbox 'valid-variation-pack.json')) {
        throw 'Source fixture was not moved after a successful install.'
    }

    Write-Host '[PASS] Valid variation pack installs unchanged into packs/controls.'
}
finally {
    Remove-Item Env:PB_INSTALL_ALL -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $Sandbox) {
        Remove-Item -LiteralPath $Sandbox -Recurse -Force -ErrorAction SilentlyContinue
    }
}
