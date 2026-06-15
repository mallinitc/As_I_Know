<#
.SYNOPSIS
    Azure Cost Guard - Single Subscription Safe Version

.DESCRIPTION
    This script is hardcoded to one Azure subscription only.

    Default mode:
    - Scans resources in the target subscription
    - Queries cost data
    - Estimates next 1, 2, and 5 days cost based on recent run-rate
    - Saves TXT and JSON reports in current working directory

    Delete mode:
    - Deletes all resource groups in the target subscription only
    - Exports resource group ARM templates before deletion
    - Saves delete logs
    - Requires explicit confirmation phrase

.IMPORTANT
    This does not guarantee immediate ₹0 billing.
    Azure cost data may lag.
    Some charges may appear after deletion due to delayed metering.
    ARM export is not a guaranteed perfect backup/restore mechanism.
#>

param(
    [switch]$DeleteAll,

    [string]$ConfirmDeletePhrase = "",

    [int]$RunRateLookbackDays = 3,

    [int[]]$ProjectionDays = @(1, 2, 5)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ============================================================
# HARD-CODED TARGET SUBSCRIPTION
# ============================================================

$TargetSubscriptionId = "3276807a-5a08-4b8a-9795-c08f1d787ab2"
$TargetSubscriptionNameExpected = "Mallik_Sub1"

# ============================================================
# Folder and log setup
# ============================================================

$StartTime = Get-Date
$Timestamp = $StartTime.ToString("yyyyMMdd_HHmmss")
$WorkingDir = (Get-Location).Path

$LogRoot = Join-Path $WorkingDir "AzureCostGuardLogs"
$RunDir = Join-Path $LogRoot "Run_$Timestamp"
$ExportDir = Join-Path $RunDir "ARMExports"

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null

$ReportTxt = Join-Path $RunDir "CostGuard_Report_$Timestamp.txt"
$InventoryJson = Join-Path $RunDir "ResourceInventory_$Timestamp.json"
$CostJson = Join-Path $RunDir "CostData_$Timestamp.json"
$DeleteLogTxt = Join-Path $RunDir "DeleteLog_$Timestamp.txt"
$PreviousStateFile = Join-Path $LogRoot "last_delete_summary.txt"

function Write-Log {
    param(
        [string]$Message,
        [string]$Path = $ReportTxt
    )

    $line = "[{0}] {1}" -f (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $Path -Value $line
}

function Invoke-AzCliJson {
    param(
        [string[]]$Arguments
    )

    $output = & az @Arguments -o json 2>&1

    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')`n$output"
    }

    if ([string]::IsNullOrWhiteSpace($output)) {
        return $null
    }

    return $output | ConvertFrom-Json
}

function Invoke-AzCliText {
    param(
        [string[]]$Arguments
    )

    $output = & az @Arguments 2>&1

    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')`n$output"
    }

    return $output
}

function Get-CostForSubscription {
    param(
        [string]$SubscriptionId,
        [datetime]$FromDateUtc,
        [datetime]$ToDateUtc
    )

    $scope = "/subscriptions/$SubscriptionId"
    $uri = "https://management.azure.com$scope/providers/Microsoft.CostManagement/query?api-version=2025-03-01"

    $bodyObject = @{
        type      = "ActualCost"
        timeframe = "Custom"
        timePeriod = @{
            from = $FromDateUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")
            to   = $ToDateUtc.ToString("yyyy-MM-ddTHH:mm:ssZ")
        }
        dataset = @{
            granularity = "Daily"
            aggregation = @{
                totalCost = @{
                    name     = "PreTaxCost"
                    function = "Sum"
                }
            }
        }
    }

    $bodyFile = Join-Path $RunDir "cost_query_$SubscriptionId.json"
    $bodyObject | ConvertTo-Json -Depth 20 | Set-Content -Path $bodyFile -Encoding UTF8

    try {
        $bodyArg = "@$bodyFile"

        $responseRaw = & az rest `
            --method post `
            --uri $uri `
            --body $bodyArg `
            -o json 2>&1

        if ($LASTEXITCODE -ne 0) {
            throw $responseRaw
        }

        $response = $responseRaw | ConvertFrom-Json

        $columns = $response.properties.columns
        $rows = $response.properties.rows

        $costIndex = -1
        $currencyIndex = -1
        $dateIndex = -1

        for ($i = 0; $i -lt $columns.Count; $i++) {
            if ($columns[$i].name -eq "PreTaxCost" -or $columns[$i].name -eq "Cost") {
                $costIndex = $i
            }

            if ($columns[$i].name -eq "Currency") {
                $currencyIndex = $i
            }

            if ($columns[$i].name -eq "UsageDate") {
                $dateIndex = $i
            }
        }

        $dailyItems = @()
        $totalCost = 0
        $currency = "Unknown"

        foreach ($row in $rows) {
            $cost = 0
            if ($costIndex -ge 0) {
                $cost = [decimal]$row[$costIndex]
            }

            $rowCurrency = "Unknown"
            if ($currencyIndex -ge 0) {
                $rowCurrency = [string]$row[$currencyIndex]
            }

            $usageDate = "Unknown"
            if ($dateIndex -ge 0) {
                $usageDate = [string]$row[$dateIndex]
            }

            $totalCost += $cost

            if ($rowCurrency -ne "Unknown") {
                $currency = $rowCurrency
            }

            $dailyItems += [PSCustomObject]@{
                UsageDate = $usageDate
                Cost      = [math]::Round($cost, 4)
                Currency  = $rowCurrency
            }
        }

        return [PSCustomObject]@{
            Success    = $true
            TotalCost  = [math]::Round($totalCost, 4)
            Currency   = $currency
            DailyItems = $dailyItems
            Error      = $null
        }
    }
    catch {
        return [PSCustomObject]@{
            Success    = $false
            TotalCost  = 0
            Currency   = "Unknown"
            DailyItems = @()
            Error      = $_.Exception.Message
        }
    }
}

# ============================================================
# Start
# ============================================================

Write-Log "Azure Cost Guard started."
Write-Log "Working directory: $WorkingDir"
Write-Log "Run directory: $RunDir"
Write-Log "Hardcoded target subscription ID: $TargetSubscriptionId"

# ============================================================
# Validate Azure CLI login
# ============================================================

try {
    $currentAccount = Invoke-AzCliJson -Arguments @("account", "show")
}
catch {
    Write-Log "ERROR: Azure CLI is not logged in."
    Write-Log "Run this first:"
    Write-Log "az login --tenant f88ffdc1-cdc8-4b37-8166-a7ebc1e71f71"
    throw
}

Write-Log "Currently logged-in subscription: $($currentAccount.name) ($($currentAccount.id))"
Write-Log "Currently logged-in tenant: $($currentAccount.tenantId)"

# ============================================================
# Force Azure CLI context to target subscription only
# ============================================================

Write-Log "Setting Azure CLI context to hardcoded target subscription..."

Invoke-AzCliText -Arguments @(
    "account",
    "set",
    "--subscription",
    $TargetSubscriptionId
) | Out-Null

$targetAccount = Invoke-AzCliJson -Arguments @("account", "show")

if ($targetAccount.id -ne $TargetSubscriptionId) {
    throw "Safety check failed. Active subscription does not match hardcoded target subscription."
}

Write-Log "Verified target subscription context:"
Write-Log "Subscription name: $($targetAccount.name)"
Write-Log "Subscription ID: $($targetAccount.id)"
Write-Log "Tenant ID: $($targetAccount.tenantId)"

if ($targetAccount.name -ne $TargetSubscriptionNameExpected) {
    Write-Log "WARNING: Subscription name does not match expected value."
    Write-Log "Expected: $TargetSubscriptionNameExpected"
    Write-Log "Actual: $($targetAccount.name)"
    Write-Log "Continuing because subscription ID matched exactly."
}

# ============================================================
# Previous deletion summary
# ============================================================

if (Test-Path $PreviousStateFile) {
    Write-Log "Previous delete summary found:"
    Get-Content $PreviousStateFile | ForEach-Object {
        Write-Log "PREVIOUS: $_"
    }
}
else {
    Write-Log "No previous delete summary found."
}

# ============================================================
# Resource inventory
# ============================================================

Write-Log "------------------------------------------------------------"
Write-Log "Scanning resources in target subscription only..."

$resources = @()

try {
    $resources = Invoke-AzCliJson -Arguments @(
        "resource",
        "list",
        "--subscription",
        $TargetSubscriptionId
    )

    if ($null -eq $resources) {
        $resources = @()
    }

    Write-Log "Resource count: $($resources.Count)"

    if ($resources.Count -eq 0) {
        Write-Log "No resources found in the target subscription."
    }
    else {
        $resourceSummary = $resources |
            Group-Object type |
            Sort-Object Count -Descending |
            Select-Object Count, Name

        Write-Log "Resource type summary:"

        foreach ($item in $resourceSummary) {
            Write-Log ("  {0} : {1}" -f $item.Name, $item.Count)
        }
    }
}
catch {
    Write-Log "ERROR while listing resources: $($_.Exception.Message)"
    throw
}

$inventory = @()

foreach ($res in $resources) {
    $inventory += [PSCustomObject]@{
        SubscriptionName = $targetAccount.name
        SubscriptionId   = $TargetSubscriptionId
        ResourceGroup    = $res.resourceGroup
        Name             = $res.name
        Type             = $res.type
        Location         = $res.location
        Id               = $res.id
    }
}

$inventory | ConvertTo-Json -Depth 20 | Set-Content -Path $InventoryJson -Encoding UTF8

Write-Log "Saved resource inventory JSON: $InventoryJson"

# ============================================================
# Cost query and projection
# ============================================================

$todayUtc = (Get-Date).ToUniversalTime()
$lookbackFromUtc = $todayUtc.AddDays(-1 * $RunRateLookbackDays)
$monthStartUtc = Get-Date -Year $todayUtc.Year -Month $todayUtc.Month -Day 1 -Hour 0 -Minute 0 -Second 0
$monthStartUtc = $monthStartUtc.ToUniversalTime()

Write-Log "------------------------------------------------------------"
Write-Log "Querying month-to-date actual cost..."

$mtdCost = Get-CostForSubscription `
    -SubscriptionId $TargetSubscriptionId `
    -FromDateUtc $monthStartUtc `
    -ToDateUtc $todayUtc

if ($mtdCost.Success) {
    Write-Log "Month-to-date cost: $($mtdCost.TotalCost) $($mtdCost.Currency)"
}
else {
    Write-Log "Could not query month-to-date cost: $($mtdCost.Error)"
}

Write-Log "Querying last $RunRateLookbackDays day actual cost for run-rate estimate..."

$recentCost = Get-CostForSubscription `
    -SubscriptionId $TargetSubscriptionId `
    -FromDateUtc $lookbackFromUtc `
    -ToDateUtc $todayUtc

$dailyAverage = 0

if ($recentCost.Success -and $RunRateLookbackDays -gt 0) {
    $dailyAverage = [math]::Round(($recentCost.TotalCost / $RunRateLookbackDays), 4)

    Write-Log "Recent $RunRateLookbackDays day total: $($recentCost.TotalCost) $($recentCost.Currency)"
    Write-Log "Estimated daily run-rate: $dailyAverage $($recentCost.Currency)"

    foreach ($days in $ProjectionDays) {
        $projected = [math]::Round(($dailyAverage * $days), 4)
        Write-Log "Projected cost for next $days day(s), if same run-rate continues: $projected $($recentCost.Currency)"
    }
}
else {
    Write-Log "Could not query recent cost: $($recentCost.Error)"
}

$costResult = [PSCustomObject]@{
    SubscriptionName       = $targetAccount.name
    SubscriptionId         = $TargetSubscriptionId
    MonthToDateCost        = $mtdCost.TotalCost
    MonthToDateCurrency    = $mtdCost.Currency
    RecentLookbackDays     = $RunRateLookbackDays
    RecentLookbackCost     = $recentCost.TotalCost
    EstimatedDailyRunRate  = $dailyAverage
    Currency               = $recentCost.Currency
    Projection             = @(
        foreach ($days in $ProjectionDays) {
            [PSCustomObject]@{
                Days          = $days
                ProjectedCost = [math]::Round(($dailyAverage * $days), 4)
                Currency      = $recentCost.Currency
            }
        }
    )
    CostQuerySuccess       = ($mtdCost.Success -and $recentCost.Success)
    CostQueryError         = @($mtdCost.Error, $recentCost.Error) -join " | "
}

$costResult | ConvertTo-Json -Depth 20 | Set-Content -Path $CostJson -Encoding UTF8

Write-Log "Saved cost data JSON: $CostJson"

# ============================================================
# Optional deletion mode
# ============================================================

if ($DeleteAll) {
    Write-Log "------------------------------------------------------------" $DeleteLogTxt
    Write-Log "DELETE MODE REQUESTED." $DeleteLogTxt
    Write-Log "Target subscription only: $($targetAccount.name) ($TargetSubscriptionId)" $DeleteLogTxt

    if ($ConfirmDeletePhrase -ne "DELETE ALL RESOURCES IN TARGET SUBSCRIPTION") {
        Write-Log "Delete blocked. Confirmation phrase missing or incorrect." $DeleteLogTxt
        Write-Log "Required confirmation phrase:" $DeleteLogTxt
        Write-Log "DELETE ALL RESOURCES IN TARGET SUBSCRIPTION" $DeleteLogTxt

        throw "Delete blocked. Confirmation phrase missing or incorrect."
    }

    Write-Log "Confirmation phrase accepted." $DeleteLogTxt
    Write-Log "Exporting ARM templates and deleting resource groups..." $DeleteLogTxt

    $resourceGroups = Invoke-AzCliJson -Arguments @(
        "group",
        "list",
        "--subscription",
        $TargetSubscriptionId
    )

    if ($null -eq $resourceGroups -or $resourceGroups.Count -eq 0) {
        Write-Log "No resource groups found. Nothing to delete." $DeleteLogTxt
    }
    else {
        foreach ($rg in $resourceGroups) {
            $rgName = $rg.name
            $safeRgName = ($rgName -replace '[^a-zA-Z0-9_-]', '_')

            $templatePath = Join-Path $ExportDir "$safeRgName-template.json"
            $rgResourcesPath = Join-Path $ExportDir "$safeRgName-resources-before-delete.json"

            Write-Log "------------------------------------------------------------" $DeleteLogTxt
            Write-Log "Preparing resource group: $rgName" $DeleteLogTxt

            try {
                Write-Log "Exporting resource list before delete: $rgResourcesPath" $DeleteLogTxt

                $rgResources = Invoke-AzCliJson -Arguments @(
                    "resource",
                    "list",
                    "--subscription",
                    $TargetSubscriptionId,
                    "--resource-group",
                    $rgName
                )

                $rgResources | ConvertTo-Json -Depth 30 | Set-Content -Path $rgResourcesPath -Encoding UTF8
            }
            catch {
                Write-Log "WARNING: Failed to export resource list for $rgName. Error: $($_.Exception.Message)" $DeleteLogTxt
            }

            try {
                Write-Log "Exporting ARM template before delete: $templatePath" $DeleteLogTxt

                $exportOutput = & az group export `
                    --subscription $TargetSubscriptionId `
                    --name $rgName `
                    -o json 2>&1

                if ($LASTEXITCODE -eq 0) {
                    $exportOutput | Set-Content -Path $templatePath -Encoding UTF8
                    Write-Log "ARM template exported successfully." $DeleteLogTxt
                }
                else {
                    Write-Log "WARNING: ARM template export failed for $rgName. Error: $exportOutput" $DeleteLogTxt
                }
            }
            catch {
                Write-Log "WARNING: Failed to export ARM template for $rgName. Error: $($_.Exception.Message)" $DeleteLogTxt
            }

            try {
                Write-Log "Deleting resource group: $rgName" $DeleteLogTxt

                & az group delete `
                    --subscription $TargetSubscriptionId `
                    --name $rgName `
                    --yes `
                    --no-wait 2>&1 | ForEach-Object {
                        Write-Log $_ $DeleteLogTxt
                    }

                Write-Log "Delete submitted for resource group: $rgName" $DeleteLogTxt
            }
            catch {
                Write-Log "ERROR deleting resource group $rgName : $($_.Exception.Message)" $DeleteLogTxt
            }
        }
    }

    $deleteSummary = @"
Last delete run: $(Get-Date)
Target subscription name: $($targetAccount.name)
Target subscription ID: $TargetSubscriptionId
Run directory: $RunDir
Delete log: $DeleteLogTxt
ARM exports directory: $ExportDir
Important: Deletion was submitted using az group delete --no-wait. Some resources may continue deleting in the background.
"@

    $deleteSummary | Set-Content -Path $PreviousStateFile -Encoding UTF8
    Write-Log "Delete summary saved to: $PreviousStateFile" $DeleteLogTxt
}
else {
    Write-Log "------------------------------------------------------------"
    Write-Log "SAFE MODE: No deletion performed."
    Write-Log "To delete all resource groups in the hardcoded target subscription only, run:"
    Write-Log ".\AzureCostGuard.ps1 -DeleteAll -ConfirmDeletePhrase `"DELETE ALL RESOURCES IN TARGET SUBSCRIPTION`""
}

# ============================================================
# End
# ============================================================

$EndTime = Get-Date

Write-Log "------------------------------------------------------------"
Write-Log "Azure Cost Guard completed."
Write-Log "Duration: $([math]::Round(($EndTime - $StartTime).TotalSeconds, 2)) seconds."
Write-Log "Main TXT report: $ReportTxt"
Write-Log "Inventory JSON: $InventoryJson"
Write-Log "Cost JSON: $CostJson"