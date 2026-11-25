$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "ZYB Tool belum disiapkan. Jalankan setup.ps1 terlebih dahulu."
}

Start-Process -FilePath $Python -ArgumentList @("-m", "zybtool.gui") -WorkingDirectory $ProjectRoot
