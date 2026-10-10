param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$Toolchain = 'C:\JTSDK64-Tools\tools\msys64\mingw64'
)
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $Toolchain 'bin\g++.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw "MSHV compiler not found: $compiler" }
$source = Join-Path $ProjectRoot 'tests\mshv\target_eligibility_test.cpp'
$scorerTest = Join-Path $ProjectRoot 'tests\mshv\target_scorer_integration_test.cpp'
$fakeDependencies = Join-Path $ProjectRoot 'tests\mshv\fake_target_scorer_dependencies.h'
$include = Join-Path $ProjectRoot 'data\build\mshv-auto-dx\src\MSHV_2762\src\HvAutoDxer'
$output = Join-Path ([IO.Path]::GetTempPath()) ('om0rx-target-priority-' + [Guid]::NewGuid().ToString('N') + '.exe')
$fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('om0rx-target-scorer-' + [Guid]::NewGuid().ToString('N'))
$originalPath = $env:PATH
try {
    $env:PATH = (Join-Path $Toolchain 'bin') + ';' + $originalPath
    & $compiler -std=c++11 "-I$include" $source -o $output
    if ($LASTEXITCODE -ne 0) { throw 'Target-priority native contract compilation failed' }
    & $output
    if ($LASTEXITCODE -ne 0) { throw 'Target-priority native contract failed' }
    Write-Host 'Native MSHV target-priority contract passed'

    New-Item -ItemType Directory -Path $fixtureRoot | Out-Null
    Copy-Item -LiteralPath (Join-Path $include 'targetscorer.h') -Destination $fixtureRoot
    Copy-Item -LiteralPath (Join-Path $include 'targeteligibility.h') -Destination $fixtureRoot
    Copy-Item -LiteralPath (Join-Path $include 'autodxselectionpolicy.h') -Destination $fixtureRoot
    Copy-Item -LiteralPath (Join-Path $include 'autodxmessageparser.h') -Destination $fixtureRoot
    Copy-Item -LiteralPath (Join-Path $include 'awardhuntingpolicy.h') -Destination $fixtureRoot
    Copy-Item -LiteralPath (Join-Path $include 'awardadifpolicy.h') -Destination $fixtureRoot
    Copy-Item -LiteralPath (Join-Path $include 'decodecache.h') -Destination $fixtureRoot
    Copy-Item -LiteralPath $scorerTest -Destination $fixtureRoot
    Copy-Item -LiteralPath $fakeDependencies -Destination $fixtureRoot

    $scorerSource = Get-Content -LiteralPath (Join-Path $include 'targetscorer.cpp') -Raw
    $scorerSource = $scorerSource.Replace('#include "dxcctracker.h"', '#include "fake_target_scorer_dependencies.h"')
    $scorerSource = $scorerSource.Replace('#include "../HvDecodeList/hvcty.h"', '')
    Set-Content -LiteralPath (Join-Path $fixtureRoot 'targetscorer.cpp') -Value $scorerSource -Encoding utf8

    $project = @'
QT += core
CONFIG += console c++11
CONFIG -= app_bundle
TEMPLATE = app
TARGET = target_scorer_integration_test
SOURCES += target_scorer_integration_test.cpp targetscorer.cpp
HEADERS += targetscorer.h targeteligibility.h autodxselectionpolicy.h autodxmessageparser.h awardhuntingpolicy.h awardadifpolicy.h fake_target_scorer_dependencies.h
'@
    Set-Content -LiteralPath (Join-Path $fixtureRoot 'target_scorer.pro') -Value $project -Encoding ascii
    Push-Location $fixtureRoot
    try {
        & (Join-Path $Toolchain 'bin\qmake.exe') '.\target_scorer.pro'
        if ($LASTEXITCODE -ne 0) { throw 'TargetScorer integration qmake failed' }
        & (Join-Path $Toolchain 'bin\mingw32-make.exe') '-j2'
        if ($LASTEXITCODE -ne 0) { throw 'TargetScorer integration compilation failed' }
        & (Join-Path $fixtureRoot 'release\target_scorer_integration_test.exe')
        if ($LASTEXITCODE -ne 0) { throw 'TargetScorer integration contract failed' }
    } finally {
        Pop-Location
    }
    Write-Host 'Native MSHV TargetScorer/tracker integration contract passed'
} finally {
    $env:PATH = $originalPath
    if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output -Force }
    if (Test-Path -LiteralPath $fixtureRoot) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
}
