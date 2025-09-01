# =======================================
# 3. Create Role-Assignable Entra Group
# =======================================
function New-RoleAssignableGroup {
  param(
    [Parameter(Mandatory=$true)][string]$DisplayName,
    [Parameter(Mandatory=$true)][string]$Description
  )

  # Role-assignable groups MUST be security-enabled + isAssignableToRole
  $grp = New-MgGroup -DisplayName $DisplayName `
                     -Description $Description `
                     -MailEnabled:$false `
                     -MailNickname ([Guid]::NewGuid().ToString("N")) `
                     -SecurityEnabled `
                     -IsAssignableToRole `
                     -GroupTypes @()

  Write-Host "Created role-assignable group: $($grp.Id)  ($DisplayName)"
  return $grp
}
