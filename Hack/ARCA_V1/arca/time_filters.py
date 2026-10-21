"""UTC time-window filtering for provider evidence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

TIME_RANGES = {
    "Last 24 Hours": timedelta(hours=24),
    "Last 2 Days": timedelta(days=2),
    "Last 7 Days": timedelta(days=7),
    "Last 15 Days": timedelta(days=15),
    "Last 30 Days": timedelta(days=30),
}


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Evidence timestamps must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def utc_label(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def evidence_reference_time(provider: str, events: list[dict], mode: str = "demonstration",
                            now: datetime | None = None) -> datetime:
    """Return the shared investigation clock for historical or live evidence."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if mode == "live":
        return current
    if mode != "demonstration":
        raise ValueError(f"Unsupported evidence mode: {mode}")
    if not events:
        return current
    provider = provider.lower()
    if provider == "azure":
        values = [event["event_timestamp"] for event in events]
    elif provider == "aws":
        values = [event["eventTime"] for event in events]
    elif provider == "snowflake":
        values = [event["start_time"] for event in events]
    else:
        raise ValueError(f"Unsupported evidence provider: {provider}")
    return max(parse_utc(value) for value in values)


def calculate_time_window(selection: str, reference_time: datetime) -> tuple[datetime, datetime]:
    if selection not in TIME_RANGES:
        raise ValueError(f"Unsupported time range: {selection}")
    end = reference_time.astimezone(timezone.utc)
    return end - TIME_RANGES[selection], end


def undocumented_window_status(events: list[dict] | None, findings: list[dict] | None) -> str:
    if events is None or findings is None:
        return "INSUFFICIENT_EVIDENCE"
    if not events:
        return "NO_ACTIVITY"
    if findings:
        return "UNMATCHED_CHANGES"
    return "NO_UNMATCHED_CHANGES"


def filter_evidence_window(provider: str, changes: list[dict], events: list[dict], selection: str,
                           now: datetime | None = None, mode: str = "live",
                           reference_time: datetime | None = None) -> dict:
    """Filter raw activity and overlapping approved changes before correlation.

    Window boundaries are inclusive. The original records are returned unchanged.
    """
    reference = reference_time or evidence_reference_time(provider, events, mode=mode, now=now)
    start, end = calculate_time_window(selection, reference)
    provider = provider.lower()
    if provider == "azure":
        event_timestamp = lambda event: event["event_timestamp"]
    elif provider == "aws":
        event_timestamp = lambda event: event["eventTime"]
    elif provider == "snowflake":
        event_timestamp = lambda event: event["start_time"]
    else:
        raise ValueError(f"Unsupported evidence provider: {provider}")

    filtered_events = [event for event in events if start <= parse_utc(event_timestamp(event)) <= end]
    filtered_changes = []
    for change in changes:
        try:
            if parse_utc(change["start"]) <= end and parse_utc(change["end"]) >= start:
                filtered_changes.append(change)
        except (KeyError, TypeError, ValueError):
            continue
    return {"selection": selection, "start": start, "end": end, "reference_time": reference,
            "mode": mode, "changes": filtered_changes, "events": filtered_events}
