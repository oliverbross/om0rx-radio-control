param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$Toolchain = 'C:\JTSDK64-Tools\tools\msys64\mingw64'
)
$ErrorActionPreference = 'Stop'
$testDir = Join-Path $ProjectRoot 'data\build\mshv-auto-dx\tests'
$source = Join-Path $ProjectRoot 'data\build\mshv-auto-dx\src\MSHV_2762\src'
$qt = Join-Path $Toolchain 'include'
$exe = Join-Path $testDir 'autodx_runtime_config_test.exe'
$moc = Join-Path $testDir 'moc_bandmanager_runtime_config.cpp'
New-Item -ItemType Directory -Force -Path $testDir | Out-Null
$oldPath = $env:PATH
try {
    $env:PATH = (Join-Path $Toolchain 'bin') + ';' + $oldPath
    & (Join-Path $Toolchain 'bin\moc.exe') `
        (Join-Path $source 'HvAutoDxer\bandmanager.h') -o $moc
    if ($LASTEXITCODE -ne 0) { throw 'BandManager fixture moc generation failed' }
    & (Join-Path $Toolchain 'bin\g++.exe') -std=c++11 -fPIC "-I$source" "-I$qt" "-I$qt\QtCore" `
        (Join-Path $ProjectRoot 'tests\mshv\autodx_runtime_config_test.cpp') `
        (Join-Path $source 'HvAutoDxer\bandmanager.cpp') $moc `
        "-L$Toolchain\lib" -lQt5Core -o $exe
    if ($LASTEXITCODE -ne 0) { throw 'AutoDX runtime config fixture compilation failed' }
    & $exe
    if ($LASTEXITCODE -ne 0) { throw 'AutoDX runtime config fixture failed' }
} finally { $env:PATH = $oldPath }
