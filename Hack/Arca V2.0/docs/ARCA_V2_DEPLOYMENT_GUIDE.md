# ARCA V2 Windows deployment and restore guide

This guide reproduces the verified ARCA V2 development environment on a fresh
Windows laptop. It does not connect to live AWS, Azure, or Snowflake systems.

## Prerequisites

- 64-bit Windows with PowerShell.
- Python 3.11 (3.11.15 verified). Direct dependencies require Python 3.10+.
- Node.js 20.9 or newer (24.22.1 verified) and npm (11.19.1 verified).
- Approximately 1 GB free disk space for source, virtual environment,
  `node_modules`, and build output.
- Outbound HTTPS only if dependencies must be downloaded or LLM assistance is
  explicitly enabled.

Verify tools:

```powershell
py -3.11 --version
node --version
npm.cmd --version
```

Use `npm.cmd` if the PowerShell execution policy blocks `npm.ps1`.

## Restore the backup

Copy the complete `Arca V2.0` backup folder to a local working location. Keep
its directory structure intact. The backup intentionally contains no `.venv`,
`node_modules`, `.next`, populated `.env`, or credentials; recreate them below.

```powershell
Set-Location 'D:\Usecase\ARCA2\Arca V2.0'
```

If restoring elsewhere, substitute the new absolute path in every command.
Do not copy a populated `.env` from another device. Supply secret values through
an approved secure transfer method on the destination laptop.

## Create the Python environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip check
```

`requirements.lock.txt` reproduces the exact verified backend/test graph.
`requirements.txt` contains the bounded direct requirements for future safe
resolution. Do not install from a global Python environment.

## Install the frontend

```powershell
Set-Location .\frontend
npm.cmd ci
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
Set-Location ..
```

Use `npm ci`, not `npm install` or `npm update`, to honor package-lock.json.

## Configure the application

Deterministic mode needs no local `.env`. To make explicit local settings:

```powershell
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env.local
```

The default frontend API URL is `http://127.0.0.1:8000`; the backend permits
`http://localhost:3000` and `http://127.0.0.1:3000`. See
`docs/ARCA_V2_CONFIGURATION.txt` for every variable and constraint.

For optional standard OpenAI assistance, edit only the untracked root `.env`:

```ini
ARCA_LLM_ENABLED=true
ARCA_LLM_PROVIDER=openai
ARCA_LLM_ENDPOINT=
ARCA_LLM_MODEL=gpt-5-mini
ARCA_LLM_API_KEY=replace-securely-on-this-laptop
ARCA_LLM_TIMEOUT_SECONDS=45
ARCA_LLM_MAX_OUTPUT_TOKENS=1200
ARCA_LLM_REASONING_EFFORT=minimal
```

The empty endpoint uses `https://api.openai.com`. Never put a secret in
`.env.example`, `frontend/.env.local`, source code, logs, screenshots, or chat.
LLM output is advisory; deterministic security findings remain authoritative.

## Start FastAPI

From the project root:

```powershell
.\scripts\start_api_v2.bat
```

This existing launcher uses `.venv\Scripts\python.exe`, rejects an occupied
port, and starts Uvicorn at `127.0.0.1:8000`. In another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Start-Process http://127.0.0.1:8000/docs
```

## Start Next.js

In a second PowerShell window:

```powershell
Set-Location 'D:\Usecase\ARCA2\Arca V2.0\frontend'
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000`. Confirm Overview loads, environment switching
works, and a deterministic demo scenario returns synthetic evidence.

## Targeted verification

No paid or live-cloud call is required:

```powershell
Set-Location 'D:\Usecase\ARCA2\Arca V2.0'
.\.venv\Scripts\python.exe -m compileall -q backend tests
.\.venv\Scripts\python.exe -m pytest -q tests\backend
.\.venv\Scripts\python.exe -m pip check

Set-Location .\frontend
npm.cmd run test:api
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

The optional browser check requires a separately started Chrome/Chromium remote
debugging endpoint; see `scripts/browser_validate_v2.mjs`. It does not install
or start a browser automatically.

## Common problems

**Python executable not found:** recreate `.venv` in the project root using
Python 3.11. Do not point the launcher at V1 or a parent environment.

**PowerShell blocks npm.ps1:** invoke `npm.cmd` explicitly. Do not weaken the
machine execution policy solely for ARCA.

**Port 8000 or 3000 occupied:** identify the owning process with
`Get-NetTCPConnection -LocalPort 8000,3000 -State Listen`. Stop it only if you
own it, or choose a different development port and update the API URL/CORS
origins consistently.

**CORS error:** the browser origin must exactly match an explicit entry in
`ARCA_API_CORS_ORIGINS`; wildcards are intentionally rejected. Restart FastAPI
after changing `.env`.

**Frontend cannot reach API:** verify the health URL, then confirm
`NEXT_PUBLIC_ARCA_API_URL`. Restart the Next.js dev server after changing public
environment variables.

**Package install fails behind a proxy:** use organization-approved proxy and
certificate settings for pip/npm. Do not disable TLS verification. Confirm DNS
and port 443 with `Resolve-DnsName` and `Test-NetConnection`.

**OpenAI gateway unavailable:** deterministic mode remains usable. Confirm
`ARCA_LLM_ENABLED`, provider, model, endpoint, and that a non-placeholder key is
present without printing it. Test `Test-NetConnection api.openai.com -Port 443`.
The verification workstation previously resolved DNS but could not establish
TCP 443, indicating an external network/firewall/proxy limitation. Do not retry
billable calls repeatedly.

**Unexpected live-cloud expectation:** V2 uses only local synthetic fixtures.
AWS, Azure, and Snowflake SDK credentials are neither required nor consumed.
