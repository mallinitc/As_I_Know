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
