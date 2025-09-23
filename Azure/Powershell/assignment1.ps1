# =========================
# 1. Azure RBAC: permanent assignment or PIM-eligible
# =========================
function Set-AzureRbacAssignment {
  param(
    [string]$AzureRoleDefinitionIdOrName,
    [string]$TargetObjectId,
    [string]$SubscriptionId,
    [string]$ManagementGroupId,
    [switch]$MakePIMEligible
  )

  $roleDefId = Get-AzureRoleDefinitionId -RoleDefinitionIdOrName $AzureRoleDefinitionIdOrName

  # Build scope
  if ($ManagementGroupId) {
    $scope = "/providers/Microsoft.Management/managementGroups/$ManagementGroupId"
  }
  elseif ($SubscriptionId) {
    $scope = "/subscriptions/$SubscriptionId"
  }
  else {
    throw "Provide either -SubscriptionId or -ManagementGroupId for Azure RBAC scope."
  }

  if (-not $MakePIMEligible) {
    Write-Host "Creating PERMANENT Azure RBAC assignment..." -ForegroundColor Green
    New-AzRoleAssignment -ObjectId $TargetObjectId -RoleDefinitionId $roleDefId -Scope $scope -ErrorAction Stop | Out-Null
    Write-Host "Permanent RBAC assignment created."
    return
  }

  # PIM-eligible via Microsoft Graph PIM for Azure Resources
  Write-Host "Creating PIM-ELIGIBLE Azure RBAC assignment..." -ForegroundColor Yellow

  # Look up ARM role definition id under scope (resource provider path)
  $body = @{
    action                         = "adminAssign"
    justification                  = "PIM eligible by pipeline (Tier $Tier, SNOW $SnowTicketNumber)"
    roleDefinitionId               = "/providers/Microsoft.Authorization/roleDefinitions/$roleDefId"
    scope                          = $scope
    principalId                    = $TargetObjectId
    scheduleInfo                   = @{
      startDateTime = (Get-Date).ToUniversalTime().ToString("o")
      expiration    = @{
        type = "noExpiration"     # change to "afterDateTime" if you want end date
      }
    }
    assignmentState                = "Eligible"
    linkedEligibleRoleAssignmentId = $null
    # Approval chain for Tier 1-2 (approver group)
    approvalSettings               = if ($ThisTier.RequiresApproval) {
      @{
        isApprovalRequired = $true
        approvalStages     = @(@{
            approvalStageTimeOutInDays      = 1
            isApproverJustificationRequired = $true
            escalationEnabled               = $false
            primaryApprovers                = @(@{ id = $ApproverGroupObjectId; isBackup = $false })
          })
      }
    }
    else {
      @{ isApprovalRequired = $false }
    }
  }

  # Endpoint: /beta/roleManagement/azure/roleEligibilityScheduleRequests
  $req = Invoke-MgGraphRequest -Method POST `
    -Uri "https://graph.microsoft.com/beta/roleManagement/azure/roleEligibilityScheduleRequests" `
    -Body ($body | ConvertTo-Json -Depth 10) -ContentType "application/json"

  Write-Host "PIM eligibility request submitted (Azure RBAC). RequestId: $($req.id)"
}


#####################################

<# ================= RBAC_Assignments_App.ps1 (POC-safe header) =================
   - Reads ONLY parameters: -TenantId -AppId -Secret  (no env fallback)
   - Solid try/catch around Az login and Graph login
   - Uses the same SPN for Graph via Get-AzAccessToken
   - DOES NOT ConvertTo-SecureString the Graph token
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$TenantId,   # Entra tenant GUID
  [Parameter(Mandatory = $true)][string]$AppId,      # App registration (client) ID
  [Parameter(Mandatory = $true)][string]$Secret      # Client secret VALUE
)

# ---- Basic validation (never print the secret) ----
if ($TenantId -notmatch '^[0-9a-fA-F-]{36}$') { throw "TenantId is not a valid GUID: $TenantId" }
if ($AppId -notmatch '^[0-9a-fA-F-]{36}$') { throw "AppId is not a valid GUID: $AppId" }

# ---- Build PSCredential for SPN ----
$secPwd = ConvertTo-SecureString $Secret -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential ($AppId, $secPwd)

# ====================== 1) Azure login (try/catch) ======================
Write-Host "Signing in to Azure (Tenant=$TenantId, AppId=$($AppId.Substring(0,8))****) ..." -ForegroundColor Cyan
try {
  Connect-AzAccount -ServicePrincipal -Tenant $TenantId -Credential $cred -ErrorAction Stop | Out-Null
  $ctx = Get-AzContext
  if (-not $ctx) { throw "Azure context is null after login." }
  Write-Host "Azure login OK. Account: $($ctx.Account.Id)" -ForegroundColor Green
}
catch {
  $msg = $_.Exception.Message
  throw "AzLogin failed. Details: $msg
Hints:
  • Verify the SPN has RBAC at your intended scope (MG/Subscription/RG).
  • Check that the client secret is valid (not expired) and belongs to AppId.
  • Ensure Az modules are present/updated: Install-Module Az -Scope CurrentUser"
}

# =================== 2) Microsoft Graph login (try/catch) ===================
# Helper handles both new(-ResourceTypeName) and old(-ResourceUrl) Az.Accounts
function Get-GraphToken {
  try { return (Get-AzAccessToken -ResourceTypeName MSGraph -ErrorAction Stop).Token }
  catch { return (Get-AzAccessToken -ResourceUrl "https://graph.microsoft.com" -ErrorAction Stop).Token }
}

Write-Host "Connecting to Microsoft Graph with the same identity..." -ForegroundColor Cyan
try {
  $graphToken = Get-GraphToken
  if ([string]::IsNullOrWhiteSpace($graphToken)) { throw "Empty Graph token returned." }

  Import-Module Microsoft.Graph -ErrorAction Stop
  Select-MgProfile -Name "beta"
  # IMPORTANT: pass the token as PLAIN STRING (do NOT ConvertTo-SecureString)
  Connect-MgGraph -AccessToken $graphToken -ErrorAction Stop | Out-Null

  $mg = Get-MgContext
  if (-not $mg) { throw "Graph context is null after Connect-MgGraph." }
  Write-Host "Graph connection OK. Tenant: $($mg.TenantId)" -ForegroundColor Green
}
catch {
  $msg = $_.Exception.Message
  throw "GraphLogin failed. Details: $msg
Hints:
  • If you call app-only Graph APIs, ensure the SPN has appropriate Graph app permissions and admin consent.
  • Update Microsoft.Graph module if needed: Install-Module Microsoft.Graph -Scope CurrentUser"
}

# ===================== continue with your script below ======================
# (role selection, New-AzRoleAssignment, PIM eligibility, etc.)
