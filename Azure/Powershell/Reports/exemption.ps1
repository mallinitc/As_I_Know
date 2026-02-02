param(
  [int]$DaysThreshold = 45,
  [string]$SenderUPN,
  [string]$ToRecipients,
  [string]$CcRecipients
)

$ErrorActionPreference = "Stop"

function Get-AzAccessToken {
  param([Parameter(Mandatory)][string]$Resource)
  $t = az account get-access-token --resource $Resource --query accessToken -o tsv
  if (-not $t) { throw "Failed to get access token for $Resource" }
  return $t
}

function Invoke-ArmGet {
  param(
    [Parameter(Mandatory)][string]$Url,
    [Parameter(Mandatory)][string]$ArmToken
  )
  $headers = @{ Authorization = "Bearer $ArmToken" }
  return Invoke-RestMethod -Method GET -Uri $Url -Headers $headers
}

function Invoke-GraphGet {
  param(
    [Parameter(Mandatory)][string]$Url,
    [Parameter(Mandatory)][string]$GraphToken
  )
  $headers = @{ Authorization = "Bearer $GraphToken" }
  return Invoke-RestMethod -Method GET -Uri $Url -Headers $headers
}

function Invoke-GraphPost {
  param(
    [Parameter(Mandatory)][string]$Url,
    [Parameter(Mandatory)][string]$GraphToken,
    [Parameter(Mandatory)]$Body
  )
  $headers = @{
    Authorization = "Bearer $GraphToken"
    "Content-Type" = "application/json"
  }
  $json = $Body | ConvertTo-Json -Depth 10
  return Invoke-RestMethod -Method POST -Uri $Url -Headers $headers -Body $json
}

# ---------- Tokens ----------
$armToken   = Get-AzAccessToken -Resource "https://management.azure.com/"
$graphToken = Get-AzAccessToken -Resource "https://graph.microsoft.com/"

# ---------- Time window ----------
$now = Get-Date
$cutoff = $now.AddDays($DaysThreshold)

# ---------- HTML header ----------
$header = @"
<style>
TABLE {border-width: 1px; border-style: solid; border-color: black; border-collapse: collapse;}
TH {border-width: 1px; padding: 6px; border-style: solid; border-color: black; background-color: #6495ED;}
TD {border-width: 1px; padding: 6px; border-style: solid; border-color: black;}
</style>
"@

# ---------- Graph user cache ----------
$userCache = @{}
function Resolve-UserDisplayName {
  param([string]$UpnOrNull)

  if (-not $UpnOrNull) { return "" }
  if ($userCache.ContainsKey($UpnOrNull)) { return $userCache[$UpnOrNull] }

  # If systemData contains a GUID instead of UPN, this lookup will fail.
  # In that case, return the raw value; you can extend this to handle objectId if needed.
  $safe = $UpnOrNull.Replace("'", "''")
  $url = "https://graph.microsoft.com/v1.0/users?`$filter=userPrincipalName eq '$safe'&`$select=displayName,userPrincipalName"
  try {
    $resp = Invoke-GraphGet -Url $url -GraphToken $graphToken
    $dn = $resp.value[0].displayName
    if (-not $dn) { $dn = $UpnOrNull }
    $userCache[$UpnOrNull] = $dn
    return $dn
  } catch {
    $userCache[$UpnOrNull] = $UpnOrNull
    return $UpnOrNull
  }
}

# ---------- Collect exemptions ----------
$output = New-Object System.Collections.ArrayList

# List subscriptions
$subsUrl = "https://management.azure.com/subscriptions?api-version=2020-01-01"
$subsResp = Invoke-ArmGet -Url $subsUrl -ArmToken $armToken
$subs = $subsResp.value

$apiVersion = "2022-07-01-preview"  # adjust if needed

foreach ($sub in $subs) {
  $subId = $sub.subscriptionId

  # Exemptions at subscription scope
  $exUrl = "https://management.azure.com/subscriptions/$subId/providers/Microsoft.Authorization/policyExemptions?api-version=$apiVersion"
  $exResp = Invoke-ArmGet -Url $exUrl -ArmToken $armToken
  $exemptions = @($exResp.value)

  foreach ($ex in $exemptions) {
    $expiresOnRaw = $ex.properties.expiresOn
    if (-not $expiresOnRaw) { continue }

    $expiresOn = [datetime]$expiresOnRaw

    if ($expiresOn -le $cutoff -and $expiresOn -ge $now) {
      $createdByRaw = $ex.systemData.createdBy
      $modifiedByRaw = $ex.systemData.lastModifiedBy

      $createdBy = Resolve-UserDisplayName -UpnOrNull $createdByRaw
      $lastModifiedBy = Resolve-UserDisplayName -UpnOrNull $modifiedByRaw

      $exName = if ($ex.properties.displayName) { $ex.properties.displayName } else { $ex.name }

      $null = $output.Add([pscustomobject][ordered]@{
        SubscriptionId = $subId
        ExemptionName  = $exName
        Scope          = $ex.properties.scope
        Category       = $ex.properties.exemptionCategory
        ExpiresOn      = $expiresOn
        ExemptionDesc  = $ex.properties.description
        CreatedBy      = $createdBy
        LastModifiedBy = $lastModifiedBy
      })
    }
  }
}

if ($output.Count -lt 1) {
  Write-Host "No policy exemptions expiring within $DaysThreshold days."
  exit 0
}

# ---------- Build HTML table ----------
$sorted = $output | Sort-Object ExpiresOn
$tableHtml = $sorted | ConvertTo-Html -Head $header -Property SubscriptionId,ExemptionName,Scope,Category,ExpiresOn,ExemptionDesc,CreatedBy,LastModifiedBy | Out-String

$bodyHtml = @"
<p>Team,<br/><br/>
This is to notify you that one or more Azure Policy exemptions listed below are nearing their expiration (within next $DaysThreshold days).</p>
$tableHtml
<p><br/>Regards,<br/>CloudSecurityEngineering</p>
"@

# ---------- Send mail via Graph ----------
# Recipients format
$to = @()
$ToRecipients.Split(",") | ForEach-Object {
  $addr = $_.Trim()
  if ($addr) { $to += @{ emailAddress = @{ address = $addr } } }
}

$cc = @()
$CcRecipients.Split(",") | ForEach-Object {
  $addr = $_.Trim()
  if ($addr) { $cc += @{ emailAddress = @{ address = $addr } } }
}

$subject = "Azure Policy Exemptions Expiring Soon"

$mailBody = @{
  message = @{
    subject = $subject
    body = @{
      contentType = "HTML"
      content = $bodyHtml
    }
    toRecipients = $to
    ccRecipients = $cc
  }
  saveToSentItems = $false
}

$sendUrl = "https://graph.microsoft.com/v1.0/users/$SenderUPN/sendMail"
Invoke-GraphPost -Url $sendUrl -GraphToken $graphToken -Body $mailBody

Write-Host "Sent email. Items: $($output.Count)"