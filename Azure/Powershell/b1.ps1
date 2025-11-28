8# ===== Normalize & validate resource scope =====

# Raw value from pipeline
$resourceScope = $Test_scope
Write-Host "DEBUG: Raw Resource Scope from pipeline: '$resourceScope'"

if ([string]::IsNullOrWhiteSpace($resourceScope)) {
    throw "#[error] Resource scope (Test_scope) is empty. Please enter a valid scope."
}

$resourceScope = $resourceScope.Trim()

# Strip any label in front (e.g. 'Snowflake/…/subscriptions/...').
$lower = $resourceScope.ToLowerInvariant()
$subIdx = $lower.IndexOf("/subscriptions")
$mgIdx  = $lower.IndexOf("/providers/microsoft.management/managementgroups")

if ($subIdx -ge 0) {
    $normalizedScope = $resourceScope.Substring($subIdx)
}
elseif ($mgIdx -ge 0) {
    $normalizedScope = $resourceScope.Substring($mgIdx)
}
else {
    # No /subscriptions or management group keyword at all → invalid
    throw "#[error] Resource scope '$resourceScope' is not a valid Azure scope. Expected '/subscriptions/<guid>/...' or a management group scope."
}

Write-Host "DEBUG: Normalized Resource Scope: '$normalizedScope'"

# Basic patterns:
#  - Subscription: /subscriptions/<guid>[/...]
#  - Management group: /providers/Microsoft.Management/managementGroups/<name>[/...]
$subPattern = '^/subscriptions/[0-9a-fA-F-]{36}($|/.*)'
$mgPattern  = '^/providers/Microsoft\.Management/managementGroups/[^/]+($|/.*)?$'

if ( ($normalizedScope -notmatch $subPattern) -and
     ($normalizedScope -notmatch $mgPattern) ) {

    throw "#[error] Resource scope '$resourceScope' (normalized as '$normalizedScope') is not a valid Azure scope. Expected '/subscriptions/<guid>/...' or '/providers/Microsoft.Management/managementGroups/<name>'."
}

# If you want to use the normalized value for New-AzRoleAssignment, assign it back:
$Test_scope = $normalizedScope

Write-Host "DEBUG: Resource scope validation PASSED."



try {
    $temp = Get-AzRoleAssignment `
        -ObjectId $spn.Id `
        -RoleDefinitionId $roleDefinitionId `
        -Scope $Test_scope `
        -ErrorAction Stop
    
    Write-Host "DEBUG: Role assignment lookup succeeded."
}
catch {
    # Extract the meaningful Azure error message
    $msg = $_.Exception.Message

    # Extract Azure error code if present
    $errorCode = $null
    if ($_.Exception.ErrorRecord -and $_.Exception.ErrorRecord.TargetObject) {
        $errorCode = $_.Exception.ErrorRecord.TargetObject.error.code
    }

    Write-Host ""
    Write-Host "================= ROLE ASSIGNMENT ERROR =================" -ForegroundColor Red
    Write-Host "Scope              : $Test_scope"
    Write-Host "Role               : $roleName"
    Write-Host "Service Principal  : $SPName"
    Write-Host ""
    Write-Host "Error Code         : $errorCode"
    Write-Host "Message            : $msg"
    Write-Host "==========================================================" -ForegroundColor Red
    Write-Host ""

    throw "#[error] Failed to validate scope '$Test_scope'. Azure returned: $msg"
}