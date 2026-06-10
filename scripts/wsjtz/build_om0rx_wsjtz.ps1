param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$MsysRoot = "C:\JTSDK64-Tools\tools\msys64",
    [switch]$InstallMissingDependencies,
    [switch]$CleanConfigure
)

$ErrorActionPreference = "Stop"

$sourceRoot = Join-Path $ProjectRoot "data\build\wsjt-z-om0rx\src"
$buildRoot = Join-Path $ProjectRoot "data\build\wsjt-z-om0rx\build-msys"
$bash = Join-Path $MsysRoot "usr\bin\bash.exe"

if (-not (Test-Path -LiteralPath $sourceRoot)) {
    & (Join-Path $PSScriptRoot "prepare_om0rx_wsjtz.ps1") -ProjectRoot $ProjectRoot
}
if (-not (Test-Path -LiteralPath $bash)) {
    throw "MSYS2 bash not found: $bash"
}

$packages = @(
    "mingw-w64-x86_64-gcc-fortran",
    "mingw-w64-x86_64-qt5-base",
    "mingw-w64-x86_64-qt5-multimedia",
    "mingw-w64-x86_64-qt5-serialport",
    "mingw-w64-x86_64-qt5-tools",
    "mingw-w64-x86_64-qt5-websockets",
    "mingw-w64-x86_64-boost",
    "mingw-w64-x86_64-fftw"
)
$packageList = $packages -join " "
$hasPackages = $true
& $bash -lc "pacman -Q $packageList >/dev/null"
if ($LASTEXITCODE -ne 0) {
    $hasPackages = $false
}
if (-not $hasPackages) {
    if (-not $InstallMissingDependencies) {
        throw "Missing MSYS2 build dependencies. Re-run with -InstallMissingDependencies."
    }
    & $bash -lc "pacman -S --needed --noconfirm $packageList"
}

if ($CleanConfigure) {
    Remove-Item -LiteralPath $buildRoot -Recurse -Force -ErrorAction SilentlyContinue
}

$src = $sourceRoot.Replace("\", "/").Replace("C:", "/c")
$build = $buildRoot.Replace("\", "/").Replace("C:", "/c")
$configureLog = (Join-Path $ProjectRoot "data\build\wsjt-z-om0rx\build-msys-configure.log").Replace("\", "/").Replace("C:", "/c")
$buildLog = (Join-Path $ProjectRoot "data\build\wsjt-z-om0rx\build-msys-build.log").Replace("\", "/").Replace("C:", "/c")

$configure = "set -o pipefail; export PATH=/mingw64/bin:/usr/bin:`$PATH; cmake -S '$src' -B '$build' -G Ninja -DCMAKE_BUILD_TYPE=Release -DWSJT_SKIP_MANPAGES=ON -DWSJT_GENERATE_DOCS=OFF -DWSJT_BUILD_UTILS=OFF -DOM0RX_BUILD_WITH_OMNIRIG=OFF -DCMAKE_PREFIX_PATH=/mingw64 2>&1 | tee '$configureLog'"
& $bash -lc $configure
if ($LASTEXITCODE -ne 0) {
    throw "WSJT-Z configure failed. See $configureLog"
}

$buildCommand = "set -o pipefail; export PATH=/mingw64/bin:/usr/bin:`$PATH; cmake --build '$build' --target wsjtx jt9 -j2 2>&1 | tee '$buildLog'"
& $bash -lc $buildCommand
if ($LASTEXITCODE -ne 0) {
    throw "WSJT-Z build failed. See $buildLog"
}

$exe = Join-Path $buildRoot "wsjtx.exe"
$wsjtzExe = Join-Path $buildRoot "wsjt-z.exe"
$decoder = Join-Path $buildRoot "jt9.exe"
$allcallSource = Join-Path $sourceRoot "ALLCALL7.TXT"
$allcallRuntime = Join-Path $buildRoot "ALLCALL7.TXT"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Build completed but wsjtx.exe was not found: $exe"
}
if (-not (Test-Path -LiteralPath $decoder)) {
    throw "Build completed but jt9.exe was not found: $decoder"
}
if (-not (Test-Path -LiteralPath $allcallSource)) {
    throw "Build completed but ALLCALL7.TXT was not found in source: $allcallSource"
}
Copy-Item -LiteralPath $exe -Destination $wsjtzExe -Force
Copy-Item -LiteralPath $allcallSource -Destination $allcallRuntime -Force

Write-Host "Built OM0RX WSJT-Z:"
Write-Host "  $wsjtzExe"
Write-Host "Original target executable:"
Write-Host "  $exe"
Write-Host "Decoder:"
Write-Host "  $decoder"
Write-Host "Runtime callsign database:"
Write-Host "  $allcallRuntime"
