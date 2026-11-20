# ARCA Observability demo

Telemetry is stored as append-only JSONL in `logs/`, which is excluded from Git. Timestamps are UTC. Model content is not recorded unless `ARCA_LOG_LLM_CONTENT=true`; metadata, usage, timing, and sanitized error categories remain available without content capture.

## Reproducible demonstration

1. Open **Change Lifecycle**, run a Stage 1 validation, then open **Observability** and confirm the assessment count increased.
2. Click **Improve Draft** once. Confirm one LLM usage record appears (or a sanitized failed call if the configured provider is unavailable).
3. Expand **Assessment feedback**, choose **Incorrect**, enter an optional reason, and submit it. Confirm Human Feedback updates. Feedback never changes the underlying decision.
4. Run **Stage 2 — Validate Privileges** and click **Validate All PIM Requests**. Confirm Stage 2 analytics update.
5. In Observability, select **Last 24 hours** and apply any environment/provider/model filters.
6. Use the CSV download controls for filtered API calls, assessments, feedback, or traces.

Cost values are ARCA estimates calculated with `config/model_pricing.json`; they are not actual provider invoices. Unknown models show unknown cost rather than an invented value. Do not place secrets in the pricing file or telemetry metadata.
