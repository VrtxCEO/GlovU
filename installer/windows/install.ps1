# GlovU Windows Installer
# Run as Administrator for full functionality (CA cert install requires elevation)

param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$InstallDir = "$env:LOCALAPPDATA\GlovU"
$PythonMin = [version]"3.11"

function Write-Step($msg) { Write-Host "  $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [ok] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "  [x]  $msg" -ForegroundColor Red }

# ---------------------------------------------------------------------------
# Uninstall path
# ---------------------------------------------------------------------------
if ($Uninstall) {
    Write-Host "`nRemoving Glove AI Protection..." -ForegroundColor White

    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        & python "$InstallDir\main.py" --uninstall 2>$null
    }

    if (Test-Path "$InstallDir") {
        Remove-Item -Recurse -Force "$InstallDir"
        Write-Ok "Installation directory removed."
    }

    # Remove CA cert
    $thumbprints = Get-ChildItem Cert:\LocalMachine\Root |
        Where-Object { $_.Subject -like "*mitmproxy*" -or $_.Subject -like "*GlovU*" } |
        Select-Object -ExpandProperty Thumbprint
    foreach ($tp in $thumbprints) {
        Remove-Item "Cert:\LocalMachine\Root\$tp" -Force 2>$null
        Write-Ok "CA certificate removed."
    }

    Write-Host "`nGlove AI Protection has been removed." -ForegroundColor White
    exit 0
}

# ---------------------------------------------------------------------------
# Install path
# ---------------------------------------------------------------------------
Write-Host "`nGlove AI Protection — Installer" -ForegroundColor White
Write-Host "================================" -ForegroundColor White

# Check Python
Write-Step "Checking Python..."
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Fail "Python not found. Please install Python 3.11+ from https://python.org"
    exit 1
}
$pyVer = [version](& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if ($pyVer -lt $PythonMin) {
    Write-Fail "Python $PythonMin or higher is required (found $pyVer)."
    exit 1
}
Write-Ok "Python $pyVer found."

# Create install directory
Write-Step "Setting up installation directory..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# Copy files
Write-Step "Copying files..."
$ScriptRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Copy-Item -Recurse -Force "$ScriptRoot\glovu" "$InstallDir\glovu"
Copy-Item -Force "$ScriptRoot\main.py" "$InstallDir\main.py"
Copy-Item -Force "$ScriptRoot\requirements.txt" "$InstallDir\requirements.txt"
Copy-Item -Recurse -Force "$ScriptRoot\assets" "$InstallDir\assets"
Write-Ok "Files copied to $InstallDir"

# Install Python dependencies
Write-Step "Installing dependencies..."
& python -m pip install -q -r "$InstallDir\requirements.txt"
if ($LASTEXITCODE -ne 0) {
    Write-Fail "pip install failed."
    exit 1
}
Write-Ok "Dependencies installed."

# Run the Python installer (generates cert, registers service, sets proxy)
Write-Step "Configuring system..."
& python "$InstallDir\main.py" --install
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Some configuration steps failed. Glove may still work but check the output above."
}

Write-Host "`nInstallation complete." -ForegroundColor Green
Write-Host "Glove AI Protection is now running in the background." -ForegroundColor White
Write-Host "Look for the small icon in your system tray." -ForegroundColor White
Write-Host "`nTo uninstall: run this script with -Uninstall`n" -ForegroundColor Gray
