$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Cli = Join-Path $ProjectRoot ".venv\Scripts\zybtool.exe"

if (-not (Test-Path -LiteralPath $Cli)) {
    throw "ZYB Tool belum disiapkan. Jalankan setup.ps1 terlebih dahulu."
}

& $Cli @args
exit $LASTEXITCODE
