# ARCA V1 / V2 Functional Parity

Verified 22 October 2026. V1 was inspected read-only; V2 is a native FastAPI/Next.js implementation and does not import V1 modules.

| Feature | V1 Behavior | V2 Current Behavior | Gap | Required Correction | Verification |
|---|---|---|---|---|---|
| OpenAI initialization | Official `OpenAI` SDK; key/model from environment | Backend-only `httpx` gateway; explicit HTTPS Responses API contract; `.env` loaded by FastAPI | Different client, but compatible protocol | Keep gateway; explicitly honor standard proxy/certificate environment settings | Mock contract test verifies `/v1/responses`, model, structured schema, and no key leakage |
| Request execution | `responses.parse`, bounded timeout/retries | Strict JSON schema, Pydantic parsing, bounded timeout, zero automatic paid retries | Error category was too generic | Classify proxy, DNS, TLS, timeout, and OS policy failures | Mock failure tests pass |
| Environment and network | `python-dotenv`; SDK environment transport | `python-dotenv`; explicit endpoint/model/key; `httpx(trust_env=True)` | None after explicit transport setting | Preserve HTTPS verification and environment proxy support | Configuration tests pass; key never emitted |
| Live connectivity | Previously worked on an earlier workstation/network state | DNS resolves, but this host blocks TCP 443 with `WinError 10013` | Outbound socket policy, before TLS/auth/API parsing | Report `NETWORK_BLOCKED`; do not weaken TLS or retry billable calls | DNS/TCP/HTTPS diagnostic completed without API request |
| Change-quality validation | Deterministic required-field and consistency controls | Native provider-specific deterministic A1 controls | None | Preserve authoritative decisions | Provider regression tests pass |
| Missing-field guidance | Field-level explanation and correction guidance | A1 renders finding, why-it-matters, and correction cards | None | Preserve | Browser tooling covers missing guidance |
| Improved Draft | Source-supported deterministic template plus optional model prose refinement | Same evidence-preserving split; unknown values stay empty | None | Preserve advisory disclosure | Draft tests prove model cannot fill unknowns or alter technical facts |
| Editable fields | Streamlit session fields retained corrections | Controlled React fields retain independent edits | Needed regression coverage | Added pure immutable update helper/test | Frontend unit tests pass |
| Consolidated description | Locally formatted ServiceNow-compatible text | Previously direct copy only | Missing preview/generation step | Added **Generate Complete Change Description**, scrollable/selectable preview, explicit unknown placeholders | Unit and browser checks |
| Clipboard | Local copy action | Previously copied directly from editor | No preview-bound copy confirmation | Copy icon now copies generated document and briefly shows **Copied** | Browser check; no model call |
| Usage telemetry | JSONL model usage, duration, status, and cost estimate | Previously response totals only | No uniform A1–A5 execution metrics | Added provider/model/status/calls/tokens/model and total duration/cost contract | Backend metric tests and UI contract tests pass |
| Token usage | Input/output/cached/reasoning/total from provider metadata | Responses usage normalized; absent usage remains unavailable | Needed cached/reasoning preservation | Extended typed usage schema | Mock Responses tests pass |
| Cost estimate | Explicit pricing catalog; unavailable when unknown | Versioned pricing catalog and status | Catalog lacked explicit version | Added schema/catalog version; no inferred usage | Known/unknown pricing tests pass |
| Latency | Request and parsing durations | Per-call model duration and total deterministic+AI duration | Missing display | Added compact AI Execution Details panel | A1–A5 responses carry metrics |
| API call count | Logged per invocation | Previously implicit | A5 planning/synthesis could not be audited separately | Record operations independently and sum once | A5 test asserts two calls in order |
| Deterministic fallback | Retained original extracted/validated result | Retains deterministic result and discloses model failure | None | Preserve sanitized status and zero fabricated metrics | Timeout/fallback tests pass |

## Connectivity conclusion

The configured endpoint, Responses protocol, model, `.env` loading, structured-output schema, proxy inheritance, timeout, and TLS verification are valid in mocked tests. On the current host, `api.openai.com` resolves, no proxy override is configured, and TCP connection attempts to port 443 fail with Windows socket error 10013. The failing layer is the workstation/network outbound policy, not authentication, TLS validation, or response parsing. No live request was attempted because the API endpoint was not reachable.
