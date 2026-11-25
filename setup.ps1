$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$Candidates = @()
$UvPython = Join-Path $env:APPDATA "uv\python\cpython-3.12.15-windows-x86_64-none\python.exe"
$LocalPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
$ProgramPython = Join-Path $env:ProgramFiles "Python312\python.exe"
$Candidates += $UvPython, $LocalPython, $ProgramPython

$PathPython = Get-Command python -ErrorAction SilentlyContinue
if ($PathPython) { $Candidates += $PathPython.Source }

$Python312 = $null
foreach ($Candidate in ($Candidates | Select-Object -Unique)) {
    if (-not $Candidate -or -not (Test-Path -LiteralPath $Candidate)) { continue }
    try {
        $Version = (& $Candidate -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null)
        if ($LASTEXITCODE -eq 0 -and $Version.Trim() -eq "3.12.15") {
            $Python312 = $Candidate
            break
        }
    } catch {
        continue
    }
}

if (-not $Python312) {
    throw "Python 3.12.15 tidak ditemukan. Pasang Python 3.12.15 untuk user saat ini, lalu jalankan setup.ps1 lagi. Tidak diperlukan hak administrator."
}

Write-Host "Python: $Python312"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $VenvPython) {
    $ExistingVersion = (& $VenvPython -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null)
    if ($LASTEXITCODE -ne 0 -or $ExistingVersion.Trim() -ne "3.12.15") {
        throw "Folder .venv sudah ada tetapi bukan Python 3.12.15. Pindahkan atau hapus .venv secara manual, lalu jalankan setup.ps1 lagi."
    }
} else {
    & $Python312 -m venv (Join-Path $ProjectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Gagal membuat virtual environment." }
}

& $VenvPython -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "Instalasi dependensi proyek gagal." }

Write-Host ""
Write-Host "ZYB Tool siap digunakan."
Write-Host "Contoh:"
Write-Host '.\run.ps1 scan "D:\Recording" --output "D:\ZYB_Reports"'
