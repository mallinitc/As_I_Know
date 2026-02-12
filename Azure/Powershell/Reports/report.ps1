<# 
Report "default*" Log Analytics workspaces across tenant:
- Last ingestion time (from Usage table)
- Ingested GB in last 60 days
- Flag if ingested in last 60 days
#>

# -----------------------------
# 0) Modules
# -----------------------------
$modules = @("Az.Accounts", "Az.ResourceGraph", "Az.OperationalInsights")
foreach ($m in $modules) {
    if (-not (Get-Module -ListAvailable -Name $m)) {
        Write-Host "Installing module: $m"
        Install-Module $m -Scope CurrentUser -Force
    }
}

Import-Module Az.Accounts
Import-Module Az.ResourceGraph
Import-Module Az.OperationalInsights

# -----------------------------
# 1) Login
# -----------------------------
Connect-AzAccount | Out-Null

# Optional: if you have multiple tenants
# Set-AzContext -Tenant "<tenant-guid>"

# -----------------------------
# 2) Find workspaces tenant-wide using Azure Resource Graph
#    (name starts with 'default' - case-insensitive)
# -----------------------------
$argQuery = @"
Resources
| where type =~ 'microsoft.operationalinsights/workspaces'
| where name startswith 'default'
| project subscriptionId, resourceGroup, name, location, id, customerId=tostring(properties.customerId)
| order by subscriptionId asc, name asc
"@

$workspaces = Search-AzGraph -Query $argQuery -First 5000

if (-not $workspaces -or $workspaces.Count -eq 0) {
    Write-Host "No workspaces found with name starting 'default'."
    return
}

# -----------------------------
# 3) KQL: last ingestion + ingested GB in last 60 days
#    We use Usage because it directly represents ingestion volume and timestamps.
#    Quantity is in MB; convert to GB by /1024.0
# -----------------------------
$kql = @"
Usage
| summarize
    LastIngest=max(TimeGenerated),
    IngestedGB_60d=sumif(Quantity, TimeGenerated > ago(60d)) / 1024.0
"@

# -----------------------------
# 4) Loop and query each workspace
# -----------------------------
$results = New-Object System.Collections.Generic.List[object]

# Cache subscription names (optional nice-to-have)
$subNameMap = @{}
Get-AzSubscription | ForEach-Object { $subNameMap[$_.Id] = $_.Name }

foreach ($ws in $workspaces) {

    $subId = $ws.subscriptionId
    $wsName = $ws.name
    $rg = $ws.resourceGroup
    $custId = $ws.customerId

    $row = [ordered]@{
        SubscriptionId        = $subId
        SubscriptionName      = $subNameMap[$subId]
        ResourceGroup         = $rg
        WorkspaceName         = $wsName
        Location              = $ws.location
        WorkspaceResourceId   = $ws.id
        CustomerId            = $custId
        LastIngestUtc         = $null
        IngestedGB_Last60Days = $null
        HasIngestedIn60Days   = $null
        Notes                 = $null
    }

    try {
        # Ensure context is correct for cross-sub access scenarios
        Set-AzContext -SubscriptionId $subId | Out-Null

        if ([string]::IsNullOrWhiteSpace($custId)) {
            # Fallback: fetch workspace to get CustomerId if ARG didn't return it
            $w = Get-AzOperationalInsightsWorkspace -ResourceGroupName $rg -Name $wsName
            $custId = $w.CustomerId.Guid
            $row.CustomerId = $custId
        }

        # Query last 365d so "LastIngest" is meaningful even if old.
        $q = Invoke-AzOperationalInsightsQuery -WorkspaceId $custId -Query $kql -Timespan (New-TimeSpan -Days 365)

        if ($q.Results.Count -gt 0) {
            $last = $q.Results[0].LastIngest
            $gb60 = $q.Results[0].IngestedGB_60d

            $row.LastIngestUtc = $last
            $row.IngestedGB_Last60Days = if ($gb60 -ne $null) { [math]::Round([double]$gb60, 3) } else { 0 }
            $row.HasIngestedIn60Days = (
                ($row.IngestedGB_Last60Days -gt 0) -or
                ($row.LastIngestUtc -and ([datetime]$row.LastIngestUtc -ge (Get-Date).ToUniversalTime().AddDays(-60)))
            )
        }
        else {
            $row.Notes = "No results returned from Usage table."
        }
    }
    catch {
        $row.Notes = "Query failed: $($_.Exception.Message)"
    }

    $results.Add([pscustomobject]$row) | Out-Null
}

# -----------------------------
# 5) Output (table + CSV)
# -----------------------------
$resultsSorted = $results | Sort-Object SubscriptionName, WorkspaceName

# Console view (tabular)
$resultsSorted |
    Select-Object SubscriptionName, ResourceGroup, WorkspaceName, IngestedGB_Last60Days, LastIngestUtc, HasIngestedIn60Days, Notes |
    Format-Table -AutoSize

# CSV export
$csvPath = Join-Path $PWD ("default-workspaces-report-{0}.csv" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
$resultsSorted | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8

Write-Host ""
Write-Host "CSV exported to: $csvPath"