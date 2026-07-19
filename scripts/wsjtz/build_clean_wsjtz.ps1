param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$MsysRoot = "C:\JTSDK64-Tools\tools\msys64",
    [switch]$InstallMissingDependencies,
    [switch]$CleanConfigure
)

$ErrorActionPreference = "Stop"

$sourceRoot = Join-Path $ProjectRoot "data\build\wsjt-z-clean\src"
$workRoot = Join-Path $ProjectRoot "data\build\wsjt-z-clean"
$buildRoot = Join-Path $workRoot "build-msys"
$patchPaths = @(
    (Join-Path $ProjectRoot "docs\wsjtx\clean-rebuild\patches\0001-build-allow-omnirig-off.patch"),
    (Join-Path $ProjectRoot "docs\wsjtx\clean-rebuild\patches\0002-build-link-fftw-threads-on-windows.patch"),
    (Join-Path $ProjectRoot "docs\wsjtx\clean-rebuild\patches\0100-band-qsy-transaction-tracing.patch"),
    (Join-Path $ProjectRoot "docs\wsjtx\clean-rebuild\patches\0200-display-status-columns.patch"),
    (Join-Path $ProjectRoot "docs\wsjtx\clean-rebuild\patches\0300-dxcc-priority-hunt.patch"),
    (Join-Path $ProjectRoot "docs\wsjtx\clean-rebuild\patches\0400-backend-target-command.patch"),
    (Join-Path $ProjectRoot "docs\wsjtx\clean-rebuild\patches\0500-visible-automation-startup.patch"),
    (Join-Path $ProjectRoot "docs\wsjtx\clean-rebuild\patches\0600-direct-reply-lock.patch")
)
$bash = Join-Path $MsysRoot "usr\bin\bash.exe"

if (-not (Test-Path -LiteralPath $sourceRoot)) {
    & (Join-Path $PSScriptRoot "prepare_clean_wsjtz.ps1") -ProjectRoot $ProjectRoot
}
if (-not (Test-Path -LiteralPath $bash)) {
    throw "MSYS2 bash not found: $bash"
}
foreach ($patchPath in $patchPaths) {
    if (-not (Test-Path -LiteralPath $patchPath)) {
        throw "Required isolated build compatibility patch not found: $patchPath"
    }
}

$allowedDirtyPaths = @(
    "CMakeLists.txt",
    "Network/MessageClient.cpp",
    "Network/MessageClient.hpp",
    "Network/NetworkMessage.hpp",
    "Transceiver/TransceiverFactory.cpp",
    "widgets/mainwindow.cpp",
    "widgets/mainwindow.h",
    "widgets/displaytext.cpp",
    "widgets/displaytext.h",
    "widgets/mainwindow.ui",
    "wsjtx_config.h.in"
)
$dirtyPaths = @(git -C $sourceRoot status --porcelain | ForEach-Object { $_.Substring(3).Replace("\", "/") })
$unexpectedDirtyPaths = @($dirtyPaths | Where-Object { $_ -notin $allowedDirtyPaths })
if ($unexpectedDirtyPaths.Count -gt 0) {
    throw "Clean source contains unexpected changes: $($unexpectedDirtyPaths -join ', ')"
}

$expectedCommit = "fa53f635462def9f37b54f63f18e407ecda2ba12"
$actualCommit = (git -C $sourceRoot rev-parse HEAD).Trim()
if ($actualCommit -ne $expectedCommit) {
    throw "Clean source is at $actualCommit, expected $expectedCommit."
}

$patchStatePath = Join-Path $workRoot "APPLIED-PATCHES.txt"
$expectedPatchState = @($patchPaths | ForEach-Object { Split-Path -Leaf $_ })
$actualPatchState = if (Test-Path -LiteralPath $patchStatePath) {
    @(Get-Content -LiteralPath $patchStatePath | Where-Object { $_ })
} else { @() }
$patchStateMatches = ($actualPatchState.Count -eq $expectedPatchState.Count) -and
    (-not (Compare-Object $actualPatchState $expectedPatchState -SyncWindow 0))

if (-not $patchStateMatches) {
    # If the final dependent patch reverses cleanly, the complete ordered stack is present.
    git -C $sourceRoot apply --unidiff-zero --reverse --check $patchPaths[-1] 2>$null
    $completeStackAlreadyApplied = $LASTEXITCODE -eq 0
    if (-not $completeStackAlreadyApplied) {
        foreach ($patchPath in $patchPaths) {
            git -C $sourceRoot apply --unidiff-zero --reverse --check $patchPath 2>$null
            $patchAlreadyApplied = $LASTEXITCODE -eq 0
            if (-not $patchAlreadyApplied) {
                git -C $sourceRoot apply --unidiff-zero --check $patchPath
                if ($LASTEXITCODE -ne 0) {
                    throw "Clean rebuild patch does not apply in sequence: $patchPath"
                }
                git -C $sourceRoot apply --unidiff-zero $patchPath
                if ($LASTEXITCODE -ne 0) {
                    throw "Unable to apply clean rebuild patch: $patchPath"
                }
            }
        }
    }
    Set-Content -LiteralPath $patchStatePath -Value $expectedPatchState -Encoding ASCII
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
& $bash -lc "pacman -Q $packageList >/dev/null"
if ($LASTEXITCODE -ne 0) {
    if (-not $InstallMissingDependencies) {
        throw "Missing MSYS2 build dependencies. Re-run with -InstallMissingDependencies."
    }
    & $bash -lc "pacman -S --needed --noconfirm $packageList"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to install MSYS2 build dependencies."
    }
}

if ($CleanConfigure -and (Test-Path -LiteralPath $buildRoot)) {
    $expectedBuildRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot "data\build\wsjt-z-clean\build-msys"))
    $actualBuildRoot = [IO.Path]::GetFullPath($buildRoot)
    if (-not $actualBuildRoot.Equals($expectedBuildRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean unexpected build directory: $actualBuildRoot"
    }
    Remove-Item -LiteralPath $buildRoot -Recurse -Force
}

$src = $sourceRoot.Replace("\", "/").Replace("C:", "/c")
$build = $buildRoot.Replace("\", "/").Replace("C:", "/c")
$configureLog = (Join-Path $workRoot "configure.log").Replace("\", "/").Replace("C:", "/c")
$buildLog = (Join-Path $workRoot "build.log").Replace("\", "/").Replace("C:", "/c")

$configure = "set -o pipefail; export PATH=/mingw64/bin:/usr/bin:`$PATH; cmake -S '$src' -B '$build' -G Ninja -DCMAKE_BUILD_TYPE=Release -DWSJT_SKIP_MANPAGES=ON -DWSJT_GENERATE_DOCS=OFF -DWSJT_BUILD_UTILS=OFF -DOM0RX_BUILD_WITH_OMNIRIG=OFF -DCMAKE_PREFIX_PATH=/mingw64 2>&1 | tee '$configureLog'"
& $bash -lc $configure
if ($LASTEXITCODE -ne 0) {
    throw "Clean WSJT-Z configure failed. See $configureLog"
}

$buildCommand = "set -o pipefail; export PATH=/mingw64/bin:/usr/bin:`$PATH; cmake --build '$build' --target wsjtx jt9 -j2 2>&1 | tee '$buildLog'"
& $bash -lc $buildCommand
if ($LASTEXITCODE -ne 0) {
    throw "Clean WSJT-Z build failed. See $buildLog"
}

$exe = Join-Path $buildRoot "wsjtx.exe"
$sideBySideExe = Join-Path $buildRoot "wsjt-z-clean.exe"
$decoder = Join-Path $buildRoot "jt9.exe"
$allcallSource = Join-Path $sourceRoot "ALLCALL7.TXT"
$allcallRuntime = Join-Path $buildRoot "ALLCALL7.TXT"
foreach ($required in @($exe, $decoder, $allcallSource)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Build completed but required runtime file is missing: $required"
    }
}
Copy-Item -LiteralPath $exe -Destination $sideBySideExe -Force
Copy-Item -LiteralPath $allcallSource -Destination $allcallRuntime -Force

$exeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sideBySideExe).Hash
$decoderHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $decoder).Hash
$identity = @(
    "source_commit=$actualCommit"
    "patches=$((@($patchPaths | ForEach-Object { Split-Path -Leaf $_ })) -join ',')"
    "executable_sha256=$exeHash"
    "decoder_sha256=$decoderHash"
)
Set-Content -LiteralPath (Join-Path $workRoot "BUILD-IDENTITY.txt") -Value $identity -Encoding ASCII

Write-Host "Built clean WSJT-Z baseline:"
Write-Host "  $sideBySideExe"
Write-Host "Decoder:"
Write-Host "  $decoder"
Write-Host "Executable SHA256: $exeHash"
Write-Host "Decoder SHA256:    $decoderHash"
