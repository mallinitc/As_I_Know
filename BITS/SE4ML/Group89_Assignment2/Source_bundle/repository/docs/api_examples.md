<!-- Managed by Notebook 9 -->
# API Examples

Set the backend address:
```bash
export API_BASE_URL=http://127.0.0.1:8000
```

## Health
```bash
curl --fail "$API_BASE_URL/health"
```

## Model information and metrics
```bash
curl --fail "$API_BASE_URL/api/v1/model/info"
curl --fail "$API_BASE_URL/api/v1/model/metrics"
```

## Complete analysis
The authoritative multipart image field is `image`; `question` is optional.
```bash
curl --fail -X POST "$API_BASE_URL/api/v1/analyze-complete" \
  -H "Accept: application/json" \
  -F "image=@reports/streamlit_demo_input.png;type=image/png" \
  -F "question=What does the threshold result mean?"
```

Preserve the returned `prediction_id` for follow-up and retrieval.

## Grounded follow-up question
```bash
curl --fail -X POST "$API_BASE_URL/api/v1/question/answer" \
  -H "Content-Type: application/json" \
  -d '{"prediction_id":"REPLACE_WITH_UUID","question":"What does this result mean?"}'
```

The client cannot submit probabilities, findings, thresholds, image evidence, or any other grounding context.

## Stored prediction
```bash
curl --fail "$API_BASE_URL/api/v1/predictions/REPLACE_WITH_UUID"
```

## Operational and LLMOps metrics
```bash
curl --fail "$API_BASE_URL/api/v1/llmops/metrics"
```

## Controlled errors
Error responses expose the versioned `APIErrorResponse` fields and must be handled as structured JSON. Do not display backend tracebacks, internal paths, or raw exception objects to interface users.
