param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$Toolchain = 'C:\JTSDK64-Tools\tools\msys64\mingw64'
)
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $Toolchain 'bin\g++.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw "MSHV compiler not found: $compiler" }
$source = Join-Path $ProjectRoot 'tests\mshv\autodx_status_ownership_test.cpp'
$native = Join-Path $ProjectRoot 'data\build\mshv-auto-dx\src\MSHV_2762\src'
$qt = Join-Path $Toolchain 'include'
$output = Join-Path ([IO.Path]::GetTempPath()) ('om0rx-autodx-status-' + [Guid]::NewGuid().ToString('N') + '.exe')
$originalPath = $env:PATH
try {
    $env:PATH = (Join-Path $Toolchain 'bin') + ';' + $originalPath
    & $compiler -std=c++11 -fPIC "-I$native" "-I$qt" "-I$qt\QtCore" $source `
        "-L$Toolchain\lib" -lQt5Core -o $output
    if ($LASTEXITCODE -ne 0) { throw 'AutoDX status-ownership native test compilation failed' }
    & $output
    if ($LASTEXITCODE -ne 0) { throw 'AutoDX status-ownership native test failed' }
    Write-Host 'Native AutoDX status ownership: durable provenance, restart clear, stale/malformed fail-closed, engaged/manual protections passed'
} finally {
    $env:PATH = $originalPath
    if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output -Force }
}
