param(
    [int]$DaysThreshold = 45,
    [string]$SubscriptionIdsCsv = ""   # optional CSV for targeted runs
)

$ErrorActionPreference = "Stop"

Write-Host "=== Context Check (Service Connection) ==="
$ctx = Get-AzContext
if (-not $ctx) {
    throw "No Az context found. Ensure AzurePowerShell@5 is using a valid service connection."
}

Write-Host "Tenant:        $($ctx.Tenant.Id)"
Write-Host "Subscription:  $($ctx.Subscription.Name) [$($ctx.Subscription.Id)]"
Write-Host "Account:       $($ctx.Account.Id)"
Write-Host ""

# Ensure required module is available (usually is in hosted agents)
Import-Module Az.Resources -ErrorAction Stop

$now = Get-Date
$cutoff = $now.AddDays($DaysThreshold)

Write-Host "Filtering exemptions expiring between $now and $cutoff (next $DaysThreshold days)"
Write-Host ""

# --- Subscription selection ---
$targetSubs = @()

if ([string]::IsNullOrWhiteSpace($SubscriptionIdsCsv)) {
    Write-Host "No SubscriptionIdsCsv provided => Using all accessible subscriptions."
    $targetSubs = Get-AzSubscription
} else {
    $ids = $SubscriptionIdsCsv.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    foreach ($id in $ids) {
        $s = Get-AzSubscription -SubscriptionId $id -ErrorAction Stop
        $targetSubs += $s
    }
}

if (-not $targetSubs -or $targetSubs.Count -eq 0) {
    throw "No subscriptions found/selected."
}

Write-Host "Subscriptions to process: $($targetSubs.Count)"
Write-Host ""

# --- Collect results ---
$results = New-Object System.Collections.Generic.List[object]

foreach ($sub in $targetSubs) {
    Write-Host "---- Processing: $($sub.Name) [$($sub.Id)] ----"

    # Set context (like your existing pattern)
    Set-AzContext -SubscriptionId $sub.Id -ErrorAction Stop | Out-Null

    # Get exemptions (subscription scope + descendants depends on cmdlet support/version)
    # If your environment supports it, you can add: -IncludeDescendent
    $exemptions = Get-AzPolicyExemption -ErrorAction SilentlyContinue

    if (-not $exemptions) {
        Write-Host "No exemptions returned for this subscription."
        continue
    }

    foreach ($ex in $exemptions) {
        # expiresOn can be null (non-expiring exemptions)
        $expiresOn = $null

        # Different versions expose different shapes; handle both
        if ($ex.Properties -and $ex.Properties.ExpiresOn) {
            $expiresOn = [datetime]$ex.Properties.ExpiresOn
        } elseif ($ex.ExpiresOn) {
            $expiresOn = [datetime]$ex.ExpiresOn
        }

        if (-not $expiresOn) { continue }

        if ($expiresOn -ge $now -and $expiresOn -le $cutoff) {
            $displayName = $null
            if ($ex.Properties -and $ex.Properties.DisplayName) { $displayName = $ex.Properties.DisplayName }

            $scope = $null
            if ($ex.Properties -and $ex.Properties.PolicyAssignmentId) { $scope = $ex.Properties.PolicyAssignmentId }
            if ($ex.Properties -and $ex.Properties.Scope) { $scope = $ex.Properties.Scope }

            $category = $null
            if ($ex.Properties -and $ex.Properties.ExemptionCategory) { $category = $ex.Properties.ExemptionCategory }

            $results.Add([pscustomobject]@{
                SubscriptionName = $sub.Name
                SubscriptionId   = $sub.Id
                ExemptionName    = $ex.Name
                DisplayName      = $displayName
                Category         = $category
                ExpiresOn        = $expiresOn
                Scope            = $scope
            })
        }
    }
}

Write-Host ""
Write-Host "=== RESULTS ==="
if ($results.Count -eq 0) {
    Write-Host "No policy exemptions expiring within $DaysThreshold days."
    exit 0
}

# Print in readable table (pipeline-friendly)
$results
| Sort-Object ExpiresOn
| Format-Table SubscriptionName, ExemptionName, Category, ExpiresOn, Scope -AutoSize