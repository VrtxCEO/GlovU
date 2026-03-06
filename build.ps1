# GlovU build script — produces a single GlovU.exe
# Run from the GlovU directory: .\build.ps1

param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "   [ok] $msg" -ForegroundColor Green }
function Write-Fail($msg) { Write-Host "   [x]  $msg" -ForegroundColor Red; exit 1 }

$ProjectDir = $PSScriptRoot
Set-Location $ProjectDir

# Clean previous build
if ($Clean -or (Test-Path "dist")) {
    Write-Step "Cleaning previous build..."
    Remove-Item -Recurse -Force "dist" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "build" -ErrorAction SilentlyContinue
    Write-Ok "Clean done."
}

# Check Python
Write-Step "Checking Python..."
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Write-Fail "Python not found." }
$pyVer = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Ok "Python $pyVer"

# Install/upgrade build dependencies
Write-Step "Installing dependencies..."
& python -m pip install -q --upgrade pip pyinstaller
& python -m pip install -q -r requirements.txt
Write-Ok "Dependencies ready."

# Build
Write-Step "Building GlovU.exe (this takes a minute)..."
& python -m PyInstaller glovu.spec --noconfirm
if ($LASTEXITCODE -ne 0) { Write-Fail "PyInstaller failed." }

$exe = "dist\GlovU.exe"
if (-not (Test-Path $exe)) { Write-Fail "Build succeeded but GlovU.exe not found." }

$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Ok "Built: $exe ($size MB)"

Write-Host "`nDone. Distribute dist\GlovU.exe" -ForegroundColor Green
Write-Host "Users double-click it — no setup required.`n" -ForegroundColor White
