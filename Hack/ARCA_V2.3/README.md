# ARCA V2.2 — Agentic Risk & Change Assurance

ARCA V2.2 is an enterprise security-assurance demonstrator with a FastAPI backend and Next.js frontend. It provides A1 Change Quality, A2 Access Intelligence, A3 Execution Assurance, A4 Undocumented Changes, A5 Ask ARCA, executive analytics, observability, human feedback, and a Manager-only Evaluation & Testing dashboard. All included AWS, Azure, and Snowflake evidence is synthetic.

Deterministic policy engines remain authoritative. Optional model-generated explanations are advisory and cannot approve access or modify infrastructure. Offline evaluation and automated tests do not invoke paid models or live cloud APIs.

## Requirements

- Python 3.11
- Node.js and npm compatible with `frontend/package-lock.json`
- Windows PowerShell for the supplied development launcher

## Backend setup

From the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip check
Copy-Item .env.example .env
.\scripts\start_api_v2.bat
```

The API starts at `http://127.0.0.1:8000`; OpenAPI documentation is at `/docs`. The default configuration uses local synthetic evidence and does not require credentials.

## Frontend setup

In a second terminal:

```powershell
Set-Location .\frontend
npm.cmd ci
Copy-Item .env.example .env.local
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000`. The frontend defaults to `http://127.0.0.1:8000`; override it only through the untracked local environment file.

## Offline verification

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend tests
.\.venv\Scripts\python.exe -m pytest -q tests\backend
.\.venv\Scripts\python.exe scripts\evaluate_ai_quality.py

Set-Location .\frontend
npm.cmd run test:api
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

## Configuration and safety

`.env` and `frontend/.env.local` are intentionally excluded from Git. `.env.example` files contain placeholders only. Never commit credentials, certificates, runtime logs, feedback records, browser profiles, virtual environments, `node_modules`, or `.next` output. See `docs/ARCA_V2_DEPLOYMENT_GUIDE.md` and `docs/ARCA_V2_CONFIGURATION.txt` for configuration details.

The Evaluation & Testing dashboard runs a bounded allowlisted offline harness. Live LLM evaluation and LLM-as-a-Judge remain disabled by default.
