param(
    [string]$Organization    = $env:ORG_NAME,
    [string]$Project         = $env:PROJECT_NAME,
    [string]$PipelineName    = $env:PIPELINE_NAME,
    [string]$EnvironmentName = $env:ENV_NAME,
    [int]   $LookbackHours   = 24   # default
)

# Override LookbackHours if env var is set
if ($env:LOOKBACK_HOURS) {
    $LookbackHours = [int]$env:LOOKBACK_HOURS
}

Write-Host "=== Role assignments approvals audit (console) ==="
Write-Host "Organization    : $Organization"
Write-Host "Project         : $Project"
Write-Host "Pipeline        : $PipelineName"
Write-Host "Environment     : $EnvironmentName"
Write-Host "Lookback (h)    : $LookbackHours"

if (-not $env:SYSTEM_ACCESSTOKEN) {
    throw "SYSTEM_ACCESSTOKEN not available. Make sure the task has env: SYSTEM_ACCESSTOKEN: `$(System.AccessToken)."
}

$cutoffUtc = (Get-Date).ToUniversalTime().AddHours(-$LookbackHours)
Write-Host "Cutoff time (UTC): $($cutoffUtc.ToString('o'))"

$baseUrl = "https://dev.azure.com/$Organization/$Project/_apis"
$headers = @{
    Authorization = "Bearer $($env:SYSTEM_ACCESSTOKEN)"
    "Content-Type" = "application/json"
}

# --------------------------------------------------------------------
# 1. Get pipeline ID from name
# --------------------------------------------------------------------
Write-Host ""
Write-Host "== Getting pipeline id for name '$PipelineName' =="

$pipelineListUrl = "$baseUrl/pipelines?api-version=7.1"
$pipelineList    = Invoke-RestMethod -Uri $pipelineListUrl -Headers $headers -Method Get

if (-not $pipelineList.value) {
    throw "No pipelines returned from '$pipelineListUrl'. Check org/project."
}

$pipeline = $pipelineList.value | Where-Object { $_.name -eq $PipelineName } | Select-Object -First 1

if (-not $pipeline) {
    throw "Pipeline with name '$PipelineName' not found in project '$Project'."
}

$pipelineId = $pipeline.id
Write-Host "Pipeline id: $pipelineId"

# --------------------------------------------------------------------
# 2. Get recent runs for this pipeline
# --------------------------------------------------------------------
Write-Host ""
Write-Host "== Pipeline runs in the last $LookbackHours hours =="

$runsUrl = "$baseUrl/pipelines/$pipelineId/runs?api-version=7.1"
$runs    = Invoke-RestMethod -Uri $runsUrl -Headers $headers -Method Get

if (-not $runs.value) {
    Write-Host "No runs returned for pipeline id $pipelineId."
} else {
    $recentRuns = $runs.value | Where-Object {
        $created = [datetime]$_.createdDate
        $created.ToUniversalTime() -ge $cutoffUtc
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
# 3. Find environment ID by name
# --------------------------------------------------------------------
Write-Host ""
Write-Host "== Looking up environment '$EnvironmentName' =="

$envsUrl = "$baseUrl/distributedtask/environments?api-version=7.1"
$envList = Invoke-RestMethod -Uri $envsUrl -Headers $headers -Method Get

if (-not $envList.value) {
    Write-Host "No environments returned from '$envsUrl'. Cannot fetch approvals."
    return
}

$environment = $envList.value | Where-Object { $_.name -eq $EnvironmentName } | Select-Object -First 1

if (-not $environment) {
    Write-Host "Environment '$EnvironmentName' not found in project '$Project'."
    Write-Host "Available environments:"
    $envList.value | Select-Object id,name | ForEach-Object {
        Write-Host ("  id={0} name={1}" -f $_.id, $_.name)
    }
    return
}

$environmentId = $environment.id
Write-Host ("Environment id : {0}" -f $environmentId)

# --------------------------------------------------------------------
# 4. Get approvals for that environment
# --------------------------------------------------------------------
Write-Host ""
Write-Host "== Stage approvals for environment in last $LookbackHours hours =="

$approvalsUrl = "$baseUrl/distributedtask/environments/$environmentId/approvals?api-version=7.1"
$envApprovals = Invoke-RestMethod -Uri $approvalsUrl -Headers $headers -Method Get

if (-not $envApprovals.value) {
    Write-Host "No approvals returned for environment id $environmentId."
    Write-Host "=== Audit finished ==="
    return
}

# Filter by time window and approved status
$recentApprovals = $envApprovals.value | Where-Object {
    $created = [datetime]$_.createdOn
    ($created.ToUniversalTime() -ge $cutoffUtc) -and
    ($_.status -eq "approved")
} | Sort-Object { [datetime]$_.createdOn } -Descending

if (-not $recentApprovals) {
    Write-Host "No approvals with status 'approved' in the last $LookbackHours hours."
    Write-Host "=== Audit finished ==="
    return
}

foreach ($a in $recentApprovals) {
    $createdOn  = [datetime]$a.createdOn
    $modifiedOn = if ($a.modifiedOn) { [datetime]$a.modifiedOn } else { $createdOn }

    $requesterName = $null
    if ($a.requester -and $a.requester.displayName) {
        $requesterName = $a.requester.displayName
    }

    $approverName  = $null
    $approverUpn   = $null
    if ($a.approver) {
        $approverName = $a.approver.displayName
        $approverUpn  = $a.approver.uniqueName
    }

    $jobInstance = $a.jobInstanceName
    $comment     = $a.comments

    Write-Host "------------------------------------------------------------"
    Write-Host ("ApprovalId      : {0}" -f $a.id)
    Write-Host ("Status          : {0}" -f $a.status)
    if ($requesterName) {
        Write-Host ("Requested by    : {0}" -f $requesterName)
    }
    Write-Host ("Approved by     : {0}" -f ($approverName ? $approverName : "(unknown)"))
    if ($approverUpn) {
        Write-Host ("Approver UPN    : {0}" -f $approverUpn)
    }
    if ($jobInstance) {
        Write-Host ("Job / Stage     : {0}" -f $jobInstance)
    }
    Write-Host ("CreatedOn       : {0}" -f $createdOn.ToString("u"))
    Write-Host ("ModifiedOn      : {0}" -f $modifiedOn.ToString("u"))
    if ($comment) {
        Write-Host ("Comment / Notes : {0}" -f $comment)
    } else {
        Write-Host ("Comment / Notes : (none)")
    }
}

Write-Host ""
Write-Host "=== Role assignments approvals audit finished ==="




$displayApproverName = if ([string]::IsNullOrWhiteSpace($approverName)) { "(unknown)" } else { $approverName }
Write-Host ("Approved by     : {0}" -f $displayApproverName)