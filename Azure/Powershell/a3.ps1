param(
    [string]$Organization  = $env:ORG_NAME,
    [string]$Project       = $env:PROJECT_NAME,
    [string]$PipelineName  = $env:PIPELINE_NAME,
    [int]   $LookbackHours = 24
)

# Allow overriding lookback via env var
if ($env:LOOKBACK_HOURS) {
    $LookbackHours = [int]$env:LOOKBACK_HOURS
}

Write-Host "=== Role assignments approvals audit (console) ==="
Write-Host "Organization : $Organization"
Write-Host "Project      : $Project"
Write-Host "Pipeline     : $PipelineName"
Write-Host "Lookback (h) : $LookbackHours"

if (-not $env:SYSTEM_ACCESSTOKEN) {
    throw "SYSTEM_ACCESSTOKEN not available. In the pipeline task, set env: SYSTEM_ACCESSTOKEN: `$(System.AccessToken)."
}

$cutoffUtc = (Get-Date).ToUniversalTime().AddHours(-$LookbackHours)
Write-Host "Cutoff time (UTC): $($cutoffUtc.ToString('o'))"

$baseUrl = "https://dev.azure.com/$Organization/$Project/_apis"
$headers = @{
    Authorization = "Bearer $($env:SYSTEM_ACCESSTOKEN)"
    "Content-Type" = "application/json"
}

# --------------------------------------------------------------------
# 1. Get pipeline ID by name and list recent runs
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

Write-Host ""
Write-Host "== Pipeline runs in the last $LookbackHours hours =="

$runsUrl = "$baseUrl/pipelines/$pipelineId/runs?api-version=7.1"
$runs    = Invoke-RestMethod -Uri $runsUrl -Headers $headers -Method Get

$recentRuns = @()

if ($runs.value) {
    $recentRuns = $runs.value | Where-Object {
        $created = [datetime]$_.createdDate
        $created.ToUniversalTime() -ge $cutoffUtc
    } | Sort-Object { [datetime]$_.createdDate } -Descending
}

if (-not $recentRuns -or $recentRuns.Count -eq 0) {
    Write-Host "No runs in the last $LookbackHours hours."
} else {
    foreach ($run in $recentRuns) {
        $created  = [datetime]$run.createdDate
        $finished = $null
        if ($run.finishedDate) {
            $finished = [datetime]$run.finishedDate
        }

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

# --------------------------------------------------------------------
# 2. Query approvals for the project and print approvers + comments
# --------------------------------------------------------------------
Write-Host ""
Write-Host "== Approved approvals in the last $LookbackHours hours (project-wide) =="

# Use Approvals & Checks API. $expand=steps gives us approver + comment.
$approvalsUrl = "$baseUrl/pipelines/approvals?state=approved&`$expand=steps&api-version=7.1"
$approvals    = Invoke-RestMethod -Uri $approvalsUrl -Headers $headers -Method Get

if (-not $approvals.value) {
    Write-Host "No approvals returned by the Approvals API."
    Write-Host "=== Audit finished ==="
    return
}

$recentApprovals = $approvals.value | Where-Object {
    $created = [datetime]$_.createdOn
    $created.ToUniversalTime() -ge $cutoffUtc
} | Sort-Object { [datetime]$_.createdOn } -Descending

if (-not $recentApprovals -or $recentApprovals.Count -eq 0) {
    Write-Host "No approvals with status 'approved' in the last $LookbackHours hours."
    Write-Host "=== Audit finished ==="
    return
}

foreach ($a in $recentApprovals) {
    $createdOn  = [datetime]$a.createdOn
    $modifiedOn = $createdOn
    if ($a.lastModifiedOn) {
        $modifiedOn = [datetime]$a.lastModifiedOn
    }

    Write-Host "------------------------------------------------------------"
    Write-Host ("Approval Id     : {0}" -f $a.id)
    Write-Host ("Status          : {0}" -f $a.status)
    Write-Host ("CreatedOn       : {0}" -f $createdOn.ToString("u"))
    Write-Host ("LastModifiedOn  : {0}" -f $modifiedOn.ToString("u"))

    if ($a.steps -and $a.steps.Count -gt 0) {
        Write-Host "Steps / approvers:"
        foreach ($step in $a.steps) {
            $actualName  = $null
            $actualUpn   = $null
            $stepComment = $null
            $stepStatus  = $step.status
            $order       = $step.order
            $stepLastMod = $null

            if ($step.actualApprover) {
                $actualName = $step.actualApprover.displayName
                $actualUpn  = $step.actualApprover.uniqueName
            }

            if ($step.comment) {
                $stepComment = $step.comment
            }

            if ($step.lastModifiedOn) {
                $stepLastMod = [datetime]$step.lastModifiedOn
            }

            # Safe display values without using ?:
            $displayName = $actualName
            if ([string]::IsNullOrWhiteSpace($displayName)) {
                $displayName = "(unknown)"
            }

            $displayComment = $stepComment
            if ([string]::IsNullOrWhiteSpace($displayComment)) {
                $displayComment = "(none)"
            }

            Write-Host ("  - Step #{0}" -f $order)
            Write-Host ("    Status        : {0}" -f $stepStatus)
            Write-Host ("    Approver      : {0}" -f $displayName)
            if ($actualUpn) {
                Write-Host ("    Approver UPN  : {0}" -f $actualUpn)
            }
            if ($stepLastMod) {
                Write-Host ("    ModifiedOn    : {0}" -f $stepLastMod.ToString("u"))
            }
            Write-Host ("    Comment       : {0}" -f $displayComment)
        }
    } else {
        Write-Host "No step details returned for this approval."
    }
}

Write-Host ""
Write-Host "=== Role assignments approvals audit finished ==="