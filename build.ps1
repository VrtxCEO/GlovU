# GlovU build script --- produces a single GlovU.exe
# Run from the GlovU directory: .\build.ps1

param(
    [switch]$Clean,
    [string]$DistDir = "dist",
    [string]$WorkDir = "build"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "   [ok] $msg" -ForegroundColor Green }
function Write-Fail($msg) { Write-Host "   [x]  $msg" -ForegroundColor Red; exit 1 }

$ProjectDir = $PSScriptRoot
Set-Location $ProjectDir

# Clean previous build
if ($Clean -or (Test-Path $DistDir) -or (Test-Path $WorkDir)) {
    Write-Step "Cleaning previous build..."
    Remove-Item -Recurse -Force $DistDir -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $WorkDir -ErrorAction SilentlyContinue
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
$spec = Join-Path $ProjectDir "glovu.spec"
if (Test-Path $spec) {
    & python -m PyInstaller $spec --noconfirm --distpath $DistDir --workpath $WorkDir
} else {
    # Fallback: build directly from main.py
    $iconPng = Join-Path $ProjectDir "assets\\glovu-icon.png"
    $iconIco = Join-Path $ProjectDir "assets\\glovu-icon.ico"
    $iconArg = @()
    if (Test-Path $iconIco) { $iconArg = @("--icon", $iconIco) }
    & python -m PyInstaller `
        --name GlovU `
        --onefile `
        --noconsole `
        --clean `
        --distpath $DistDir `
        --workpath $WorkDir `
        --add-data "assets\\glovu-icon.png;assets" `
        @iconArg `
        main.py
}
if ($LASTEXITCODE -ne 0) { Write-Fail "PyInstaller failed." }

$exe = Join-Path $DistDir "GlovU.exe"
if (-not (Test-Path $exe)) { Write-Fail "Build succeeded but GlovU.exe not found." }

$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Ok "Built: $exe ($size MB)"

Write-Host "`nDone. Distribute $exe" -ForegroundColor Green
Write-Host "Users double-click it --- no setup required.`n" -ForegroundColor White

