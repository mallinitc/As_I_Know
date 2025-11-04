# =========================================
# 2. Entra Directory Role -> Group Assign
# =========================================
function Set-EntraDirectoryRoleAssignment {
  param(
    [string]$DirectoryRoleDisplayName,
    [string]$AssigneeGroupObjectId,
    [switch]$MakePIMEligible
  )

  $dirRoleId = Get-DirectoryRoleDefinitionId -DisplayName $DirectoryRoleDisplayName

  if (-not $MakePIMEligible) {
    Write-Host "Creating PERMANENT directory role assignment..." -ForegroundColor Green
    # POST /directoryRoles/{id}/members/$ref
    New-MgDirectoryRoleMemberByRef -DirectoryRoleId $dirRoleId -BodyParameter @{
      "@odata.id" = "https://graph.microsoft.com/v1.0/directoryObjects/$AssigneeGroupObjectId"
    }
    Write-Host "Permanent directory role assignment created."
    return
  }

  Write-Host "Creating PIM-ELIGIBLE directory role assignment..." -ForegroundColor Yellow
  # PIM for Entra ID roles -> unifiedRoleEligibilityScheduleRequests
  $body = @{
    action = "adminAssign"
    justification = "PIM eligible by pipeline (Tier $Tier, SNOW $SnowTicketNumber)"
    roleDefinitionId = $dirRoleId
    directoryScopeId = "/"                 # tenant-wide
    principalId = $AssigneeGroupObjectId
    scheduleInfo = @{
      startDateTime = (Get-Date).ToUniversalTime().ToString("o")
      expiration = @{ type = "noExpiration" }
    }
    assignmentState = "Eligible"
    approvalSettings = if ($ThisTier.RequiresApproval) {
      @{
        isApprovalRequired = $true
        approvalStages = @(@{
          approvalStageTimeOutInDays = 1
          isApproverJustificationRequired = $true
          escalationEnabled = $false
          primaryApprovers = @(@{ id = $ApproverGroupObjectId; isBackup = $false })
        })
      }
    } else {
      @{ isApprovalRequired = $false }
    }
  }

  # POST /beta/roleManagement/directory/roleEligibilityScheduleRequests
  $req = Invoke-MgGraphRequest -Method POST `
    -Uri "https://graph.microsoft.com/beta/roleManagement/directory/roleEligibilityScheduleRequests" `
    -Body ($body | ConvertTo-Json -Depth 10) -ContentType "application/json"

  Write-Host "PIM eligibility request submitted (Directory Role). RequestId: $($req.id)"
}



$body = @{
  action = "adminAssign"
  roleDefinitionId = $roleDefinitionId
  principalId = $groupId
  directoryScopeId = "/"
  justification = "Pipeline assignment"
  scheduleInfo = @{
    startDateTime = (Get-Date).ToUniversalTime().ToString("o")
    expiration = @{
      type = "afterDateTime"
      endDateTime = (Get-Date).ToUniversalTime().AddYears(1).ToString("o")
    }
  }
}

Invoke-RestMethod -Headers $H -Method POST `
  -Uri "https://graph.microsoft.com/beta/roleManagement/directory/roleEligibilityScheduleRequests" `
  -Body ($body | ConvertTo-Json -Depth 8)



$tokenResp = Invoke-RestMethod -Method POST -Uri "https://login.microsoftonline.com/$TenantId/oauth2/v2.0/token" -Body @{
  client_id     = $ClientId
  client_secret = $Secret
  scope         = "https://graph.microsoft.com/.default"
  resource      = "https://graph.microsoft.com/"
  grant_type    = "client_credentials"
}
$token = $tokenResp.access_token
$H = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }



Invoke-RestMethod -Headers $H -Method GET `
  "https://graph.microsoft.com/beta/roleManagement/directory/roleEligibilityScheduleRequests?`$top=1"


$start = (Get-Date).ToUniversalTime().ToString("o")
$end   = (Get-Date).ToUniversalTime().AddYears(1).ToString("o")

$body = @{
  action = "adminAssign"
  roleDefinitionId = $roleDefinitionId
  principalId = $groupId
  directoryScopeId = "/"
  justification = "Pipeline assignment"
  scheduleInfo = @{
    startDateTime = $start
    expiration = @{
      type = "afterDateTime"
      endDateTime = $end
    }
  }
}

Write-Host "Sending JSON body:"
$body | ConvertTo-Json -Depth 10 | Write-Host

$response = Invoke-RestMethod -Headers $H -Method POST `
  "https://graph.microsoft.com/beta/roleManagement/directory/roleEligibilityScheduleRequests" `
  -Body ($body | ConvertTo-Json -Depth 10)

Write-Host "✅ PIM eligible assignment created: $($response.id)"



# ----- Direct (permanent) role assignment for a group -----

# 1) Ensure a directoryRole *instance* exists for $roleName
$dirRole = Invoke-RestMethod -Headers $H -Method GET `
  "https://graph.microsoft.com/v1.0/directoryRoles?`$filter=displayName eq '$roleName'&`$select=id"

if (-not $dirRole.value) {
  $tmplId = (Invoke-RestMethod -Headers $H -Method GET `
    "https://graph.microsoft.com/v1.0/directoryRoleTemplates?`$filter=displayName eq '$roleName'&`$select=id"
  ).value[0].id

  $dirRole = Invoke-RestMethod -Headers $H -Method POST `
    "https://graph.microsoft.com/v1.0/directoryRoles" `
    -Body (@{ roleTemplateId = $tmplId } | ConvertTo-Json)
} else {
  $dirRole = $dirRole.value[0]
}

# 2) Add the group as a member of the role (permanent active assignment)
$refBody = @{ '@odata.id' = "https://graph.microsoft.com/v1.0/directoryObjects/$groupId" }

try {
  Invoke-RestMethod -Headers $H -Method POST `
    "https://graph.microsoft.com/v1.0/directoryRoles/$($dirRole.id)/members/`$ref" `
    -Body ($refBody | ConvertTo-Json)
  Write-Host "✅ Direct role assignment added for group $groupId to '$roleName'."
}
catch {
  # Idempotency: ignore 'already exists' errors
  if ($_.ErrorDetails.Message -match 'already exist') {
    Write-Host "ℹ️ Group already has direct assignment for '$roleName'."
  } else { throw }
}




# Inputs assumed available:
# $H (Bearer token header), $MakePIMEligible (bool), $roleName (display name), $roleDefinitionId, $groupId

function Invoke-GraphJson {
    param([string]$Method,[string]$Url,[hashtable]$Body=[hashtable]::new())
    $json = if ($Body.Count) { $Body | ConvertTo-Json -Depth 10 } else { $null }
    try {
        Invoke-RestMethod -Headers $H -Method $Method -Uri ($Url.Trim()) -Body $json
    } catch {
        Write-Host "URL: $Url"
        if ($_.ErrorDetails.Message) { Write-Host "Server: $($_.ErrorDetails.Message)" }
        throw
    }
}

if ($MakePIMEligible) {
    # ------- PIM eligible assignment (beta) -------
    $start = (Get-Date).ToUniversalTime().ToString("o")
    $end   = (Get-Date).ToUniversalTime().AddYears(1).ToString("o")

    $body = @{
        action           = "adminAssign"
        roleDefinitionId = $roleDefinitionId   # from /v1.0/roleDefinitions
        principalId      = $groupId
        directoryScopeId = "/"
        justification    = "Pipeline assignment"
        scheduleInfo     = @{
            startDateTime = $start
            expiration    = @{ type="afterDateTime"; endDateTime=$end }
        }
    }

    $url = 'https://graph.microsoft.com/beta/roleManagement/directory/roleEligibilityScheduleRequests'
    $null = $body | ConvertTo-Json -Depth 10 | Write-Host  # optional: see what you're sending
    $response = $null
    $response = Invoke-GraphJson -Method POST -Url $url -Body $body
    Write-Host "✅ PIM eligible assignment created: $($response.id)"
}
else {
    # ------- Direct (permanent) assignment (v1.0) -------
    # 1) Ensure a directoryRole instance exists for $roleName (uses directoryRoleId, not roleDefinitionId)
    $dirRole = Invoke-GraphJson -Method GET -Url ("https://graph.microsoft.com/v1.0/directoryRoles?`$filter=displayName eq '{0}'&`$select=id" -f $roleName)
    if (-not $dirRole.value) {
        $tmplId = (Invoke-GraphJson -Method GET -Url ("https://graph.microsoft.com/v1.0/directoryRoleTemplates?`$filter=displayName eq '{0}'&`$select=id" -f $roleName)).value[0].id
        $dirRole = Invoke-GraphJson -Method POST -Url 'https://graph.microsoft.com/v1.0/directoryRoles' -Body @{ roleTemplateId = $tmplId }
    } else {
        $dirRole = $dirRole.value[0]
    }

    # 2) Add the group as a member of the role
    $refBody = @{ '@odata.id' = "https://graph.microsoft.com/v1.0/directoryObjects/$groupId" }
    try {
        Invoke-GraphJson -Method POST -Url ("https://graph.microsoft.com/v1.0/directoryRoles/{0}/members/`$ref" -f $dirRole.id) -Body $refBody
        Write-Host "✅ Direct role assignment added for group $groupId to '$roleName'."
    } catch {
        # Idempotency: Graph returns 400/409 if already present; treat as success
        if ($_.ErrorDetails.Message -match 'already exist|One or more added object references already exist') {
            Write-Host "ℹ️ Group already has direct assignment for '$roleName'."
        } else { throw }
    }
}





# URLs (do not change)
$PimEligibleUrl = 'https://graph.microsoft.com/beta/roleManagement/directory/roleEligibilityScheduleRequests'
$DirectMemberUrl = { param($roleId) "https://graph.microsoft.com/v1.0/directoryRoles/$roleId/members/`$ref" }

if ($MakePIMEligible) {
    # -- PIM Eligible --
    $response = Invoke-RestMethod -Headers $H -Method POST `
        -Uri $PimEligibleUrl.Trim() `
        -Body ($body | ConvertTo-Json -Depth 10)
    Write-Host "✅ PIM eligible assignment created: $($response.id)"
}
else {
    # -- Direct assignment --
    # (resolve/create $dirRole earlier as shown before)
    $refBody = @{ '@odata.id' = "https://graph.microsoft.com/v1.0/directoryObjects/$groupId" }
    Invoke-RestMethod -Headers $H -Method POST `
        -Uri (& $DirectMemberUrl $dirRole.id).Trim() `
        -Body ($refBody | ConvertTo-Json)
    Write-Host "✅ Direct role assignment added."
}



# $H = @{ Authorization="Bearer $token"; "Content-Type"="application/json" }
$roleName = 'Reports Reader'   # your Entra role display name

# URL-encode the $filter to avoid 400 on spaces/quotes
$filter = [uri]::EscapeDataString("displayName eq '$roleName'")
$url = "https://graph.microsoft.com/v1.0/roleManagement/directory/roleDefinitions?`$filter=$filter&`$select=id,templateId,displayName"

$def = Invoke-RestMethod -Headers $H -Method GET -Uri $url
$roleDefinitionId = $def.value[0].id
$templateId       = $def.value[0].templateId




# Inputs you already have:
# $H = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }
# $groupName = "<display name of the group>"

function Get-GraphGroupByName {
    param(
        [Parameter(Mandatory)]
        [string] $GroupDisplayName,
        [Parameter(Mandatory)]
        [hashtable] $Headers
    )

    # Filter: exact display name match (URL-encoded to avoid 400)
    $filter = [uri]::EscapeDataString("displayName eq '$GroupDisplayName'")
    $select = [uri]::EscapeDataString("id,displayName,mail,mailNickname,groupTypes,securityEnabled,isAssignableToRole")

    $url = "https://graph.microsoft.com/v1.0/groups?`$filter=$filter&`$select=$select"
    $resp = Invoke-RestMethod -Headers $Headers -Method GET -Uri $url

    if (-not $resp.value -or $resp.value.Count -eq 0) {
        Write-Host "❌ No group found with displayName '$GroupDisplayName'."
        return $null
    }

    if ($resp.value.Count -gt 1) {
        Write-Host "⚠️ Multiple groups found with the same displayName '$GroupDisplayName'. Showing all matches:"
        # Return all matches so caller can choose
        return $resp.value | Select-Object id,displayName,mail,mailNickname,securityEnabled,isAssignableToRole,groupTypes
    }

    # Exactly one match
    return $resp.value[0] | Select-Object id,displayName,mail,mailNickname,securityEnabled,isAssignableToRole,groupTypes
}

# ----- Usage -----
$grp = Get-GraphGroupByName -GroupDisplayName $groupName -Headers $H
if ($grp) {
    Write-Host "✅ Group found:"
    $grp | Format-List
    # Access id as: $grp.id
}



# Check and install Microsoft Graph module if not present
if (-not (Get-Module -ListAvailable -Name Microsoft.Graph)) {
    Write-Host "Microsoft.Graph module not found. Installing..."
    Install-Module Microsoft.Graph -Scope CurrentUser -Force
}

# Import the module
Import-Module Microsoft.Graph -Force

# Now you can safely connect
# Connect-MgGraph -Scopes "Directory.ReadWrite.All","Group.ReadWrite.All","RoleManagement.ReadWrite.Directory"