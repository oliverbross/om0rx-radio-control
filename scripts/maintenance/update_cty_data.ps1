param(
    [string[]]$DatUrl = @(),
    [string[]]$CsvUrl = @(),
    [switch]$SkipCsv
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)

$argsList = @("scripts\maintenance\update_cty_data.py")
foreach ($url in $DatUrl) {
    $argsList += "--dat-url"
    $argsList += $url
}
foreach ($url in $CsvUrl) {
    $argsList += "--csv-url"
    $argsList += $url
}
if ($SkipCsv) {
    $argsList += "--skip-csv"
}

Push-Location $ProjectRoot
try {
    & python @argsList
    if ($LASTEXITCODE -ne 0) {
        throw "CTY update failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
