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



# Inputs: $H (Graph header with bearer token), $EntraRole (display name)

# 1) Get the ROLE DEFINITION (use this id for PIM)
$filter = [uri]::EscapeDataString("displayName eq '$EntraRole'")
$defUrl = "https://graph.microsoft.com/v1.0/roleManagement/directory/roleDefinitions?`$filter=$filter&`$select=id,templateId,displayName"
$def = Invoke-RestMethod -Headers $H -Method GET -Uri $defUrl
if (-not $def.value) { throw "Role '$EntraRole' not found in roleDefinitions." }

$roleDefinitionId = $def.value[0].id          # <-- for PIM
$templateId       = $def.value[0].templateId   # <-- to locate/create instance

Write-Host "roleDefinitionId : $roleDefinitionId"
Write-Host "templateId       : $templateId"

# 2) Get/ensure the DIRECTORY ROLE INSTANCE (use this id for direct assignment)
$dirUrl = "https://graph.microsoft.com/v1.0/directoryRoles?`$filter=roleTemplateId eq '$templateId'&`$select=id,displayName,roleTemplateId"
$dir = Invoke-RestMethod -Headers $H -Method GET -Uri $dirUrl

if (-not $dir.value) {
    # create role instance from the template
    $dir = Invoke-RestMethod -Headers $H -Method POST `
        -Uri "https://graph.microsoft.com/v1.0/directoryRoles" `
        -Body (@{ roleTemplateId = $templateId } | ConvertTo-Json)
} else {
    $dir = $dir.value[0]
}
$directoryRoleId = $dir.id                     # <-- for direct assignment

Write-Host "directoryRoleId  : $directoryRoleId"





# Example ServiceNow change object response (replace this with your actual $result)
# $result = @{
#     result = @{
#         number = "CHG0934716"
#         state = "Approved"
#         start_date = "2025-11-11T06:00:00Z"
#         end_date = "2025-11-11T18:00:00Z"
#     }
# }

# Extract fields
$change = $result.result
$status = $change.state
$start  = [datetime]::Parse($change.start_date)
$end    = [datetime]::Parse($change.end_date)
$now    = (Get-Date).ToUniversalTime()

Write-Host "Change Number : $($change.number)"
Write-Host "Status        : $status"
Write-Host "Planned Start : $start"
Write-Host "Planned End   : $end"
Write-Host "Current (UTC) : $now"

# Check validity
if ($status -eq "Approved" -and $now -ge $start -and $now -le $end) {
    Write-Host "✅ Change is valid (Approved and within planned window)."
    $isChangeValid = $true
}
else {
    Write-Host "❌ Change is NOT valid."
    if ($status -ne "Approved") {
        Write-Host "Reason: Status is '$status' (expected 'Approved')."
    }
    elseif ($now -lt $start) {
        Write-Host "Reason: Change window has not started yet."
    }
    elseif ($now -gt $end) {
        Write-Host "Reason: Change window has already ended."
    }
    $isChangeValid = $false
}

# You can then use this variable to decide whether to proceed
if (-not $isChangeValid) {
    throw "Change validation failed — stopping execution."
}





try {
    New-AzRoleAssignment `
        -ObjectId       $spnId `
        -RoleDefinitionId $roleDefinitionId `
        -Scope          $scope `
        -ErrorAction    Stop

    Write-Host "Role assignment created successfully."
}
catch {
    # CloudException from Az modules
    $ex = $_.Exception

    # Default output if we can’t parse ARM body
    $msg = $ex.Message
    $httpStatus = $null
    $armCode = $null
    $armMessage = $null

    # Try to read HTTP status
    if ($ex.Response -and $ex.Response.StatusCode) {
        $httpStatus = $ex.Response.StatusCode
    }

    # Try to read ARM JSON body: { "error": { "code": "...", "message": "..." } }
    if ($ex.Body) {
        try {
            $body = $ex.Body | ConvertFrom-Json
            if ($body.error) {
                $armCode    = $body.error.code
                $armMessage = $body.error.message
            }
        } catch {
            # ignore JSON parse failure, we'll fall back to $msg
        }
    }

    Write-Host "----------------------------------------"
    if ($httpStatus) {
        Write-Host ("HTTP Status : {0}" -f $httpStatus)
    }

    if ($armCode) {
        Write-Host ("ARM Code    : {0}" -f $armCode)
    }

    if ($armMessage) {
        Write-Host ("Message     : {0}" -f $armMessage)
    }
    else {
        Write-Host ("Message     : {0}" -f $msg)
    }
    Write-Host "----------------------------------------"

    # If you don't want the pipeline to fail, comment the next line
    throw
}