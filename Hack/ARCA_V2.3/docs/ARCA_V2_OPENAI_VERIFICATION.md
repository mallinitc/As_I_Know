# ARCA V2 OpenAI Verification

Verification date: 2026-10-22

## Configuration

- ARCA V2 uses its native gateway with provider `openai` and configured model `gpt-5-mini`; the live API identified `gpt-5-mini-2025-08-07`.
- The standard OpenAI endpoint uses a 45-second timeout, minimal reasoning effort, a 1,200-token output limit, and no gateway retries.
- The local `.env` is ignored. No credential is present in source, frontend output, tests, logs, or this document.
- Frontend port 3000 and FastAPI port 8000 were healthy. The capability endpoint reported LLM Assisted mode available.

## Live Agent 5 result

Verified scenario `ASK-07` asked for unapproved Snowflake role grants in the last 30 days. The first local attempt was blocked before reaching OpenAI by the restricted process network context (`WinError 10013`) and returned zero tokens. FastAPI was restarted with normal network access; one end-to-end retry then made exactly two model requests: planning and synthesis.

- Planning: OpenAI returned a valid structured intent and allowlisted tool plan.
- Tool execution: `find_potentially_unapproved_activity` and `retrieve_supporting_evidence` completed.
- Deterministic result: 27 findings and 22 evidence references; findings, evidence, and overall status exactly matched the deterministic baseline.
- Synthesis: OpenAI executed and returned Pydantic-valid structured output.
- Final validation: failed because the synthesis returned no acceptable evidence citation. ARCA correctly returned `deterministic_fallback` with `llm_status=invalid_response`; no synthesis was presented as successful.
- Usage for planning plus synthesis: 5,888 input tokens, 692 output tokens, 6,580 total tokens.

The integration defect was a contract mismatch: the structured schema allowed an empty `evidence_citations` array while runtime validation required at least one citation when evidence existed. V2.15E temporarily tightened citation presence and membership; the later hackathon policy below supersedes that requirement while retaining deterministic evidence safety.

## Five-agent UI verification

The existing `scripts/browser_validate_v2.mjs` now has a targeted final-verification mode. Five browser assertions passed:

- Agents 1-4 rendered completed LLM-assisted analysis using mocked HTTP fixtures, with model, status, deterministic output, recommendations, and evidence visible. These fixtures made no model calls.
- Agent 5 rendered the observed citation-validation fallback state using a non-billable fixture: model identifier, invalid-response status, deterministic findings, evidence references, allowlisted tool trace, and error disclosure were visible; no model-generated explanation was shown.

The browser could not display a successful real Agent 5 synthesis because no validated live synthesis response existed. Machine-readable results are in `docs/demo/browser-llm-verification-results.json`.

## Security verification

- Keys remain server-side and do not appear in frontend contracts, OpenAPI, logs, tests, or documentation.
- Model-selected tools are checked against the fixed read-only allowlist; arbitrary tools and generated SQL execution remain prohibited.
- Deterministic findings are computed independently and cannot be changed by model output.
- Evidence citations are optional. Exact tool-returned identifiers are preserved; unknown identifiers are filtered and disclosed rather than treated as evidence.
- Prompts treat user questions and evidence as untrusted data and do not expose raw chain-of-thought.
- Invalid synthesis is explicitly labeled as deterministic fallback, never silent AI success.

## Tests

- Affected backend tests: 24 passed.
- Frontend API tests: 9 passed.
- Browser checks: 5 passed.
- Python compilation, dependency check, browser-script syntax, TypeScript, ESLint, and Next.js production build: passed.

## Remaining limitation

No live request was required after adopting optional citations. Advisory-claim validation is deliberately conservative and deterministic; generated prose remains non-authoritative and cannot alter findings, severities, confidence, evidence, or overall status.

## V2.15E synthesis-only verification

V2.15E reused the deterministic `ASK-07` investigation context and made one direct synthesis request; planning was not repeated and no automatic retry occurred. The request used configured model `gpt-5-mini`, 27 unchanged findings, the unchanged deterministic status, and 22 supplied evidence IDs.

The model returned structured synthesis output with citations, but at least one citation was not an exact member of the supplied evidence-reference set. ARCA rejected the response before it could be presented as successful. Findings, severities, confidence, and overall status remained unchanged. The final response was therefore rejected, and no model prose or invalid citation was persisted as an accepted Agent 5 answer.

The remaining contract gap was that `minItems: 1` required a citation but still allowed arbitrary strings. The evidence-bearing Pydantic schema now dynamically restricts citation items to the exact supplied ID enum. Offline tests verify both a valid member and rejection of an invented ID. A non-billable Agent 5-only browser fixture using an actual deterministic evidence ID confirmed that the UI renders the completed model status, explanation, citation, deterministic findings, and tool trace.

V2.15E results:

- Live synthesis calls: 1.
- Live citation validation: rejected safely.
- Targeted citation tests: 4 passed.
- Full affected gateway and Agent 5 tests: 25 passed.
- Dependency check and browser-script syntax: passed.
- Agent 5-only browser assertion: 1 passed using a clearly identified fixture; no additional model call was made.
- The exact-ID schema was subsequently replaced by the optional-citation policy below.

## Optional citation policy

For the hackathon, Agent 5 citations are optional metadata rather than a prerequisite for advisory synthesis. The synthesis schema permits an empty citation list. The prompt directs the model to cite only exact supplied IDs or return no citations. The response validator preserves valid IDs, removes invalid IDs, deduplicates mixed lists, and records a limitation when filtering occurs. Citation mismatch alone no longer rejects an otherwise acceptable explanation.

AI explanations are prefixed `Advisory AI explanation:`. A deterministic claim validator rejects unsupported compliance or authorization statements, new confirmed findings, and severity classifications absent from the deterministic findings. All authoritative findings, evidence records, classifications, confidence, and status remain untouched. Non-citation synthesis errors continue to return the existing explicit deterministic fallback.

Verification used mocked provider responses only: valid citations, no citations, invalid citations, mixed lists, unsupported claims, and deterministic immutability are covered. The affected Agent 5 suite passes with no paid API calls.
