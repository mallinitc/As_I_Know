# --- Assumes you already connected Az (pipeline does) and you already connected MgGraph with AccessToken ---
# Token/Connect-MgGraph block stays the same as your working script

# Fetch exemptions (subscription + descendants)
$scope = "/subscriptions/$($Subscription.Id)"
$Exemptions = Get-AzPolicyExemption -Scope $scope -IncludeDescendent -ErrorAction SilentlyContinue

Write-Host "Exemptions Count: $(@($Exemptions).Count)"

foreach ($Exemption in $Exemptions) {

    # Scope: trim exemption ID to parent scope (same as your old script)
    $parentScope = ($Exemption.Id -split "/providers/Microsoft.Authorization")[0]

    # Name: prefer DisplayName, else Name (same as your old script)
    $ExemptionName =
        if ($Exemption.DisplayName) { $Exemption.DisplayName }
        elseif ($Exemption.Properties -and $Exemption.Properties.DisplayName) { $Exemption.Properties.DisplayName }
        else { $Exemption.Name }

    # Category / ExpiresOn / Description
    $Category   = $null
    $ExpiresOn  = $null
    $Desc       = $null

    if ($Exemption.Properties) {
        $Category  = $Exemption.Properties.ExemptionCategory
        $Desc      = $Exemption.Properties.Description
        $ExpiresOn = $Exemption.Properties.ExpiresOn
    } else {
        # fallback if your object shape exposes top-level fields
        $Category  = $Exemption.ExemptionCategory
        $Desc      = $Exemption.Description
        $ExpiresOn = $Exemption.ExpiresOn
    }

    # CreatedBy / LastModifiedBy from SystemData (UPN/objectId/email) -> resolve to DisplayName via Graph
    $createdByDisplay = $null
    $modifiedByDisplay = $null

    $createdByRaw  = $null
    $modifiedByRaw = $null

    if ($Exemption.SystemData) {
        $createdByRaw  = $Exemption.SystemData.CreatedBy
        $modifiedByRaw = $Exemption.SystemData.LastModifiedBy
    } elseif ($Exemption.Properties -and $Exemption.Properties.SystemData) {
        $createdByRaw  = $Exemption.Properties.SystemData.CreatedBy
        $modifiedByRaw = $Exemption.Properties.SystemData.LastModifiedBy
    }

    # Resolve only if we have something and it looks like a UPN/email
    if ($createdByRaw) {
        try {
            $u = Get-MgUser -Filter "userPrincipalName eq '$createdByRaw'" -ErrorAction Stop
            $createdByDisplay = $u.DisplayName
        } catch {
            $createdByDisplay = $createdByRaw
        }
    }

    if ($modifiedByRaw) {
        try {
            $u = Get-MgUser -Filter "userPrincipalName eq '$modifiedByRaw'" -ErrorAction Stop
            $modifiedByDisplay = $u.DisplayName
        } catch {
            $modifiedByDisplay = $modifiedByRaw
        }
    }

    # Build output object (same columns as your old mail table)
    $obj = [pscustomobject]@{
        SubscriptionName = $Subscription.Name
        ExemptionName    = $ExemptionName
        Scope            = $parentScope
        Category         = $Category
        ExpiresOn        = $ExpiresOn
        ExemptionDesc    = $Desc
        CreatedBy        = $createdByDisplay
        LastModifiedBy   = $modifiedByDisplay
    }

    $Output.Add($obj) | Out-Null
}

# After loop, print a quick table for testing
$Output | Select SubscriptionName, ExemptionName, Category, ExpiresOn, Scope, CreatedBy, LastModifiedBy | Format-Table -AutoSize






function Resolve-UpnToDisplayNameOrKeep {
    param(
        [Parameter(Mandatory=$false)]
        [string] $UpnOrMail
    )

    # If input is empty/null -> return empty (don’t force "Unknown")
    if ([string]::IsNullOrWhiteSpace($UpnOrMail)) {
        return $UpnOrMail
    }

    # Try UPN match
    try {
        $u = Get-MgUser -Filter "userPrincipalName eq '$UpnOrMail'" -ErrorAction Stop
        if ($u) { return $u[0].DisplayName }
    } catch {}

    # Try mail match (covers cases where UPN != mail)
    try {
        $u = Get-MgUser -Filter "mail eq '$UpnOrMail'" -ErrorAction Stop
        if ($u) { return $u[0].DisplayName }
    } catch {}

    # Could be deleted user / not resolvable -> keep original string
    return $UpnOrMail
}




$obj = [pscustomobject]@{
    SubscriptionName = $Subscription.Name
    ExemptionName    = $ExemptionName
    Scope            = $parentScope
    Category         = $Category
    ExpiresOn        = $ExpiresOn
    ExemptionDesc    = $Desc
    CreatedBy        = $createdByDisplay     # display name or original UPN
    LastModifiedBy   = $modifiedByDisplay    # display name or original UPN
}
$null = $Output.Add($obj)


$createdByRaw  = $Exemption.SystemDataCreatedBy
$modifiedByRaw = $Exemption.SystemDataLastModifiedBy

$createdByDisplay  = Resolve-UpnToDisplayNameOrKeep -UpnOrMail $createdByRaw
$modifiedByDisplay = Resolve-UpnToDisplayNameOrKeep -UpnOrMail $modifiedByRaw





