param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$Toolchain = 'C:\JTSDK64-Tools\tools\msys64\mingw64',
    [string]$SourceDirectory
)
$ErrorActionPreference = 'Stop'
if (-not $SourceDirectory) {
    $SourceDirectory = Join-Path $ProjectRoot 'data\build\mshv-auto-dx\src\MSHV_2762\src\HvDxccTracker'
}
$output = Join-Path $ProjectRoot ('data\build\mshv-tracker-benchmark-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $output | Out-Null
$oldPath = $env:PATH
$oldPlugins = $env:QT_PLUGIN_PATH
try {
    $env:PATH = "$Toolchain\bin;" + $oldPath
    $env:QT_PLUGIN_PATH = "$Toolchain\share\qt5\plugins"
    & "$Toolchain\bin\moc.exe" (Join-Path $SourceDirectory 'hvdxcctracker.h') -o "$output\moc_tracker.cpp"
    if ($LASTEXITCODE -ne 0) { throw 'Tracker benchmark MOC failed' }
    & "$Toolchain\bin\g++.exe" -O2 -fno-keep-inline-dllexport -std=c++11 -fPIC `
        "-I$SourceDirectory" "-I$Toolchain\include" "-I$Toolchain\include\QtCore" "-I$Toolchain\include\QtSql" `
        (Join-Path $ProjectRoot 'tests\mshv\tracker_hotpath_benchmark.cpp') `
        (Join-Path $SourceDirectory 'hvdxcctracker.cpp') "$output\moc_tracker.cpp" `
        "-L$Toolchain\lib" -lQt5Sql -lQt5Core -o "$output\benchmark.exe"
    if ($LASTEXITCODE -ne 0) { throw 'Tracker benchmark compilation failed' }
    & "$output\benchmark.exe"
    if ($LASTEXITCODE -ne 0) { throw 'Tracker benchmark failed' }
} finally {
    $env:PATH = $oldPath
    $env:QT_PLUGIN_PATH = $oldPlugins
}
