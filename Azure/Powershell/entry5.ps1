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



# --- Minimal setup for Get-MgGroup ---

# Install only the modules needed for auth + groups (if missing)
foreach ($m in 'Microsoft.Graph.Authentication','Microsoft.Graph.Groups') {
  if (-not (Get-Module -ListAvailable -Name $m)) {
    Set-PSRepository PSGallery -InstallationPolicy Trusted -ErrorAction SilentlyContinue
    Install-Module $m -Scope CurrentUser -Force -AllowClobber -ErrorAction Stop
  }
  Import-Module $m -Force
}

# ---- OPTION A: App-only with client secret (recommended for pipelines) ----
# Requires APP perms granted in Entra (e.g., Group.Read.All or Group.ReadWrite.All)
# $TenantId, $ClientId, $ClientSecret must be set
# Connect-MgGraph -NoWelcome avoids the banner
$secureSecret = ConvertTo-SecureString $ClientSecret -AsPlainText -Force
Connect-MgGraph -TenantId $TenantId -ClientId $ClientId -ClientSecret $secureSecret -NoWelcome

# ---- OPTION B: Reuse an existing Az token (uncomment if you prefer) ----
# $graphToken = (Get-AzAccessToken -ResourceUrl "https://graph.microsoft.com").Token
# $secureTok  = ConvertTo-SecureString $graphToken -AsPlainText -Force
# Connect-MgGraph -AccessToken $secureTok -NoWelcome

# ---- Example usage ----
# Exact-name lookup (safe casing & spaces)
# $g = Get-MgGroup -Filter "displayName eq '$GroupName'" -ConsistencyLevel eventual -Count groupCount
# $g | Select-Object Id, DisplayName, Mail, SecurityEnabled
