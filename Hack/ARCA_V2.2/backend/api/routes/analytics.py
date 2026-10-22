from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response

from backend.auth import feedback_capability, principal_from

from backend.schemas.analytics import AnalyticsAccessResponse, AnalyticsExecutionResponse, AnalyticsOverviewResponse, AnalyticsRisksResponse, EvaluationHistoryResponse, EvaluationRunRequest, EvaluationRunResponse, FeedbackCreateRequest, FeedbackLatestResponse, FeedbackRecord, ObservabilityResponse
from backend.services.analytics import AnalyticsService
from backend.services.evaluation import export_run, get_run, history as evaluation_history, latest_run, start_evaluation
from backend.services.observability import csv_export, latest_feedback, observability_summary, submit_feedback


router = APIRouter(prefix="/api/v1/analytics", tags=["Executive Analytics"])
service = AnalyticsService()


def _filters(provider: str, days: int | None, severity: str) -> tuple[str, int | None, str]:
    if provider not in {"all", "aws", "azure", "snowflake"}: raise HTTPException(422, "Unsupported provider filter.")
    if days not in {None, 7, 15, 30}: raise HTTPException(422, "Time period must be 7, 15, 30, or omitted for all available evidence.")
    if severity not in {"all", "critical", "high", "medium", "low"}: raise HTTPException(422, "Unsupported severity filter.")
    return provider, days, severity


@router.get("/overview", response_model=AnalyticsOverviewResponse)
def overview(provider: str = Query("all"), days: int | None = Query(None), severity: str = Query("all")) -> AnalyticsOverviewResponse:
    return AnalyticsOverviewResponse.model_validate(service.overview(*_filters(provider, days, severity)))


@router.get("/risks", response_model=AnalyticsRisksResponse)
def risks(provider: str = Query("all"), days: int | None = Query(None), severity: str = Query("all")) -> AnalyticsRisksResponse:
    return AnalyticsRisksResponse.model_validate(service.risks(*_filters(provider, days, severity)))


@router.get("/execution", response_model=AnalyticsExecutionResponse)
def execution(provider: str = Query("all"), days: int | None = Query(None), severity: str = Query("all")) -> AnalyticsExecutionResponse:
    return AnalyticsExecutionResponse.model_validate(service.execution(*_filters(provider, days, severity)))


@router.get("/access", response_model=AnalyticsAccessResponse)
def access(provider: str = Query("all"), days: int | None = Query(None), severity: str = Query("all")) -> AnalyticsAccessResponse:
    return AnalyticsAccessResponse.model_validate(service.access(*_filters(provider, days, severity)))


@router.get("/observability", response_model=ObservabilityResponse)
def observability(days: int = Query(30), environment: str = Query("all"), agent: str = Query("all"), provider: str = Query("all"), model: str = Query("all"), status: str = Query("all")) -> ObservabilityResponse:
    if days not in {1, 2, 5, 7, 15, 30}: raise HTTPException(422, "Unsupported observability time period.")
    if environment not in {"all", "aws", "azure", "snowflake"}: raise HTTPException(422, "Unsupported environment filter.")
    if agent not in {"all", "A1", "A2", "A3", "A4", "A5"}: raise HTTPException(422, "Unsupported agent filter.")
    if any(len(value) > 300 for value in (provider, model, status)): raise HTTPException(422, "Filter value is too long.")
    return ObservabilityResponse.model_validate(observability_summary(days=days, environment=environment, agent=agent, provider=provider, model=model, status=status))


@router.post("/feedback", response_model=FeedbackRecord)
def feedback(payload: FeedbackCreateRequest, request: Request) -> FeedbackRecord:
    principal = principal_from(request)
    capability = feedback_capability(payload.stage)
    if capability is None or not principal.allows(capability):
        raise HTTPException(403, "This persona cannot submit feedback for the requested stage.")
    data = payload.model_dump()
    data["user_identity"] = principal.identity
    data["user_role"] = principal.role
    return FeedbackRecord.model_validate(submit_feedback(data))


@router.get("/feedback/latest", response_model=FeedbackLatestResponse)
def feedback_latest(request: Request, assessment_id: str = Query(min_length=3, max_length=240), stage: str = Query(pattern="^A[1-5]$")) -> FeedbackLatestResponse:
    principal = principal_from(request)
    capability = feedback_capability(stage)
    if capability is None or not principal.allows(capability):
        raise HTTPException(403, "This persona cannot view feedback for the requested stage.")
    item = latest_feedback(assessment_id)
    return FeedbackLatestResponse(item=FeedbackRecord.model_validate(item) if item else None)


@router.get("/observability/export/{record_type}")
def export_observability(record_type: str, days: int = Query(30), environment: str = Query("all"), agent: str = Query("all"), provider: str = Query("all"), model: str = Query("all"), status: str = Query("all")) -> Response:
    if record_type not in {"executions", "feedback"}: raise HTTPException(404, "Unknown observability export.")
    data = observability_summary(days=days, environment=environment, agent=agent, provider=provider, model=model, status=status)
    rows = data["recent_executions" if record_type == "executions" else "recent_feedback"]
    return Response(csv_export(rows), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="arca_{record_type}.csv"'})


@router.get("/evaluation/latest")
def evaluation_latest() -> dict:
    return latest_run() or {"status": "not_run", "evaluation_mode": "deterministic_and_mocked_llm", "live_llm_calls": 0}


@router.get("/evaluation/history", response_model=EvaluationHistoryResponse)
def evaluation_runs() -> EvaluationHistoryResponse:
    return EvaluationHistoryResponse(items=evaluation_history())


@router.post("/evaluation/runs", response_model=EvaluationRunResponse, status_code=202)
def run_evaluation(_payload: EvaluationRunRequest) -> EvaluationRunResponse:
    try:
        return EvaluationRunResponse.model_validate(start_evaluation())
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/evaluation/runs/{run_id}")
def evaluation_run(run_id: str) -> dict:
    if not run_id.startswith("eval-") or len(run_id) > 40:
        raise HTTPException(404, "Unknown evaluation run.")
    result = get_run(run_id)
    if not result:
        raise HTTPException(404, "Unknown evaluation run.")
    return result


@router.get("/evaluation/runs/{run_id}/export/{export_format}")
def evaluation_export(run_id: str, export_format: str) -> Response:
    if export_format not in {"csv", "json"}:
        raise HTTPException(404, "Unknown evaluation export format.")
    result = get_run(run_id)
    if not result or result.get("status") != "completed":
        raise HTTPException(404, "Completed evaluation run not found.")
    body, media_type = export_run(result, export_format)
    return Response(body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="arca_{run_id}.{export_format}"'})
