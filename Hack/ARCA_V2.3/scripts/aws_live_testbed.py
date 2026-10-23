"""Provision, exercise, and tear down real AWS resources for ARCA live AWS scenarios.

    python scripts/aws_live_testbed.py provision   # create arca-test-* resources and real CloudTrail activity
    python scripts/aws_live_testbed.py status      # show the manifest and resource state
    python scripts/aws_live_testbed.py teardown    # delete every resource recorded in the manifest

Every resource is named arca-test-*, tagged Project=ARCA-Test, and recorded in
data/aws_live/manifest.json as soon as it exists, so teardown also cleans up a
partially failed provision. Created resources: one private S3 bucket, one
unattached security group (default VPC, or this instance's VPC when the account
has none), two customer managed IAM policies,
and five IAM roles that only the provisioning principal can assume. No compute.

The manifest also carries the change records, access requests, and scenario
definitions that reference these real resources. ServiceNow change IDs do not
exist in CloudTrail, so each change is matched on actor, operation, target ARN,
and its own UTC window, exactly as ARCA does for production evidence.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import botocore.session
from botocore.exceptions import ClientError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT / "data" / "aws_live" / "manifest.json"
PREFIX = "arca-test"
TAG = {"Key": "Project", "Value": "ARCA-Test"}
IAM_PROPAGATION_SECONDS = 15
INGRESS_RULE = {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "10.255.255.254/32", "Description": "ARCA live test rule"}]}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _text(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _policy(*statements: dict[str, Any]) -> str:
    return json.dumps({"Version": "2012-10-17", "Statement": list(statements)})


def _allow(action: str | list[str], resource: str | list[str]) -> dict[str, Any]:
    return {"Effect": "Allow", "Action": action, "Resource": resource}


def _ignore(codes: set[str], call: Callable[[], Any]) -> None:
    try:
        call()
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in codes:
            raise


def _save(manifest: dict[str, Any]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _wait_until(moment: datetime) -> None:
    delay = (moment - datetime.now(timezone.utc)).total_seconds()
    if delay > 0:
        time.sleep(delay)


class Testbed:
    def __init__(self, region: str, vpc_id: str | None = None):
        self.region = region
        self.vpc_id = vpc_id
        self.session = botocore.session.get_session()
        self.s3 = self.session.create_client("s3", region_name=region)
        self.ec2 = self.session.create_client("ec2", region_name=region)
        self.iam = self.session.create_client("iam", region_name=region)
        self.sts = self.session.create_client("sts", region_name=region)

    def _caller(self) -> tuple[str, str, str, str]:
        identity = self.sts.get_caller_identity()
        account, arn = identity["Account"], identity["Arn"]
        if ":assumed-role/" in arn:
            role_name, session = arn.split(":assumed-role/", 1)[1].split("/", 1)
            return account, role_name, self.iam.get_role(RoleName=role_name)["Role"]["Arn"], session
        if ":user/" in arn:
            return account, arn.rsplit("/", 1)[1], arn, ""
        raise SystemExit(f"Unsupported caller identity for the testbed: {arn}")

    def _vpc_id(self, caller_session: str) -> str:
        # Prefer an explicit VPC, then the default VPC, then the VPC of the EC2
        # instance whose role session is running this script. The group is never attached.
        if self.vpc_id:
            return self.vpc_id
        vpcs = self.ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
        if vpcs:
            return vpcs[0]["VpcId"]
        if caller_session.startswith("i-"):
            reservations = self.ec2.describe_instances(InstanceIds=[caller_session])["Reservations"]
            if reservations and reservations[0]["Instances"][0].get("VpcId"):
                return reservations[0]["Instances"][0]["VpcId"]
        raise SystemExit("No default VPC in this Region; pass --vpc-id for the unattached test security group.")

    def _assumed_ec2(self, role_arn: str):
        credentials = self.sts.assume_role(RoleArn=role_arn, RoleSessionName="arca-live-operator", DurationSeconds=900)["Credentials"]
        return self.session.create_client(
            "ec2", region_name=self.region,
            aws_access_key_id=credentials["AccessKeyId"], aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
        )

    def provision(self) -> None:
        if MANIFEST.exists():
            raise SystemExit(f"{MANIFEST} already exists. Run teardown before provisioning again.")
        account, caller_name, caller_arn, caller_session = self._caller()
        suffix = secrets.token_hex(3)
        manifest: dict[str, Any] = {
            "schema_version": 1, "account_id": account, "region": self.region, "suffix": suffix,
            "provisioned_by": caller_arn, "provisioned_at": _text(_now()),
            "resources": {"bucket": None, "security_group": None, "managed_policies": [], "roles": []},
        }
        _save(manifest)
        resources = manifest["resources"]
        print(f"Provisioning in account {account} ({self.region}) as {caller_name}, suffix {suffix}")

        bucket = f"{PREFIX}-{account}-{suffix}"
        if self.region == "us-east-1":
            self.s3.create_bucket(Bucket=bucket)
        else:
            self.s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": self.region})
        resources["bucket"] = bucket
        _save(manifest)
        self.s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
        })
        self.s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [TAG]})
        bucket_arn = f"arn:aws:s3:::{bucket}"
        print(f"  bucket {bucket}")

        vpc_id = self._vpc_id(caller_session)
        group = self.ec2.create_security_group(
            GroupName=f"{PREFIX}-sg-{suffix}", Description="ARCA live test group; not attached to anything",
            VpcId=vpc_id, TagSpecifications=[{"ResourceType": "security-group", "Tags": [TAG]}],
        )
        group_id = group["GroupId"]
        resources["security_group"] = group_id
        _save(manifest)
        group_arn = f"arn:aws:ec2:{self.region}:{account}:security-group/{group_id}"
        print(f"  security group {group_id}")

        def managed_policy(name: str, document: str) -> str:
            arn = self.iam.create_policy(PolicyName=name, PolicyDocument=document, Tags=[TAG])["Policy"]["Arn"]
            resources["managed_policies"].append(arn)
            _save(manifest)
            print(f"  managed policy {name}")
            return arn

        change_policy_arn = managed_policy(f"{PREFIX}-managed-{suffix}", _policy(_allow("s3:GetBucketTagging", bucket_arn)))
        boundary_arn = managed_policy(f"{PREFIX}-boundary-{suffix}", _policy(_allow("s3:GetBucketTagging", bucket_arn)))

        trust = _policy({"Effect": "Allow", "Principal": {"AWS": caller_arn}, "Action": "sts:AssumeRole"})
        roles: dict[str, str] = {}

        def role(key: str, inline: str, boundary: str | None = None) -> None:
            name = f"{PREFIX}-{key}-{suffix}"
            kwargs: dict[str, Any] = {"RoleName": name, "AssumeRolePolicyDocument": trust, "Tags": [TAG], "MaxSessionDuration": 3600,
                                      "Description": "ARCA live test role; assumable only by the provisioning principal"}
            if boundary:
                kwargs["PermissionsBoundary"] = boundary
            arn = self.iam.create_role(**kwargs)["Role"]["Arn"]
            resources["roles"].append({"name": name, "arn": arn, "inline_policy": "arca-test-access"})
            _save(manifest)
            self.iam.put_role_policy(RoleName=name, PolicyName="arca-test-access", PolicyDocument=inline)
            roles[key] = name
            print(f"  role {name}")

        role("operator", _policy(_allow(["ec2:AuthorizeSecurityGroupIngress", "ec2:RevokeSecurityGroupIngress"], group_arn)))
        role("scoped", _policy(_allow("s3:PutBucketPolicy", bucket_arn)))
        role("broad", _policy(_allow("s3:*", "*")))
        role("denied", _policy(_allow("s3:PutBucketPolicy", bucket_arn), {"Effect": "Deny", "Action": "s3:PutBucketPolicy", "Resource": bucket_arn}))
        role("bounded", _policy(_allow("s3:PutBucketPolicy", bucket_arn)), boundary=boundary_arn)
        role_arn = {key: f"arn:aws:iam::{account}:role/{name}" for key, name in roles.items()}

        print(f"Waiting {IAM_PROPAGATION_SECONDS}s for IAM propagation")
        time.sleep(IAM_PROPAGATION_SECONDS)
        operator_ec2 = self._assumed_ec2(role_arn["operator"])

        # Scenario evidence starts here; setup activity above is excluded from ARCA.
        evidence_start = _now() + timedelta(seconds=2)
        manifest["evidence_start"] = _text(evidence_start)
        _save(manifest)
        print(f"Generating scenario activity from {manifest['evidence_start']}")

        # CHG7008: approved bucket tagging fails (invalid reserved tag key) inside its own one-minute window.
        _wait_until(evidence_start + timedelta(seconds=20))
        try:
            self.s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [TAG, {"Key": "aws:arca-change", "Value": "CHG7008"}]})
            raise SystemExit("PutBucketTagging with a reserved aws: key unexpectedly succeeded.")
        except ClientError as exc:
            print(f"  CHG7008 PutBucketTagging failed as intended: {exc.response['Error']['Code']}")

        # CHG7001: compliant bucket policy update by the approved implementer.
        window_start = evidence_start + timedelta(seconds=90)
        _wait_until(window_start + timedelta(seconds=10))
        self.s3.put_bucket_policy(Bucket=bucket, Policy=_policy({
            "Sid": "DenyInsecureTransport", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
            "Resource": [bucket_arn, f"{bucket_arn}/*"], "Condition": {"Bool": {"aws:SecureTransport": "false"}},
        }))
        print("  CHG7001 PutBucketPolicy succeeded")

        # CHG7005: security group change executed by the operator role instead of the approved implementer.
        operator_ec2.authorize_security_group_ingress(GroupId=group_id, IpPermissions=[INGRESS_RULE])
        print("  CHG7005 AuthorizeSecurityGroupIngress succeeded (operator role)")

        # CHG7006: managed policy update after its approved window closed.
        self.iam.create_policy_version(PolicyArn=change_policy_arn, SetAsDefault=True,
                                       PolicyDocument=_policy(_allow(["s3:GetBucketTagging", "s3:GetBucketLocation"], bucket_arn)))
        print("  CHG7006 CreatePolicyVersion succeeded")

        # CHG7007: approved tag change applied to the wrong role.
        self.iam.tag_role(RoleName=roles["broad"], Tags=[{"Key": "ChangeTicket", "Value": "CHG7007"}])
        print("  CHG7007 TagRole succeeded on the wrong role")

        # Unapproved: the operator role revokes the rule with no change record.
        operator_ec2.revoke_security_group_ingress(GroupId=group_id, IpPermissions=[INGRESS_RULE])
        print("  Unapproved RevokeSecurityGroupIngress succeeded (operator role)")
        manifest["evidence_end"] = _text(_now() + timedelta(seconds=2))

        manifest.update(self._records(manifest, caller_name, roles, role_arn, bucket_arn, group_arn, change_policy_arn, boundary_arn, evidence_start, window_start))
        _save(manifest)
        print(f"Wrote {MANIFEST}")
        print("CloudTrail usually shows management events within 5-15 minutes; check with the status command.")

    @staticmethod
    def _records(manifest: dict[str, Any], implementer: str, roles: dict[str, str], role_arn: dict[str, str], bucket_arn: str,
                 group_arn: str, change_policy_arn: str, boundary_arn: str, evidence_start: datetime, window_start: datetime) -> dict[str, Any]:
        hour = timedelta(hours=1)
        future = window_start + timedelta(days=1)
        approved = {"start": _text(window_start), "end": _text(window_start + hour)}

        def change(change_id: str, description: str, expected: list[dict[str, str]], *, actor: str = implementer,
                   start: datetime | None = None, end: datetime | None = None, state: str = "approved") -> dict[str, Any]:
            window = {"start": _text(start), "end": _text(end)} if start and end else approved
            return {"change_id": change_id, "environment": "aws-live-test", "actor": actor, "state": state, **window,
                    "description": description, "expected": expected}

        bucket_policy = [{"eventName": "PutBucketPolicy", "resource": bucket_arn}]
        changes = [
            change("CHG7001", "Apply a deny-insecure-transport bucket policy to the ARCA live test bucket; rollback by deleting the bucket policy.", bucket_policy),
            change("CHG7005", "Open TCP 443 from 10.255.255.254/32 on the unattached ARCA test security group; rollback by revoking the rule.",
                   [{"eventName": "AuthorizeSecurityGroupIngress", "resource": group_arn}]),
            change("CHG7006", "Publish version 2 of the ARCA test managed policy to add s3:GetBucketLocation; rollback by restoring version 1.",
                   [{"eventName": "CreatePolicyVersion", "resource": change_policy_arn}], start=evidence_start - 3 * hour, end=evidence_start - 2 * hour),
            change("CHG7007", "Tag the scoped ARCA test role with its change ticket; rollback by removing the tag.",
                   [{"eventName": "TagRole", "resource": role_arn["scoped"]}]),
            change("CHG7008", "Add a change-ticket tag to the ARCA live test bucket; rollback by restoring the previous tag set.",
                   [{"eventName": "PutBucketTagging", "resource": bucket_arn}], start=evidence_start, end=evidence_start + timedelta(seconds=60)),
            change("CHG7002", "Grant the broad ARCA test role access to update the test bucket policy.", bucket_policy,
                   actor=roles["broad"], start=future, end=future + hour),
            change("CHG7003", "Grant the denied ARCA test role access to update the test bucket policy.", bucket_policy,
                   actor=roles["denied"], start=future, end=future + hour),
            change("CHG7004", "Grant the boundary-restricted ARCA test role access to update the test bucket policy.", bucket_policy,
                   actor=roles["bounded"], start=future, end=future + hour),
            change("CHG7009", "", [{"eventName": "PutBucketVersioning", "resource": bucket_arn}], start=future, end=future + hour),
            change("CHG7010", "Enable versioning on the ARCA live test bucket; rollback by suspending versioning.",
                   [{"eventName": "PutBucketVersioning", "resource": bucket_arn}], start=future + hour, end=future),
            change("CHG7011", "Enable versioning on the ARCA live test bucket; rollback by suspending versioning.",
                   [{"eventName": "PutBucketVersioning", "resource": bucket_arn}], start=future, end=future + hour, state="pending_approval"),
        ]

        def request(change_id: str, key: str, duration: int = 60) -> dict[str, Any]:
            return {"request_id": f"live-ar-{change_id[-4:]}", "change_id": change_id, "principal": role_arn[key],
                    "role": roles[key], "duration_minutes": duration, "policy_ids": [f"live-pol-{key}"]}

        access_requests = [request("CHG7001", "scoped"), request("CHG7002", "broad", 240), request("CHG7003", "denied"),
                           request("CHG7004", "bounded"), request("CHG7005", "operator")]
        policy_sources = [{"policy_id": f"live-pol-{key}", "policy_type": "identity", "role_name": roles[key], "inline_policy": "arca-test-access"}
                          for key in ("scoped", "broad", "denied", "bounded", "operator")]
        policy_sources.append({"policy_id": "live-pol-bounded-boundary", "policy_type": "permissions_boundary", "managed_policy_arn": boundary_arn})
        for item in access_requests:
            if item["change_id"] == "CHG7004":
                item["policy_ids"].append("live-pol-bounded-boundary")

        demo_scenarios = [
            {"scenario_id": "AWS-LIVE-CHANGE-01", "scenario_name": "Live 01 - Valid Change", "stage": "change", "change_id": "CHG7001", "expected_status": "VALID", "expected_findings": []},
            {"scenario_id": "AWS-LIVE-CHANGE-02", "scenario_name": "Live 02 - Missing Change Description", "stage": "change", "change_id": "CHG7009", "expected_status": "INCOMPLETE", "expected_findings": ["MISSING_MANDATORY_FIELD"]},
            {"scenario_id": "AWS-LIVE-CHANGE-03", "scenario_name": "Live 03 - Invalid Change Window", "stage": "change", "change_id": "CHG7010", "expected_status": "INCONSISTENT", "expected_findings": ["INVALID_CHANGE_WINDOW"]},
            {"scenario_id": "AWS-LIVE-CHANGE-04", "scenario_name": "Live 04 - Unapproved Change", "stage": "change", "change_id": "CHG7011", "expected_status": "MANUAL_REVIEW_REQUIRED", "expected_findings": ["CHANGE_NOT_APPROVED"]},
            {"scenario_id": "AWS-LIVE-ACCESS-05", "scenario_name": "Live 05 - Scoped Bucket Policy Permission", "stage": "access", "change_id": "CHG7001", "expected_status": "APPROPRIATE_WITH_LIMITATIONS", "expected_findings": []},
            {"scenario_id": "AWS-LIVE-ACCESS-06", "scenario_name": "Live 06 - Wildcard S3 Role", "stage": "access", "change_id": "CHG7002", "expected_status": "OVERPRIVILEGED", "expected_findings": ["ACTION_WILDCARD", "RESOURCE_WILDCARD", "EXCESSIVE_ACCESS_DURATION"]},
            {"scenario_id": "AWS-LIVE-ACCESS-07", "scenario_name": "Live 07 - Explicit Deny on Role", "stage": "access", "change_id": "CHG7003", "expected_status": "EXPLICITLY_DENIED", "expected_findings": ["EXPLICIT_DENY"]},
            {"scenario_id": "AWS-LIVE-ACCESS-08", "scenario_name": "Live 08 - Permissions Boundary Blocks Access", "stage": "access", "change_id": "CHG7004", "expected_status": "INSUFFICIENT_ACCESS", "expected_findings": ["PERMISSION_BOUNDARY_CONSTRAINT"]},
            {"scenario_id": "AWS-LIVE-ACCESS-09", "scenario_name": "Live 09 - Security Group Action Needs Manual Review", "stage": "access", "change_id": "CHG7005", "expected_status": "MANUAL_REVIEW_REQUIRED", "expected_findings": ["UNKNOWN_IAM_ACTION"]},
        ]

        def execution(number: int, name: str, expected: list[str], *, change_id: str | None = None, user: str | None = None) -> dict[str, Any]:
            return {"scenario_id": f"AWS-LIVE-EXEC-{number:02d}", "scenario_name": f"Live {number:02d} - {name}",
                    "mode": "change" if change_id else "user", "change_id": change_id, "user_identity": user, "window_days": 1,
                    "expected_findings": expected}

        execution_scenarios = [
            execution(1, "Compliant Bucket Policy Update", ["COMPLIANT_EXECUTION"], change_id="CHG7001"),
            execution(2, "Security Group Change by Wrong Principal", ["UNAUTHORIZED_IMPLEMENTER"], change_id="CHG7005"),
            execution(3, "Policy Version Published After Window", ["EXECUTED_OUTSIDE_WINDOW"], change_id="CHG7006"),
            execution(4, "Tag Applied to Wrong Role", ["WRONG_TARGET_RESOURCE", "EXPECTED_OPERATION_MISSING"], change_id="CHG7007"),
            execution(5, "Failed Bucket Tagging", ["FAILED_EXECUTION", "EXPECTED_OPERATION_MISSING"], change_id="CHG7008"),
            execution(6, "Operator Role Investigation", ["UNAUTHORIZED_IMPLEMENTER", "POSSIBLE_UNAPPROVED_ACTIVITY"], user=roles["operator"]),
            execution(7, "Implementer Role Investigation", ["COMPLIANT_EXECUTION"], user=implementer),
        ]
        return {"changes": changes, "access_requests": access_requests, "policy_sources": policy_sources,
                "demo_scenarios": demo_scenarios, "execution_scenarios": execution_scenarios}

    def status(self) -> None:
        if not MANIFEST.exists():
            print("No testbed manifest; nothing is provisioned.")
            return
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        resources = manifest["resources"]
        print(f"Account {manifest['account_id']} ({manifest['region']}), provisioned {manifest['provisioned_at']} by {manifest['provisioned_by']}")
        print(f"Evidence window {manifest.get('evidence_start')} to {manifest.get('evidence_end')}")
        print(f"  bucket: {resources['bucket']}")
        print(f"  security group: {resources['security_group']}")
        for arn in resources["managed_policies"]:
            print(f"  managed policy: {arn}")
        for item in resources["roles"]:
            print(f"  role: {item['name']}")
        if manifest.get("evidence_start"):
            sys.path.insert(0, str(PROJECT_ROOT))
            from backend.repositories.aws_live import AwsLiveSource
            events = AwsLiveSource(MANIFEST.parent).execution_events()
            print(f"CloudTrail scenario events visible now: {len(events)} (6 expected once delivery completes)")
            for event in events:
                print(f"  {event['eventTime']} {event['eventName']:<32} {event.get('errorCode') or 'OK':<12} {', '.join(r['ARN'] for r in event['resources'])}")

    def teardown(self) -> None:
        if not MANIFEST.exists():
            print("No testbed manifest; nothing to tear down.")
            return
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        resources = manifest["resources"]
        for item in resources["roles"]:
            name = item["name"]
            _ignore({"NoSuchEntity"}, lambda: self.iam.delete_role_policy(RoleName=name, PolicyName=item["inline_policy"]))
            _ignore({"NoSuchEntity"}, lambda: self.iam.delete_role_permissions_boundary(RoleName=name))
            _ignore({"NoSuchEntity"}, lambda: self.iam.delete_role(RoleName=name))
            print(f"  deleted role {name}")
        for arn in resources["managed_policies"]:
            try:
                for version in self.iam.list_policy_versions(PolicyArn=arn)["Versions"]:
                    if not version["IsDefaultVersion"]:
                        self.iam.delete_policy_version(PolicyArn=arn, VersionId=version["VersionId"])
                self.iam.delete_policy(PolicyArn=arn)
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "NoSuchEntity":
                    raise
            print(f"  deleted managed policy {arn.rsplit('/', 1)[1]}")
        if resources["security_group"]:
            group_id = resources["security_group"]
            _ignore({"InvalidGroup.NotFound"}, lambda: self.ec2.delete_security_group(GroupId=group_id))
            print(f"  deleted security group {group_id}")
        if resources["bucket"]:
            bucket = resources["bucket"]
            try:
                listing = self.s3.list_object_versions(Bucket=bucket)
                for item in listing.get("Versions", []) + listing.get("DeleteMarkers", []):
                    self.s3.delete_object(Bucket=bucket, Key=item["Key"], VersionId=item["VersionId"])
                self.s3.delete_bucket(Bucket=bucket)
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "NoSuchBucket":
                    raise
            print(f"  deleted bucket {bucket}")
        MANIFEST.unlink()
        print("Teardown complete; manifest removed.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["provision", "status", "teardown"])
    parser.add_argument("--region", default=os.getenv("ARCA_AWS_LIVE_REGION") or os.getenv("AWS_REGION") or "us-east-1")
    parser.add_argument("--vpc-id", help="VPC for the unattached test security group (default VPC or this instance's VPC otherwise)")
    args = parser.parse_args()
    getattr(Testbed(args.region, args.vpc_id), args.command)()


if __name__ == "__main__":
    main()
