param(
    [string]$Organization  = $env:ORG_NAME,
    [string]$Project       = $env:PROJECT_NAME,
    [string]$PipelineName  = $env:PIPELINE_NAME,
    [int]   $LookbackHours = [int]($env:LOOKBACK_HOURS ? $env:LOOKBACK_HOURS : 24),

    [string]$WorkspaceId   = $env:LA_WORKSPACE_ID,
    [string]$SharedKey     = $env:LA_SHARED_KEY,
    [string]$LogType       = $env:LOG_TYPE
)

Write-Host "=== Approvals audit starting ==="
Write-Host "Organization : $Organization"
Write-Host "Project      : $Project"
Write-Host "Pipeline     : $PipelineName"
Write-Host "Lookback (h) : $LookbackHours"

if (-not $env:SYSTEM_ACCESSTOKEN) {
    throw "SYSTEM_ACCESSTOKEN not available. In the pipeline UI, enable 'Allow scripts to access the OAuth token'."
}

if (-not $WorkspaceId -or -not $SharedKey) {
    throw "Log Analytics WorkspaceId / SharedKey are empty. Make sure LA_WORKSPACE_ID and LA_SHARED_KEY env vars are set from secure pipeline variables."
}

$baseUrl = "https://dev.azure.com/$Organization/$Project/_apis"
$cutoff  = (Get-Date).ToUniversalTime().AddHours(-$LookbackHours)
Write-Host "Cutoff time (UTC) : $($cutoff.ToString('o'))"

$adoHeaders = @{
    Authorization = "Bearer $($env:SYSTEM_ACCESSTOKEN)"
    "Content-Type" = "application/json"
}

# --------------------------------------------------------------------
# 1. Get approvals (status=approved) from Approvals & Checks API
# --------------------------------------------------------------------
$approvalsUrl = "$baseUrl/pipelines/approvals?status=approved&api-version=7.1-preview.1"
Write-Host "Calling approvals API: $approvalsUrl"

$approvalsResponse = Invoke-RestMethod -Uri $approvalsUrl -Headers $adoHeaders -Method Get

if (-not $approvalsResponse.value) {
    Write-Host "No approvals returned by API."
    return
}

# Filter to our pipeline name + time window
$pipelineApprovals = $approvalsResponse.value |
    Where-Object {
        $_.pipeline.name -eq $PipelineName -and
        ([datetime]$_.createdOn).ToUniversalTime() -ge $cutoff
    }

if (-not $pipelineApprovals) {
    Write-Host "No approvals for pipeline '$PipelineName' in the last $LookbackHours hours."
    return
}

Write-Host ("Found {0} approvals for the pipeline in the time window." -f $pipelineApprovals.Count)

# For your first run, dump one sample so you can see the exact JSON shape
Write-Host "Sample approval (first item) for debugging:"
$pipelineApprovals[0] | ConvertTo-Json -Depth 10

# --------------------------------------------------------------------
# 2. Map approvals -> records for Log Analytics
#    NOTE: some property names may need small tweaks once you see the sample JSON.
# --------------------------------------------------------------------
$records = foreach ($a in $pipelineApprovals) {

    $approvalId = $a.id
    $pipeline   = $a.pipeline
    $runLabel   = $pipeline.owner.name     # often run name (like 20251123.7)
    $runId      = $pipeline.owner.id

    # These fields depend on the API output; adjust if needed after inspecting the sample JSON.
    $createdOn  = [datetime]$a.createdOn
    $modifiedOn = if ($a.lastModifiedOn) { [datetime]$a.lastModifiedOn } else { $createdOn }

    # Approver information – in many orgs this is under "requestedBy" or similar.
    # If your sample JSON shows a different property, just adjust these two lines.
    $approvedBy      = $a.requestedBy.displayName
    $approvedByEmail = $a.requestedBy.uniqueName

    # Stage / environment details – again, adjust property names after first run if needed.
    $stageName       = $a.stageName
    $environmentName = $a.resource.name

    [pscustomobject]@{
        TimeGenerated      = $modifiedOn.ToString("o")

        PipelineName_s     = $pipeline.name
        RunId_s            = "$runId"
        RunLabel_s         = $runLabel
        ApprovalId_s       = "$approvalId"

        StageName_s        = $stageName
        EnvironmentName_s  = $environmentName

        ApprovedBy_s       = $approvedBy
        ApprovedByEmail_s  = $approvedByEmail
        ApprovedOn_t       = $modifiedOn.ToString("o")
        CreatedOn_t        = $createdOn.ToString("o")
    }
}

if (-not $records -or $records.Count -eq 0) {
    Write-Host "No records created after mapping; check property names against the sample approval JSON."
    return
}

Write-Host ("Prepared {0} records for Log Analytics ingestion." -f $records.Count)

# --------------------------------------------------------------------
# 3. Send to Log Analytics (HTTP Data Collector API)
# --------------------------------------------------------------------
function New-LogSignature {
    param(
        [string]$CustomerId,
        [string]$SharedKey,
        [string]$Date,
        [int]   $ContentLength,
        [string]$Method,
        [string]$ContentType,
        [string]$Resource
    )

    $xHeaders      = "x-ms-date:$Date"
    $stringToHash  = "$Method`n$ContentLength`n$ContentType`n$xHeaders`n$Resource"
    $bytesToHash   = [Text.Encoding]::UTF8.GetBytes($stringToHash)
    $keyBytes      = [Convert]::FromBase64String($SharedKey)

    $hmacSha256          = New-Object System.Security.Cryptography.HMACSHA256
    $hmacSha256.Key      = $keyBytes
    $hash                = $hmacSha256.ComputeHash($bytesToHash)
    $encodedHash         = [Convert]::ToBase64String($hash)
    $authorizationHeader = "SharedKey $CustomerId:$encodedHash"
    return $authorizationHeader
}

function Send-LogAnalyticsData {
    param(
        [string]$CustomerId,
        [string]$SharedKey,
        [string]$LogType,
        [string]$Body
    )

    $method       = "POST"
    $contentType  = "application/json"
    $resource     = "/api/logs"
    $date         = [DateTime]::UtcNow.ToString("r")
    $contentLength = $Body.Length

    $signature = New-LogSignature -CustomerId $CustomerId -SharedKey $SharedKey `
                                  -Date $date -ContentLength $contentLength `
                                  -Method $method -ContentType $contentType `
                                  -Resource $resource

    $uri = "https://$CustomerId.ods.opinsights.azure.com$resource?api-version=2016-04-01"

    $headers = @{
        "Authorization"        = $signature
        "Log-Type"             = $LogType
        "x-ms-date"            = $date
        "time-generated-field" = "TimeGenerated"
    }

    Write-Host "Sending data to Log Analytics table ${LogType}_CL ..."
    Invoke-RestMethod -Method $method -Uri $uri -Headers $headers -Body $Body -ContentType $contentType | Out-Null
}

$bodyJson = $records | ConvertTo-Json
Send-LogAnalyticsData -CustomerId $WorkspaceId -SharedKey $SharedKey -LogType $LogType -Body $bodyJson

Write-Host "=== Approvals audit completed successfully ==="











param(
    [string]$Organization  = $env:ORG_NAME,
    [string]$Project       = $env:PROJECT_NAME,
    [string]$PipelineName  = $env:PIPELINE_NAME,
    [int]   $LookbackHours = [int]($env:LOOKBACK_HOURS ? $env:LOOKBACK_HOURS : 24)
)

Write-Host "=== Approvals audit (console only) starting ==="
Write-Host "Organization : $Organization"
Write-Host "Project      : $Project"
Write-Host "Pipeline     : $PipelineName"
Write-Host "Lookback (h) : $LookbackHours"

if (-not $env:SYSTEM_ACCESSTOKEN) {
    throw "SYSTEM_ACCESSTOKEN not available. Make sure the task has env: SYSTEM_ACCESSTOKEN: \$(System.AccessToken)."
}

$baseUrl = "https://dev.azure.com/$Organization/$Project/_apis"
$cutoff  = (Get-Date).ToUniversalTime().AddHours(-$LookbackHours)
Write-Host "Cutoff time (UTC): $($cutoff.ToString('o'))"

$adoHeaders = @{
    Authorization = "Bearer $($env:SYSTEM_ACCESSTOKEN)"
    "Content-Type" = "application/json"
}

# --------------------------------------------------------------------
# 1. Find pipeline ID by name
# --------------------------------------------------------------------
Write-Host ""
Write-Host "== Getting pipeline id for name '$PipelineName' =="
$pipelineListUrl = "$baseUrl/pipelines?api-version=7.1"
$pipelineList    = Invoke-RestMethod -Uri $pipelineListUrl -Headers $adoHeaders -Method Get

if (-not $pipelineList.value) {
    throw "No pipelines returned from '$pipelineListUrl'. Check org/project."
}

$pipeline = $pipelineList.value | Where-Object { $_.name -eq $PipelineName } | Select-Object -First 1

if (-not $pipeline) {
    throw "Pipeline with name '$PipelineName' not found in project '$Project'."
}

$pipelineId = $pipeline.id
Write-Host "Pipeline id: $pipelineId"
Write-Host ""

# --------------------------------------------------------------------
# 2. Get runs for this pipeline and filter to last 24h
# --------------------------------------------------------------------
Write-Host "== Pipeline runs in the last $LookbackHours hours =="
$runsUrl = "$baseUrl/pipelines/$pipelineId/runs?api-version=7.1"
$runs    = Invoke-RestMethod -Uri $runsUrl -Headers $adoHeaders -Method Get

if (-not $runs.value) {
    Write-Host "No runs returned for pipeline id $pipelineId."
} else {
    $recentRuns = $runs.value | Where-Object {
        # createdDate is ISO string in UTC
        $created = [datetime]$_.createdDate
        $created.ToUniversalTime() -ge $cutoff
    } | Sort-Object { [datetime]$_.createdDate } -Descending

    if (-not $recentRuns) {
        Write-Host "No runs in the last $LookbackHours hours."
    } else {
        foreach ($run in $recentRuns) {
            $created  = [datetime]$run.createdDate
            $finished = if ($run.finishedDate) { [datetime]$run.finishedDate } else { $null }

            Write-Host "------------------------------------------------------------"
            Write-Host ("RunId    : {0}" -f $run.id)
            Write-Host ("Name     : {0}" -f $run.name)
            Write-Host ("State    : {0}" -f $run.state)
            Write-Host ("Result   : {0}" -f $run.result)
            Write-Host ("Created  : {0}" -f $created.ToString("u"))
            if ($finished) {
                Write-Host ("Finished : {0}" -f $finished.ToString("u"))
            } else {
                Write-Host "Finished : (still running or not set)"
            }
        }
    }
}

# --------------------------------------------------------------------
# 3. Get approvals (approved) in the last 24h and print approvers
# --------------------------------------------------------------------
Write-Host ""
Write-Host "== Approved approvals in the last $LookbackHours hours (all pipelines/resources) =="

# We ask for all approvals with status=approved and expand steps (so we see who approved)
$approvalsUrl = "$baseUrl/pipelines/approvals?api-version=7.1&state=approved&`$expand=steps"
$approvals    = Invoke-RestMethod -Uri $approvalsUrl -Headers $adoHeaders -Method Get

if (-not $approvals.value) {
    Write-Host "No approvals returned by the Approvals API."
    return
}

# Filter by time window
$recentApprovals = $approvals.value | Where-Object {
    $created = [datetime]$_.createdOn
    $created.ToUniversalTime() -ge $cutoff
} | Sort-Object { [datetime]$_.createdOn } -Descending

if (-not $recentApprovals) {
    Write-Host "No approvals in the last $LookbackHours hours."
    return
}

foreach ($a in $recentApprovals) {
    $createdOn  = [datetime]$a.createdOn
    $modifiedOn = if ($a.lastModifiedOn) { [datetime]$a.lastModifiedOn } else { $createdOn }

    Write-Host "------------------------------------------------------------"
    Write-Host ("Approval Id   : {0}" -f $a.id)
    Write-Host ("Status        : {0}" -f $a.status)
    Write-Host ("CreatedOn     : {0}" -f $createdOn.ToString("u"))
    Write-Host ("LastModified  : {0}" -f $modifiedOn.ToString("u"))
    Write-Host ("Min approvers : {0}" -f $a.minRequiredApprovers)

    if ($a.steps -and $a.steps.Count -gt 0) {
        Write-Host "Steps / approvers:"
        foreach ($step in $a.steps) {
            $order      = $step.order
            $stepStatus = $step.status
            $lastMod    = if ($step.lastModifiedOn) { [datetime]$step.lastModifiedOn } else { $null }

            $actualName  = $step.actualApprover.displayName
            $actualEmail = $step.actualApprover.uniqueName

            Write-Host ("  - Step #{0}" -f $order)
            Write-Host ("    Status        : {0}" -f $stepStatus)
            Write-Host ("    Approver      : {0}" -f ($actualName ? $actualName : "(none)"))
            if ($actualEmail) {
                Write-Host ("    Approver UPN  : {0}" -f $actualEmail)
            }
            if ($lastMod) {
                Write-Host ("    LastModified  : {0}" -f $lastMod.ToString("u"))
            }
        }
    } else {
        Write-Host "No step details returned (try removing `$expand=steps if API behaves differently)."
    }
}

Write-Host ""
Write-Host "=== Approvals audit (console only) finished ==="








foreach ($step in $a.steps) {
    $order      = $step.order
    $stepStatus = $step.status
    $lastMod    = if ($step.lastModifiedOn) { [datetime]$step.lastModifiedOn } else { $null }

    $actualName  = $step.actualApprover.displayName
    $actualEmail = $step.actualApprover.uniqueName

    # handle null/empty display name without ternary
    $displayName = if ([string]::IsNullOrWhiteSpace($actualName)) { "(none)" } else { $actualName }

    Write-Host ("  - Step #{0}" -f $order)
    Write-Host ("    Status        : {0}" -f $stepStatus)
    Write-Host ("    Approver      : {0}" -f $displayName)

    if ($actualEmail) {
        Write-Host ("    Approver UPN  : {0}" -f $actualEmail)
    }
    if ($lastMod) {
        Write-Host ("    LastModified  : {0}" -f $lastMod.ToString("u"))
    }
}