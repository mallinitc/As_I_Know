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


№####################

Write-Host "Getting Microsoft Graph token..."
try {
    # Get a Graph-scoped token from the Az context
    $graphToken = (Get-AzAccessToken -ResourceUrl "https://graph.microsoft.com").Token
    Write-Host "Token fetched successfully"
}
catch {
    throw "Failed to get Graph token: $($_.Exception.Message)"
}

$headers = @{
    "Authorization" = "Bearer $graphToken"
    "Content-Type"  = "application/json"
}

# Test Graph connectivity
$testUri = "https://graph.microsoft.com/v1.0/applications?`$top=1"
try {
    $response = Invoke-RestMethod -Headers $headers -Uri $testUri -Method GET
    Write-Host "Graph connectivity successful. App count:" ($response.value.Count)
}
catch {
    Write-Host "Graph connectivity failed."
    throw $_.Exception.Message
}


№##########

# Get a GRAPH-scoped token as a STRING
$graphToken = (Get-AzAccessToken -ResourceUrl 'https://graph.microsoft.com').Token  # <-- string

# (optional) verify the audience
$aud = (
  [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String(($graphToken.Split('.')[1] + '=='))
  ) | ConvertFrom-Json
).aud
Write-Host "aud = $aud"   # should be https://graph.microsoft.com

# Use it
$headers = @{
  Authorization = "Bearer $graphToken"
  'Content-Type' = 'application/json'
}
$test = Invoke-RestMethod -Headers $headers -Uri 'https://graph.microsoft.com/v1.0/applications?$top=1' -Method GET


####
# $secureAccessToken is a SecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureAccessToken)
try {
  $tokenPlain = [Runtime.InteropServices.Marshal]::PtrToStringUni($ptr)
}
finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}

# now safe to use
$decoded = (
  [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String(($tokenPlain.Split('.')[1] + '=='))
  ) | ConvertFrom-Json
).aud
$headers = @{ Authorization = "Bearer $tokenPlain" }