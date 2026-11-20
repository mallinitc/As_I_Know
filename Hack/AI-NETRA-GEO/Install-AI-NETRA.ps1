# AI NETRA GEO - Portable Windows Installation
# Run once before starting the application.

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " AI NETRA GEO - Installation" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Set-Location $ProjectRoot

# Verify Python 3.11
$pythonCommand = Get-Command py -ErrorAction SilentlyContinue

if (-not $pythonCommand) {
    throw "Python launcher not found. Install Python 3.11 with the Windows Python launcher."
}

& py -3.11 --version

if ($LASTEXITCODE -ne 0) {
    throw "Python 3.11 is required."
}

# Verify Node.js
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue

if (-not $npmCommand) {
    throw "npm not found. Install Node.js and ensure npm is available in PATH."
}

& npm.cmd --version

if ($LASTEXITCODE -ne 0) {
    throw "npm verification failed."
}

# Create Python virtual environment
$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "`nCreating Python virtual environment..." -ForegroundColor Yellow
    & py -3.11 -m venv (Join-Path $ProjectRoot ".venv")

    if ($LASTEXITCODE -ne 0) {
        throw "Virtual environment creation failed."
    }
}

# Install backend dependencies
Write-Host "`nInstalling Python dependencies..." -ForegroundColor Yellow

& $venvPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")

if ($LASTEXITCODE -ne 0) {
    throw "Python dependency installation failed."
}

# Install frontend dependencies
$frontend = Join-Path $ProjectRoot "frontend"

if (-not (Test-Path (Join-Path $frontend "package.json"))) {
    throw "Frontend package.json not found."
}

Write-Host "`nInstalling frontend dependencies..." -ForegroundColor Yellow

Push-Location $frontend

try {
    if (Test-Path "package-lock.json") {
        & npm.cmd ci
    }
    else {
        & npm.cmd install
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Frontend dependency installation failed."
    }
}
finally {
    Pop-Location
}

Write-Host "`n========================================" -ForegroundColor Green
Write-Host " AI NETRA Installation Complete" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "Run: .\Start-AI-NETRA-PORTABLE.ps1"
