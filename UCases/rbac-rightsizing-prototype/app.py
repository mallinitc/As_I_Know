import json
import random
from datetime import datetime

import pandas as pd
import streamlit as st


# =========================================================
# Page Configuration
# =========================================================

st.set_page_config(
    page_title="UC2 - RBAC Group Access Review",
    layout="wide"
)


# =========================================================
# Mock Data Generator - Prototype Only
# =========================================================

random.seed(42)


def generate_members(prefix, count, domain="contoso.com"):
    members = []
    for i in range(1, count + 1):
        first = f"{prefix.lower()}user{i:02d}"
        members.append({
            "user_id": f"{prefix.lower()}-usr-{i:03d}",
            "name": f"{prefix} User {i:02d}",
            "upn": f"{first}@{domain}",
            "department": random.choice([
                "Cloud Platform",
                "Network Operations",
                "Application Support",
                "Storage Operations",
                "Security Engineering",
                "DevOps",
                "Audit"
            ]),
            "location": random.choice([
                "Hyderabad",
                "Bangalore",
                "Pune",
                "Chennai",
                "Mumbai",
                "Remote"
            ])
        })
    return members


GROUPS = [
    {
        "group_id": "grp-001",
        "group_name": "AZR-PROD-NETWORK-OPERATIONS-GRP",
        "business_unit": "Infrastructure",
        "application": "Enterprise Network Platform",
        "environment": "Prod",
        "members": generate_members("NetworkOps", 28)
    },
    {
        "group_id": "grp-002",
        "group_name": "AZR-PROD-STORAGE-SUPPORT-GRP",
        "business_unit": "Cloud Operations",
        "application": "Enterprise Storage Services",
        "environment": "Prod",
        "members": generate_members("StorageOps", 22)
    },
    {
        "group_id": "grp-003",
        "group_name": "AZR-NONPROD-AUDIT-READERS-GRP",
        "business_unit": "Risk and Compliance",
        "application": "Audit Reporting",
        "environment": "Non-Prod",
        "members": generate_members("Audit", 35)
    },
    {
        "group_id": "grp-004",
        "group_name": "AZR-PROD-COMPUTE-OPERATIONS-GRP",
        "business_unit": "Cloud Platform",
        "application": "Compute Operations",
        "environment": "Prod",
        "members": generate_members("ComputeOps", 24)
    },
    {
        "group_id": "grp-005",
        "group_name": "AZR-PROD-KEYVAULT-SUPPORT-GRP",
        "business_unit": "Security Engineering",
        "application": "Secrets Management",
        "environment": "Prod",
        "members": generate_members("KeyVaultOps", 14)
    },
    {
        "group_id": "grp-006",
        "group_name": "BREAKGLASS-AZURE-PLATFORM-ADMINS",
        "business_unit": "Security Engineering",
        "application": "Emergency Access",
        "environment": "Prod",
        "members": generate_members("BreakGlass", 4)
    }
]


ROLE_ASSIGNMENTS = [
    {
        "assignment_id": "ra-001",
        "group_id": "grp-001",
        "role_name": "Network Contributor",
        "scope": "/subscriptions/sub-prod-001/resourceGroups/rg-network-prod",
        "assignment_type": "Permanent",
        "environment": "Prod"
    },
    {
        "assignment_id": "ra-002",
        "group_id": "grp-002",
        "role_name": "Storage Account Contributor",
        "scope": "/subscriptions/sub-prod-001/resourceGroups/rg-storage-prod",
        "assignment_type": "Permanent",
        "environment": "Prod"
    },
    {
        "assignment_id": "ra-003",
        "group_id": "grp-003",
        "role_name": "Reader",
        "scope": "/subscriptions/sub-nonprod-001",
        "assignment_type": "Permanent",
        "environment": "Non-Prod"
    },
    {
        "assignment_id": "ra-004",
        "group_id": "grp-004",
        "role_name": "Virtual Machine Contributor",
        "scope": "/subscriptions/sub-prod-001/resourceGroups/rg-compute-prod",
        "assignment_type": "Permanent",
        "environment": "Prod"
    },
    {
        "assignment_id": "ra-005",
        "group_id": "grp-005",
        "role_name": "Key Vault Contributor",
        "scope": "/subscriptions/sub-prod-001/resourceGroups/rg-security-prod",
        "assignment_type": "Permanent",
        "environment": "Prod"
    },
    {
        "assignment_id": "ra-006",
        "group_id": "grp-006",
        "role_name": "Owner",
        "scope": "/subscriptions/sub-prod-001",
        "assignment_type": "Permanent",
        "environment": "Prod"
    }
]


ROLE_DEFINITIONS = {
    "Network Contributor": {
        "role_type": "write_bearing",
        "has_data_actions": False,
        "risk_level": "High",
        "observable_actions": [
            "Microsoft.Network/networkSecurityGroups/securityRules/write",
            "Microsoft.Network/networkSecurityGroups/write",
            "Microsoft.Network/networkSecurityGroups/delete",
            "Microsoft.Network/virtualNetworks/write",
            "Microsoft.Network/virtualNetworks/subnets/write",
            "Microsoft.Network/routeTables/write",
            "Microsoft.Network/publicIPAddresses/write",
            "Microsoft.Network/loadBalancers/write",
            "Microsoft.Network/privateEndpoints/write",
            "Microsoft.Network/networkInterfaces/write"
        ],
        "unobservable_actions": [
            "Microsoft.Network/*/read"
        ]
    },
    "Storage Account Contributor": {
        "role_type": "write_bearing",
        "has_data_actions": True,
        "risk_level": "High",
        "observable_actions": [
            "Microsoft.Storage/storageAccounts/write",
            "Microsoft.Storage/storageAccounts/delete",
            "Microsoft.Storage/storageAccounts/listKeys/action",
            "Microsoft.Storage/storageAccounts/regenerateKey/action",
            "Microsoft.Storage/storageAccounts/blobServices/write",
            "Microsoft.Storage/storageAccounts/fileServices/write"
        ],
        "unobservable_actions": [
            "Microsoft.Storage/storageAccounts/read",
            "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read",
            "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/write"
        ]
    },
    "Reader": {
        "role_type": "read_only",
        "has_data_actions": False,
        "risk_level": "Low",
        "observable_actions": [],
        "unobservable_actions": [
            "*/read"
        ]
    },
    "Virtual Machine Contributor": {
        "role_type": "write_bearing",
        "has_data_actions": False,
        "risk_level": "Medium",
        "observable_actions": [
            "Microsoft.Compute/virtualMachines/write",
            "Microsoft.Compute/virtualMachines/delete",
            "Microsoft.Compute/virtualMachines/start/action",
            "Microsoft.Compute/virtualMachines/restart/action",
            "Microsoft.Compute/virtualMachines/powerOff/action",
            "Microsoft.Compute/virtualMachines/deallocate/action",
            "Microsoft.Compute/disks/write",
            "Microsoft.Network/networkInterfaces/write"
        ],
        "unobservable_actions": [
            "Microsoft.Compute/*/read"
        ]
    },
    "Key Vault Contributor": {
        "role_type": "write_bearing",
        "has_data_actions": True,
        "risk_level": "High",
        "observable_actions": [
            "Microsoft.KeyVault/vaults/write",
            "Microsoft.KeyVault/vaults/delete",
            "Microsoft.KeyVault/vaults/accessPolicies/write",
            "Microsoft.KeyVault/vaults/privateEndpointConnections/write"
        ],
        "unobservable_actions": [
            "Microsoft.KeyVault/vaults/read",
            "Microsoft.KeyVault/vaults/secrets/read",
            "Microsoft.KeyVault/vaults/secrets/write",
            "Microsoft.KeyVault/vaults/keys/read"
        ]
    },
    "Owner": {
        "role_type": "high_privilege",
        "has_data_actions": False,
        "risk_level": "Critical",
        "observable_actions": [
            "Microsoft.Authorization/roleAssignments/write",
            "Microsoft.Authorization/roleAssignments/delete",
            "Microsoft.Authorization/policyAssignments/write",
            "Microsoft.Resources/deployments/write",
            "Microsoft.Resources/subscriptions/resourceGroups/write",
            "Microsoft.Network/networkSecurityGroups/securityRules/write",
            "Microsoft.Compute/virtualMachines/write",
            "Microsoft.Storage/storageAccounts/write"
        ],
        "unobservable_actions": [
            "*/read"
        ]
    }
}


EXCLUDED_GROUPS = [
    "BREAKGLASS-AZURE-PLATFORM-ADMINS"
]


# =========================================================
# Mock Activity Logs
# =========================================================


def find_group(group_id):
    for group in GROUPS:
        if group["group_id"] == group_id:
            return group
    return None


def get_upn(group_id, member_index):
    group = find_group(group_id)
    return group["members"][member_index]["upn"]


ACTIVITY_LOGS = []

# Network group: low usage, only 3 operations by 2 users.
ACTIVITY_LOGS.extend([
    {
        "time_generated": "2026-01-12T10:15:00Z",
        "caller": get_upn("grp-001", 0),
        "operation": "Microsoft.Network/networkSecurityGroups/securityRules/write",
        "resource_id": "/subscriptions/sub-prod-001/resourceGroups/rg-network-prod/providers/Microsoft.Network/networkSecurityGroups/nsg-app-001",
        "resource_group": "rg-network-prod",
        "status": "Success",
        "change_reference": "CHG0012456"
    },
    {
        "time_generated": "2026-03-20T14:40:00Z",
        "caller": get_upn("grp-001", 0),
        "operation": "Microsoft.Network/networkSecurityGroups/securityRules/write",
        "resource_id": "/subscriptions/sub-prod-001/resourceGroups/rg-network-prod/providers/Microsoft.Network/networkSecurityGroups/nsg-app-002",
        "resource_group": "rg-network-prod",
        "status": "Success",
        "change_reference": "CHG0013321"
    },
    {
        "time_generated": "2026-05-02T09:25:00Z",
        "caller": get_upn("grp-001", 5),
        "operation": "Microsoft.Network/routeTables/write",
        "resource_id": "/subscriptions/sub-prod-001/resourceGroups/rg-network-prod/providers/Microsoft.Network/routeTables/rt-app-001",
        "resource_group": "rg-network-prod",
        "status": "Success",
        "change_reference": "CHG0014902"
    }
])

# Storage group: no activity by group members, only outside-user activity.
ACTIVITY_LOGS.extend([
    {
        "time_generated": "2026-04-05T08:20:00Z",
        "caller": "external.user@contoso.com",
        "operation": "Microsoft.Storage/storageAccounts/write",
        "resource_id": "/subscriptions/sub-prod-001/resourceGroups/rg-storage-prod/providers/Microsoft.Storage/storageAccounts/stprod001",
        "resource_group": "rg-storage-prod",
        "status": "Success",
        "change_reference": "CHG0013800"
    }
])

# Compute group: regular usage by many members.
compute_operations = [
    "Microsoft.Compute/virtualMachines/start/action",
    "Microsoft.Compute/virtualMachines/restart/action",
    "Microsoft.Compute/virtualMachines/powerOff/action",
    "Microsoft.Compute/virtualMachines/write",
    "Microsoft.Compute/disks/write",
    "Microsoft.Network/networkInterfaces/write"
]

for i in range(22):
    ACTIVITY_LOGS.append({
        "time_generated": f"2026-05-{(i % 20) + 1:02d}T{(8 + i % 10):02d}:10:00Z",
        "caller": get_upn("grp-004", i % 10),
        "operation": compute_operations[i % len(compute_operations)],
        "resource_id": f"/subscriptions/sub-prod-001/resourceGroups/rg-compute-prod/providers/Microsoft.Compute/virtualMachines/vm-prod-{i % 6 + 1:03d}",
        "resource_group": "rg-compute-prod",
        "status": "Success",
        "change_reference": f"CHG0015{i:03d}"
    })

# Break-glass group: rare but sensitive activity.
ACTIVITY_LOGS.extend([
    {
        "time_generated": "2026-02-18T23:10:00Z",
        "caller": get_upn("grp-006", 0),
        "operation": "Microsoft.Authorization/roleAssignments/write",
        "resource_id": "/subscriptions/sub-prod-001",
        "resource_group": "",
        "status": "Success",
        "change_reference": "INC0007812"
    }
])


# =========================================================
# Helper Functions
# =========================================================


def render_card(title, value, min_height=95):
    st.markdown(
        f"""
        <div style="
            padding: 12px;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            background-color: #f9fafb;
            min-height: {min_height}px;
            overflow-wrap: break-word;
            word-wrap: break-word;
            white-space: normal;
            margin-bottom: 8px;
        ">
            <div style="
                font-size: 13px;
                color: #6b7280;
                margin-bottom: 8px;
                font-weight: 600;
            ">
                {title}
            </div>
            <div style="
                font-size: 18px;
                color: #111827;
                font-weight: 700;
                line-height: 1.3;
            ">
                {value}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def get_group_by_name(group_name):
    for group in GROUPS:
        if group["group_name"] == group_name:
            return group
    return None


def get_assignments_for_group(group_id):
    return [a for a in ROLE_ASSIGNMENTS if a["group_id"] == group_id]


def get_role_definition(role_name):
    return ROLE_DEFINITIONS.get(role_name)


def scope_matches(resource_id, assignment_scope):
    return resource_id.lower().startswith(assignment_scope.lower())


def match_activity_logs(group, assignment):
    role_def = get_role_definition(assignment["role_name"])
    if not role_def:
        return []

    member_upns = [m["upn"].lower() for m in group["members"]]
    observable_actions = [a.lower() for a in role_def["observable_actions"]]

    matched_logs = []

    for log in ACTIVITY_LOGS:
        if log["status"] != "Success":
            continue

        caller_match = log["caller"].lower() in member_upns
        operation_match = log["operation"].lower() in observable_actions
        scope_match = scope_matches(log["resource_id"], assignment["scope"])

        if caller_match and operation_match and scope_match:
            matched_logs.append(log)

    return matched_logs


def get_last_used(matched_logs):
    if not matched_logs:
        return "Not observed"

    dates = [
        datetime.fromisoformat(log["time_generated"].replace("Z", "+00:00"))
        for log in matched_logs
    ]

    return max(dates).strftime("%Y-%m-%d")


def calculate_recommendation(group, assignment, matched_logs):
    role_def = get_role_definition(assignment["role_name"])

    if group["group_name"] in EXCLUDED_GROUPS:
        return {
            "decision": "MANUAL_REVIEW_REQUIRED",
            "confidence": "Low",
            "reason": "This group is marked as a break-glass or emergency access group. It should not be automatically removed or downgraded based only on low usage."
        }

    if not role_def:
        return {
            "decision": "MANUAL_REVIEW_REQUIRED",
            "confidence": "Low",
            "reason": "Role definition was not found in the local role catalog."
        }

    total_invocations = len(matched_logs)
    distinct_members = len(set([log["caller"] for log in matched_logs]))
    total_members = len(group["members"])
    member_usage_ratio = distinct_members / total_members if total_members else 0

    role_type = role_def["role_type"]
    has_data_actions = role_def["has_data_actions"]

    if role_type == "read_only":
        return {
            "decision": "KEEP_LOW_PRIORITY",
            "confidence": "Medium",
            "reason": "This is a read-only role. Read operations are generally not visible in Azure Activity Log, so zero observed activity should not be treated as evidence that the role is unused."
        }

    if has_data_actions and total_invocations == 0:
        return {
            "decision": "INSUFFICIENT_VISIBILITY",
            "confidence": "Low",
            "reason": "This role includes data-plane or read-heavy permissions. No matching management-plane activity was observed, but data-plane diagnostic logs are required before recommending removal."
        }

    if total_invocations == 0:
        return {
            "decision": "REMOVE_CANDIDATE",
            "confidence": "High",
            "reason": "No observable write/action/delete operations covered by this role were performed by current group members within the assignment scope during the review window."
        }

    if total_invocations <= 3 or distinct_members <= 2 or member_usage_ratio <= 0.10:
        return {
            "decision": "MAKE_PIM_ELIGIBLE",
            "confidence": "High",
            "reason": "The role was used rarely or by a small percentage of group members. Permanent standing access may not be justified. Converting the assignment to PIM eligible is recommended."
        }

    return {
        "decision": "KEEP_PERMANENT",
        "confidence": "Medium",
        "reason": "The role shows regular usage by multiple members. Permanent assignment may be justified, but scope and role fit should still be periodically reviewed."
    }


def build_explanation(group, assignment, matched_logs, recommendation):
    role_def = get_role_definition(assignment["role_name"])

    total_members = len(group["members"])
    total_invocations = len(matched_logs)
    distinct_members = len(set([log["caller"] for log in matched_logs]))
    member_usage_ratio = round((distinct_members / total_members) * 100, 2) if total_members else 0
    last_used = get_last_used(matched_logs)

    if role_def:
        role_type = role_def["role_type"]
        risk_level = role_def["risk_level"]
        observable_count = len(role_def["observable_actions"])
        unobservable_count = len(role_def["unobservable_actions"])
    else:
        role_type = "Unknown"
        risk_level = "Unknown"
        observable_count = 0
        unobservable_count = 0

    explanation = f"""
The group **{group['group_name']}** belongs to the **{group['business_unit']}** business unit and is associated with **{group['application']}** in the **{group['environment']}** environment.

This group currently has **{total_members} member(s)** and is assigned the role **{assignment['role_name']}** at the following scope:

`{assignment['scope']}`

Role classification:
- Role type: **{role_type}**
- Risk level: **{risk_level}**
- Observable management-plane actions tracked in this prototype: **{observable_count}**
- Unobservable/read/data-plane actions: **{unobservable_count}**

During the review window:
- Matching observable operations found: **{total_invocations}**
- Distinct current group members who performed matching operations: **{distinct_members}**
- Percentage of group members observed using this role capability: **{member_usage_ratio}%**
- Last observed usage: **{last_used}**

Recommendation: **{recommendation['decision']}**

Confidence: **{recommendation['confidence']}**

Reason:
{recommendation['reason']}

Important interpretation:
This prototype does not claim that this exact RBAC assignment authorized the operation. It confirms that operations covered by this role were performed by current members of this group within the assignment scope. In a real Azure environment, the same user may also have access through another group, direct assignment, inherited assignment, or PIM activation.
"""
    return explanation.strip()


# =========================================================
# Streamlit UI
# =========================================================

st.title("UC2 - RBAC Group Access Review and Right-Sizing")
st.caption("Prototype using organization-style mock Azure RBAC assignments and mock Azure Activity Logs")

st.sidebar.header("Review Input")

group_names = [g["group_name"] for g in GROUPS]
selected_group_name = st.sidebar.selectbox("Select Security Group", group_names)

lookback_days = st.sidebar.slider(
    "Lookback Period",
    min_value=30,
    max_value=180,
    value=180,
    step=30
)

selected_group = get_group_by_name(selected_group_name)
assignments = get_assignments_for_group(selected_group["group_id"])

st.subheader("Organization Group Overview")

overview_col1, overview_col2, overview_col3, overview_col4 = st.columns(4)

with overview_col1:
    render_card("Group", selected_group["group_name"], min_height=110)

with overview_col2:
    render_card("Members", len(selected_group["members"]), min_height=110)

with overview_col3:
    render_card("Environment", selected_group["environment"], min_height=110)

with overview_col4:
    render_card("Lookback Days", lookback_days, min_height=110)

st.write("### Group Details")

group_details = {
    "Group Name": selected_group["group_name"],
    "Business Unit": selected_group["business_unit"],
    "Application": selected_group["application"],
    "Environment": selected_group["environment"],
    "Member Count": len(selected_group["members"])
}

st.json(group_details)

st.write("### Group Members")
members_df = pd.DataFrame(selected_group["members"])
st.dataframe(members_df, use_container_width=True, height=260)

st.write("### RBAC Assignments for Selected Group")

if not assignments:
    st.warning("No role assignments found for this group.")
else:
    assignment_df = pd.DataFrame(assignments)
    st.dataframe(assignment_df, use_container_width=True)

    assignment_labels = [
        f"{a['role_name']} | {a['scope']}" for a in assignments
    ]

    selected_assignment_label = st.selectbox(
        "Select Role Assignment to Review",
        assignment_labels
    )

    selected_assignment_index = assignment_labels.index(selected_assignment_label)
    selected_assignment = assignments[selected_assignment_index]

    role_def = get_role_definition(selected_assignment["role_name"])
    matched_logs = match_activity_logs(selected_group, selected_assignment)
    recommendation = calculate_recommendation(selected_group, selected_assignment, matched_logs)
    explanation = build_explanation(selected_group, selected_assignment, matched_logs, recommendation)

    total_members = len(selected_group["members"])
    total_invocations = len(matched_logs)
    distinct_members = len(set([log["caller"] for log in matched_logs]))
    member_usage_ratio = round((distinct_members / total_members) * 100, 2) if total_members else 0
    last_used = get_last_used(matched_logs)

    st.divider()

    st.subheader("Access Review Summary")

    summary_col1, summary_col2, summary_col3 = st.columns(3)

    with summary_col1:
        render_card("Role", selected_assignment["role_name"])

    with summary_col2:
        render_card("Assignment Type", selected_assignment["assignment_type"])

    with summary_col3:
        render_card("Recommendation", recommendation["decision"])

    summary_col4, summary_col5, summary_col6 = st.columns(3)

    with summary_col4:
        render_card("Matched Operations", total_invocations)

    with summary_col5:
        render_card("Active Members", f"{distinct_members}/{total_members}")

    with summary_col6:
        render_card("Member Usage Ratio", f"{member_usage_ratio}%")

    st.write("### Role Permission Profile")

    if role_def:
        profile_col1, profile_col2, profile_col3 = st.columns(3)

        with profile_col1:
            render_card("Role Type", role_def["role_type"])

        with profile_col2:
            render_card("Risk Level", role_def["risk_level"])

        with profile_col3:
            render_card("Has Data Actions", str(role_def["has_data_actions"]))

        st.write("#### Observable Management-Plane Actions")
        observable_df = pd.DataFrame(
            role_def["observable_actions"],
            columns=["Observable Action"]
        )
        st.dataframe(observable_df, use_container_width=True, height=240)

        st.write("#### Unobservable / Read / Data-Plane Actions")
        unobservable_df = pd.DataFrame(
            role_def["unobservable_actions"],
            columns=["Unobservable / Read / Data-Plane Action"]
        )
        st.dataframe(unobservable_df, use_container_width=True, height=180)

    else:
        st.warning("Role definition not found.")

    st.write("### Matching Activity Evidence")

    if matched_logs:
        matched_df = pd.DataFrame(matched_logs)
        st.dataframe(matched_df, use_container_width=True, height=260)

        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            st.write("#### Operations by Caller")
            caller_counts = matched_df["caller"].value_counts().reset_index()
            caller_counts.columns = ["caller", "operation_count"]
            st.bar_chart(caller_counts.set_index("caller"))

        with chart_col2:
            st.write("#### Operations by Type")
            operation_counts = matched_df["operation"].value_counts().reset_index()
            operation_counts.columns = ["operation", "operation_count"]
            st.bar_chart(operation_counts.set_index("operation"))

    else:
        st.info("No matching observable activity logs found for this group-role-scope assignment.")

    st.write("### Recommendation")

    decision = recommendation["decision"]

    if decision == "REMOVE_CANDIDATE":
        st.error(f"Decision: {decision}")
    elif decision == "MAKE_PIM_ELIGIBLE":
        st.warning(f"Decision: {decision}")
    elif decision == "KEEP_PERMANENT":
        st.success(f"Decision: {decision}")
    elif decision == "KEEP_LOW_PRIORITY":
        st.info(f"Decision: {decision}")
    elif decision == "INSUFFICIENT_VISIBILITY":
        st.warning(f"Decision: {decision}")
    else:
        st.warning(f"Decision: {decision}")

    rec_col1, rec_col2, rec_col3 = st.columns(3)

    with rec_col1:
        render_card("Confidence", recommendation["confidence"])

    with rec_col2:
        render_card("Last Used", last_used)

    with rec_col3:
        render_card("Member Usage Ratio", f"{member_usage_ratio}%")

    st.write("**Reason:**")
    st.write(recommendation["reason"])

    st.write("### Explanation")
    st.markdown(explanation)

    output_payload = {
        "group": selected_group,
        "assignment": selected_assignment,
        "matched_logs": matched_logs,
        "summary": {
            "total_members": total_members,
            "matched_operations": total_invocations,
            "distinct_members_used": distinct_members,
            "member_usage_ratio": member_usage_ratio,
            "last_used": last_used
        },
        "recommendation": recommendation,
        "explanation": explanation
    }

    st.download_button(
        label="Download Review JSON",
        data=json.dumps(output_payload, indent=2),
        file_name=f"uc2_review_{selected_group['group_name']}.json",
        mime="application/json"
    )
