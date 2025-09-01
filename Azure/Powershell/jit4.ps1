# ===================================================
# 4. Optional: Configure Activation Settings per Tier
# ===================================================
function Set-DirectoryRoleActivationSettings {
  param(
    [string]$RoleId,          # directory role id
    [int]$MaxActivationHours  # from $ThisTier.DurationHours
  )

  $settings = @{
    # This is a simplified example; real tenants often use policy + rules.
    # POST /beta/roleManagement/directory/roleManagementPolicies/{policyId}/rules
    # You can query existing policy and update the "ExpiryRule"
  }
  Write-Host "NOTE: Configure policy/rules for activation duration ($MaxActivationHours h) as per your tenant's governance model."
}
