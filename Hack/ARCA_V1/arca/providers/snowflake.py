"""Snowflake Stage 1 adapter over local synthetic change evidence only."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from arca.paths import data_dir
from arca.time_filters import parse_utc
from arca.snowflake_stage2 import assess_stage2, assess_unified_stage1
from arca.snowflake_post_implementation import investigate_change, investigate_user, persist_investigation_result
from arca.snowflake_post_implementation import correlate_query, normalize_query

DISPLAY_NAME = "Snowflake"
EVIDENCE_SOURCE = "Synthetic Snowflake change-management evidence"
IMPLEMENTATION_STATUS = "mock_unified_stage1"
DATA = data_dir("snowflake")


def load_demo_scenarios(path: Path | None = None, change_ids: set[str] | None = None) -> list[dict]:
    """Load and validate the dedicated scenario registry with actionable failures."""
    source = path or DATA / "demo_scenarios.json"
    if not source.is_file():
        raise FileNotFoundError(f"Snowflake demo scenario file is missing: {source}. Restore data/snowflake/demo_scenarios.json.")
    try:
        scenarios = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Snowflake demo scenario file contains invalid JSON at line {exc.lineno}: {source}") from exc
    if not isinstance(scenarios, list):
        raise ValueError(f"Snowflake demo scenario file must contain a JSON array: {source}")
    required = {"scenario_id", "scenario_name", "description", "change_id", "evaluation_timestamp", "expected_check_outcomes"}
    for scenario in scenarios:
        missing = required - scenario.keys()
        if missing: raise ValueError(f"Snowflake demo scenario {scenario.get('scenario_id', '<unknown>')} is missing {sorted(missing)}")
        if change_ids is not None and scenario["change_id"] not in change_ids:
            raise ValueError(f"Snowflake demo scenario {scenario['scenario_id']} references unknown change {scenario['change_id']}")
        parse_utc(scenario["evaluation_timestamp"])
    if len({item["scenario_id"] for item in scenarios}) != len(scenarios):
        raise ValueError("Snowflake demo scenario IDs must be unique")
    return scenarios


def load_post_implementation_scenarios(path: Path | None = None, change_ids: set[str] | None = None) -> list[dict]:
    source = path or DATA / "post_implementation_scenarios.json"
    if not source.is_file():
        raise FileNotFoundError(f"Snowflake post-implementation scenario file is missing: {source}")
    try:
        scenarios = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Snowflake post-implementation scenarios contain invalid JSON at line {exc.lineno}: {source}") from exc
    required = {"scenario_id", "scenario_name", "evaluation_timestamp", "investigation_mode", "expected_findings", "evidence_query_ids"}
    if not isinstance(scenarios, list):
        raise ValueError("Snowflake post-implementation scenario registry must be a JSON array")
    for scenario in scenarios:
        missing = required - scenario.keys()
        if missing: raise ValueError(f"Snowflake post-implementation scenario {scenario.get('scenario_id', '<unknown>')} is missing {sorted(missing)}")
        if scenario["investigation_mode"] not in {"change", "user"}:
            raise ValueError(f"Snowflake post-implementation scenario {scenario['scenario_id']} has invalid investigation_mode")
        if scenario["investigation_mode"] == "change" and change_ids is not None and scenario.get("change_id") not in change_ids:
            raise ValueError(f"Snowflake post-implementation scenario {scenario['scenario_id']} references unknown change {scenario.get('change_id')}")
        parse_utc(scenario["evaluation_timestamp"])
    if len({item["scenario_id"] for item in scenarios}) != len(scenarios):
        raise ValueError("Snowflake post-implementation scenario IDs must be unique")
    return scenarios


def load_investigation_scenarios(path: Path | None = None, change_ids: set[str] | None = None) -> list[dict]:
    source = path or DATA / "investigation_scenarios.json"
    if not source.is_file(): raise FileNotFoundError(f"Snowflake investigation scenario file is missing: {source}")
    try: scenarios = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc: raise ValueError(f"Snowflake investigation scenarios contain invalid JSON at line {exc.lineno}: {source}") from exc
    required = {"scenario_id", "scenario_name", "investigation_prompt", "expected_intent", "evaluation_timestamp", "expected_finding_categories"}
    for scenario in scenarios:
        missing = required - scenario.keys()
        if missing: raise ValueError(f"Snowflake investigation scenario {scenario.get('scenario_id', '<unknown>')} is missing {sorted(missing)}")
        if scenario.get("change_id") and change_ids is not None and scenario["change_id"] not in change_ids:
            raise ValueError(f"Snowflake investigation scenario {scenario['scenario_id']} references unknown change {scenario['change_id']}")
        parse_utc(scenario["evaluation_timestamp"])
    return scenarios


def load_bundle():
    changes = json.loads((DATA / "changes.json").read_text(encoding="utf-8"))
    objects_path = DATA / "objects.json"
    objects = json.loads(objects_path.read_text(encoding="utf-8")) if objects_path.exists() else []
    change_ids = {item["change_id"] for item in changes}
    scenarios = load_demo_scenarios(change_ids=change_ids)
    query_history = _load("query_history.json")
    return {"changes": changes, "access_requests": [], "events": query_history, "resources": objects,
            "demo_scenarios": scenarios,
            "post_implementation_scenarios": load_post_implementation_scenarios(change_ids=change_ids),
            "investigation_scenarios": load_investigation_scenarios(change_ids=change_ids),
            "query_history": query_history, "access_history": _load("access_history.json"),
            "login_history": _load("login_history.json"), "users": _load("users.json"),
            "grants_to_users": _load("grants_to_users.json"), "grants_to_roles": _load("grants_to_roles.json"),
            "roles": json.loads((DATA / "roles.json").read_text(encoding="utf-8")),
            "role_grants": json.loads((DATA / "role_grants.json").read_text(encoding="utf-8")),
            "object_grants": json.loads((DATA / "object_grants.json").read_text(encoding="utf-8")),
            "role_definitions": [], "rbac_assignments": []}


def _load(filename: str):
    return json.loads((DATA / filename).read_text(encoding="utf-8"))


def evaluate_post_implementation_by_change(change_id: str, context=None, **kwargs):
    persist = kwargs.pop("persist_output", False)
    result = investigate_change(change_id, context or load_bundle(), **kwargs)
    if persist: result["output_path"] = persist_investigation_result(result)
    return result


def evaluate_post_implementation_by_user(identifier: str, context=None, **kwargs):
    persist = kwargs.pop("persist_output", False)
    result = investigate_user(identifier, context or load_bundle(), **kwargs)
    if persist: result["output_path"] = persist_investigation_result(result)
    return result


def access_for_change(bundle, change_id):
    return {}


def normalize_change(change):
    """Map a Snowflake record to ARCA's canonical change evidence shape."""
    implementer = change.get("implementer", "")
    if isinstance(implementer, dict):
        actor_id = implementer.get("principal_id", "")
        actor_name = implementer.get("principal_name", "")
    else:
        actor_id = actor_name = implementer
    return {
        "provider": "snowflake", "evidence_id": change.get("change_id", ""),
        "change_id": change.get("change_id", ""), "environment": change.get("environment", ""),
        "actor_id": actor_id, "actor_name": actor_name,
        "window_start": change.get("start", ""), "window_end": change.get("end", ""),
        "description": change.get("description", ""),
        "expected": [{"operation": item.get("operation", ""), "resource_id": item.get("resource_id", "")}
                     for item in change.get("expected", [])],
        "raw": change,
    }


def evaluate_change_quality(change):
    """Apply deterministic Snowflake change completeness and consistency controls."""
    missing = []
    issues = []

    def require(field, value, reason):
        if not value:
            missing.append(field)
            issues.append({"field": field, "severity": "ERROR", "reason": reason})

    require("change_id", change.get("change_id"), "Change ID is required.")
    require("description", change.get("description"), "Change description is required.")
    require("environment", change.get("environment"), "Environment is required.")
    require("implementer", change.get("implementer"), "Implementer is required.")
    require("start", change.get("start"), "Start timestamp is required.")
    require("end", change.get("end"), "End timestamp is required.")
    expected = change.get("expected") or []
    require("expected", expected, "At least one expected operation is required.")
    if str(change.get("state", "")).strip().lower() != "approved":
        missing.append("approved_state")
        issues.append({"field": "state", "severity": "ERROR", "reason": "Change must be approved before implementation."})

    start = end = None
    if change.get("start"):
        try: start = parse_utc(change["start"])
        except (TypeError, ValueError):
            missing.append("valid_start_timestamp")
            issues.append({"field": "start", "severity": "ERROR", "reason": "Start timestamp must be valid ISO 8601 with an explicit timezone."})
    if change.get("end"):
        try: end = parse_utc(change["end"])
        except (TypeError, ValueError):
            missing.append("valid_end_timestamp")
            issues.append({"field": "end", "severity": "ERROR", "reason": "End timestamp must be valid ISO 8601 with an explicit timezone."})
    if start and end and start >= end:
        missing.append("valid_change_window")
        issues.append({"field": "change_window", "severity": "ERROR", "reason": "End timestamp must be later than start timestamp."})

    for index, item in enumerate(expected):
        if not item.get("operation"):
            missing.append(f"expected[{index}].operation")
            issues.append({"field": "expected", "severity": "ERROR", "reason": f"Expected operation {index + 1} is missing its operation name."})
        if not item.get("resource_id"):
            missing.append(f"expected[{index}].resource_id")
            issues.append({"field": "expected", "severity": "ERROR", "reason": f"Expected operation {index + 1} is missing its target object."})

    return {"status": "VALID" if not issues else "NEEDS_INFO", "provider": "snowflake",
            "missing": missing, "issues": issues, "expected": expected,
            "risk": change.get("risk"), "snowflake_context": change.get("snowflake_context", {})}


def evaluate_stage1(change, context=None):
    """Run unified change-quality, maintenance-window, and access validation."""
    catalog = context or load_bundle()
    value = catalog.get("evaluation_time")
    evaluation_time = parse_utc(value) if isinstance(value, str) else value if isinstance(value, datetime) else None
    return assess_unified_stage1(change, catalog, evaluate_change_quality(change), evaluation_time)


def evaluate_stage2(change, access_request=None, context=None):
    catalog = context or load_bundle()
    value = catalog.get("evaluation_time")
    evaluation_time = parse_utc(value) if isinstance(value, str) else value if isinstance(value, datetime) else None
    return assess_stage2(change, catalog, evaluation_time)


def evaluate_stage3(*_args, **_kwargs):
    raise NotImplementedError("Snowflake Stage 3 is not implemented.")


def find_unmatched(changes, events, context=None):
    """Return governed successful activity without sufficient approved-change correlation."""
    context = context or load_bundle()
    access = {row["query_id"]: row for row in context.get("access_history", [])}
    output = []
    for raw in events:
        event = normalize_query(raw, access)
        if event["execution_status"] != "SUCCESS" or event["operation"] == "SELECT": continue
        correlation = correlate_query(event, changes, context.get("users", []))
        if correlation["classification"] == "UNMATCHED":
            output.append({"event_id": event["query_id"], "timestamp": event["timestamp"],
                           "operation": event["operation"], "resource_id": event["target_object"],
                           "actor": event["user"], "role": event["role"],
                           "classification": "POSSIBLE_UNAPPROVED_ACTIVITY",
                           "correlation_confidence": correlation["confidence"],
                           "warning": "Unmatched activity is not proof of malicious or unauthorized behavior."})
        elif correlation.get("change"):
            assessment = investigate_change(correlation["change"]["change_id"], context,
                                            evaluation_time=event["timestamp"], query_ids=[event["query_id"]])
            categories = [item["category"] for item in assessment.get("findings", [])
                          if item["category"] != "COMPLIANT_EXECUTION"]
            if categories:
                output.append({"event_id": event["query_id"], "timestamp": event["timestamp"],
                               "operation": event["operation"], "resource_id": event["target_object"],
                               "actor": event["user"], "role": event["role"],
                               "change_id": correlation["change"]["change_id"],
                               "classification": "CHANGE_DEVIATION", "deviations": categories,
                               "correlation_confidence": correlation["confidence"],
                               "warning": "Deviation categories are deterministic evidence comparisons; final object state is not verified."})
    return output
