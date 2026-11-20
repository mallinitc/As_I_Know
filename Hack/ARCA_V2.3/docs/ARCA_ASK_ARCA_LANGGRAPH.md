# Ask ARCA — LangGraph Investigation Architecture

## Graph and state

`InvestigationAgent` builds and compiles this checkpointed graph in `arca/investigation/agent.py:34-44`:

```mermaid
flowchart LR
    START --> PLAN[plan node]
    PLAN --> INVESTIGATE[investigate node]
    INVESTIGATE --> END
```

`ConversationState` (`:17-28`) carries messages, query, intent, validated parameters, context, tool results, response, evidence references, status, direct response, and planner error. `MemorySaver` persists state by the `thread_id` passed to `ask()` (`:53-55`). Resetting creates a new thread identifier rather than mutating an immutable checkpoint.

## Planning

The plan node (`:61-69`) first routes obvious greetings, capability questions, known cloud explanations, general cloud questions, and unrelated questions with `classify_conversation()`. Investigation requests go to the selected adapter:

- `MockModelAdapter`: deterministic parser for supported demonstration scenarios.
- `OpenAIModelAdapter`: shared OpenAI provider with structured `InvestigationPlan` output.
- `BedrockModelAdapter`: shared Bedrock provider with the same schema.

`InvestigationParameters` forbids extra fields and accepts only identity, role, scope, start, end, environment, and resource query. Time phrases are resolved against the evidence reference time.

## Tool routing

Tool selection is implemented as explicit Python branches in `_investigate()` (`agent.py:107-177`), not as arbitrary model code execution.

| Tool | Method | Preserved evidence |
|---|---|---|
| Resource search | `find_resources()` | Resource IDs, subscription, group, type |
| Resource details | `get_resource_details()` | Original resource record |
| Activity | `get_activity_logs()` | Event IDs, UTC timestamps, actors, operations |
| Assignments | `get_role_assignments()` | Assignment IDs, principals, roles, scopes, windows |
| PIM | `get_pim_requests()` | Request IDs, principals, roles, schedules, change refs |
| Changes | `get_change_records()` | Change IDs, implementers, windows, expected operations |
| Unmatched activity | `find_undocumented_changes()` | Provider-correlation results and query window |

Implementations and module-level wrappers are in `arca/investigation/tools.py:25-171`. Every tool returns `{tool, count, items, query}` and is read-only.

## Conversation behavior

- Resource queries attempt exact name/ID matching, context references such as “this resource,” then type hints (`agent.py:71-89`). Ambiguity triggers clarification, never first-match fabrication.
- Access troubleshooting also requires an identity (`:149-151`).
- Resource investigations retrieve activity and associated approved changes (`:153-176`).
- Access investigations additionally retrieve assignments and PIM evidence; role-removal and storage-firewall changes are described only as possible causes (`:157-171,215-222`).
- “Who performed those changes?” and “Were they approved?” reuse `previous_findings` (`:179-202`). Approval correlation requires window, principal, operation, and resource alignment.
- Evidence references are extracted from original IDs (`:91-99`).

## Response generation

Deterministic evidence summaries are always available. If the selected adapter exposes `respond()` (currently OpenAI), `_finish()` may request an evidence-grounded narrative after tools return (`:204-212`). Failure preserves deterministic output and explicitly states that model narration was unavailable. General cloud questions may use an optional model without claiming that local evidence was inspected.

## Current limitations

- The graph itself is linear; intent routing occurs inside the investigate node.
- In-process `MemorySaver` state is not durable across application restarts or shared across workers.
- Tools operate on local demonstration evidence, not live Azure/AWS APIs.
- Root-cause conclusions remain qualified without resource-state, sign-in, and broader diagnostic evidence.

