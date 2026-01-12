<#
.SYNOPSIS
Exports tenant-wide Azure RBAC role assignments where the principal is a *User* (direct user assignments),
including scope (MG/sub/RG/resource), role name, and principal identifiers.

Uses Azure Resource Graph for fast inventory across many subscriptions.
Optionally resolves principalId -> UPN/displayName via Microsoft Graph.

REQUIREMENTS:
- Azure CLI installed and logged in: az login --tenant <tenantId>
- Permissions: Reader or above on target subscriptions (or MG level).
- Optional: ImportExcel module for XLSX output.
- Optional: Graph directory read permissions to resolve principal IDs to UPN.

OUTPUT:
- <OutPath>.xlsx if ImportExcel available, else <OutPath>.csv
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$TenantId,

    [Parameter(Mandatory = $true)]
    [string]$OutPath,

    # If set, script tries to resolve principalId -> UPN/displayName via Graph.
    [switch]$ResolveUsersViaGraph = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-AzCliJson {
    param([Parameter(Mandatory=$true)][string]$Command)
    $raw = & powershell -NoProfile -Command $Command 2>$null
    if (-not $raw) { return $null }
    return ($raw | ConvertFrom-Json)
}

function Get-AccessToken {
    param(
        [Parameter(Mandatory=$true)][string]$Resource
    )
    $cmd = "az account get-access-token --resource $Resource --tenant $TenantId -o json"
    $tok = Invoke-AzCliJson -Command $cmd
    if (-not $tok -or -not $tok.accessToken) {
        throw "Failed to get access token for resource: $Resource. Ensure you ran: az login --tenant $TenantId"
    }
    return $tok.accessToken
}

function Invoke-RestJson {
    param(
        [Parameter(Mandatory=$true)][string]$Method,
        [Parameter(Mandatory=$true)][string]$Uri,
        [Parameter(Mandatory=$true)][hashtable]$Headers,
        [Parameter()][object]$Body
    )
    if ($null -ne $Body) {
        $jsonBody = $Body | ConvertTo-Json -Depth 50
        return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $Headers -Body $jsonBody -ContentType "application/json"
    } else {
        return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $Headers
    }
}

function Get-AllSubscriptionIds {
    # Uses Azure CLI to list all visible subscriptions
    $cmd = "az account list --all -o json"
    $subs = Invoke-AzCliJson -Command $cmd
    if (-not $subs) { throw "Could not list subscriptions. Ensure Azure CLI is installed and you're logged in." }
    $ids = @($subs | ForEach-Object { $_.id } | Where-Object { $_ -and $_.Trim().Length -gt 0 })
    return $ids
}

function Invoke-ResourceGraphQueryPaged {
    param(
        [Parameter(Mandatory=$true)][string]$ArmToken,
        [Parameter(Mandatory=$true)][string[]]$SubscriptionIds,
        [Parameter(Mandatory=$true)][string]$Query
    )

    $uri = "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2024-04-01"
    $headers = @{ Authorization = "Bearer $ArmToken" }

    $all = New-Object System.Collections.Generic.List[object]
    $skipToken = $null

    do {
        $body = @{
            subscriptions = $SubscriptionIds
            query         = $Query
            options       = @{
                resultFormat = "objectArray"
                top          = 1000
            }
        }

        if ($skipToken) {
            $body.options.skipToken = $skipToken
        }

        $resp = Invoke-RestJson -Method "POST" -Uri $uri -Headers $headers -Body $body

        if ($resp.data) {
            foreach ($row in $resp.data) { $all.Add($row) }
        }

        $skipToken = $null
        if ($resp.skipToken) { $skipToken = $resp.skipToken }

    } while ($skipToken)

    return $all
}

function Resolve-UsersByIdsGraph {
    param(
        [Parameter(Mandatory=$true)][string]$GraphToken,
        [Parameter(Mandatory=$true)][string[]]$Ids
    )

    # Graph getByIds supports batching ids. Keep batches conservative.
    $uri = "https://graph.microsoft.com/v1.0/directoryObjects/getByIds"
    $headers = @{ Authorization = "Bearer $GraphToken" }

    $map = @{}  # id -> @{ upn=..., displayName=... }

    $batchSize = 250
    for ($i=0; $i -lt $Ids.Count; $i += $batchSize) {
        $chunk = $Ids[$i..([Math]::Min($i+$batchSize-1, $Ids.Count-1))]

        $body = @{
            ids = $chunk
            types = @("user")
        }

        try {
            $resp = Invoke-RestJson -Method "POST" -Uri $uri -Headers $headers -Body $body
            foreach ($obj in ($resp.value | Where-Object { $_.id })) {
                $map[$obj.id] = @{
                    userPrincipalName = $obj.userPrincipalName
                    displayName       = $obj.displayName
                }
            }
        } catch {
            # If Graph permissions are missing, stop resolving and return what we have.
            Write-Warning "Graph resolution failed (likely missing Directory/User read permissions). Continuing without UPN resolution. Details: $($_.Exception.Message)"
            break
        }
    }

    return $map
}

Write-Host "Step 1: Getting ARM token (Resource Graph)..."
$armToken = Get-AccessToken -Resource "https://management.azure.com/"

Write-Host "Step 2: Listing subscriptions visible to you..."
$subIds = Get-AllSubscriptionIds
Write-Host ("Found {0} subscriptions in scope." -f $subIds.Count)

Write-Host "Step 3: Running Azure Resource Graph query for direct USER role assignments..."

# Resource Graph query:
# - Pull roleAssignments
# - Filter principalType == User
# - Join roleDefinitions to get role name
# - Project scope and principal identifiers
$query = @"
authorizationresources
| where type =~ 'microsoft.authorization/roleassignments'
| extend
    principalType = tostring(properties.principalType),
    principalId   = tostring(properties.principalId),
    roleDefId     = tostring(properties.roleDefinitionId),
    scope         = tostring(properties.scope),
    principalName = tostring(properties.principalName)
| where principalType =~ 'User'
| join kind=leftouter (
    authorizationresources
    | where type =~ 'microsoft.authorization/roledefinitions'
    | extend roleDefId = tostring(id)
    | project roleDefId, roleName=tostring(properties.roleName)
) on roleDefId
| project scope, roleName, principalId, principalName
"@

$rows = Invoke-ResourceGraphQueryPaged -ArmToken $armToken -SubscriptionIds $subIds -Query $query
Write-Host ("Returned {0} role assignment rows." -f $rows.Count)

# Build a list and (optionally) resolve principal IDs via Graph
$principalIds = @($rows | ForEach-Object { $_.principalId } | Where-Object { $_ -and $_.Trim().Length -gt 0 } | Select-Object -Unique)

$userMap = @{}
if ($ResolveUsersViaGraph -and $principalIds.Count -gt 0) {
    Write-Host "Step 4: Attempting Graph resolution of principalId -> UPN/displayName..."
    $graphToken = Get-AccessToken -Resource "https://graph.microsoft.com/"
    $userMap = Resolve-UsersByIdsGraph -GraphToken $graphToken -Ids $principalIds
    Write-Host ("Resolved {0} users via Graph." -f $userMap.Count)
} else {
    Write-Host "Step 4: Skipping Graph resolution."
}

Write-Host "Step 5: Building final report rows..."
$report = foreach ($r in $rows) {
    $pid = [string]$r.principalId
    $resolvedUpn = $null
    $resolvedDn  = $null

    if ($pid -and $userMap.ContainsKey($pid)) {
        $resolvedUpn = $userMap[$pid].userPrincipalName
        $resolvedDn  = $userMap[$pid].displayName
    }

    [pscustomobject]@{
        UserPrincipalName = $resolvedUpn
        DisplayName       = $resolvedDn
        PrincipalNameRaw  = [string]$r.principalName   # may be empty depending on tenant/PII scrubbing
        PrincipalId       = $pid
        RoleName          = [string]$r.roleName
        Scope             = [string]$r.scope
    }
}

# Sort for readability
$report = $report | Sort-Object Scope, RoleName, UserPrincipalName, DisplayName

Write-Host "Step 6: Exporting output..."
$xlsxPath = "$OutPath.xlsx"
$csvPath  = "$OutPath.csv"

# XLSX if ImportExcel exists, else CSV
if (Get-Module -ListAvailable -Name ImportExcel) {
    Import-Module ImportExcel -ErrorAction Stop
    $report | Export-Excel -Path $xlsxPath -WorksheetName "DirectUserAssignments" -AutoSize -FreezeTopRow -BoldTopRow
    Write-Host "Done. Excel report generated: $xlsxPath"
} else {
    $report | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
    Write-Host "ImportExcel module not found. CSV report generated instead: $csvPath"
    Write-Host "If you want .xlsx: Install-Module ImportExcel -Scope CurrentUser"
}

Write-Host "Completed."