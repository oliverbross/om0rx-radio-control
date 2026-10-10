param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$Toolchain = 'C:\JTSDK64-Tools\tools\msys64\mingw64',
    [string]$Runtime,
    [switch]$SkipReleaseAttestation
)
$ErrorActionPreference = 'Stop'
$attestationArgs = @{ ProjectRoot=$ProjectRoot }
if ($Runtime) {
    $resolvedRuntime = [IO.Path]::GetFullPath($Runtime)
    if (-not (Test-Path -LiteralPath (Join-Path $resolvedRuntime 'om0rx-build.json'))) {
        throw "MSHV candidate runtime manifest missing: $resolvedRuntime"
    }
    $attestationArgs.Runtime = $resolvedRuntime
    # Bind every native fixture below to this exact packaged candidate before
    # compiling against its attested build-source tree.
    & (Join-Path $PSScriptRoot 'assert_release.ps1') @attestationArgs
    Write-Host "Native fixture candidate attested before test compilation: $resolvedRuntime"
}
& (Join-Path $PSScriptRoot 'test_autodx_runtime_config.ps1') -ProjectRoot $ProjectRoot -Toolchain $Toolchain
& (Join-Path $PSScriptRoot 'test_autodx_selection_policy.ps1') -ProjectRoot $ProjectRoot -Toolchain $Toolchain
& (Join-Path $PSScriptRoot 'test_target_priority.ps1') -ProjectRoot $ProjectRoot -Toolchain $Toolchain
& (Join-Path $PSScriptRoot 'test_award_adif.ps1') -ProjectRoot $ProjectRoot -Toolchain $Toolchain
& (Join-Path $PSScriptRoot 'test_autodx_status_ownership.ps1') -ProjectRoot $ProjectRoot -Toolchain $Toolchain
$testDir = Join-Path $ProjectRoot 'data\build\mshv-auto-dx\tests'
New-Item -ItemType Directory -Force -Path $testDir | Out-Null
$qt = Join-Path $Toolchain 'include'
$source = Join-Path $ProjectRoot 'data\build\mshv-auto-dx\src\MSHV_2762\src'
$watchdogExe = Join-Path $testDir 'tx_watchdog_edge_test.exe'
$originalPath = $env:PATH
$env:PATH = "$Toolchain\bin;" + $originalPath
& (Join-Path $Toolchain 'bin\g++.exe') -std=c++11 "-I$source" (Join-Path $ProjectRoot 'tests\mshv\tx_watchdog_edge_test.cpp') -o $watchdogExe
if ($LASTEXITCODE -ne 0) { throw 'TX watchdog edge test compilation failed' }
try { & $watchdogExe; if ($LASTEXITCODE -ne 0) { throw 'TX watchdog edge test failed' } }
finally { $env:PATH = $originalPath }
Write-Host 'TX watchdog edge: normal TX release cancels the armed edge; only continuous stuck TX trips'
$exe = Join-Path $testDir 'station_gate_test.exe'
$env:PATH = "$Toolchain\bin;" + $originalPath
& (Join-Path $Toolchain 'bin\g++.exe') -std=c++11 -fPIC "-I$source" "-I$qt" "-I$qt\QtCore" "-I$qt\QtNetwork" (Join-Path $ProjectRoot 'tests\mshv\station_gate_test.cpp') "-L$Toolchain\lib" -lQt5Network -lQt5Core -o $exe
if ($LASTEXITCODE -ne 0) { throw 'Station gate test compilation failed' }
try { $env:PATH = "$Toolchain\bin;" + $originalPath; & $exe; if ($LASTEXITCODE -ne 0) { throw 'Station gate test failed' } }
finally { $env:PATH = $originalPath }
Write-Host 'Station gate: 7.2s delayed approval/reject/request mismatch/timeout/error/halt cancellation/frequency change/nonloopback tests passed'
$nativeSource = Join-Path $ProjectRoot 'data\build\mshv-auto-dx\src\MSHV_2762'
$objectScript = Join-Path $nativeSource 'object_script.MSHV_OM0RX.Release'
if (-not (Test-Path $objectScript) -or -not (Test-Path (Join-Path $nativeSource 'build\hvrigcontrol.o'))) {
    throw 'Build MSHV from the maintained patch before running the linked HvRigControl PTT test'
}
$rigObject = Join-Path $nativeSource 'build\rig_ptt_edge_test.o'
$rigExe = Join-Path $testDir 'rig_ptt_edge_test.exe'
$env:PATH = "$Toolchain\bin;" + $originalPath
$compileArgs = @(
    '-c','-std=c++11','-O2','-fno-exceptions','-D_WIN64_','-DNO_OMNIRIG',
    '-DQT_NO_EXCEPTIONS','-DQT_NO_DEBUG','-DQT_WIDGETS_LIB','-DQT_GUI_LIB',
    '-DQT_WEBSOCKETS_LIB','-DQT_NETWORK_LIB','-DQT_SQL_LIB','-DQT_CORE_LIB',
    "-I$source","-I$qt","-I$qt\QtWidgets","-I$qt\QtGui", "-I$qt\QtWebSockets",
    "-I$qt\QtNetwork","-I$qt\QtSql","-I$qt\QtCore",
    (Join-Path $ProjectRoot 'tests\mshv\rig_ptt_edge_test.cpp'),'-o',$rigObject
)
& (Join-Path $Toolchain 'bin\g++.exe') @compileArgs
if ($LASTEXITCODE -ne 0) { throw 'Linked HvRigControl PTT test compilation failed' }
$objects = @(Get-Content $objectScript | Where-Object { $_.Trim() -ne 'build/main.o' })
$objects += 'build/rig_ptt_edge_test.o'
$linkArgs = @('-Wl,-subsystem,console','-o',$rigExe) + $objects + @(
    'src/Hv_Lib_DirectX90c/win64/libdsound.a',
    'src/Hv_lib_fftw/win/libfftw3v3310_gcc730_64bit.a','-lsetupapi',
    (Join-Path $Toolchain 'lib\libQt5Widgets.dll.a'),
    (Join-Path $Toolchain 'lib\libQt5Gui.dll.a'),
    (Join-Path $Toolchain 'lib\libQt5WebSockets.dll.a'),
    (Join-Path $Toolchain 'lib\libQt5Network.dll.a'),
    (Join-Path $Toolchain 'lib\libQt5Sql.dll.a'),
    (Join-Path $Toolchain 'lib\libQt5Core.dll.a'),'-lshell32'
)
Push-Location $nativeSource
try {
    & (Join-Path $Toolchain 'bin\g++.exe') @linkArgs
    if ($LASTEXITCODE -ne 0) { throw 'Linked HvRigControl PTT test link failed' }
} finally { Pop-Location }
$oldQpa = $env:QT_QPA_PLATFORM
$oldPluginPath = $env:QT_PLUGIN_PATH
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    $env:QT_PLUGIN_PATH = Join-Path $Toolchain 'share\qt5\plugins'
    & $rigExe
    if ($LASTEXITCODE -ne 0) { throw 'Linked HvRigControl PTT test failed' }
} finally {
    $env:QT_QPA_PLATFORM = $oldQpa
    $env:QT_PLUGIN_PATH = $oldPluginPath
}
Write-Host 'HvRigControl PTT: native true/false and explicit Halt RX edges are direct; no OM0RX permit API invoked'
$historyRaceObject = Join-Path $nativeSource 'build\history_action_race_test.o'
$historyRaceExe = Join-Path $testDir 'history_action_race_test.exe'
$historyCompileArgs = @(
    '-c','-std=c++11','-O2','-fno-exceptions','-D_WIN64_','-DNO_OMNIRIG',
    '-DQT_NO_EXCEPTIONS','-DQT_NO_DEBUG','-DQT_WIDGETS_LIB','-DQT_GUI_LIB',
    '-DQT_WEBSOCKETS_LIB','-DQT_NETWORK_LIB','-DQT_SQL_LIB','-DQT_CORE_LIB',
    "-I$source","-I$qt","-I$qt\QtWidgets","-I$qt\QtGui", "-I$qt\QtWebSockets",
    "-I$qt\QtNetwork","-I$qt\QtSql","-I$qt\QtCore",
    (Join-Path $ProjectRoot 'tests\mshv\history_action_race_test.cpp'),'-o',$historyRaceObject
)
$env:PATH = "$Toolchain\bin;" + $originalPath
& (Join-Path $Toolchain 'bin\g++.exe') @historyCompileArgs
if ($LASTEXITCODE -ne 0) { throw 'Wavelog history action-race test compilation failed' }
$historyObjects = @(Get-Content $objectScript | Where-Object { $_.Trim() -ne 'build/main.o' })
$historyObjects += 'build/history_action_race_test.o'
$historyLinkArgs = @('-Wl,-subsystem,console','-o',$historyRaceExe) + $historyObjects + @(
    'src/Hv_Lib_DirectX90c/win64/libdsound.a',
    'src/Hv_lib_fftw/win/libfftw3v3310_gcc730_64bit.a','-lsetupapi',
    (Join-Path $Toolchain 'lib\libQt5Widgets.dll.a'),
    (Join-Path $Toolchain 'lib\libQt5Gui.dll.a'),
    (Join-Path $Toolchain 'lib\libQt5WebSockets.dll.a'),
    (Join-Path $Toolchain 'lib\libQt5Network.dll.a'),
    (Join-Path $Toolchain 'lib\libQt5Sql.dll.a'),
    (Join-Path $Toolchain 'lib\libQt5Core.dll.a'),'-lshell32'
)
Push-Location $nativeSource
try {
    & (Join-Path $Toolchain 'bin\g++.exe') @historyLinkArgs
    if ($LASTEXITCODE -ne 0) { throw 'Wavelog history action-race test link failed' }
} finally { Pop-Location }
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    $env:QT_PLUGIN_PATH = Join-Path $Toolchain 'share\qt5\plugins'
    & $historyRaceExe
    if ($LASTEXITCODE -ne 0) { throw 'Wavelog history action-race test failed' }
} finally {
    $env:PATH = $originalPath
    $env:QT_QPA_PLATFORM = $oldQpa
    $env:QT_PLUGIN_PATH = $oldPluginPath
}
Write-Host 'Wavelog history action race: revoked/pending in-flight band changes emit no dial/TX-frequency action; authorized flow retained'
$env:PATH = "$Toolchain\bin;" + $originalPath
try {
    $moc = Join-Path $testDir 'moc_hvdxcctracker.cpp'
    & (Join-Path $Toolchain 'bin\moc.exe') (Join-Path $source 'HvDxccTracker\hvdxcctracker.h') -o $moc
    if ($LASTEXITCODE -ne 0) { throw 'Tracker MOC failed' }
    $autoDxMoc = Join-Path $testDir 'moc_dxcctracker.cpp'
    & (Join-Path $Toolchain 'bin\moc.exe') (Join-Path $source 'HvAutoDxer\dxcctracker.h') -o $autoDxMoc
    if ($LASTEXITCODE -ne 0) { throw 'AutoDX tracker MOC failed' }
    $trackerExe = Join-Path $testDir 'tracker_test.exe'
    & (Join-Path $Toolchain 'bin\g++.exe') -std=c++11 -fPIC "-I$source" "-I$qt" "-I$qt\QtWidgets" "-I$qt\QtGui" "-I$qt\QtCore" "-I$qt\QtSql" (Join-Path $ProjectRoot 'tests\mshv\tracker_test.cpp') (Join-Path $source 'HvDxccTracker\hvdxcctracker.cpp') (Join-Path $source 'HvAutoDxer\dxcctracker.cpp') $moc $autoDxMoc "-L$Toolchain\lib" -lQt5Widgets -lQt5Gui -lQt5Sql -lQt5Core -o $trackerExe
    if ($LASTEXITCODE -ne 0) { throw 'Tracker test compilation failed' }
    $env:QT_PLUGIN_PATH = "$Toolchain\share\qt5\plugins"
    & $trackerExe
    if ($LASTEXITCODE -ne 0) { throw 'Tracker import/remap test failed' }
} finally { $env:PATH = $originalPath }
Write-Host 'Tracker: official-ID collisions, aliases, exact calls, FT8/FT4/MFSK imports passed'
if (-not $SkipReleaseAttestation) {
    & (Join-Path $PSScriptRoot 'assert_release.ps1') @attestationArgs
}
