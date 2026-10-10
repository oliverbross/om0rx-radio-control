param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$Toolchain = 'C:\JTSDK64-Tools\tools\msys64\mingw64'
)
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $Toolchain 'bin\g++.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw "MSHV compiler not found: $compiler" }
$source = Join-Path $ProjectRoot 'tests\mshv\award_adif_integration_test.cpp'
$include = Join-Path $ProjectRoot 'data\build\mshv-auto-dx\src\MSHV_2762\src\HvAutoDxer'
$qt = Join-Path $Toolchain 'include'
$output = Join-Path ([IO.Path]::GetTempPath()) ('om0rx-award-adif-' + [Guid]::NewGuid().ToString('N') + '.exe')
$originalPath = $env:PATH
try {
    $env:PATH = (Join-Path $Toolchain 'bin') + ';' + $originalPath
    & $compiler -std=c++11 '-fPIC' "-I$include" "-I$qt" "-I$qt\QtCore" $source `
        "-L$Toolchain\lib" '-lQt5Core' '-o' $output
    if ($LASTEXITCODE -ne 0) { throw 'Award ADIF native fixture compilation failed' }
    & $output
    if ($LASTEXITCODE -ne 0) { throw 'Award ADIF native fixture failed' }
    Write-Host 'Award selection -> structured active refs -> persistent columns -> ADIF fields passed'
} finally {
    $env:PATH = $originalPath
    if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output -Force }
}
