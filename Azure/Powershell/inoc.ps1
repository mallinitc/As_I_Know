
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
