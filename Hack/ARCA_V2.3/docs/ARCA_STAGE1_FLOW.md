# ARCA Stage 1 — Change Validation

## Purpose

Stage 1 independently validates a change draft before submission. It does not require PIM or execution evidence and never saves a pasted draft into synthetic datasets.

## UI-to-result flow

```mermaid
flowchart TD
    UI[app.py Stage 1] --> MODE{Input mode}
    MODE --> EXIST[Existing Change]
    MODE --> PASTE[Paste Change Details]
    EXIST --> ECE[extract_existing_change]
    PASTE --> EXT[get_extractor().extract]
    EXT -->|mock| MX[MockChangeExtractor]
    EXT -->|openai/bedrock| LX[LLMChangeExtractor + Pydantic]
    ECE --> VAL[validate_draft]
    MX --> VAL
    LX --> VAL
    VAL --> RESULT[DraftValidationResult]
    RESULT --> IMP[Improve Draft]
    IMP --> BASE[Deterministic ImprovedChangeDraft]
    BASE -. optional language-only refinement .-> LLM[OpenAI/Bedrock]
    BASE --> EDIT[Editable controls]
    LLM --> EDIT
    EDIT --> REVAL[draft_to_extracted + validate_draft]
    EDIT --> COPY[servicenow_text]
```

## Source trace

| Step | Source |
|---|---|
| Stage navigation and input controls | `app.py:380-434` |
| Existing-record conversion | `arca/change_extraction.py:117-133` |
| Extractor selection | `arca/change_extraction.py:110-114` |
| Deterministic parser | `arca/change_extraction.py:41-69` |
| Provider-neutral LLM extraction | `arca/change_extraction.py:91-107` |
| Validation policy loader | `arca/change_validation.py:13-14` |
| Deterministic validator | `arca/change_validation.py:24-63` |
| Smart-draft refinement/cache | `arca/smart_draft.py:108-167` |
| Finding-to-field mapping | `arca/smart_draft.py:170-195` |
| Revalidation conversion | `arca/smart_draft.py:198-214` |
| Copy-ready output | `arca/smart_draft.py:217-231` |

## Validation contract

`ExtractedChange` and `DraftValidationResult` are Pydantic models in `arca/change_models.py`. Mandatory fields come from `config/change_validation_policy.json`: purpose, business justification, environment, target resources, implementer, implementation tasks, start/end, expected outcome, validation steps, rollback plan, and risk/impact. Roles, scopes, and expected operations are recommended.

`validate_draft()`:

1. Emits `INCOMPLETE` issues for missing mandatory values.
2. Parses timestamps deterministically and requires timezone information.
3. Emits `INCONSISTENT` when start is not earlier than end.
4. Flags configured vague phrases as `AMBIGUOUS`.
5. Produces field, reason, severity, category, correction, completeness, questions, and readiness.

Status precedence is `INCONSISTENT`, `AMBIGUOUS`, `INCOMPLETE`, `MANUAL_REVIEW_REQUIRED`, then `VALID`. `ready_for_submission` is true only for `VALID`.

## Improve Draft safeguards

`improve_draft_with_status()` always creates a deterministic baseline first. Optional LLM refinement receives prose-only fields, is cached by provider/model settings and payload hash, and cannot fill a field that was empty in the baseline. Technical identifiers remain outside the language-refinement payload. On timeout/error the baseline is retained and the UI must not claim model generation.

Revalidate calls only `draft_to_extracted()` and `validate_draft()`; it does not call an LLM. Field findings map existing issues to editable controls, including the end-time message “End time must be later than start time.”

## Implemented limitations

- Mock extraction recognizes explicit labelled facts; it is not semantic LLM reasoning.
- Existing synthetic change descriptions may not contain all pre-submission mandatory details, so an existing record may still be incomplete under the draft policy.
- “Copy Draft” creates text; it does not write to ServiceNow or the evidence files.

