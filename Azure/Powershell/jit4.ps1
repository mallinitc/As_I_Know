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





# ---------- Inputs ----------
$TenantId         = "<tenant-guid>"
$ClientId         = "<app-id>"
$ClientSecret     = "<client-secret>"
$GroupName        = "My Role Assignable Group"
$GroupDescription = "This group can be assigned Microsoft Entra roles."

# ---------- Get Graph app token (no modules required) ----------
$tokenResp = Invoke-RestMethod -Method POST -Uri "https://login.microsoftonline.com/$TenantId/oauth2/v2.0/token" -Body @{
  client_id     = $ClientId
  client_secret = $ClientSecret
  scope         = "https://graph.microsoft.com/.default"
  grant_type    = "client_credentials"
}
$H = @{ Authorization = "Bearer $($tokenResp.access_token)"; "Content-Type" = "application/json" }

# ---------- Helpers ----------
function New-MailNickname {
  param([string]$Name)
  # letters/digits only, replace others with '-', trim and lowercase
  $n = ($Name -replace '[^A-Za-z0-9]', '-').Trim('-').ToLower()
  if (-not $n) { $n = "grp" + (Get-Random -Max 99999) }
  return $n.Substring(0, [Math]::Min(64, $n.Length))
}

# ---------- Check if a group with this display name already exists ----------
$filter = [uri]::EscapeDataString("displayName eq '$GroupName'")
$select = [uri]::EscapeDataString("id,displayName,isAssignableToRole,securityEnabled,mail,mailNickname")
$url    = "https://graph.microsoft.com/v1.0/groups?`$filter=$filter&`$select=$select"

$existing = Invoke-RestMethod -Headers $H -Method GET -Uri $url
if ($existing.value -and $existing.value.Count -gt 0) {
  Write-Host "⚠️  Entra group with displayName '$GroupName' already exists:"
  $existing.value | Select-Object id,displayName,isAssignableToRole,securityEnabled,mailNickname | Format-List
  return
}

# ---------- Create a role-assignable security group ----------
# mailNickname must be unique tenant-wide
$nickname = New-MailNickname -Name $GroupName

$body = @{
  displayName        = $GroupName
  description        = $GroupDescription
  mailEnabled        = $false
  mailNickname       = $nickname
  securityEnabled    = $true
  isAssignableToRole = $true                  # <-- key bit for role-assignable groups
  groupTypes         = @()                    # security group (not M365)
}

try {
  $created = Invoke-RestMethod -Headers $H -Method POST `
    -Uri "https://graph.microsoft.com/v1.0/groups" `
    -Body ($body | ConvertTo-Json -Depth 6)

  Write-Host "✅ Group created:"
  $created | Select-Object id,displayName,isAssignableToRole,securityEnabled,mailNickname | Format-List
}
catch {
  # If nickname collision, Graph returns 400; try a different nickname automatically
  if ($_.ErrorDetails.Message -match 'Another object with the same value for property mailNickname already exists') {
    $nickname = ("$nickname-{0}" -f (Get-Random -Max 99999))
    $body.mailNickname = $nickname
    $created = Invoke-RestMethod -Headers $H -Method POST `
      -Uri "https://graph.microsoft.com/v1.0/groups" `
      -Body ($body | ConvertTo-Json -Depth 6)
    Write-Host "✅ Group created on retry with unique mailNickname:"
    $created | Select-Object id,displayName,isAssignableToRole,securityEnabled,mailNickname | Format-List
  } else {
    Write-Host "❌ Create failed:" 
    if ($_.ErrorDetails.Message) { Write-Host $_.ErrorDetails.Message } 
    throw
  }
}