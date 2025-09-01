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
  } elseif ($SubscriptionId) {
    $scope = "/subscriptions/$SubscriptionId"
  } else {
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
    action = "adminAssign"
    justification = "PIM eligible by pipeline (Tier $Tier, SNOW $SnowTicketNumber)"
    roleDefinitionId = "/providers/Microsoft.Authorization/roleDefinitions/$roleDefId"
    scope = $scope
    principalId = $TargetObjectId
    scheduleInfo = @{
      startDateTime = (Get-Date).ToUniversalTime().ToString("o")
      expiration = @{
        type = "noExpiration"     # change to "afterDateTime" if you want end date
      }
    }
    assignmentState = "Eligible"
    linkedEligibleRoleAssignmentId = $null
    # Approval chain for Tier 1-2 (approver group)
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

  # Endpoint: /beta/roleManagement/azure/roleEligibilityScheduleRequests
  $req = Invoke-MgGraphRequest -Method POST `
    -Uri "https://graph.microsoft.com/beta/roleManagement/azure/roleEligibilityScheduleRequests" `
    -Body ($body | ConvertTo-Json -Depth 10) -ContentType "application/json"

  Write-Host "PIM eligibility request submitted (Azure RBAC). RequestId: $($req.id)"
}
