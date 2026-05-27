param(
    [string]$MsysRoot = "C:\msys64",
    [string]$Toolchain = "ucrt64"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$vendorDir = Join-Path $repoRoot "vendor\ft8_lib"
$binDir = Join-Path $MsysRoot "$Toolchain\bin"
$usrBin = Join-Path $MsysRoot "usr\bin"

if (-not (Test-Path (Join-Path $binDir "gcc.exe"))) {
    throw "gcc.exe not found in $binDir"
}
if (-not (Test-Path (Join-Path $usrBin "make.exe"))) {
    throw "make.exe not found in $usrBin"
}

$env:PATH = "$binDir;$usrBin;$env:PATH"
Push-Location $vendorDir
try {
    & (Join-Path $usrBin "make.exe") clean
    & (Join-Path $usrBin "make.exe") decode_ft8 CC=gcc AR=ar CFLAGS='-O3 -I.'
}
finally {
    Pop-Location
}

Write-Host "Built $vendorDir\decode_ft8.exe"
