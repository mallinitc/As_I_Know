#requires -Version 7.0
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---- Config ----
$BatchSize      = 100        # process 100 subs at a time
$ThrottleLimit  = 20         # parallel workers (tune based on CPU + throttling)
$OutputCsv      = ".\DirectUserRbacAssignments.csv"

# If you want to exclude some roles (optional) add names here:
$ExcludeRoleNames = @(
  # "Reader"
)

# ---- Login ----
# Az login (ARM)
Connect-AzAccount | Out-Null

# Graph login (for user enrichment)
# You can skip Graph and use Get-AzADUser, but Graph is generally better at scale.
# Requires Microsoft.Graph module installed.
try {
    Import-Module Microsoft.Graph.Users -ErrorAction Stop
    Connect-MgGraph -Scopes "User.Read.All" | Out-Null
} catch {
    Write-Warning "Microsoft.Graph.Users not available or Graph login failed. Will fall back to Get-AzADUser."
    $UseGraph = $false
}
if (-not $PSBoundParameters.ContainsKey('UseGraph')) { $UseGraph = $true }

# ---- Helper: Get user details (Graph preferred) ----
function Get-EntraUserInfo {
    param(
        [Parameter(Mandatory)]
        [string] $ObjectId,
        [hashtable] $Cache,
        [bool] $PreferGraph = $true
    )

    if ($Cache.ContainsKey($ObjectId)) { return $Cache[$ObjectId] }

    $info = [pscustomobject]@{
        ObjectId    = $ObjectId
        DisplayName = $null
        UserPrincipalName = $null
        Mail        = $null
        AccountEnabled = $null
    }

    try {
        if ($PreferGraph -and (Get-Command Get-MgUser -ErrorAction SilentlyContinue)) {
            $u = Get-MgUser -UserId $ObjectId -Property "displayName,userPrincipalName,mail,accountEnabled" -ErrorAction Stop
            $info.DisplayName = $u.DisplayName
            $info.UserPrincipalName = $u.UserPrincipalName
            $info.Mail = $u.Mail
            $info.AccountEnabled = $u.AccountEnabled
        } else {
            # Fallback
            $u = Get-AzADUser -ObjectId $ObjectId -ErrorAction Stop
            $info.DisplayName = $u.DisplayName
            $info.UserPrincipalName = $u.UserPrincipalName
            $info.Mail = $u.Mail
            $info.AccountEnabled = $u.AccountEnabled
        }
    } catch {
        # User might be deleted / guest / access blocked; keep nulls.
    }

    $Cache[$ObjectId] = $info
    return $info
}

# ---- Get subscriptions ----
$subs = Get-AzSubscription | Select-Object Id, Name, TenantId

# ---- Work in batches of 100 subscriptions ----
$allResults = New-Object System.Collections.Generic.List[object]

for ($i = 0; $i -lt $subs.Count; $i += $BatchSize) {
    $batch = $subs[$i..([Math]::Min($i + $BatchSize - 1, $subs.Count - 1))]

    Write-Host "Processing subscriptions $i to $([Math]::Min($i+$BatchSize-1,$subs.Count-1)) ..." -ForegroundColor Cyan

    # IMPORTANT: In -Parallel runspaces, reuse auth context carefully.
    # We'll set context inside each worker.
    $batchResults = $batch | ForEach-Object -Parallel {
        param($ExcludeRoleNames, $UseGraph)

        $subId   = $_.Id
        $subName = $_.Name

        # Set context per worker
        Set-AzContext -SubscriptionId $subId | Out-Null

        # Cache user lookups per subscription worker
        $userCache = @{}

        # Pull all role assignments in subscription
        # -IncludeClassicAdministrators optional; remove if you don't care.
        $assignments = Get-AzRoleAssignment -Scope "/subscriptions/$subId" -ErrorAction Stop

        # Filter to direct user assignments (ARM)
        $directUsers = $assignments | Where-Object {
            $_.ObjectType -eq "User" -and
            $_.SignInName -ne $null -and
            ($ExcludeRoleNames.Count -eq 0 -or ($ExcludeRoleNames -notcontains $_.RoleDefinitionName))
        }

        foreach ($a in $directUsers) {
            $user = Get-EntraUserInfo -ObjectId $a.ObjectId -Cache $userCache -PreferGraph:$UseGraph

            # Determine "level" for quick reporting
            $level = if ($a.Scope -eq "/subscriptions/$subId") {
                "Subscription"
            } elseif ($a.Scope -like "/subscriptions/$subId/resourceGroups/*") {
                "ResourceGroupOrBelow"
            } else {
                "Other"
            }

            [pscustomobject]@{
                SubscriptionId   = $subId
                SubscriptionName = $subName
                ScopeLevel       = $level
                Scope            = $a.Scope
                RoleName         = $a.RoleDefinitionName
                RoleAssignmentId = $a.RoleAssignmentId

                # Principal (RBAC)
                PrincipalType    = $a.ObjectType
                PrincipalObjectId = $a.ObjectId
                PrincipalSignInName = $a.SignInName

                # Entra enrichment
                EntraDisplayName = $user.DisplayName
                EntraUPN         = $user.UserPrincipalName
                EntraMail        = $user.Mail
                EntraAccountEnabled = $user.AccountEnabled

                # Handy fields
                CreatedOn        = $null  # ARM role assignment doesn't reliably expose created time
            }
        }
    } -ThrottleLimit $ThrottleLimit -ArgumentList ($ExcludeRoleNames, $UseGraph)

    $batchResults | ForEach-Object { $allResults.Add($_) }
}

# ---- Export ----
$allResults
| Sort-Object SubscriptionName, Scope, RoleName, EntraUPN
| Export-Csv -Path $OutputCsv -NoTypeInformation -Encoding UTF8

Write-Host "Done. Exported: $OutputCsv" -ForegroundColor Green