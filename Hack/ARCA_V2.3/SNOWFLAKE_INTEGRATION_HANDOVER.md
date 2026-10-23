# ARCA Snowflake Integration Handover

## Current implementation

ARCA is a Streamlit application whose entry point is `app.py`. Its Azure/AWS evidence-provider selection is independent of its mock/OpenAI/Bedrock LLM selection. Current evidence is local and synthetic; Snowflake is not installed or connected.

The UI exposes five assurance capabilities:

1. Stage 1 change validation and Smart Draft editing.
2. Stage 2 PIM/access validation and combined least-privilege coverage.
3. Stage 3 execution-evidence verification.
4. Automated deviation and undocumented-change investigation.
5. Ask ARCA conversational, read-only investigation.

It also exposes Metrics/Observability for assessments, LLM usage/cost, timings, errors, and feedback.

## Azure evidence architecture

`arca/providers/azure.py:load_bundle()` loads:

- `data/azure/servicenow_changes.json`
- `data/azure/pim_requests.json`
- `data/azure/rbac_assignments.json`
- `data/azure/role_definitions.json`
- `data/azure/resources.json`
- `data/azure/activity_logs.json`

The same module implements provider-specific Stage 1/2/3 evaluation and unmatched-event correlation. `arca/providers/schemas.py` defines provider-neutral change, privilege, resource, and activity evidence shapes while preserving original identifiers and UTC timestamps. Azure RBAC evaluation remains distinct from the AWS logic in `arca/providers/aws.py`.

## LangGraph implementation

`arca/workflow.py:build()` compiles the lifecycle graph:

`START -> change -> [privilege -> audit -> optional investigate] -> summary -> END`

Stage 1 validity gates Stage 2. A Stage 3 deviation gates the automated investigation node. The provider travels in workflow state and selects the appropriate adapter.

`arca/investigation/agent.py:InvestigationAgent` compiles the Ask ARCA graph:

`START -> plan -> investigate -> END`

It uses LangGraph `MemorySaver` keyed by thread ID. Model output is constrained by Pydantic `InvestigationPlan`; explicit Python branches select read-only tools. Ambiguous resources and missing identities trigger clarification.

## LLM provider configuration

`arca/llm_provider.py` supplies `mock`, `openai`, and `bedrock` adapters. OpenAI uses structured Responses parsing; Bedrock uses Converse; mock mode is deterministic. LLMs may extract or improve prose and plan investigations, but deterministic policy code decides completeness, RBAC coverage, scope, duration, and evidence correlation.

Configuration comes from `.env` via python-dotenv. `.env` must remain local; `.env.example` contains placeholders only.

## Ask ARCA tools

`arca/investigation/tools.py:InvestigationTools` implements:

- `find_resources()`
- `get_resource_details()`
- `get_activity_logs()`
- `get_role_assignments()`
- `get_pim_requests()`
- `get_change_records()`
- `find_undocumented_changes()`

Each returns structured read-only results with original evidence identifiers. Shared time-window behavior is in `arca/time_filters.py`.

## Observability

`arca/observability.py` writes local JSONL records for LLM calls, assessments, feedback, errors, and performance spans. It normalizes provider token usage and estimates cost from `config/model_pricing.json`. `arca/observability_ui.py` filters and renders these records and produces CSV exports. Runtime logs are intentionally excluded from GitHub because they are local operational data.

## Proposed Snowflake integration

Snowflake should be introduced behind an evidence-repository interface, not embedded directly in Streamlit, provider evaluators, or LangGraph nodes. The current module names above are implemented; the repository modules below are proposed and do not yet exist:

- `arca/repositories/base.py` — repository protocol.
- `arca/repositories/json_repository.py` — current JSON behavior behind the protocol.
- `arca/repositories/snowflake_repository.py` — parameterized, read-only Snowflake queries.

The protocol should provide filtered changes, privileges, assignments, role definitions, resources, and activity. Both repositories must return the current evidence shapes so Azure/AWS evaluators and investigation tools remain unchanged.

Recommended Snowflake entities are `CHANGE_EVIDENCE`, `EXPECTED_OPERATION`, `PRIVILEGE_REQUEST`, `ROLE_ASSIGNMENT`, `ROLE_DEFINITION`, `RESOURCE_EVIDENCE`, and `ACTIVITY_EVIDENCE`. Preserve source IDs, use UTC `TIMESTAMP_TZ`, retain raw records in `VARIANT`, and add ingestion/source-mode metadata separately.

## Ask ARCA routing with Snowflake

Keep intent planning unchanged. Select the evidence repository from environment/session configuration before constructing `InvestigationTools`. The tools should query Azure evidence, Snowflake evidence, or an explicitly scoped union; model output must not construct SQL.

Routing requirements:

1. Validate tenant, provider, resource, identity, and UTC time-window parameters.
2. Use bound SQL parameters and a read-only Snowflake role.
3. Surface provenance and reference time in every result.
4. Ask for clarification when Azure and Snowflake produce ambiguous resource matches.
5. Keep provider-specific correlation in the Azure/AWS adapters.
6. Never silently combine different principals or environments.
7. Preserve deterministic fallback when an LLM is unavailable.

## Migration plan

1. Put existing JSON loading behind a repository protocol without changing outcomes.
2. Add contract tests using the current synthetic records.
3. Create Snowflake tables/views and ingest those same fixtures.
4. Implement parameterized queries and compare evidence IDs/results with JSON.
5. Add configuration and health diagnostics.
6. Pilot read-only live ingestion under an approved service role.
7. Only then enable mixed-source Ask ARCA investigations.

This approach preserves all Azure functionality and separates storage changes from assurance rules, provider semantics, orchestration, and presentation.
