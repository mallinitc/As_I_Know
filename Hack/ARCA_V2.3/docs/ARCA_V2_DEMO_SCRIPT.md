# ARCA V2 Enterprise Demo Script

Target duration: 8–10 minutes. Before presenting, start the API on port 8000 and frontend on port 3000, then confirm `/api/v1/health` reports `healthy`.

## 1. Executive Overview

Open **Overview**. Point out the environment and time filters, risk distribution, environment health, and recent findings. State explicitly that this page uses centralized **Synthetic demonstration data** and does not represent live cloud activity.

## 2. AWS Change Assurance

Choose **AWS** in the global environment selector and open **Change Assurance**.

1. Stage 1: select `01 - Valid Change` and run change validation.
2. Stage 2: select `11 - Explicit Deny` (`AWS-ACCESS-11`, change `CHG1010`) and run access validation.

Expected: the first case is `VALID`; the second is `EXPLICITLY_DENIED`, with the policy evidence ID and explicit-deny explanation retained.

## 3. Azure PIM/RBAC Validation

Choose **Azure**, remain on **Change Assurance**, and select a verified Stage 2 example such as `AZ-ACCESS-01`.

Expected: ARCA shows the approved change, PIM assessments, RBAC coverage, evidence references, and a deterministic recommendation. Explain that ARCA recommends; it never approves or activates access.

## 4. Snowflake Change Assurance

Choose **Snowflake**, open **Change Assurance**, select `SF-UNIFIED-01` / `CHG-SF-1007`, and run validation using its populated demo timestamp.

Expected: change quality, window, and requested-role assessments render from the native FastAPI result. The verified overall outcome is `PASS`.

## 5. Execution Assurance Deviation

Choose **Azure**, open **Execution Assurance**, and select `AZ-EXEC-09 — Wrong Implementer`.

Expected: the timeline preserves `az-event-0009`; findings include `UNAUTHORIZED_IMPLEMENTER` and the associated role/scope concern. Emphasize that audit activity does not independently prove final resource state.

## 6. Cross-Environment Risk Investigation

Open **Risk Investigations** and select `RISK-10 — Multi-environment deviations`, then run the investigation.

Expected: AWS, Azure, and Snowflake appear in the environment distribution. Findings and evidence retain provider identity, confidence, timestamps, and original evidence IDs. Possible risks remain distinct from confirmed deviations.

## 7. Ask ARCA

Open **Ask ARCA** and select `ASK-10 — Cross-environment risk summary`, then click **Ask ARCA**.

Expected: the response identifies Mock Agent Mode, shows the resolved cross-environment intent, invokes the registered Agent 4 tool, and displays actual completed trace steps, findings, and evidence references. Then select `ASK-14 — Ambiguous user question` to demonstrate a clarification request instead of an invented identity.

Close by noting that V2 is read-only, synthetic, provider-aware, and deterministic. AI mode is not operational without an approved provider configuration, and no cloud or paid-model calls occur during this demonstration.
