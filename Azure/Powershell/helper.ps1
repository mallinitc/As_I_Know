# =========================
# 0. Shared Helpers
# =========================

param(
  [ValidateSet('AzureRbacAssign','EntraRoleAssign','CreateRoleAssignableGroup')]
  [string]$Action,

  # Common inputs
  [string]$TenantId,
  [string]$SubscriptionId,              # for Azure RBAC
  [string]$ManagementGroupId,          # for Azure RBAC at MG scope
  [string]$AzureRoleDefinitionIdOrName,# e.g. "Owner" or GUID
  [string]$TargetObjectId,             # group/service principal/managed identity objectId
  [switch]$MakePIMEligible,            # toggle PIM eligibility instead of permanent assignment

  # PIM/Tiering
  [ValidateRange(1,4)]
  [int]$Tier = 3,
  [string]$ApproverGroupObjectId,      # required for Tier 1-2
  [string]$SnowTicketNumber,           # required for Tier 1-2

  # Entra Directory Role assignment
  [string]$DirectoryRoleDisplayName,   # e.g. "Global Reader", "Teams Administrator"
  [string]$AssigneeGroupObjectId,      # Entra group to be assigned to directory role

  # Role-assignable group creation
  [string]$NewGroupDisplayName,
  [string]$NewGroupDescription
)

# ---- Tier policy (duration + approvals) ----
$TierPolicy = @{
  '1' = @{ DurationHours = 4;  RequiresApproval = $true  }
  '2' = @{ DurationHours = 6;  RequiresApproval = $true  }
  '3' = @{ DurationHours = 8;  RequiresApproval = $false }
  '4' = @{ DurationHours = 24; RequiresApproval = $false }
}
$ThisTier = $TierPolicy["$Tier"]

if (($ThisTier.RequiresApproval) -and [string]::IsNullOrWhiteSpace($ApproverGroupObjectId)) {
  throw "Tier $Tier requires approval. Provide -ApproverGroupObjectId."
}
if (($ThisTier.RequiresApproval) -and [string]::IsNullOrWhiteSpace($SnowTicketNumber)) {
  throw "Tier $Tier requires a ServiceNow ticket. Provide -SnowTicketNumber."
}

# ---- Auth helpers ----
function Connect-Cloud {
  param([string]$TenantId,[string]$SubscriptionId)

  Write-Host "Connecting to Azure (Az)..." -ForegroundColor Cyan
  Connect-AzAccount -Tenant $TenantId -Identity:$false -WarningAction SilentlyContinue | Out-Null
  if ($SubscriptionId) { Set-AzContext -SubscriptionId $SubscriptionId | Out-Null }

  Write-Host "Connecting to Microsoft Graph (delegated or workload identity)..." -ForegroundColor Cyan
  # Use both stable and beta (beta needed for some PIM endpoints)
  $Scopes = @(
    "Application.ReadWrite.All",
    "Group.ReadWrite.All",
    "RoleManagement.ReadWrite.Directory",
    "PrivilegedAccess.ReadWrite.AzureAD",
    "PrivilegedAccess.ReadWrite.AzureResources"
  )
  Connect-MgGraph -TenantId $TenantId -Scopes $Scopes | Out-Null
  Select-MgProfile -Name "beta"             # for PIM schedule requests
}

# ---- Utility: map role name->id for Azure RBAC if needed ----
function Get-AzureRoleDefinitionId {
  param([string]$RoleDefinitionIdOrName)

  if ($RoleDefinitionIdOrName -match '^[0-9a-f-]{36}$') { return $RoleDefinitionIdOrName }
  $role = Get-AzRoleDefinition -Name $RoleDefinitionIdOrName -ErrorAction Stop
  return $role.Id
}

# ---- Utility: directory role template -> definition id ----
function Get-DirectoryRoleDefinitionId {
  param([string]$DisplayName)

  # Ensure role is activated in the tenant
  $role = Get-MgDirectoryRole | Where-Object {$_.DisplayName -eq $DisplayName}
  if (-not $role) {
    # Activate from template if needed
    $tmpl = Get-MgDirectoryRoleTemplate | Where-Object {$_.DisplayName -eq $DisplayName}
    if (-not $tmpl) { throw "Directory role '$DisplayName' not found." }
    $role = New-MgDirectoryRole -RoleTemplateId $tmpl.Id
  }
  return $role.Id
}

Connect-Cloud -TenantId $TenantId -SubscriptionId $SubscriptionId
