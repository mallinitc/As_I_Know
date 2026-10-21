"""Generate deterministic, fully synthetic Azure evidence for the ARCA demo."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "azure"
SUB = "00000000-1111-2222-3333-444444444444"
TENANT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
BASE = f"/subscriptions/{SUB}"
RG = f"{BASE}/resourceGroups/rg-arca-prod"


def rid(provider, kind, name):
    return f"{RG}/providers/{provider}/{kind}/{name}"


def stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


resources = []
resource_specs = [
    ("Microsoft.Storage", "storageAccounts", "starchprod", 6),
    ("Microsoft.Compute", "virtualMachines", "vm-arca-prod", 6),
    ("Microsoft.Web", "sites", "app-arca-prod", 6),
    ("Microsoft.KeyVault", "vaults", "kv-arca-prod", 4),
    ("Microsoft.Sql", "servers/databases", "sql-arca-prod/db", 4),
    ("Microsoft.Network", "networkSecurityGroups", "nsg-arca-prod", 4),
]
for provider, kind, prefix, count in resource_specs:
    for number in range(1, count + 1):
        name = f"{prefix}{number:02d}"
        resources.append({
            "resource_id": rid(provider, kind, name), "name": name, "type": f"{provider}/{kind}",
            "subscription_id": SUB, "resource_group": "rg-arca-prod", "location": "centralindia",
            "environment": "production", "criticality": "high" if number <= 2 else "moderate",
            "tags": {"application": "ARCA", "owner": "cloud-platform", "synthetic": "true"},
        })

role_specs = [
    ("storage-contrib", "Storage Account Contributor", ["Microsoft.Storage/storageAccounts/read", "Microsoft.Storage/storageAccounts/write"]),
    ("vm-contrib", "Virtual Machine Contributor", ["Microsoft.Compute/virtualMachines/*"]),
    ("web-contrib", "Website Contributor", ["Microsoft.Web/sites/*"]),
    ("kv-contrib", "Key Vault Contributor", ["Microsoft.KeyVault/vaults/*"]),
    ("sql-contrib", "SQL DB Contributor", ["Microsoft.Sql/servers/databases/*"]),
    ("network-contrib", "Network Contributor", ["Microsoft.Network/networkSecurityGroups/*"]),
    ("reader", "Reader", ["*/read"]),
    ("contributor", "Contributor", ["*"]),
    ("uaa", "User Access Administrator", ["Microsoft.Authorization/roleAssignments/*"]),
]
role_definitions = []
for index, (slug, name, actions) in enumerate(role_specs, 1):
    role_definitions.append({
        "role_definition_id": f"{BASE}/providers/Microsoft.Authorization/roleDefinitions/10000000-0000-0000-0000-{index:012d}",
        "role_name": name, "role_type": "BuiltInRole", "synthetic_key": slug,
        "permissions": [{"actions": actions, "not_actions": [], "data_actions": [], "not_data_actions": []}],
        "assignable_scopes": [BASE],
    })
roles = {x["synthetic_key"]: x for x in role_definitions}

actors = [{"principal_id": f"20000000-0000-0000-0000-{i:012d}", "principal_name": f"engineer{i:02d}@example.invalid", "principal_type": "User"} for i in range(1, 13)]

scenario_specs = [
    # operation, resource index, role, scope style, scenario
    ("Microsoft.Storage/storageAccounts/write", 0, "storage-contrib", "resource", "VALID_APPROVED_CHANGE"),
    ("Microsoft.Compute/virtualMachines/restart/action", 6, "vm-contrib", "resource", "INCOMPLETE_CHANGE_REQUEST"),
    ("Microsoft.Web/sites/write", 12, "contributor", "resource_group", "OVERPRIVILEGED_PIM_REQUEST"),
    ("Microsoft.Compute/virtualMachines/delete", 7, "reader", "resource", "INSUFFICIENT_RBAC_PERMISSIONS"),
    ("Microsoft.Storage/storageAccounts/write", 1, "storage-contrib", "subscription", "EXCESSIVE_SUBSCRIPTION_SCOPE"),
    ("Microsoft.Web/sites/write", 13, "web-contrib", "resource", "PIM_EXTENDS_BEYOND_CHANGE_WINDOW"),
    ("Microsoft.Storage/storageAccounts/write", 2, "storage-contrib", "resource", "UNEXPECTED_RESOURCE_MODIFICATION"),
    ("Microsoft.Compute/virtualMachines/start/action", 8, "vm-contrib", "resource", "ACTIVITY_OUTSIDE_CHANGE_WINDOW"),
    ("Microsoft.KeyVault/vaults/write", 18, "kv-contrib", "resource", "UNEXPECTED_ENGINEER"),
    ("Microsoft.Sql/servers/databases/write", 22, "sql-contrib", "resource", "VALID_APPROVED_CHANGE"),
    ("Microsoft.Authorization/roleAssignments/delete", 0, "uaa", "resource_group", "STORAGE_ACCESS_LOSS_ROLE_REMOVAL"),
    ("Microsoft.Storage/storageAccounts/write", 3, "storage-contrib", "resource", "STORAGE_ACCESS_LOSS_FIREWALL"),
    ("Microsoft.Network/networkSecurityGroups/write", 26, "network-contrib", "resource", "VALID_APPROVED_CHANGE"),
    ("Microsoft.Web/sites/config/write", 14, "web-contrib", "resource", "VALID_APPROVED_CHANGE"),
    ("Microsoft.Compute/virtualMachines/deallocate/action", 9, "vm-contrib", "resource", "VALID_APPROVED_CHANGE"),
    ("Microsoft.Storage/storageAccounts/write", 4, "storage-contrib", "resource", "VALID_APPROVED_CHANGE"),
    ("Microsoft.Sql/servers/databases/write", 23, "sql-contrib", "resource", "VALID_APPROVED_CHANGE"),
    ("Microsoft.KeyVault/vaults/write", 19, "kv-contrib", "resource", "VALID_APPROVED_CHANGE"),
    ("Microsoft.Network/networkSecurityGroups/securityRules/write", 27, "network-contrib", "resource", "VALID_APPROVED_CHANGE"),
    ("Microsoft.Web/sites/restart/action", 15, "web-contrib", "resource", "VALID_APPROVED_CHANGE"),
]

changes, pim_requests, assignments, events = [], [], [], []
start_base = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)
for index, (operation, resource_index, role_key, scope_style, scenario) in enumerate(scenario_specs, 1):
    change_id = f"CHG-AZ-{2000 + index}"
    actor = actors[(index - 1) % len(actors)]
    start = start_base + timedelta(hours=index * 2)
    end = start + timedelta(hours=1)
    target = resources[resource_index]["resource_id"]
    expected_resource = target
    if scenario == "STORAGE_ACCESS_LOSS_ROLE_REMOVAL":
        expected_resource = f"{target}/providers/Microsoft.Authorization/roleAssignments/30000000-0000-0000-0000-000000000011"
    description = f"Implement approved synthetic Azure operation {operation} on {resources[resource_index]['name']}."
    if scenario == "INCOMPLETE_CHANGE_REQUEST": description = ""
    changes.append({
        "sys_id": f"sn-az-{index:04d}", "change_id": change_id, "provider": "azure", "tenant_id": TENANT,
        "environment": "production", "requested_by": f"requestor{index:02d}@example.invalid", "implementer": actor,
        "start": stamp(start), "end": stamp(end), "description": description, "risk": "moderate",
        "state": "approved", "scenario": scenario,
        "expected": [{"operation": operation, "resource_id": expected_resource}],
    })
    role = roles[role_key]
    scope = target if scope_style == "resource" else (RG if scope_style == "resource_group" else BASE)
    pim_start, pim_end = start, end
    if scenario == "PIM_EXTENDS_BEYOND_CHANGE_WINDOW": pim_start, pim_end = start - timedelta(hours=1), end + timedelta(hours=3)
    request_id = f"pim-az-{index:04d}"
    pim_requests.append({
        "pim_request_id": request_id, "change_id": change_id, "principal_id": actor["principal_id"],
        "principal_name": actor["principal_name"], "principal_type": "User", "request_type": "SelfActivate",
        "role_definition_id": role["role_definition_id"], "role_name": role["role_name"], "scope": scope,
        "justification": f"Implement approved synthetic change {change_id}", "status": "Approved",
        "schedule": {"start": stamp(pim_start), "end": stamp(pim_end), "expiration_type": "AfterDuration", "duration": f"PT{int((pim_end-pim_start).total_seconds()/3600)}H"},
        "ticket": {"system": "ServiceNow", "number": change_id}, "scenario": scenario,
    })
    assignments.append({
        "assignment_id": f"rbac-az-{index:04d}", "principal_id": actor["principal_id"], "principal_type": "User",
        "role_definition_id": role["role_definition_id"], "role_name": role["role_name"], "scope": scope,
        "assignment_type": "Active", "source": "PIM", "pim_request_id": request_id,
        "valid_from": stamp(pim_start), "valid_to": stamp(pim_end), "condition": None, "condition_version": None,
    })

    event_actor = actor
    event_time = start + timedelta(minutes=25)
    event_resource = expected_resource
    if scenario == "UNEXPECTED_RESOURCE_MODIFICATION": event_resource = resources[3]["resource_id"]
    if scenario == "ACTIVITY_OUTSIDE_CHANGE_WINDOW": event_time = end + timedelta(minutes=35)
    if scenario == "UNEXPECTED_ENGINEER": event_actor = actors[(index + 2) % len(actors)]
    properties = {"synthetic_scenario": scenario}
    if scenario == "STORAGE_ACCESS_LOSS_ROLE_REMOVAL": properties["affected_resource_id"] = target
    if scenario == "STORAGE_ACCESS_LOSS_FIREWALL": properties["changed_settings"] = ["networkAcls"]
    events.append({
        "event_data_id": f"az-event-{len(events)+1:04d}", "correlation_id": f"az-corr-{index:04d}",
        "event_timestamp": stamp(event_time), "category": "Administrative", "caller": event_actor["principal_name"],
        "caller_principal_id": event_actor["principal_id"],
        "operation_name": {"value": operation, "localized_value": operation.split("/")[-1].title()},
        "authorization": {"action": operation, "scope": event_resource}, "resource_id": event_resource,
        "resource_group": "rg-arca-prod", "subscription_id": SUB,
        "status": {"value": "Succeeded", "localized_value": "Succeeded"}, "sub_status": {"value": "OK"}, "properties": properties,
    })

# Ten successful production writes deliberately have no matching approved record.
write_operations = [
    "Microsoft.Storage/storageAccounts/write", "Microsoft.Compute/virtualMachines/delete",
    "Microsoft.Web/sites/config/write", "Microsoft.Network/networkSecurityGroups/securityRules/write",
    "Microsoft.KeyVault/vaults/write", "Microsoft.Sql/servers/databases/write",
]
for number in range(10):
    resource = resources[(number * 3 + 5) % len(resources)]
    operation = write_operations[number % len(write_operations)]
    actor = actors[(number + 4) % len(actors)]
    events.append({
        "event_data_id": f"az-event-{len(events)+1:04d}", "correlation_id": f"az-undoc-{number+1:04d}",
        "event_timestamp": stamp(datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc) + timedelta(minutes=number * 17)),
        "category": "Administrative", "caller": actor["principal_name"], "caller_principal_id": actor["principal_id"],
        "operation_name": {"value": operation, "localized_value": "Synthetic undocumented production write"},
        "authorization": {"action": operation, "scope": resource["resource_id"]}, "resource_id": resource["resource_id"],
        "resource_group": resource["resource_group"], "subscription_id": SUB,
        "status": {"value": "Succeeded", "localized_value": "Succeeded"}, "sub_status": {"value": "OK"},
        "properties": {"synthetic_scenario": "UNDOCUMENTED_PRODUCTION_MODIFICATION"},
    })

# Fill the corpus with benign read evidence, distributed across every resource.
while len(events) < 100:
    number = len(events) + 1
    resource = resources[(number - 1) % len(resources)]
    actor = actors[(number - 1) % len(actors)]
    operation = f"{resource['type']}/read"
    events.append({
        "event_data_id": f"az-event-{number:04d}", "correlation_id": f"az-read-{number:04d}",
        "event_timestamp": stamp(datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=number * 5)),
        "category": "Administrative", "caller": actor["principal_name"], "caller_principal_id": actor["principal_id"],
        "operation_name": {"value": operation, "localized_value": "Read synthetic resource"},
        "authorization": {"action": operation, "scope": resource["resource_id"]}, "resource_id": resource["resource_id"],
        "resource_group": resource["resource_group"], "subscription_id": SUB,
        "status": {"value": "Succeeded", "localized_value": "Succeeded"}, "sub_status": {"value": "OK"},
        "properties": {"synthetic_scenario": "BENIGN_READ"},
    })

write("servicenow_changes.json", changes)
write("pim_requests.json", pim_requests)
write("rbac_assignments.json", assignments)
write("role_definitions.json", role_definitions)
write("resources.json", resources)
write("activity_logs.json", events)
print({"changes": len(changes), "pim_requests": len(pim_requests), "rbac_assignments": len(assignments),
       "role_definitions": len(role_definitions), "resources": len(resources), "activity_logs": len(events)})
