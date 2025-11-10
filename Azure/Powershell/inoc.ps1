
#Azure RBAC → PIM-eligible at Subscription scope

.\pim.ps1 -Action AzureRbacAssign -TenantId "xxxx-tenant" -SubscriptionId "sub-guid" `
  -AzureRoleDefinitionIdOrName "Contributor" -TargetObjectId "objId-of-group-or-sp" `
  -MakePIMEligible -Tier 1 -ApproverGroupObjectId "approver-group-objId" -SnowTicketNumber "SNOW123456"


#Entra Directory Role (Global Reader) → assign to group, PIM-eligible

.\pim.ps1 -Action EntraRoleAssign -TenantId "xxxx-tenant" `
  -DirectoryRoleDisplayName "Global Reader" -AssigneeGroupObjectId "group-objId" `
  -MakePIMEligible -Tier 3


#Create role-assignable group

.\pim.ps1 -Action CreateRoleAssignableGroup -TenantId "xxxx-tenant" `
  -NewGroupDisplayName "SEC - PIM Eligible - Platform Readers" `
  -NewGroupDescription "Role-assignable group for platform reader access (PIM-eligible)."





param(
  [Parameter(Mandatory)]
  [string] $ChangeNumber     # <-- passed from pipeline
)

$ErrorActionPreference = 'Stop'

# ---- 4 values from your variable group (exposed as env vars in ADO) ----
$SnBaseUrl      = $env:SNOW_BASEURL
$SnClientId     = $env:SNOW_CLIENTID
$SnClientSecret = $env:SNOW_CLIENTSECRET
$SnUsername     = $env:SNOW_USERNAME
$SnPassword     = $env:SNOW_PASSWORD

# quick sanity
foreach ($kv in @(
  @{n='SNOW_BASEURL';v=$SnBaseUrl},
  @{n='SNOW_CLIENTID';v=$SnClientId},
  @{n='SNOW_CLIENTSECRET';v=$SnClientSecret},
  @{n='SNOW_USERNAME';v=$SnUsername},
  @{n='SNOW_PASSWORD';v=$SnPassword}
)) { if ([string]::IsNullOrWhiteSpace($kv.v)) { throw "Missing variable group value: $($kv.n)" } }

# ---- call the existing script file (same folder) and capture output + exit code ----
$checkerPath = Join-Path $PSScriptRoot 'ServiceNowChange.ps1'  # exact file name in your repo
$stdOut = & "$checkerPath" `
  -ChangeNumber $ChangeNumber `
  -BaseUrl      $SnBaseUrl `
  -ClientId     $SnClientId `
  -ClientSecret $SnClientSecret `
  -Username     $SnUsername `
  -Password     $SnPassword

$exitCode = $LASTEXITCODE

# Expect the checker to print a single JSON line like:
# {"Approved":true,"Message":"...","Number":"CHG12345",...}
# (If your checker prints something else, adjust parsing below.)

# Try to parse JSON even when exit code is non-zero (so we can show message)
$change = $null
try { $change = $stdOut | ConvertFrom-Json } catch { }

if ($exitCode -ne 0 -or -not $change -or -not $change.Approved) {
  $msg = if ($change) { $change.Message } else { $stdOut }
  Write-Warning "ServiceNow gate FAILED for '$ChangeNumber'. Details: $msg"
  throw "Aborting – change not approved."
}

Write-Host "✅ ServiceNow gate PASSED for '$ChangeNumber'. Proceeding…"

# ------- continue with your existing group-create REST code below -------
# (token -> check existing group -> create group, etc.)
