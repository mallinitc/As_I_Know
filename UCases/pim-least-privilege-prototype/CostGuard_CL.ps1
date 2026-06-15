<#
======================================================================
 azure-cost-guard.ps1
======================================================================
 PURPOSE
   A daily-run helper for a PERSONAL Azure prototype subscription.

   Default run (no switch):  REPORT ONLY (safe)
     - Lists every resource in ONE target subscription
     - Pulls recent cost, shows a per-day breakdown
     - Projects the next 1, 2, and 5 days
     - Appends everything to a txt log in the current directory

   With -Teardown:           TEAR DOWN (guarded)
     - Shows the subscription + resources, makes you type the
       subscription NAME to confirm, then deletes every resource
       group in that one subscription
     - Records what it deleted in the same txt log

 SAFETY (do not weaken these)
   - Operates on exactly ONE subscription that YOU set below.
   - Refuses to run if the subscription id is blank.
   - Verifies the active context matches the target before doing anything.
   - Teardown requires BOTH the -Teardown switch AND a typed confirmation.

 NOT INCLUDED (on purpose)
   - Auto-recreation from the log. A deletion log cannot faithfully
     rebuild Azure resources. Use Bicep/Terraform for that instead.

 PREREQUISITES
   - PowerShell 7+ recommended (Windows PowerShell 5.1 also works)
   - Az module:   Install-Module Az -Scope CurrentUser
   - Signed in:   the script will call Connect-AzAccount if needed
======================================================================
#>

[CmdletBinding()]
param(
    # Pass -Teardown to ENABLE deletion. Without it, the script only reports.
    [switch]$Teardown,

    # How many days of recent usage to average for the projection.
    [int]$LookbackDays = 7
)

# ---------------------------------------------------------------------
# 1. CONFIG  --  YOU MUST SET THIS
# ---------------------------------------------------------------------
# Paste the Subscription ID of your PERSONAL prototype subscription.
# Leave it blank and the script will list your subscriptions and stop,
# so you can copy the right id in here. This is the core safety scope.
$TargetSubscriptionId = ""

# Log file lives in the current working directory, as requested.
$LogFile = Join-Path (Get-Location) "azure-cost-guard-log.txt"

# ---------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------
function Write-Log {
    param([string]$Text)
    Add-Content -Path $LogFile -Value $Text
    Write-Host $Text
}

function Write-Separator {
    $line = ("=" * 70)
    Add-Content -Path $LogFile -Value $line
    Write-Host $line -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------
# 2. Ensure the Az module is present
# ---------------------------------------------------------------------
if (-not (Get-Module -ListAvailable -Name Az.Accounts)) {
    Write-Host "The Az module is not installed." -ForegroundColor Yellow
    Write-Host "Install it once with:  Install-Module Az -Scope CurrentUser" -ForegroundColor Yellow
    return
}

# ---------------------------------------------------------------------
# 3. Connect + lock onto the ONE target subscription
# ---------------------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($TargetSubscriptionId)) {
    Write-Host "No TargetSubscriptionId set." -ForegroundColor Yellow
    Write-Host "Here are the subscriptions this login can see:`n" -ForegroundColor Yellow
    try {
        if (-not (Get-AzContext)) { Connect-AzAccount | Out-Null }
        Get-AzSubscription | Select-Object Name, Id, State | Format-Table -AutoSize
    } catch {
        Write-Host "Could not list subscriptions: $($_.Exception.Message)" -ForegroundColor Red
    }
    Write-Host "`nCopy the correct Id into the `$TargetSubscriptionId variable, then re-run." -ForegroundColor Yellow
    return
}

try {
    if (-not (Get-AzContext)) { Connect-AzAccount | Out-Null }
    Set-AzContext -SubscriptionId $TargetSubscriptionId -ErrorAction Stop | Out-Null
} catch {
    Write-Host "Could not select subscription '$TargetSubscriptionId': $($_.Exception.Message)" -ForegroundColor Red
    return
}

$ctx = Get-AzContext
if ($ctx.Subscription.Id -ne $TargetSubscriptionId) {
    Write-Host "Active subscription does not match the target. Aborting for safety." -ForegroundColor Red
    return
}

$subName = $ctx.Subscription.Name
$runStamp = (Get-Date).ToString("dd-MMM-yyyy HH:mm:ss")

Write-Separator
Write-Log "RUN: $runStamp"
Write-Log "Subscription: $subName ($TargetSubscriptionId)"

# ---------------------------------------------------------------------
# 4. Inventory the subscription
# ---------------------------------------------------------------------
$resources = Get-AzResource
$resourceCount = ($resources | Measure-Object).Count

# --- The "we deleted it yesterday" path ------------------------------
if ($resourceCount -eq 0) {
    Write-Log "No resources found in this subscription."
    Write-Log ""

    # Surface the most recent teardown record from the log, if any.
    if (Test-Path $LogFile) {
        $logText = Get-Content $LogFile
        $lastTeardownIdx = ($logText | Select-String "TEARDOWN PERFORMED" | Select-Object -Last 1).LineNumber
        if ($lastTeardownIdx) {
            Write-Host "`nMost recent teardown on record:" -ForegroundColor Cyan
            $logText[($lastTeardownIdx-1)..([Math]::Min($lastTeardownIdx+40, $logText.Count-1))] |
                ForEach-Object { Write-Host $_ }
        } else {
            Write-Host "`nNo prior teardown is recorded in the log." -ForegroundColor Cyan
        }
    }

    Write-Host "`nNothing to recreate automatically." -ForegroundColor Yellow
    Write-Host "Rebuild from your Bicep/Terraform template, not from this log." -ForegroundColor Yellow
    Write-Separator
    return
}

Write-Log "Resource count: $resourceCount"
Write-Log "--- Current resources ---"
foreach ($r in $resources) {
    Write-Log ("  [{0}] {1}  (RG: {2}, {3})" -f $r.ResourceType, $r.Name, $r.ResourceGroupName, $r.Location)
}
Write-Log ""

# ---------------------------------------------------------------------
# 5. Cost: recent actuals + projection (best-effort)
# ---------------------------------------------------------------------
# NOTE: Azure cost data lags ~8-24h. Projections assume usage continues
# at the recent average. They are accurate for fixed/hourly resources
# and only rough for pay-per-use ones (e.g. Azure OpenAI per-token).
$startDate = (Get-Date).AddDays(-$LookbackDays)
$endDate   = Get-Date
$currency  = "INR"
$dailyAverage = 0.0
$haveCost = $false

try {
    $usage = Get-AzConsumptionUsageDetail -StartDate $startDate -EndDate $endDate -ErrorAction Stop

    if ($usage -and $usage.Count -gt 0) {
        $haveCost = $true
        if ($usage[0].Currency) { $currency = $usage[0].Currency }

        # Per-day totals
        $byDay = $usage | Group-Object { ([datetime]$_.UsageStart).ToString("dd-MMM") } |
                 ForEach-Object {
                     [PSCustomObject]@{
                         Day  = $_.Name
                         Cost = ([math]::Round((($_.Group | Measure-Object PretaxCost -Sum).Sum), 2))
                     }
                 }

        $totalCost   = ($usage | Measure-Object PretaxCost -Sum).Sum
        $distinctDays = ($usage | Group-Object { ([datetime]$_.UsageStart).Date }).Count
        if ($distinctDays -lt 1) { $distinctDays = 1 }
        $dailyAverage = [math]::Round(($totalCost / $distinctDays), 2)

        Write-Log "--- Cost (last $LookbackDays days, currency: $currency) ---"
        foreach ($d in $byDay) { Write-Log ("  {0}: {1} {2}" -f $d.Day, $currency, $d.Cost) }
        Write-Log ("  Total over period : {0} {1}" -f $currency, ([math]::Round($totalCost,2)))
        Write-Log ("  Average per day   : {0} {1}" -f $currency, $dailyAverage)
    } else {
        Write-Log "Cost data returned empty (usage may not have posted yet, or the account type isn't supported by this cmdlet)."
    }
} catch {
    Write-Log "Could not retrieve cost data: $($_.Exception.Message)"
    Write-Log "Inventory above is still accurate; only the cost figures are unavailable."
}

if ($haveCost) {
    Write-Log ""
    Write-Log "--- Projection if resources are LEFT RUNNING (estimate) ---"
    Write-Log ("  Next 1 day  : ~{0} {1}" -f $currency, ([math]::Round($dailyAverage * 1, 2)))
    Write-Log ("  Next 2 days : ~{0} {1}" -f $currency, ([math]::Round($dailyAverage * 2, 2)))
    Write-Log ("  Next 5 days : ~{0} {1}  (per day ~{2} {0})" -f $currency, ([math]::Round($dailyAverage * 5, 2)), $dailyAverage)
    Write-Log "  (Estimate only: assumes usage continues at the recent average.)"
}

Write-Log ""

# ---------------------------------------------------------------------
# 6. Optional guarded teardown
# ---------------------------------------------------------------------
if (-not $Teardown) {
    Write-Host "`nReport complete. To tear everything down, re-run with:  -Teardown" -ForegroundColor Green
    Write-Separator
    return
}

# --- Teardown path: requires typed confirmation ----------------------
Write-Host "`n*** TEARDOWN REQUESTED ***" -ForegroundColor Red
Write-Host "This will DELETE every resource group in:" -ForegroundColor Red
Write-Host "    $subName ($TargetSubscriptionId)" -ForegroundColor Red
Write-Host "Resources that will be removed:" -ForegroundColor Red
foreach ($r in $resources) {
    Write-Host ("    {0}  ({1})" -f $r.Name, $r.ResourceType) -ForegroundColor Red
}

$confirm = Read-Host "`nType the subscription NAME exactly to confirm deletion"
if ($confirm -ne $subName) {
    Write-Host "Name did not match. Nothing was deleted." -ForegroundColor Yellow
    Write-Separator
    return
}

Write-Log ""
Write-Log "TEARDOWN PERFORMED: $((Get-Date).ToString('dd-MMM-yyyy HH:mm:ss'))"
Write-Log "Deleting all resource groups in $subName ($TargetSubscriptionId)..."

$groups = Get-AzResourceGroup
foreach ($g in $groups) {
    # Record what's inside before deleting, for the audit trail.
    $inGroup = $resources | Where-Object { $_.ResourceGroupName -eq $g.ResourceGroupName }
    Write-Log ("  Resource group: {0}" -f $g.ResourceGroupName)
    foreach ($r in $inGroup) {
        Write-Log ("     - deleted: [{0}] {1}" -f $r.ResourceType, $r.Name)
    }
    try {
        Remove-AzResourceGroup -Name $g.ResourceGroupName -Force -ErrorAction Stop | Out-Null
        Write-Log ("     -> resource group '{0}' removed." -f $g.ResourceGroupName)
    } catch {
        Write-Log ("     !! failed to remove '{0}': {1}" -f $g.ResourceGroupName, $_.Exception.Message)
    }
}

Write-Log ""
Write-Log "Teardown complete. New charges should stop now and trend toward ~0 $currency."
Write-Log "Note: charges already accrued BEFORE deletion will still appear on the bill (usually tiny)."
Write-Separator