# ARCA Office Laptop Setup Guide

## Repository

The private GitHub repository URL will be inserted after repository creation is explicitly approved. Until then, use `<PRIVATE_REPOSITORY_URL>` in the commands below.

## Prerequisites

- Windows 10/11 with PowerShell
- Git
- Python 3.11 recommended
- Network access to the selected model provider only when real inference is required

## Clone and create the environment

```powershell
git clone <PRIVATE_REPOSITORY_URL>
Set-Location ARCA-Hackathon
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, run Python directly as `.\.venv\Scripts\python.exe` instead of changing the machine execution policy.

## Configure ARCA

```powershell
Copy-Item .env.example .env
notepad .env
```

Never commit `.env`. Select one LLM provider:

```ini
# Offline deterministic mode
LLM_PROVIDER=mock

# OpenAI
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-5-mini
OPENAI_API_KEY=replace_locally

# Amazon Bedrock
LLM_PROVIDER=bedrock
BEDROCK_MODEL_ID=replace_with_approved_model_id
AWS_REGION=replace_with_approved_region
```

Use only the variables relevant to the selected provider. Office Bedrock authentication should use the organization-approved AWS mechanism; do not store access keys in the repository. `ARCA_MODE=mock` keeps evidence access on local demonstration data even when an LLM is configured.

## Launch

```powershell
$env:ARCA_MODE = "mock"
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

Open `http://127.0.0.1:8501`.

## Offline verification

```powershell
.\.venv\Scripts\python.exe -m compileall -q arca app.py
.\.venv\Scripts\python.exe -c "import app; from arca.workflow import build; from arca.investigation.agent import InvestigationAgent; print('Imports OK')"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

Do not authorize paid-provider tests unless intentionally testing external connectivity.

## Verify synthetic evidence

```powershell
.\.venv\Scripts\python.exe -c "from arca.providers import get_provider; a=get_provider('azure').load_bundle(); print({k: len(v) for k,v in a.items()})"
```

The Azure bundle should include ServiceNow-style changes, PIM requests, RBAC assignments, role definitions, resources, and Activity Logs. AWS demonstration evidence is under `data\changes.json`, `data\access_requests.json`, and `data\events.json`. The scenario catalog is `data\demo_catalog.json`.

## Functional checks

1. In **Change Lifecycle**, select Stage 1 examples and validate both complete and incomplete drafts. Confirm Improve Draft preserves empty unknowns and Revalidate works.
2. In Stage 2, search `CHG-AZ-2021`; verify all associated PIM requests appear and combined coverage is assessed.
3. In Stage 3, use catalog examples for potential match and deviation outcomes.
4. Run Full Lifecycle Assessment with a catalog scenario.
5. In Undocumented Changes, select a time window and confirm the demonstration evidence reference time is visible in Environment Details.
6. In Ask ARCA, use a suggested question, then a follow-up. In mock mode the response is deterministic and makes no paid request.
7. Open **Metrics** and confirm filters, assessment records, performance traces, feedback, and CSV export render. A fresh clone may initially have no local telemetry because `logs\` is intentionally excluded from GitHub.

## Demo dropdown verification

Use `DEMO_VERIFIED_CASES.txt` as the presentation walkthrough. The dropdown records come from `data\demo_catalog.json`; selections populate inputs without modifying source evidence.

## Known limitations

- Evidence is synthetic and local; there are no live Azure, AWS, ServiceNow, or Snowflake connectors.
- Conversation checkpoints use in-process memory and do not survive a restart.
- LLM availability depends on local credentials, network/proxy/TLS configuration, model access, and organization policy.
- ARCA recommendations do not approve PIM access, submit changes, or execute infrastructure modifications.
- Snowflake integration is proposed, not implemented.

## Troubleshooting

- **Port already in use:** add `--server.port 8502` and open the corresponding URL.
- **Import failure:** confirm the activated interpreter is `.venv`, then reinstall `requirements.txt` and run `pip check`.
- **No metrics:** exercise a workflow first; local runtime telemetry is generated under `logs\`.
- **OpenAI connection failure:** verify `.env` loading, proxy environment variables, DNS, TLS certificates, and firewall access without printing the key.
- **Bedrock unavailable:** verify approved AWS authentication, region, model access, and `BEDROCK_MODEL_ID`.
- **PowerShell activation blocked:** call `.\.venv\Scripts\python.exe` directly.

