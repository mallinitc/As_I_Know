function Test-AzScopeFormat {
    param(
        [string]$Scope
    )

    if ([string]::IsNullOrWhiteSpace($Scope)) {
        return $false
    }

    $scope = $Scope.Trim()

    # If user pasted something like "Snowflake/…/subscriptions/…", keep only the part from /subscriptions or /providers
    $subIdx = $scope.IndexOf("/subscriptions", [System.StringComparison]::OrdinalIgnoreCase)
    $mgIdx  = $scope.IndexOf("/providers/Microsoft.Management/managementGroups", [System.StringComparison]::OrdinalIgnoreCase)

    if ($subIdx -ge 0) {
        $scope = $scope.Substring($subIdx)
    }
    elseif ($mgIdx -ge 0) {
        $scope = $scope.Substring($mgIdx)
    }

    # Basic patterns
    $subPattern = '^/subscriptions/[0-9a-fA-F-]{36}($|/.*)'
    $mgPattern  = '^/providers/Microsoft\.Management/managementGroups/[^/]+$'

    return ($scope -match $subPattern -or $scope -match $mgPattern)
}



$Test_scope = $Test_scope.Trim()

if (-not (Test-AzScopeFormat $Test_scope)) {
    throw "#[error] Resource scope '$Test_scope' is not a valid Azure scope. Expected something like `/subscriptions/<guid>/...` or a management group scope."
}