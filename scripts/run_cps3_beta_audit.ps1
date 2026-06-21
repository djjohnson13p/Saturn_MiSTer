param(
    [string]$ReleaseZip = "C:\Users\djjoh\Downloads\jtfriday_260612_mister.zip",
    [string]$BetaZip = "C:\Users\djjoh\Downloads\jtbeta.zip",
    [string]$SdRoot = "\\MiSTer\sdcard"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$AuditScript = Join-Path $RepoRoot "scripts\cps3_beta_audit.py"

Push-Location $RepoRoot
try {
    Write-Host "Running CPS3 beta audit..."
    Write-Host "Release ZIP: $ReleaseZip"
    Write-Host "Beta ZIP:    $BetaZip"
    Write-Host "SD root:     $SdRoot"
    Write-Host ""

    python $AuditScript `
        $ReleaseZip `
        $BetaZip `
        $SdRoot `
        --expected-beta-crc 8b6976d8 `
        --reference-label "Patreon 2026-06-12" `
        --allow-rbf-drift `
        --targeted-sd-copy

    $ExitCode = $LASTEXITCODE
    Write-Host ""
    Write-Host "CPS3 beta audit finished with exit code $ExitCode."
    exit $ExitCode
}
finally {
    Pop-Location
}
