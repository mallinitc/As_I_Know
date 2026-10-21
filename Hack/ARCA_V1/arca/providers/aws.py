"""AWS adapter preserving the original ARCA behavior."""
from __future__ import annotations

from arca.core import load, stage1, stage2, stage3, unmatched

DISPLAY_NAME = "AWS"
EVIDENCE_SOURCE = "Synthetic AWS IAM and CloudTrail-shaped evidence"


def load_bundle():
    return {
        "changes": load("changes.json"),
        "access_requests": load("access_requests.json"),
        "events": load("events.json"),
        "resources": [],
        "role_definitions": [],
        "rbac_assignments": [],
    }


def access_for_change(bundle, change_id):
    return next((x for x in bundle["access_requests"] if x["change_id"] == change_id), {})


def evaluate_stage1(change, context=None):
    return stage1(change)


def evaluate_stage2(change, access_request, context=None):
    return stage2(change, access_request)


def evaluate_stage3(change, events, context=None):
    return stage3(change, events)


def find_unmatched(changes, events, context=None):
    return unmatched(changes, events)
