# Cache assignments so we don't call ARM repeatedly
$assignmentCache = @{}

function Get-AssignmentDisplayName {
    param([string]$PolicyAssignmentId)

    if ([string]::IsNullOrWhiteSpace($PolicyAssignmentId)) { return $null }
    if ($assignmentCache.ContainsKey($PolicyAssignmentId)) { return $assignmentCache[$PolicyAssignmentId] }

    try {
        $a = Get-AzPolicyAssignment -Id $PolicyAssignmentId -ErrorAction Stop
        $dn = $a.Properties.DisplayName
        if (-not $dn) { $dn = $a.Name }  # fallback
        $assignmentCache[$PolicyAssignmentId] = $dn
        return $dn
    } catch {
        # If assignment is at MG scope not accessible in this sub context, keep the ID tail as fallback
        $fallback = ($PolicyAssignmentId.Split("/") | Select-Object -Last 1)
        $assignmentCache[$PolicyAssignmentId] = $fallback
        return $fallback
    }
}

function Get-FriendlyScope {
    param([string]$RawScope)

    if ([string]::IsNullOrWhiteSpace($RawScope)) { return $null }

    # Examples:
    # /subscriptions/<id>
    # /subscriptions/<id>/resourceGroups/<rg>
    # /providers/Microsoft.Management/managementGroups/<mg>
    if ($RawScope -match "/subscriptions/[^/]+/resourceGroups/([^/]+)") { return "RG: $($Matches[1])" }
    if ($RawScope -match "/subscriptions/([^/]+)") { return "SUB: $($Matches[1])" }
    if ($RawScope -match "/providers/Microsoft.Management/managementGroups/([^/]+)") { return "MG: $($Matches[1])" }

    return $RawScope
}

$rows = foreach ($ex in $exemptions) {

    $displayName = $ex.Properties.DisplayName
    if (-not $displayName) { $displayName = $ex.Name }  # fallback

    $assignmentId = $ex.Properties.PolicyAssignmentId
    $assignmentName = Get-AssignmentDisplayName -PolicyAssignmentId $assignmentId

    $rawScope = $ex.Properties.Scope
    if (-not $rawScope) { $rawScope = $ex.Id -replace "/providers/Microsoft.Authorization/policyExemptions/.*$","" }

    $expiresOn = $ex.Properties.ExpiresOn  # may be $null
    $createdBy = $null
    if ($ex.SystemData -and $ex.SystemData.CreatedBy) { $createdBy = $ex.SystemData.CreatedBy }
    if (-not $createdBy -and $ex.Properties -and $ex.Properties.CreatedBy) { $createdBy = $ex.Properties.CreatedBy } # some shapes

    [pscustomobject]@{
        Name            = $displayName                         # Portal "Name"
        Assignment      = $assignmentName                       # Portal "Assignments"
        Scope           = Get-FriendlyScope -RawScope $rawScope # Friendly-ish
        ExemptionType   = $ex.Properties.ExemptionCategory      # Portal "Exemption category"
        CreatedBy       = $createdBy                            # Portal "Created by" (best-effort)
        ExpirationDate  = $expiresOn                            # Portal "Expiration date"
        # Debug columns (optional):
        ExemptionId     = $ex.Id
        PolicyAssignId  = $assignmentId
        RawScope        = $rawScope
    }
}

$rows | Select Name, Assignment, Scope, ExemptionType, CreatedBy, ExpirationDate | Format-Table -AutoSize