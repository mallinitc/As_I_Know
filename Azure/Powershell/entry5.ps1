# ====================
# 5. Entry Point
# ====================
switch ($Action) {
  'AzureRbacAssign' {
    Set-AzureRbacAssignment -AzureRoleDefinitionIdOrName $AzureRoleDefinitionIdOrName `
                            -TargetObjectId $TargetObjectId `
                            -SubscriptionId $SubscriptionId `
                            -ManagementGroupId $ManagementGroupId `
                            -MakePIMEligible:$MakePIMEligible
  }
  'EntraRoleAssign' {
    Set-EntraDirectoryRoleAssignment -DirectoryRoleDisplayName $DirectoryRoleDisplayName `
                                     -AssigneeGroupObjectId $AssigneeGroupObjectId `
                                     -MakePIMEligible:$MakePIMEligible
    # Optional: Set-DirectoryRoleActivationSettings -RoleId (Get-DirectoryRoleDefinitionId -DisplayName $DirectoryRoleDisplayName) -MaxActivationHours $ThisTier.DurationHours
  }
  'CreateRoleAssignableGroup' {
    New-RoleAssignableGroup -DisplayName $NewGroupDisplayName -Description $NewGroupDescription | Out-Null
  }
  default { throw "Unknown -Action. Use AzureRbacAssign | EntraRoleAssign | CreateRoleAssignableGroup" }
}

Write-Host "DONE: $Action (Tier $Tier, Duration = $($ThisTier.DurationHours)h, ApprovalRequired=$($ThisTier.RequiresApproval))"
