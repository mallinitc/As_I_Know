# ARCA Code Walkthrough

Line references describe the implementation inspected on 2026-10-21.

## Start at the UI

`app.py` is the Streamlit entry point. Theme/hero helpers begin at lines 33 and 101. Provider selection is at line 345, primary ARCA/Metrics navigation at 353, Metrics dispatch at 372, and ARCA feature tabs at 376.

| User action | UI location | Downstream implementation |
|---|---:|---|
| Validate existing change | `app.py:390-401` | `extract_existing_change()` → `validate_draft()` |
| Validate pasted draft | `app.py:404-422` | `get_extractor().extract()` → `validate_draft()` |
| Improve Draft | `app.py:434-451` | `improve_draft_with_status()`; cached optional LLM refinement |
| Revalidate / Copy | `render_smart_draft()` at `app.py:221` | `draft_to_extracted()`, `validate_draft()`, `servicenow_text()` |
| Retrieve PIM by change | `app.py:480` | `find_pim_requests_by_change()` |
| Search PIM by user | `app.py:488-490` | `find_pim_requests()` and `activation_state()` |
| Parse pasted PIM | `app.py:500-502` | `parse_pim_records()` |
| Validate all PIM | `app.py:520-524` | `assess_pim()` + `assess_combined_pim()` |
| Verify execution | `app.py:544-549` | provider `evaluate_stage3()` |
| Run lifecycle | `app.py:557-569` | `build().invoke(state)` |
| Undocumented changes | `app.py:590-603` | shared window utilities → provider `find_unmatched()` |
| Ask ARCA | `app.py:633-706` | `InvestigationAgent.ask()`; same path for custom/suggested/follow-up |

## Models and deterministic rules

`arca/change_models.py` contains `ExpectedOperation`, `ExtractedChange`, `ValidationIssue`, `DraftValidationResult`, and `ImprovedChangeDraft`. Stage 1 policy is loaded by `arca/change_validation.py:load_validation_policy()` and applied by `validate_draft()`.

`arca/pim_validation.py` contains `ParsedPIMRecord`, `PIMAssessment`, and `CombinedPIMAssessment`. Parsing (`:120-173`) is isolated from validation (`:261-423`). Role actions come only from the local role-definition catalog. Scope and role suitability are evaluated separately.

## Provider path

`arca/providers/__init__.py:get_provider()` returns the Azure or AWS module. Each module implements `load_bundle`, `access_for_change`, three stage evaluators, and `find_unmatched`. Azure additionally normalizes provider-neutral evidence in `arca/providers/azure.py:39-80`. Provider selection is carried in UI and graph state; LLM selection is independent.

## Lifecycle graph excerpt

```python
g.add_edge(START, "change")
g.add_conditional_edges("change", next_step,
                        {"privilege": "privilege", "summary": "summary"})
g.add_edge("privilege", "audit")
g.add_conditional_edges("audit", after_audit,
                        {"investigate": "investigate", "summary": "summary"})
```

This is `arca/workflow.py:36-40`. Invalid Stage 1 bypasses privilege/audit. Stage 3 deviations enter Agent 4; all paths end in summary.

## Ask ARCA excerpt

```python
graph.add_node("plan", self._plan)
graph.add_node("investigate", self._investigate)
graph.add_edge(START, "plan")
graph.add_edge("plan", "investigate")
graph.add_edge("investigate", END)
```

This is `arca/investigation/agent.py:39-43`. The planner schema is in `investigation/models.py:19-33`; read-only tools are in `investigation/tools.py:25-171`. Tool dispatch is explicit code in `_investigate()`, and session context contains selected resource, subscription, group, identity, window, and previous findings.

## LLM calls

The shared factory is `arca/llm_provider.py:get_llm_provider()` (`:149-155`). OpenAI uses `responses.parse()` (`:58`) and Bedrock uses `converse()` (`:114`). Structured results are Pydantic validated. Call sites are:

- Stage 1 extraction: `arca/change_extraction.py:103`.
- Smart Draft prose refinement: `arca/smart_draft.py:115-123`.
- Free-text PIM extraction when configured: `arca/pim_validation.py:120-152`.
- Lifecycle narrative: `arca/bedrock.py:explain()`.
- Ask ARCA planning and optional OpenAI narration: `arca/investigation/models.py:123-186`.

Deterministic validators remain authoritative. Automated tests must select mock/fake clients and make no paid calls.

## Time, provenance, and observability

`arca/time_filters.py:15-70` centralizes UTC parsing, reference time, windows, and event filtering. Demonstration mode anchors to evidence; live mode uses current UTC. `arca/observability.py` records sanitized telemetry and performance; `arca/observability_ui.py:render_observability()` applies global filters and exports.

## Data walkthrough

Azure `load_bundle()` (`arca/providers/azure.py:24-33`) joins six JSON collections by stable IDs. For example, `CHG-AZ-2021` is associated with three PIM request IDs through structured references; role definitions resolve action coverage; resource IDs resolve scope; activity events retain `event_data_id` and UTC timestamp. AWS loads the original three JSON files and preserves its existing core logic.

## Safe extension points

- Add an evidence provider by implementing the provider module contract and schemas.
- Add an LLM by implementing the small parse interface; never put approval logic in it.
- Add a read-only investigation tool, then explicitly route it and add evidence-reference extraction.
- Add a durable checkpoint store without changing conversation state semantics.
- Add Snowflake behind a repository interface as described in `ARCA_SNOWFLAKE_INTEGRATION.md`.

