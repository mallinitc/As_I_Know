# ARCA V2 Demo Readiness

Validated: 22 October 2026 (Asia/Calcutta workstation; all evidence timestamps are UTC).

## Architecture summary

ARCA V2 is a native two-tier application. The Next.js/React/TypeScript frontend runs on `127.0.0.1:3000` and calls the FastAPI service on `127.0.0.1:8000`. FastAPI provides provider-specific AWS, Azure, and Snowflake validation and execution engines, deterministic Agent 4 risk discovery, and Agent 5 deterministic or approved-LLM-assisted orchestration. Provider repositories read isolated synthetic datasets. No V1 modules, Streamlit runtime, live cloud SDK calls, or cloud mutations were used. Approved, bounded OpenAI verification calls are documented in `ARCA_V2_OPENAI_VERIFICATION.md`.

## Component status

| Component | Status | Data source |
|---|---|---|
| Overview | Ready | Native V2 analytics aggregation over provider fixtures and computed assurance findings |
| Change Assurance | Ready | Native V2 APIs and provider datasets |
| Execution Assurance | Ready | Native V2 APIs and audit evidence |
| Risk Investigations | Ready | Agent 4 over AWS, Azure, and Snowflake evidence |
| Ask ARCA | Ready; Deterministic default | Optional approved LLM planning/synthesis over deterministic allowlisted tools |
| Analytics | Ready | Native V2 risk, execution, access, trend, and evidence-coverage APIs |
| API docs | Ready | FastAPI OpenAPI at `http://127.0.0.1:8000/docs` |

## Five-agent UI mapping

The sidebar and Overview now expose ARCA's original operating model as five independently identifiable workspaces:

- Agent 1 — Change Quality: `/agents/change-quality` for deterministic change completeness and clarity validation.
- Agent 2 — Access Intelligence: `/agents/access-intelligence` for AWS IAM, Azure PIM/RBAC, and Snowflake role assessment.
- Agent 3 — Execution Assurance: `/execution-assurance` for approved-versus-observed execution correlation.
- Agent 4 — Risk Investigation: `/risk-investigations` for potentially undocumented or suspicious activity.
- Agent 5 — Ask ARCA: `/ask-arca` with explicit Deterministic and availability-gated LLM Assisted modes using the same allowlisted tools.

Every agent page identifies its number, responsibility, selected environment, execution mode, and position in the five-agent workflow. Workflow navigation does not imply that another agent has completed. The legacy `/change-assurance` route redirects to Agent 1 for compatibility.

AWS and Azure use their existing independent change-quality and access-validation APIs. Snowflake continues to use its single unified Change & Access Validation endpoint; both Agent 1 and Agent 2 views disclose that one shared backend assessment ran and emphasize the relevant result sections without fabricating separate executions.

## Verified workflows

- AWS: change quality, IAM access, change execution, and principal activity.
- Azure: change quality, PIM/RBAC validation, change execution, and user activity.
- Snowflake: unified change/access validation, change execution, and user activity.
- Agent 4: provider-specific and cross-environment investigation; identity, role, resource, time, and severity filters.
- Agent 5: provider routing, change/user/role/unauthorized/cross-environment intents, clarification, evidence preservation, and actual execution traces.

Live HTTP validation returned provider-correct schemas, catalog timestamps, and evidence references without backend errors. Cross-environment evidence retained `aws`, `azure`, or `snowflake` provenance. The OpenAI gateway is configured and LLM Assisted mode is available; deterministic mode remains the default.

## Analytics contract

The versioned endpoints are `GET /api/v1/analytics/overview`, `/risks`, `/execution`, and `/access`. Each accepts `provider=all|aws|azure|snowflake`, optional `days=7|15|30` (omission means all available evidence), and `severity=all|critical|high|medium|low`. Time windows are anchored to the latest applicable synthetic evidence timestamp returned in response metadata, not the workstation clock. Provider plus change ID identifies a unique change; provider-aware deterministic finding IDs prevent duplicate scenario evidence from inflating totals. Compliance excludes review, unknown, and insufficient-evidence outcomes from its explicit denominator. Evidence coverage reports linked execution evidence and never treats absent events as proof of compliance. Every response includes metric definitions, limitations, and the `Synthetic Demo Dataset` label.

## Interactive browser validation

Installed Google Chrome was exercised through the DevTools protocol without adding a browser dependency. The V2.16 run passed 81 assertions across Overview, Agents 1–5, and Analytics. Viewports checked were 1440×900, 1366×768, 768×1024, and 390×844. Coverage included compact five-agent navigation, Agent 1 missing-field guidance and editable drafts, contextual Ask ARCA autorun, Agent 1 and Agent 2 AWS/Azure/Snowflake scenarios, environment switching, Agent 3 execution, Agent 4 investigations, Agent 5 response disclosure, analytics, stale-result clearing, offline recovery, disabled processing controls, mobile navigation, and page-level overflow.

The browser run found one application defect: the frontend was served from `127.0.0.1:3000`, but the default API CORS allowlist contained only `localhost:3000`. The explicit allowlist now includes both loopback origins; wildcard origins remain rejected. V2.15D added five targeted LLM-display checks: Agents 1-4 rendered mocked completed-analysis fixtures, while Agent 5 rendered the correctly labeled citation-validation fallback. Results are stored in `docs/demo/browser-llm-verification-results.json`.

## Scenario catalogs

- AWS Change Assurance: `AWS-CHANGE-01` through `AWS-CHANGE-05`, `AWS-ACCESS-06` through `AWS-ACCESS-21` (21 scenarios).
- AWS Execution Assurance: `AWS-EXEC-01` through `AWS-EXEC-20`.
- Azure Change Assurance: 50 `AZ-CHANGE-*` / `AZ-ACCESS-*` scenarios covering 25 changes.
- Azure Execution Assurance: `AZ-EXEC-01` through `AZ-EXEC-30`.
- Snowflake Change Assurance: 25 `SF-UNIFIED-*` scenarios.
- Snowflake Execution Assurance: 20 `SF-POST-*` scenarios.
- Agent 4: `RISK-01` through `RISK-15`.
- Agent 5: `ASK-01` through `ASK-15`.

Recommended anchor cases: `AWS-ACCESS-11` (explicit deny), `AZ-EXEC-09` (wrong implementer), `SF-UNIFIED-01` (appropriate Snowflake access), `RISK-10` (cross-environment), and `ASK-10` (cross-environment natural-language investigation).

## Startup instructions

Backend terminal:

```bat
cd /d D:\Usecase\ARCA2\ARCA_V2
scripts\start_api_v2.bat
```

Frontend terminal:

```bat
cd /d D:\Usecase\ARCA2\ARCA_V2\frontend
npm run dev
```

Open `http://127.0.0.1:3000`. The API must remain on port 8000. If either port is occupied, identify the process and confirm it is an obsolete ARCA V2 instance before stopping it; never redirect silently.

## Verification results

- Backend V2.15A targeted suite: 39 tests passed across gateway contracts/failures, API safety, Agent 4, and Agent 5 regression behavior. The earlier 86-test provider smoke suite also passed before this isolated milestone.
- Frontend API-client and mode-state unit tests: 8 passed, including unavailable/available LLM switching, analytics filtering, and malformed-response handling.
- TypeScript: passed (`tsc --noEmit`).
- ESLint: passed.
- Next.js production build: passed; all nine application routes generated, including both explicit Agent 1/2 routes and the compatibility redirect route.
- Python dependencies: `pip check` passed.
- Runtime: Overview and Analytics returned HTTP 200; all 80 provider/time/severity combinations reconciled Overview finding totals with Analytics risk totals. Health, provider APIs, Agent 4, and Agent 5 regression tests passed.
- Browser: 81/81 interactive assertions passed; desktop, laptop, tablet, and mobile layouts were exercised with no page-level overflow.

## Security and reliability

- Pydantic validates versioned request contracts and API errors suppress internal traces.
- Agent 5 uses an explicit eight-tool allowlist and identifies the actual execution and LLM status.
- Agent 5 now supports two explicit execution modes: `Deterministic` (default, no external model call) and `LLM Assisted` (available only with a complete approved-provider configuration). LLM planning is limited to five calls from the existing eight-tool read-only allowlist; deterministic services remain authoritative for all findings.
- The provider-neutral gateway supports standard `openai`, the distinct `azure_openai` deployment contract, and a configured `openai_compatible` Responses-style enterprise endpoint. It uses HTTPS only, bounded timeouts, no automatic paid-request retries, Pydantic-validated plans/answers, prompt trust boundaries, evidence-citation checks, and sanitized errors. Keys remain backend-only and are never returned to Next.js.
- Synthetic evidence is read-only; no backend module imports live cloud SDKs or performs cloud commands.
- `.env`, credential files, keys, logs, and archives are excluded by `.gitignore`; the local V2 `.env` is runtime-only and is not exposed to the frontend.
- This directory contains no Git metadata, so tracked-file history could not be inspected locally.

## Known limitations

- Analytics is calculated from synthetic fixtures and deterministic native V2 results; it is not live cloud telemetry.
- Time filters use the latest applicable synthetic evidence timestamp, so 7/15/30-day views remain reproducible and can emphasize providers with later fixture dates.
- Effective-permission and final resource-state coverage remain unavailable where the fixture evidence cannot prove them.
- Results tables intentionally use contained horizontal scrolling at narrow widths; no page-level overflow was observed.
- Agent 5 LLM Assisted mode is configured with OpenAI. Live V2.15D planning and tool execution passed; synthesis executed but was rejected by final citation validation. The schema/prompt alignment is fixed and offline-tested, but a successful post-fix live synthesis remains outstanding because the two-call ceiling was reached.
- V2.16 used its single authorized Azure Agent 1 model call. Deterministic validation returned `INCOMPLETE`, but AI assistance returned `provider_error` because TCP 443 connectivity to `api.openai.com` was unavailable. The deterministic result remained intact and the UI disclosed that no AI analysis was generated.
- Synthetic audit evidence supports demonstration correlation, not complete effective-permission or final-resource-state proof.
- Risk findings can be numerous because the catalog intentionally contains repeated synthetic deviation patterns; unique provider evidence IDs prevent duplicate records from being counted twice per investigation.

## Recommended demo sequence

Use the companion `ARCA_V2_DEMO_SCRIPT.md`: Overview, AWS change/access, Azure PIM/RBAC, Snowflake validation, one execution deviation, cross-environment Agent 4, then Agent 5. Keep the synthetic-evidence and execution-mode labels visible.

Final UI readiness: ready for deterministic hackathon demonstration. LLM Assisted release readiness remains conditional on one successful post-fix Agent 5 live synthesis verification.

## V2.18 functional parity and telemetry

The V1 comparison is recorded in `ARCA_V1_V2_FUNCTIONAL_PARITY.md`. Agent 1 now completes the full local draft workflow: guidance, source-supported draft preparation, independent field edits, consolidated ServiceNow-style description generation, scrollable/selectable preview, and copy confirmation. Consolidation never invokes a model, and missing values remain explicit placeholders. Selecting another provider/change clears the stale draft and generated description.

All A1–A5 deterministic and assisted responses now expose a compact **AI Execution Details** contract: agent, execution mode, provider, actual model, invocation status, per-call operation/status/duration, measured input/output/total usage, model duration, total analysis duration, and estimated cost. Agent 5 planning and synthesis are separate calls and are counted once each. Pricing comes from versioned `config/model_pricing.json`; unknown pricing or absent provider usage is shown as unavailable rather than estimated. Prompt content and credentials are excluded.

Current OpenAI status is **NETWORK_BLOCKED**. DNS resolution succeeds, while direct TCP 443 and HTTPS fail locally with `WinError 10013`, before TLS, authentication, or API parsing. The gateway retains HTTPS verification, explicitly honors standard proxy/certificate environment configuration, performs no automatic paid retries, and returns a sanitized `network_blocked` status while preserving deterministic output. No live request was attempted during V2.18.

V2.18 verification passed 138 backend tests, 15 frontend tests, TypeScript, ESLint, dependency checks, and the Next.js production build. The updated Chrome DevTools browser run passed 85/85 assertions, including edited-field preservation, explicit unknown placeholders, local consolidation with no API call, copy confirmation, stale-output clearing on scenario change, and the A1 execution-details panel.

## LLM Assisted configuration and verification

Copy the `ARCA_LLM_*` placeholders from `.env.example` into the local backend environment. Set `ARCA_LLM_ENABLED=true`, choose `openai`, `azure_openai`, or `openai_compatible`, and supply the approved HTTPS endpoint when required, model/deployment identifier, backend-only API key, and Azure API version when applicable. Restart FastAPI, then check `GET /api/v1/agents/ask-arca/capabilities`: `llm.available` must be `true` and credentials must not appear. In Ask ARCA, select **LLM Assisted**, run a non-sensitive verified scenario, and confirm the response shows the provider/model, `llm_status=completed`, deterministic findings, actual tool trace, and evidence-cited model explanation. If final validation fails, ARCA labels the deterministic fallback explicitly.

### Agents 1-4 advisory responsibilities

- Agent 1 interprets change intent, ambiguity, missing context, and contradictions; deterministic required-field, approval, metadata, and window controls remain authoritative.
- Agent 2 explains access suitability, scope, duration, and evidence-supported least-privilege alternatives; native AWS IAM, Azure PIM/RBAC, and Snowflake grants remain authoritative.
- Agent 3 explains expected-versus-observed deviations and suggests follow-up investigation; deterministic event matching, confidence, windows, and compliance outcomes cannot be changed by the model.
- Agent 4 summarizes correlated findings and investigation priorities without asserting unsupported causality or malicious intent; original findings, severities, and evidence remain unchanged.

Every Agent 1-4 request defaults to `deterministic`. `llm_assisted` first runs the same deterministic engine and then makes one structured advisory call through the V2.15A gateway. The optional `ai_analysis` response is separate from deterministic fields and exposes actual invocation status, configured model, observations, recommendations, validated evidence references, and limitations. Snowflake keeps one combined Agent 1/2 model call and discloses its shared assessment.

## V2.16 restored agent experience

- **A1 — Change Quality:** pre-change validation does not require audit logs. Findings explain what is missing, why it matters, and the recommended correction. Improved Draft builds an editable ServiceNow-style draft from the selected source record, keeps unknown values empty, optionally refines supported prose through the existing gateway, and copies locally without changing the authoritative record.
- **A2 — Access Intelligence:** remains an independent pre-execution access assessment. Snowflake continues using its existing shared A1/A2 contract rather than a duplicate engine.
- **A3 — Execution Assurance:** remains post-implementation and correlates approved intent with audit evidence.
- **A4 — Undocumented Changes:** discovers potentially undocumented activity while preserving confirmed, possible, and evidence-insufficient distinctions.
- **A5 — Ask ARCA:** contextual actions from A1–A4 and the Executive Dashboard store structured context, populate a suggested question, and autorun it once. Refreshes do not repeat the request. Responses use Executive Summary, What Was Found, Why It Matters, Recommended Next Steps, and expandable Technical Evidence.

Fast retrieval keeps a 10-second frontend timeout. LLM-assisted operations use configurable `NEXT_PUBLIC_ARCA_LLM_TIMEOUT_MS` (55 seconds by default); the backend uses `ARCA_LLM_TIMEOUT_SECONDS` (45 seconds in the verified environment). Gateway requests have no automatic paid retries. Model failure preserves deterministic output and is never presented as AI success.

Only agent-relevant result fields are sent. Strings, record counts, nesting, and total prompt size are bounded; `ARCA_LLM_INPUT_MAX_CHARS` defaults to 30000. Descriptions and audit records are explicitly treated as untrusted content. Pydantic rejects malformed output; citations are optional, valid supplied IDs are preserved, and invalid IDs are filtered. No credentials or environment variables enter prompts, and gateway failure leaves deterministic results intact. Known limitations: generated prose is advisory, verified role alternatives depend on available catalogs, and incomplete evidence requires explicit uncertainty.
