# AI NETRA GEO - Windows PowerShell 5.1 compatible startup launcher.
[CmdletBinding()]
param(
    [string]$ProjectRoot = $PSScriptRoot,
    [int]$StartupTimeoutSeconds = 60
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$FrontendDir = Join-Path $ProjectRoot 'frontend'
$PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$LogDir = Join-Path $ProjectRoot 'logs\startup'
$RuntimeDir = Join-Path $ProjectRoot 'scripts\runtime'

function Write-Status {
    param([string]$Level, [string]$Message)
    $color = switch ($Level) {
        'PASS' { 'Green' }
        'FAIL' { 'Red' }
        'WARN' { 'Yellow' }
        default { 'Cyan' }
    }
    Write-Host ('[' + $Level + '] ' + $Message) -ForegroundColor $color
}

function Test-Endpoint {
    param([string]$Url, [bool]$IsApi)
    try {
        if ($IsApi) {
            $data = Invoke-RestMethod -Uri $Url -TimeoutSec 3
            return ($data.status -eq 'healthy')
        }
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
    } catch {
        return $false
    }
}

function Escape-PSLiteral {
    param([string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

Write-Status 'INFO' ('Project directory: ' + $ProjectRoot)
$required = @(
    $PythonExe,
    (Join-Path $ProjectRoot 'api.py'),
    (Join-Path $ProjectRoot 'waterlogging_api.py'),
    (Join-Path $FrontendDir 'package.json')
)
$missing = @($required | Where-Object { -not (Test-Path -LiteralPath $_) })
if ($missing.Count -gt 0) {
    foreach ($path in $missing) { Write-Status 'FAIL' ('Missing: ' + $path) }
    exit 1
}

$npmCommand = Get-Command 'npm.cmd' -ErrorAction SilentlyContinue
if ($null -eq $npmCommand) {
    Write-Status 'FAIL' 'npm.cmd not found. Confirm Node.js is installed and available in PATH.'
    exit 1
}
$NpmExe = $npmCommand.Source

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null

$services = @(
    [pscustomobject]@{ Name='Building API'; Kind='building'; Port=8000; Url='http://127.0.0.1:8000/health'; Api=$true; WorkDir=$ProjectRoot; Log=(Join-Path $LogDir 'building-api.log') },
    [pscustomobject]@{ Name='Waterlogging API'; Kind='waterlogging'; Port=8001; Url='http://127.0.0.1:8001/health'; Api=$true; WorkDir=$ProjectRoot; Log=(Join-Path $LogDir 'waterlogging-api.log') },
    [pscustomobject]@{ Name='Next.js frontend'; Kind='frontend'; Port=3000; Url='http://127.0.0.1:3000/'; Api=$false; WorkDir=$FrontendDir; Log=(Join-Path $LogDir 'frontend.log') }
)

foreach ($service in $services) {
    if (Test-Endpoint -Url $service.Url -IsApi $service.Api) {
        Write-Status 'PASS' ($service.Name + ' is already running; leaving it untouched.')
        continue
    }

    $listener = @(Get-NetTCPConnection -LocalPort $service.Port -State Listen -ErrorAction SilentlyContinue)
    if ($listener.Count -gt 0) {
        Write-Status 'FAIL' ('Port ' + $service.Port + ' is occupied, but the service health check failed.')
        foreach ($entry in $listener) { Write-Status 'WARN' ('Owning PID: ' + $entry.OwningProcess) }
        continue
    }

    $work = Escape-PSLiteral $service.WorkDir
    $log = Escape-PSLiteral $service.Log
    $python = Escape-PSLiteral $PythonExe
    $npm = Escape-PSLiteral $NpmExe
    $command = switch ($service.Kind) {
        'building' { '& ' + $python + ' -m uvicorn api:app --reload --host 127.0.0.1 --port 8000 2>&1 | Tee-Object -FilePath ' + $log + ' -Append' }
        'waterlogging' { '& ' + $python + ' -m uvicorn waterlogging_api:app --reload --host 127.0.0.1 --port 8001 2>&1 | Tee-Object -FilePath ' + $log + ' -Append' }
        'frontend' { '& ' + $npm + ' run dev -- --hostname 127.0.0.1 --port 3000 2>&1 | Tee-Object -FilePath ' + $log + ' -Append' }
    }
    $childFile = Join-Path $RuntimeDir ('run-' + $service.Kind + '.ps1')
    $childText = @(
        '$ErrorActionPreference = ''Continue''',
        ('Set-Location -LiteralPath ' + $work),
        ('Write-Host ''Starting AI NETRA ' + $service.Name + ''' -ForegroundColor Cyan'),
        $command,
        'Write-Host ''Service exited. Review the log or error output above.'' -ForegroundColor Yellow',
        'Read-Host ''Press Enter to close this window'''
    ) -join [Environment]::NewLine
    Set-Content -LiteralPath $childFile -Value $childText -Encoding ASCII

    try {
        $arguments = '-NoProfile -ExecutionPolicy Bypass -NoExit -File "' + $childFile + '"'
        Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WorkingDirectory $service.WorkDir | Out-Null
        Write-Status 'INFO' ('Opened separate window for ' + $service.Name)
    } catch {
        Write-Status 'FAIL' ('Launch error for ' + $service.Name + ': ' + $_.Exception.Message)
    }
}

Write-Status 'INFO' ('Checking endpoints for up to ' + $StartupTimeoutSeconds + ' seconds...')
$deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
do {
    $results = @(
        foreach ($service in $services) {
            [pscustomobject]@{
                Name=$service.Name
                Url=$service.Url
                Healthy=(Test-Endpoint -Url $service.Url -IsApi $service.Api)
                Log=$service.Log
            }
        }
    )
    if (@($results | Where-Object { -not $_.Healthy }).Count -eq 0) { break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

Write-Host ''
$failures = 0
foreach ($item in $results) {
    if ($item.Healthy) {
        Write-Status 'PASS' ($item.Name + ': ' + $item.Url)
    } else {
        $failures++
        Write-Status 'FAIL' ($item.Name + ' not responding: ' + $item.Url)
        if (Test-Path -LiteralPath $item.Log) {
            Write-Status 'WARN' ('Recent log output: ' + $item.Log)
            Get-Content -LiteralPath $item.Log -Tail 15 | Out-Host
        } else {
            Write-Status 'WARN' ('No log available yet: ' + $item.Log)
        }
    }
}
if ($failures -gt 0) {
    Write-Status 'FAIL' 'Startup incomplete. Review the service windows and logs above.'
    exit 1
}
Write-Status 'PASS' 'AI NETRA is ready at http://127.0.0.1:3000/'
Write-Status 'INFO' 'Stop services with Ctrl+C in their respective windows.'

