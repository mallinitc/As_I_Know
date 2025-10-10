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


#####
$token = (Get-AzAccessToken -ResourceTypeName MSGraph).Token
$headers = @{ Authorization = "Bearer $token" }

# Example: users
$users = Invoke-RestMethod -Headers $headers -Uri "https://graph.microsoft.com/v1.0/users?`$top=5" -Method GET

# Example: application by displayName
$encoded = [System.Web.HttpUtility]::UrlEncode("displayName eq '$SPName'")
$app = Invoke-RestMethod -Headers $headers -Uri "https://graph.microsoft.com/v1.0/applications?`$filter=$encoded" -Method GET

# Example: service principal by displayName
$spn = Invoke-RestMethod -Headers $headers -Uri "https://graph.microsoft.com/v1.0/servicePrincipals?`$filter=$encoded" -Method GET


######


# Get a token scoped to Microsoft Graph
$graphToken = (Get-AzAccessToken -ResourceUrl "https://graph.microsoft.com").Token
$headers = @{ Authorization = "Bearer $graphToken" }

# Now call Graph safely
$app = Invoke-RestMethod -Headers $headers -Uri "https://graph.microsoft.com/v1.0/applications?`$filter=displayName eq '$SPName'" -Method GET