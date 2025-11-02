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
