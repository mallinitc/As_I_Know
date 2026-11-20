"""Live AWS evidence source tests.

The offline tests replay CloudTrail LookupEvents records shaped exactly like the
ones the testbed produces, through the real AWS validation and execution
services. The live tests at the bottom run the same scenarios against the
provisioned testbed (scripts/aws_live_testbed.py) and are skipped unless
ARCA_AWS_LIVE_TESTS=1.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.config import PROJECT_ROOT
from backend.errors import AwsEvidenceError
from backend.repositories.aws import AwsRepository
from backend.repositories.aws_live import AwsLiveSource
from backend.services.aws_execution import AwsExecutionService
from backend.services.aws_validation import AwsValidationService

ACCOUNT = "123456789012"
REGION = "us-east-1"
SUFFIX = "abc123"
BUCKET = f"arca-test-{ACCOUNT}-{SUFFIX}"
BUCKET_ARN = f"arn:aws:s3:::{BUCKET}"
GROUP = "sg-0123456789abcdef0"
GROUP_ARN = f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group/{GROUP}"
MANAGED_ARN = f"arn:aws:iam::{ACCOUNT}:policy/arca-test-managed-{SUFFIX}"
BOUNDARY_ARN = f"arn:aws:iam::{ACCOUNT}:policy/arca-test-boundary-{SUFFIX}"
IMPLEMENTER = "arca-implementer-role"
ROLES = {key: f"arca-test-{key}-{SUFFIX}" for key in ("operator", "scoped", "broad", "denied", "bounded")}
ROLE_ARN = {key: f"arn:aws:iam::{ACCOUNT}:role/{name}" for key, name in ROLES.items()}
EVIDENCE_START = "2026-10-22T22:49:38Z"
WINDOW_START = "2026-10-22T22:51:08Z"


def _policy(*statements):
    return {"Version": "2012-10-17", "Statement": list(statements)}


INLINE = {
    ROLES["operator"]: _policy({"Effect": "Allow", "Action": ["ec2:AuthorizeSecurityGroupIngress", "ec2:RevokeSecurityGroupIngress"], "Resource": GROUP_ARN}),
    ROLES["scoped"]: _policy({"Effect": "Allow", "Action": "s3:PutBucketPolicy", "Resource": BUCKET_ARN}),
    ROLES["broad"]: _policy({"Effect": "Allow", "Action": "s3:*", "Resource": "*"}),
    ROLES["denied"]: _policy({"Effect": "Allow", "Action": "s3:PutBucketPolicy", "Resource": BUCKET_ARN}, {"Effect": "Deny", "Action": "s3:PutBucketPolicy", "Resource": BUCKET_ARN}),
    ROLES["bounded"]: _policy({"Effect": "Allow", "Action": "s3:PutBucketPolicy", "Resource": BUCKET_ARN}),
}


def manifest() -> dict:
    hour_later = "2026-10-22T23:51:08Z"
    future = {"start": "2026-10-23T22:51:08Z", "end": "2026-10-23T23:51:08Z"}

    def change(change_id, expected, *, actor=IMPLEMENTER, start=WINDOW_START, end=hour_later, description="Documented change; rollback documented.", state="approved"):
        return {"change_id": change_id, "environment": "aws-live-test", "actor": actor, "state": state, "start": start, "end": end, "description": description, "expected": expected}

    policy = [{"eventName": "PutBucketPolicy", "resource": BUCKET_ARN}]
    versioning = [{"eventName": "PutBucketVersioning", "resource": BUCKET_ARN}]
    changes = [
        change("CHG7001", policy),
        change("CHG7005", [{"eventName": "AuthorizeSecurityGroupIngress", "resource": GROUP_ARN}]),
        change("CHG7006", [{"eventName": "CreatePolicyVersion", "resource": MANAGED_ARN}], start="2026-10-22T19:49:38Z", end="2026-10-22T20:49:38Z"),
        change("CHG7007", [{"eventName": "TagRole", "resource": ROLE_ARN["scoped"]}]),
        change("CHG7008", [{"eventName": "PutBucketTagging", "resource": BUCKET_ARN}], start=EVIDENCE_START, end="2026-10-22T22:50:38Z"),
        change("CHG7002", policy, actor=ROLES["broad"], **future),
        change("CHG7003", policy, actor=ROLES["denied"], **future),
        change("CHG7004", policy, actor=ROLES["bounded"], **future),
        change("CHG7009", versioning, description="", **future),
        change("CHG7010", versioning, start=future["end"], end=future["start"]),
        change("CHG7011", versioning, state="pending_approval", **future),
    ]

    def request(change_id, key, duration=60):
        return {"request_id": f"live-ar-{change_id[-4:]}", "change_id": change_id, "principal": ROLE_ARN[key], "role": ROLES[key], "duration_minutes": duration, "policy_ids": [f"live-pol-{key}"]}

    requests = [request("CHG7001", "scoped"), request("CHG7002", "broad", 240), request("CHG7003", "denied"), request("CHG7004", "bounded"), request("CHG7005", "operator")]
    requests[3]["policy_ids"].append("live-pol-bounded-boundary")
    sources = [{"policy_id": f"live-pol-{key}", "policy_type": "identity", "role_name": ROLES[key], "inline_policy": "arca-test-access"} for key in ROLES]
    sources.append({"policy_id": "live-pol-bounded-boundary", "policy_type": "permissions_boundary", "managed_policy_arn": BOUNDARY_ARN})

    def demo(number, stage, change_id, status):
        return {"scenario_id": f"AWS-LIVE-{stage.upper()}-{number:02d}", "scenario_name": f"Live {number:02d}", "stage": stage, "change_id": change_id, "expected_status": status, "expected_findings": []}

    def execution(number, expected, change_id=None, user=None):
        return {"scenario_id": f"AWS-LIVE-EXEC-{number:02d}", "scenario_name": f"Live {number:02d}", "mode": "change" if change_id else "user", "change_id": change_id, "user_identity": user, "window_days": 1, "expected_findings": expected}

    return {
        "schema_version": 1, "account_id": ACCOUNT, "region": REGION, "suffix": SUFFIX,
        "evidence_start": EVIDENCE_START, "evidence_end": "2026-10-22T22:51:21Z",
        "resources": {"bucket": BUCKET, "security_group": GROUP, "managed_policies": [MANAGED_ARN, BOUNDARY_ARN],
                      "roles": [{"name": name, "arn": ROLE_ARN[key], "inline_policy": "arca-test-access"} for key, name in ROLES.items()]},
        "changes": changes, "access_requests": requests, "policy_sources": sources,
        "demo_scenarios": [demo(1, "change", "CHG7001", "VALID"), demo(5, "access", "CHG7001", "APPROPRIATE_WITH_LIMITATIONS")],
        "execution_scenarios": [
            execution(1, ["COMPLIANT_EXECUTION"], change_id="CHG7001"),
            execution(2, ["UNAUTHORIZED_IMPLEMENTER"], change_id="CHG7005"),
            execution(6, ["UNAUTHORIZED_IMPLEMENTER", "POSSIBLE_UNAPPROVED_ACTIVITY"], user=ROLES["operator"]),
        ],
    }


def identity(role: str, session: str) -> dict:
    return {
        "type": "AssumedRole", "principalId": f"AROAEXAMPLE{role.upper()}:{session}",
        "arn": f"arn:aws:sts::{ACCOUNT}:assumed-role/{role}/{session}", "accountId": ACCOUNT,
        "sessionContext": {"sessionIssuer": {"type": "Role", "principalId": f"AROAEXAMPLE{role.upper()}", "arn": f"arn:aws:iam::{ACCOUNT}:role/{role}", "accountId": ACCOUNT, "userName": role}},
    }


def lookup(event_id, time, source, name, params, *, role=IMPLEMENTER, read_only=False, error=None, resources=None) -> dict:
    record = {"eventVersion": "1.11", "userIdentity": identity(role, "i-0123456789abcdef0" if role == IMPLEMENTER else "arca-live-operator"),
              "eventTime": time, "eventSource": source, "eventName": name, "awsRegion": REGION, "sourceIPAddress": "10.0.0.10",
              "requestParameters": params, "responseElements": None, "eventID": event_id, "readOnly": read_only,
              "eventType": "AwsApiCall", "managementEvent": True, "recipientAccountId": ACCOUNT}
    if error:
        record.update({"errorCode": error, "errorMessage": "The TagKey you have provided is invalid"})
    return {"EventId": event_id, "EventName": name, "ReadOnly": str(read_only).lower(), "EventTime": time, "EventSource": source,
            "Resources": resources or [], "CloudTrailEvent": json.dumps(record)}


EVENTS = [
    lookup("e-setup", "2026-10-22T22:49:10Z", "s3.amazonaws.com", "PutBucketTagging", {"bucketName": BUCKET}),
    lookup("e-2008", "2026-10-22T22:49:58Z", "s3.amazonaws.com", "PutBucketTagging", {"bucketName": BUCKET, "tagging": ""}, error="InvalidTag"),
    lookup("e-2001", "2026-10-22T22:51:18Z", "s3.amazonaws.com", "PutBucketPolicy", {"bucketName": BUCKET, "policy": ""}),
    lookup("e-2005", "2026-10-22T22:51:19Z", "ec2.amazonaws.com", "AuthorizeSecurityGroupIngress", {"groupId": GROUP}, role=ROLES["operator"]),
    lookup("e-2006", "2026-10-22T22:51:19Z", "iam.amazonaws.com", "CreatePolicyVersion", {"policyArn": MANAGED_ARN, "setAsDefault": True}),
    lookup("e-2007", "2026-10-22T22:51:20Z", "iam.amazonaws.com", "TagRole", {"roleName": ROLES["broad"]}),
    lookup("e-revoke", "2026-10-22T22:51:20Z", "ec2.amazonaws.com", "RevokeSecurityGroupIngress", {"groupId": GROUP}, role=ROLES["operator"]),
    lookup("e-read", "2026-10-22T22:51:20Z", "s3.amazonaws.com", "GetBucketPolicy", {"bucketName": BUCKET}, read_only=True),
    lookup("e-other", "2026-10-22T22:51:20Z", "s3.amazonaws.com", "PutBucketPolicy", {"bucketName": "someone-elses-bucket"}),
]


class FakeCloudTrail:
    def __init__(self):
        self.calls = []

    def lookup_events(self, **kwargs):
        self.calls.append(kwargs)
        # Setup activity before evidence_start is outside the requested range, as in CloudTrail.
        visible = [item for item in EVENTS if item["EventTime"] >= EVIDENCE_START]
        if "NextToken" not in kwargs:
            return {"Events": visible[:4], "NextToken": "page-2"}
        return {"Events": visible[4:]}


class FakeIam:
    def get_role_policy(self, RoleName, PolicyName):
        return {"PolicyDocument": INLINE[RoleName]}

    def get_policy(self, PolicyArn):
        return {"Policy": {"DefaultVersionId": "v1"}}

    def get_policy_version(self, PolicyArn, VersionId):
        # Exercise the URL-encoded JSON form IAM can return.
        return {"PolicyVersion": {"Document": "%7B%22Version%22%3A%222012-10-17%22%2C%22Statement%22%3A%5B%7B%22Effect%22%3A%22Allow%22%2C%22Action%22%3A%22s3%3AGetBucketTagging%22%2C%22Resource%22%3A%22" + BUCKET_ARN.replace(":", "%3A") + "%22%7D%5D%7D"}}


class FakeSession:
    def __init__(self):
        self.cloudtrail, self.iam = FakeCloudTrail(), FakeIam()

    def create_client(self, service, region_name):
        assert region_name == REGION
        return {"cloudtrail": self.cloudtrail, "iam": self.iam}[service]


@pytest.fixture
def live(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("backend.repositories.aws_live.LOOKUP_PAGE_DELAY_SECONDS", 0)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest()), encoding="utf-8")
    session = FakeSession()
    repository = AwsRepository(live=AwsLiveSource(tmp_path, session=session))
    return repository, session


def categories(result) -> set[str]:
    return {item["category"] for item in result["findings"]}


def test_cloudtrail_events_are_scoped_normalized_and_cached(live):
    repository, session = live
    events = repository.execution_events()
    assert [e["eventID"] for e in events] == ["e-2008", "e-2001", "e-2005", "e-2006", "e-2007", "e-revoke"]
    assert not repository.synthetic
    by_id = {e["eventID"]: e for e in events}
    assert by_id["e-2001"]["resources"] == [{"ARN": BUCKET_ARN}]
    assert by_id["e-2005"]["resources"] == [{"ARN": GROUP_ARN}]
    assert by_id["e-2006"]["resources"] == [{"ARN": MANAGED_ARN}]
    assert by_id["e-2007"]["resources"] == [{"ARN": ROLE_ARN["broad"]}]
    assert by_id["e-2008"]["errorCode"] == "InvalidTag"
    assert "sourceIPAddress" not in by_id["e-2001"]
    request = session.cloudtrail.calls[0]
    assert request["LookupAttributes"] == [{"AttributeKey": "ReadOnly", "AttributeValue": "false"}]
    repository.execution_events()
    assert len(session.cloudtrail.calls) == 2


def test_iam_policy_documents_come_from_the_account(live):
    repository, _ = live
    policies = {item["policy_id"]: item for item in repository.policy_evidence()}
    assert policies["live-pol-broad"]["document"] == INLINE[ROLES["broad"]]
    assert policies["live-pol-broad"]["change_id"] == "CHG7002"
    boundary = policies["live-pol-bounded-boundary"]
    assert boundary["policy_type"] == "permissions_boundary"
    assert boundary["document"]["Statement"][0]["Action"] == "s3:GetBucketTagging"


@pytest.mark.parametrize(("change_id", "status", "expected"), [
    ("CHG7001", "APPROPRIATE_WITH_LIMITATIONS", set()),
    ("CHG7002", "OVERPRIVILEGED", {"ACTION_WILDCARD", "RESOURCE_WILDCARD", "EXCESSIVE_ACCESS_DURATION"}),
    ("CHG7003", "EXPLICITLY_DENIED", {"EXPLICIT_DENY"}),
    ("CHG7004", "INSUFFICIENT_ACCESS", {"PERMISSION_BOUNDARY_CONSTRAINT"}),
    ("CHG7005", "MANUAL_REVIEW_REQUIRED", {"UNKNOWN_IAM_ACTION"}),
])
def test_access_validation_uses_live_iam_policies(live, change_id, status, expected):
    result = AwsValidationService(live[0]).validate_access(change_id)
    assert result["overall_status"] == status
    assert expected <= categories(result)


@pytest.mark.parametrize(("change_id", "status"), [("CHG7001", "VALID"), ("CHG7009", "INCOMPLETE"), ("CHG7010", "INCONSISTENT"), ("CHG7011", "MANUAL_REVIEW_REQUIRED")])
def test_change_quality_for_live_change_records(live, change_id, status):
    assert AwsValidationService(live[0]).validate_change(change_id)["overall_status"] == status


@pytest.mark.parametrize(("change_id", "status", "expected", "absent"), [
    ("CHG7001", "COMPLIANT", {"COMPLIANT_EXECUTION"}, {"UNAPPROVED_OPERATION"}),
    ("CHG7005", "NON_COMPLIANT", {"UNAUTHORIZED_IMPLEMENTER"}, {"COMPLIANT_EXECUTION"}),
    ("CHG7006", "NON_COMPLIANT", {"EXECUTED_OUTSIDE_WINDOW"}, {"COMPLIANT_EXECUTION"}),
    ("CHG7007", "NON_COMPLIANT", {"WRONG_TARGET_RESOURCE", "EXPECTED_OPERATION_MISSING"}, {"COMPLIANT_EXECUTION"}),
    ("CHG7008", "NON_COMPLIANT", {"FAILED_EXECUTION", "EXPECTED_OPERATION_MISSING"}, {"COMPLIANT_EXECUTION"}),
])
def test_change_execution_against_cloudtrail(live, change_id, status, expected, absent):
    result = AwsExecutionService(live[0]).assess_change(change_id, "2026-10-22T23:30:00Z")
    assert result["overall_status"] == status
    assert expected <= categories(result)
    assert not absent & categories(result)


def test_operator_investigation_flags_unapproved_revoke(live):
    result = AwsExecutionService(live[0]).assess_user(ROLES["operator"], 1, "2026-10-22T23:30:00Z")
    assert result["event_ids"] == ["e-2005", "e-revoke"]
    assert {"UNAUTHORIZED_IMPLEMENTER", "POSSIBLE_UNAPPROVED_ACTIVITY"} <= categories(result)
    revoke = next(item for item in result["timeline"] if item["event_id"] == "e-revoke")
    assert revoke["change_match"] == "UNMATCHED"


def test_execution_scenarios_resolve_live_event_ids(live):
    service = AwsExecutionService(live[0])
    scenarios = {item["scenario_id"]: item for item in service.scenarios()}
    assert scenarios["AWS-LIVE-EXEC-01"]["event_ids"] == ["e-2001"]
    assert scenarios["AWS-LIVE-EXEC-02"]["event_ids"] == ["e-2005"]
    assert scenarios["AWS-LIVE-EXEC-06"]["event_ids"] == ["e-2005", "e-revoke"]
    assert scenarios["AWS-LIVE-EXEC-01"]["evaluation_timestamp"].endswith("Z")
    result = service.assess_change("CHG7001", "2026-10-22T23:30:00Z", "AWS-LIVE-EXEC-01")
    assert result["overall_status"] == "COMPLIANT"


def _live_ask_service(repository):
    from backend.services.ask_arca import AskArcaService
    service = AskArcaService()
    service.repos["aws"] = repository
    service.validation["aws"] = AwsValidationService(repository)
    service.execution["aws"] = AwsExecutionService(repository)
    service.risk.aws_repo = repository
    service.risk.aws = AwsExecutionService(repository)
    return service


def test_ask_arca_routes_live_change_ids_to_that_change_only(live):
    service = _live_ask_service(live[0])
    result = service.ask("Investigate AWS change CHG7001.", mode="deterministic", evaluation_timestamp="2026-10-22T23:30:00Z")
    assert result["resolved_intent"]["change_id"] == "CHG7001" and result["providers_investigated"] == ["aws"]
    assert [item["event_id"] for item in result["activity_timeline"]] == ["e-2001"]
    assert "COMPLIANT_EXECUTION" in categories(result)
    wrong = service.ask("Was AWS change CHG7005 implemented correctly?", mode="deterministic", evaluation_timestamp="2026-10-22T23:30:00Z")
    assert "UNAUTHORIZED_IMPLEMENTER" in categories(wrong)


def test_live_mode_replaces_only_aws_only_examples(live):
    service = _live_ask_service(live[0])
    synthetic = _live_ask_service(AwsRepository(root=PROJECT_ROOT / "data" / "aws"))
    live_items = {item["scenario_id"]: item for item in service.scenarios()}
    synthetic_items = {item["scenario_id"]: item for item in synthetic.scenarios()}
    replaced = {key for key in live_items if live_items[key] != synthetic_items[key]}
    assert replaced == {"ASK-03", "ASK-06", "ASK-09", "ASK-13", "ASK-15"}
    assert all(synthetic_items[key]["expected_providers"] == ["aws"] for key in replaced)
    assert ROLES["operator"] in live_items["ASK-06"]["question"]
    risk = {item["scenario_id"]: item for item in service.risk.scenarios()}
    assert risk["RISK-01"]["identity"] == ROLES["operator"] and risk["RISK-01"]["resource"] == GROUP
    assert risk["RISK-10"]["environment"] == "all"


@pytest.mark.parametrize("scenario_id", ["RISK-01", "RISK-02", "RISK-03", "RISK-11", "RISK-12", "RISK-13", "RISK-14"])
def test_live_risk_scenarios_find_expected_categories(live, scenario_id):
    service = _live_ask_service(live[0]).risk
    scenario = next(item for item in service.scenarios() if item["scenario_id"] == scenario_id)
    result = service.investigate(environment="aws", identity=scenario["identity"], role=scenario["role"], resource=scenario["resource"],
                                 window_days=scenario["window_days"], severity=scenario["severity"], evaluation_timestamp="2026-10-22T23:30:00Z")
    found = categories(result)
    assert set(scenario["expected_findings"]) <= found, (scenario_id, found)
    if not scenario["expected_findings"]:
        assert not found


def test_missing_manifest_and_aws_errors_are_sanitized(tmp_path, monkeypatch):
    with pytest.raises(AwsEvidenceError, match="no testbed manifest"):
        AwsRepository(live=AwsLiveSource(tmp_path)).changes()

    class Broken(FakeSession):
        def create_client(self, service, region_name):
            class Client:
                def lookup_events(self, **kwargs):
                    raise RuntimeError(f"AccessDenied for arn:aws:iam::{ACCOUNT}:role/secret")
            return Client()

    (tmp_path / "manifest.json").write_text(json.dumps(manifest()), encoding="utf-8")
    with pytest.raises(AwsEvidenceError) as failure:
        AwsRepository(live=AwsLiveSource(tmp_path, session=Broken())).execution_events()
    assert ACCOUNT not in str(failure.value)


def test_synthetic_remains_the_default(monkeypatch):
    monkeypatch.delenv("ARCA_AWS_EVIDENCE_SOURCE", raising=False)
    repository = AwsRepository()
    assert repository.synthetic and repository.live is None
    monkeypatch.setenv("ARCA_AWS_EVIDENCE_SOURCE", "live")
    assert not AwsRepository().synthetic
    assert AwsRepository(root=PROJECT_ROOT / "data" / "aws").synthetic
    monkeypatch.setenv("ARCA_AWS_EVIDENCE_SOURCE", "prod")
    with pytest.raises(ValueError, match="ARCA_AWS_EVIDENCE_SOURCE"):
        AwsRepository()


live_only = pytest.mark.skipif(
    os.getenv("ARCA_AWS_LIVE_TESTS") != "1" or not (PROJECT_ROOT / "data" / "aws_live" / "manifest.json").is_file(),
    reason="Set ARCA_AWS_LIVE_TESTS=1 after provisioning with scripts/aws_live_testbed.py",
)


@pytest.fixture(scope="module")
def real_repository():
    return AwsRepository(live=AwsLiveSource(PROJECT_ROOT / "data" / "aws_live"))


@live_only
def test_live_demo_scenarios_match_expected_status(real_repository):
    service = AwsValidationService(real_repository)
    for scenario in service.list_demo_scenarios():
        validate = service.validate_change if scenario["stage"] == "change" else service.validate_access
        result = validate(scenario["change_id"])
        assert result["overall_status"] == scenario["expected_status"], scenario["scenario_id"]
        assert set(scenario["expected_findings"]) <= categories(result), scenario["scenario_id"]


@live_only
def test_live_execution_scenarios_match_expected_findings(real_repository):
    service = AwsExecutionService(real_repository)
    assert len(real_repository.execution_events()) == 6, "CloudTrail has not delivered all six scenario events yet"
    for scenario in service.scenarios():
        if scenario["mode"] == "change":
            result = service.assess_change(scenario["change_id"], scenario_id=scenario["scenario_id"])
        else:
            result = service.assess_user(scenario["user_identity"], scenario["window_days"], scenario_id=scenario["scenario_id"])
        assert set(scenario["expected_findings"]) <= categories(result), (scenario["scenario_id"], categories(result))
