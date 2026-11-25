$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { throw "Project environment not found. Run setup.ps1 on the developer machine first." }
& $Python -m pip install "pyinstaller==6.19.0"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller installation failed." }
& $Python -m PyInstaller --noconfirm --clean --windowed --onedir --name ZYBTool --paths src --collect-all metaqr --collect-all av --hidden-import zybtool.gui --hidden-import zybtool.settings --hidden-import av src\zybtool\gui.py
if ($LASTEXITCODE -ne 0) { throw "Portable build failed." }
$Portable = Join-Path $ProjectRoot "dist\ZYBTool"
Copy-Item PORTABLE-README.txt (Join-Path $Portable "README.txt") -Force
$Archive = Join-Path $ProjectRoot "dist\ZYBTool-portable-windows-x64.zip"
if (Test-Path $Archive) { Remove-Item $Archive -Force }
tar.exe -a -c -f $Archive -C (Join-Path $ProjectRoot "dist") ZYBTool
if ($LASTEXITCODE -ne 0) { throw "ZIP creation failed." }
Write-Host "Portable package: $Archive"
