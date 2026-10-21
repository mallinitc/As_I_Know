# ARCA — Agentic Risk & Change Assurance

## Portable LLM configuration

ARCA keeps its OpenAI/Bedrock/mock model selection separate from the Azure/AWS evidence-provider adapters. Copy `.env.example` to `.env`; `.env` is already excluded by `.gitignore`. Replace the API-key placeholder only in your local `.env` and never commit it.

Personal laptop / OpenAI:

```ini
LLM_PROVIDER=openai
OPENAI_API_KEY=your-real-key-here
OPENAI_MODEL=gpt-5-mini
OPENAI_TIMEOUT_SECONDS=45
OPENAI_MAX_RETRIES=1
OPENAI_REASONING_EFFORT=minimal
OPENAI_MAX_OUTPUT_TOKENS=1200
ARCA_CHANGE_EXTRACTOR=openai
ARCA_INVESTIGATION_MODEL=openai
```

Office laptop / Amazon Bedrock:

```ini
LLM_PROVIDER=bedrock
ARCA_CHANGE_EXTRACTOR=bedrock
ARCA_INVESTIGATION_MODEL=bedrock
AWS_PROFILE=your-approved-profile
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=your-approved-model-id
```

Offline tests and demonstrations:

```ini
LLM_PROVIDER=mock
ARCA_CHANGE_EXTRACTOR=mock
ARCA_INVESTIGATION_MODEL=mock
ARCA_MODE=mock
```

Restart Streamlit after changing `.env`. Models interpret text, select validated read-only investigation tools, and write evidence-backed narratives. Deterministic policy code remains responsible for mandatory-field, RBAC, scope, identity, duration, and evidence-correlation controls. A model cannot approve PIM access or execute infrastructure changes. Automated tests use mock mode or injected clients and make no paid calls.

**Working prototype:** synthetic ServiceNow-style change requests → change validation → provider-specific privilege comparison → cloud activity correlation → conditional LangGraph investigation → Streamlit dashboard. The dashboard defaults to synthetic Azure PIM/RBAC and Activity Log evidence, with the original AWS IAM and CloudTrail-shaped starter dataset preserved. Optional Bedrock narrative via Boto3.

## Synthetic evidence providers

- **Azure (dashboard default):** 20 ServiceNow changes, 20 PIM requests, 20 RBAC assignments, 9 role definitions, 30 resources, and 100 Activity Log events under `data/azure/`.
- **AWS:** the original `changes.json`, `access_requests.json`, and `events.json` datasets and their original analysis behavior.

All identities, tenant/subscription identifiers, resource names, timestamps, and evidence are fictional. No Azure SDK or live cloud connection is used. Regenerate the deterministic Azure fixtures with:

```cmd
.venv\Scripts\python.exe ARCA2_starter\scripts\generate_azure_data.py
```

## Conversational investigation (Agent 5)

The **AI Investigation Assistant** dashboard section uses a checkpointed LangGraph workflow and seven local, read-only evidence tools. It supports access troubleshooting, undocumented-change review, resource modification review, PIM queries, and multi-turn actor/approval follow-ups.

The default planner is a clearly labeled deterministic mock parser and never invokes Bedrock. Optional Bedrock planning is isolated behind these settings:

```cmd
set ARCA_INVESTIGATION_MODEL=bedrock
set AWS_PROFILE=arca-dev
set AWS_REGION=us-east-1
set BEDROCK_MODEL_ID=your-approved-model-id
```

If Bedrock configuration or access is unavailable, the assistant reports that limitation and does not claim model reasoning occurred. Tool execution remains local and read-only.

## Windows quick start

```cmd
cd /d D:\Usecase\ARCA2
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q
streamlit run app.py
```

Default `ARCA_MODE=mock` does not use AWS or incur inference costs. To invoke Bedrock, configure approved AWS credentials and set:

```cmd
set ARCA_MODE=bedrock
set AWS_PROFILE=arca-dev
set AWS_REGION=us-east-1
set BEDROCK_MODEL_ID=amazon.nova-lite-v1:0
streamlit run app.py
```

Set model ID to one your account can invoke; availability in model catalog does not prove authorization. Costs are incurred for inference.

## Portability

Copy these files to the office device or commit to an approved Git repository. Never commit `.env`, `.venv`, credentials or actual enterprise data. Use synthetic records only.

## IMPORTANT limitations

This is a hackathon demonstrator, not a security enforcement system. The IAM comparator only handles curated action/resource examples, not all IAM conditions, deny semantics, permission boundaries, SCPs, session policies, resource policies or ABAC. The Azure comparator is likewise illustrative: it does not calculate transitive group access, deny assignments, management-group inheritance, custom conditions, data-plane authorization, or complete effective access. Activity events alone do not prove an intended property-level change was applied. Storage access-loss signals identify only a possible relationship supported by nearby synthetic evidence. No automatic access approvals or infrastructure modifications occur. The unmatched activity list represents lack of correlation with *available* approved records, not proof of an unauthorized change.
