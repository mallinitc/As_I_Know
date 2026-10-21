from datetime import datetime, timedelta, timezone

import pytest

from arca.providers import azure, aws
from arca.time_filters import (
    TIME_RANGES,
    calculate_time_window,
    evidence_reference_time,
    filter_evidence_window,
    parse_utc,
    undocumented_window_status,
    utc_label,
)


NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def test_time_filter_public_import_contract():
    assert callable(evidence_reference_time)
    assert callable(filter_evidence_window)
    assert callable(undocumented_window_status)
    assert callable(utc_label)
    assert callable(calculate_time_window)
    assert callable(parse_utc)
    assert list(TIME_RANGES) == ["Last 24 Hours", "Last 2 Days", "Last 7 Days", "Last 15 Days", "Last 30 Days"]


def iso(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def event(provider, identifier, timestamp):
    if provider == "azure":
        return {"event_data_id": identifier, "event_timestamp": iso(timestamp)}
    return {"eventID": identifier, "eventTime": iso(timestamp)}


@pytest.mark.parametrize("provider", ["azure", "aws"])
@pytest.mark.parametrize("selection,expected", [
    ("Last 24 Hours", 1),
    ("Last 2 Days", 2),
    ("Last 7 Days", 3),
    ("Last 15 Days", 4),
    ("Last 30 Days", 5),
])
def test_all_time_ranges(provider, selection, expected):
    ages = [timedelta(hours=12), timedelta(hours=36), timedelta(days=3),
            timedelta(days=10), timedelta(days=20), timedelta(days=31)]
    events = [event(provider, f"event-{index}", NOW - age) for index, age in enumerate(ages)]
    result = filter_evidence_window(provider, [], events, selection, now=NOW)
    assert len(result["events"]) == expected
    assert result["end"] == NOW
    assert result["start"] == NOW - TIME_RANGES[selection]


@pytest.mark.parametrize("provider", ["azure", "aws"])
def test_utc_boundaries_are_inclusive_and_future_events_are_excluded(provider):
    start = NOW - timedelta(days=7)
    events = [
        event(provider, "at-start", start),
        event(provider, "at-end", NOW),
        event(provider, "before-start", start - timedelta(seconds=1)),
        event(provider, "future", NOW + timedelta(seconds=1)),
    ]
    result = filter_evidence_window(provider, [], events, "Last 7 Days", now=NOW)
    key = "event_data_id" if provider == "azure" else "eventID"
    assert {item[key] for item in result["events"]} == {"at-start", "at-end"}
    assert result["start"].tzinfo == timezone.utc
    assert result["end"].tzinfo == timezone.utc


@pytest.mark.parametrize("provider", ["azure", "aws"])
def test_only_approved_changes_overlapping_the_window_are_retained(provider):
    changes = [
        {"change_id": "overlaps-start", "start": iso(NOW - timedelta(days=8)), "end": iso(NOW - timedelta(days=7))},
        {"change_id": "inside", "start": iso(NOW - timedelta(days=2)), "end": iso(NOW - timedelta(days=1))},
        {"change_id": "ends-before", "start": iso(NOW - timedelta(days=9)), "end": iso(NOW - timedelta(days=8))},
        {"change_id": "starts-future", "start": iso(NOW + timedelta(seconds=1)), "end": iso(NOW + timedelta(hours=1))},
    ]
    result = filter_evidence_window(provider, changes, [], "Last 7 Days", now=NOW)
    assert {item["change_id"] for item in result["changes"]} == {"overlaps-start", "inside"}


def test_filter_is_applied_before_aws_undocumented_correlation():
    bundle = aws.load_bundle()
    current = datetime(2026, 10, 20, 10, 20, tzinfo=timezone.utc)
    window = filter_evidence_window("aws", bundle["changes"], bundle["events"], "Last 24 Hours", now=current)
    results = aws.find_unmatched(window["changes"], window["events"], bundle)
    assert all(item["event_id"] in {event["eventID"] for event in window["events"]} for item in results)


def test_filter_is_applied_before_azure_undocumented_correlation():
    bundle = azure.load_bundle()
    current = datetime(2026, 10, 25, 13, 0, tzinfo=timezone.utc)
    window = filter_evidence_window("azure", bundle["changes"], bundle["events"], "Last 24 Hours", now=current)
    results = azure.find_unmatched(window["changes"], window["events"], bundle)
    assert results
    assert all(item["event_id"] in {event["event_data_id"] for event in window["events"]} for item in results)
    assert all(window["start"] <= datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")) <= window["end"] for item in results)
