$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$rcedit = Join-Path $PSScriptRoot 'rcedit-x64.exe'
$exe = Join-Path $root '.venv\Scripts\beeref.exe'
$icon = Join-Path $root 'beeref\assets\logo.ico'
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) 'beeref_stub.exe'

if (-not (Test-Path $rcedit)) {
    throw "rcedit not found: $rcedit (download it from github.com/electron/rcedit/releases)"
}
if (-not (Test-Path $exe)) {
    throw "launcher not found: $exe (has the package been pip-installed?)"
}
if (-not (Test-Path $icon)) {
    throw "icon not found: $icon"
}

function Get-PeOverlayStart([byte[]]$data) {
    $e_lfanew = [BitConverter]::ToInt32($data, 0x3C)
    $numSec = [BitConverter]::ToUInt16($data, $e_lfanew + 6)
    $optSize = [BitConverter]::ToUInt16($data, $e_lfanew + 20)
    $secTable = $e_lfanew + 24 + $optSize
    $overlay = 0
    for ($i = 0; $i -lt $numSec; $i++) {
        $end = [BitConverter]::ToUInt32($data, $secTable + $i * 40 + 20) +
               [BitConverter]::ToUInt32($data, $secTable + $i * 40 + 16)
        if ($end -gt $overlay) { $overlay = $end }
    }
    return $overlay
}

$data = [System.IO.File]::ReadAllBytes($exe)
$stubLen = Get-PeOverlayStart $data
if ($stubLen -ge $data.Length) {
    throw "No appended archive found in $exe"
}
if ($data[$stubLen] -ne 0x23 -or $data[$stubLen + 1] -ne 0x21) {
    throw "Unexpected launcher layout in $exe"
}

$stub = [byte[]]$data[0..($stubLen - 1)]
$tail = [byte[]]$data[$stubLen..($data.Length - 1)]

[System.IO.File]::WriteAllBytes($tmp, $stub)
try {
    & $rcedit $tmp --set-icon $icon
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    $patched = [System.IO.File]::ReadAllBytes($tmp)
}
finally {
    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
}

if ((Get-PeOverlayStart $patched) -ne $patched.Length) {
    throw 'rcedit left trailing bytes; the appended archive would not be found - icon not applied'
}

[System.IO.File]::WriteAllBytes($exe, $patched + $tail)
Write-Host "Icon applied to $exe"
