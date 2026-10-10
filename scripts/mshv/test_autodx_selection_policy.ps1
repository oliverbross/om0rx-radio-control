param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$Toolchain = 'C:\JTSDK64-Tools\tools\msys64\mingw64'
)
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $Toolchain 'bin\g++.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw "MSHV compiler not found: $compiler" }
$include = Join-Path $ProjectRoot 'data\build\mshv-auto-dx\src\MSHV_2762\src\HvAutoDxer'
$qt = Join-Path $Toolchain 'include'
$source = Join-Path $ProjectRoot 'tests\mshv\autodx_selection_policy_test.cpp'
$output = Join-Path ([IO.Path]::GetTempPath()) ('om0rx-autodx-selection-' + [Guid]::NewGuid().ToString('N') + '.exe')
$oldPath = $env:PATH
try {
    $env:PATH = (Join-Path $Toolchain 'bin') + ';' + $oldPath
    & $compiler -std=c++11 -fPIC "-I$include" "-I$qt" "-I$qt\QtCore" $source "-L$Toolchain\lib" -lQt5Core -o $output
    if ($LASTEXITCODE -ne 0) { throw 'AutoDX selection policy fixture compilation failed' }
    & $output
    if ($LASTEXITCODE -ne 0) { throw 'AutoDX selection policy fixture failed' }
    Write-Host 'Native AutoDX selection/filter/timing policy passed'
} finally {
    $env:PATH = $oldPath
    if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output -Force }
}
