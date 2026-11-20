from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from urllib.parse import unquote

from backend.errors import AwsEvidenceError
from backend.services.timestamps import parse_utc, utc_text


logger = logging.getLogger("arca.api")

# Live AWS calls are rate limited (LookupEvents allows 2 requests per second per
# account), so fetched evidence is reused for this long.
CACHE_SECONDS = 120
LOOKUP_PAGE_DELAY_SECONDS = 0.6
EVENT_FIELDS = (
    "eventID", "eventTime", "eventSource", "eventName", "awsRegion", "userIdentity", "requestParameters",
    "responseElements", "errorCode", "errorMessage", "readOnly", "recipientAccountId",
)


def _policy_document(value: Any) -> dict[str, Any]:
    # IAM returns URL-encoded JSON; botocore usually decodes it, but not for every operation.
    if isinstance(value, dict):
        return value
    return json.loads(unquote(str(value)))


class AwsLiveSource:
    """Read-only AWS evidence from CloudTrail and IAM for the provisioned live testbed.

    Change records, access requests, and scenario definitions come from the
    testbed manifest because ServiceNow data does not exist in AWS. CloudTrail
    events and IAM policy documents are always fetched from the account.
    Evidence is scoped to the testbed's resources and its activity window so
    unrelated account activity never enters an assessment.
    """

    def __init__(self, root: Path, *, session: Any = None, clock=monotonic):
        self.root = root
        self._session = session
        self._clients: dict[str, Any] = {}
        self._clock = clock
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, Any]] = {}

    def manifest(self) -> dict[str, Any]:
        source = self.root / "manifest.json"
        if not source.is_file():
            raise AwsEvidenceError("Live AWS evidence is selected but no testbed manifest exists; run scripts/aws_live_testbed.py provision.")
        try:
            manifest = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AwsEvidenceError("The live AWS testbed manifest contains invalid JSON.") from exc
        if not manifest.get("evidence_start") or not manifest.get("changes"):
            raise AwsEvidenceError("The live AWS testbed manifest is incomplete; provisioning did not finish.")
        return manifest

    def read(self, filename: str) -> list[dict[str, Any]]:
        readers = {
            "changes.json": lambda: self.manifest()["changes"],
            "access_requests.json": lambda: self.manifest()["access_requests"],
            "demo_scenarios.json": lambda: self.manifest()["demo_scenarios"],
            "policy_evidence.json": self.policy_evidence,
            "events.json": self.execution_events,
            # Live CloudTrail is returned once through events.json; repository.execution_events() concatenates both.
            "execution_events.json": lambda: [],
            "execution_scenarios.json": self.execution_scenarios,
        }
        if filename not in readers:
            raise AwsEvidenceError(f"Required AWS evidence is missing: {filename}")
        return readers[filename]()

    def _client(self, service: str):
        if service not in self._clients:
            if self._session is None:
                import botocore.session
                self._session = botocore.session.get_session()
            self._clients[service] = self._session.create_client(service, region_name=self.manifest()["region"])
        return self._clients[service]

    def _cached(self, key: str, load):
        with self._lock:
            hit = self._cache.get(key)
            if hit and self._clock() - hit[0] < CACHE_SECONDS:
                return hit[1]
            try:
                value = load()
            except AwsEvidenceError:
                raise
            except Exception as exc:
                # AWS error text can include account and principal details; log the type only.
                logger.warning("Live AWS evidence retrieval failed key=%s error=%s", key, type(exc).__name__)
                raise AwsEvidenceError("Live AWS evidence could not be retrieved from the account.") from exc
            self._cache[key] = (self._clock(), value)
            return value

    def _scope(self, manifest: dict[str, Any]) -> set[str]:
        account, region, resources = manifest["account_id"], manifest["region"], manifest["resources"]
        scope = {f"arn:aws:s3:::{resources['bucket']}"} if resources.get("bucket") else set()
        if resources.get("security_group"):
            scope.add(f"arn:aws:ec2:{region}:{account}:security-group/{resources['security_group']}")
        scope.update(resources.get("managed_policies") or [])
        scope.update(item["arn"] for item in resources.get("roles") or [])
        return scope

    @staticmethod
    def _resource_arns(record: dict[str, Any], lookup: dict[str, Any], account: str, region: str) -> list[str]:
        params = record.get("requestParameters") or {}
        source = str(record.get("eventSource") or "")
        arns = [str(item.get("ARN")) for item in record.get("resources") or [] if isinstance(item, dict) and item.get("ARN")]
        arns += [str(item.get("ResourceName")) for item in lookup.get("Resources") or [] if str(item.get("ResourceName") or "").startswith("arn:")]
        if source == "s3.amazonaws.com" and params.get("bucketName"):
            arns.append(f"arn:aws:s3:::{params['bucketName']}")
        elif source == "ec2.amazonaws.com":
            ids = [params.get("groupId")] + [item.get("resourceId") for item in ((params.get("resourcesSet") or {}).get("items") or [])]
            arns += [f"arn:aws:ec2:{region}:{account}:security-group/{item}" for item in ids if str(item or "").startswith("sg-")]
        elif source == "iam.amazonaws.com":
            if params.get("roleName"):
                arns.append(f"arn:aws:iam::{account}:role/{params['roleName']}")
            if str(params.get("policyArn") or "").startswith("arn:"):
                arns.append(str(params["policyArn"]))
        return list(dict.fromkeys(arns))

    def execution_events(self) -> list[dict[str, Any]]:
        return self._cached("cloudtrail", self._load_events)

    def _load_events(self) -> list[dict[str, Any]]:
        manifest = self.manifest()
        account, region, scope = manifest["account_id"], manifest["region"], self._scope(manifest)
        start = parse_utc(manifest["evidence_start"])
        end = parse_utc(manifest["evidence_end"]) if manifest.get("evidence_end") else datetime.now(timezone.utc)
        client = self._client("cloudtrail")
        events: dict[str, dict[str, Any]] = {}
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {"StartTime": start, "EndTime": end, "MaxResults": 50,
                                      "LookupAttributes": [{"AttributeKey": "ReadOnly", "AttributeValue": "false"}]}
            if token:
                kwargs["NextToken"] = token
            page = client.lookup_events(**kwargs)
            for lookup in page.get("Events") or []:
                record = json.loads(lookup.get("CloudTrailEvent") or "{}")
                if record.get("readOnly") is True:
                    continue
                arns = self._resource_arns(record, lookup, account, region)
                if not scope.intersection(arns):
                    continue
                event = {key: record[key] for key in EVENT_FIELDS if key in record}
                event["resources"] = [{"ARN": arn} for arn in arns]
                events[str(event["eventID"])] = event
            token = page.get("NextToken")
            if not token:
                break
            sleep(LOOKUP_PAGE_DELAY_SECONDS)
        return sorted(events.values(), key=lambda item: str(item.get("eventTime")))

    def policy_evidence(self) -> list[dict[str, Any]]:
        return self._cached("iam", self._load_policies)

    def _load_policies(self) -> list[dict[str, Any]]:
        manifest = self.manifest()
        client = self._client("iam")
        owners = {policy_id: item["change_id"] for item in manifest["access_requests"] for policy_id in item.get("policy_ids") or []}
        policies = []
        for source in manifest.get("policy_sources") or []:
            if source.get("inline_policy"):
                response = client.get_role_policy(RoleName=source["role_name"], PolicyName=source["inline_policy"])
                document, origin = response["PolicyDocument"], f"role/{source['role_name']}/inline/{source['inline_policy']}"
            else:
                arn = source["managed_policy_arn"]
                version = client.get_policy(PolicyArn=arn)["Policy"]["DefaultVersionId"]
                document = client.get_policy_version(PolicyArn=arn, VersionId=version)["PolicyVersion"]["Document"]
                origin = f"{arn}:{version}"
            policies.append({"policy_id": source["policy_id"], "change_id": owners.get(source["policy_id"]),
                             "policy_type": source["policy_type"], "document": _policy_document(document), "source": origin})
        return policies

    def _principals(self) -> tuple[str, str, str]:
        manifest = self.manifest()
        implementer = next(item["actor"] for item in manifest["changes"] if item["change_id"] == "CHG7001")
        operator = next(item for item in manifest["resources"]["roles"] if item["name"].startswith("arca-test-operator-"))
        return implementer, operator["name"], operator["arn"]

    def ask_scenarios(self) -> dict[str, dict[str, Any]]:
        """Live replacements for the AWS-only Ask ARCA examples, keyed by the scenario they replace."""
        implementer, operator, _ = self._principals()
        evaluated = utc_text(datetime.now(timezone.utc))

        def scenario(scenario_id: str, name: str, question: str, intent: str) -> dict[str, Any]:
            return {"scenario_id": scenario_id, "scenario_name": f"AWS live: {name}", "question": question,
                    "evaluation_timestamp": evaluated, "expected_intent": intent, "expected_providers": ["aws"]}

        items = [
            scenario("ASK-03", "change investigation", "Investigate AWS change CHG7001.", "change_investigation"),
            scenario("ASK-06", "IAM principal investigation", f"Investigate AWS activities by {operator} in the last 1 days.", "user_investigation"),
            scenario("ASK-09", "unauthorized activity", "Find unauthorized AWS activity in the last 1 days.", "unauthorized_activity"),
            scenario("ASK-13", "change executed by the wrong principal", "Was AWS change CHG7005 implemented correctly?", "change_execution"),
            scenario("ASK-15", "implementer investigation", f"Investigate AWS activities by {implementer} in the last 1 days.", "user_investigation"),
        ]
        return {item["scenario_id"]: item for item in items}

    def risk_scenarios(self) -> dict[str, dict[str, Any]]:
        """Live replacements for the AWS-only Agent 4 examples, keyed by the scenario they replace."""
        manifest = self.manifest()
        implementer, operator, operator_arn = self._principals()
        resources = manifest["resources"]
        managed = next(arn for arn in resources["managed_policies"] if "/arca-test-managed-" in arn).rsplit("/", 1)[1]
        evaluated = utc_text(datetime.now(timezone.utc))

        def scenario(scenario_id: str, name: str, expected: list[str], *, identity: str | None = None, role: str | None = None,
                     resource: str | None = None, severity: str = "all") -> dict[str, Any]:
            return {"scenario_id": scenario_id, "scenario_name": f"AWS live: {name}", "environment": "aws", "evaluation_timestamp": evaluated,
                    "window_days": 1, "identity": identity, "role": role, "resource": resource, "severity": severity,
                    "expected_providers": ["aws"], "expected_findings": expected}

        items = [
            scenario("RISK-01", "unapproved security group change", ["POSSIBLE_UNAPPROVED_ACTIVITY", "MISSING_APPROVED_CHANGE"], identity=operator, resource=resources["security_group"]),
            scenario("RISK-02", "out-of-window policy version", ["EXECUTED_OUTSIDE_WINDOW"], identity=implementer, resource=managed),
            scenario("RISK-03", "assumed-role activity", ["UNAUTHORIZED_IMPLEMENTER"], identity=operator_arn, role=operator),
            scenario("RISK-11", "implementer investigation", ["WRONG_TARGET_RESOURCE", "FAILED_ADMINISTRATIVE_OPERATION"], identity=implementer),
            scenario("RISK-12", "high-severity investigation", ["UNAUTHORIZED_IMPLEMENTER"], severity="high"),
            scenario("RISK-13", "no-deviation investigation", [], identity=implementer, resource=resources["bucket"], severity="low"),
            scenario("RISK-14", "failed administrative operation", ["FAILED_ADMINISTRATIVE_OPERATION"], identity=implementer, resource=resources["bucket"]),
        ]
        return {item["scenario_id"]: item for item in items}

    def execution_scenarios(self) -> list[dict[str, Any]]:
        # Imported here because the execution service imports the repository module.
        from backend.services.aws_execution import AwsExecutionService, _aliases, _norm

        manifest = self.manifest()
        events = self.execution_events()
        changes = {item["change_id"]: item for item in manifest["changes"]}
        classifier = AwsExecutionService(repository=self)
        evaluated = utc_text(datetime.now(timezone.utc))
        scenarios = []
        for scenario in manifest["execution_scenarios"]:
            if scenario["mode"] == "change":
                change = changes[scenario["change_id"]]
                ids = [e["eventID"] for e in events if classifier._classification(e, change) != "UNMATCHED"]
            else:
                ids = [e["eventID"] for e in events if _norm(scenario["user_identity"]) in _aliases(e)]
            scenarios.append({**scenario, "evaluation_timestamp": evaluated, "event_ids": ids})
        return scenarios
