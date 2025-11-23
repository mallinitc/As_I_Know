param(
    [string]$Organization  = $env:ORG_NAME,
    [string]$Project       = $env:PROJECT_NAME,
    [string]$PipelineName  = $env:PIPELINE_NAME,
    [int]   $LookbackHours = 24
)

# Allow overriding via env var
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
# 1. Get pipeline ID by name and get recent runs (for mapping only)
# --------------------------------------------------------------------
Write-Host ""
Write-Host "== Resolving pipeline '$PipelineName' and loading runs =="

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

$runsUrl = "$baseUrl/pipelines/$pipelineId/runs?api-version=7.1"
$runs    = Invoke-RestMethod -Uri $runsUrl -Headers $headers -Method Get

$recentRuns = @()

if ($runs.value) {
    $recentRuns = $runs.value | Where-Object {
        $created = [datetime]$_.createdDate
        $created.ToUniversalTime() -ge $cutoffUtc
    } | Sort-Object { [datetime]$_.createdDate }  # ascending for easier mapping
}

if (-not $recentRuns -or $recentRuns.Count -eq 0) {
    Write-Host "No runs for this pipeline in the last $LookbackHours hours. Approvals mapping may be empty."
}

# --------------------------------------------------------------------
# 2. Get approvals (approved only) and map to nearest run
# --------------------------------------------------------------------
Write-Host ""
Write-Host "== Approved approvals in last $LookbackHours hours (mapped to nearest run) =="

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
} | Sort-Object { [datetime]$_.createdOn }  # ascending

if (-not $recentApprovals -or $recentApprovals.Count -eq 0) {
    Write-Host "No approvals with status 'approved' in the last $LookbackHours hours."
    Write-Host "=== Audit finished ==="
    return
}

foreach ($a in $recentApprovals) {

    $approvalCreated = [datetime]$a.createdOn

    # ---- Map to closest earlier run (same pipeline) ----
    $matchedRun = $null
    if ($recentRuns -and $recentRuns.Count -gt 0) {
        $matchedRun = $recentRuns |
            Where-Object {
                $runCreated = [datetime]$_.createdDate
                $runCreated.ToUniversalTime() -le $approvalCreated.ToUniversalTime()
            } |
            Sort-Object { [datetime]$_.createdDate } -Descending |
            Select-Object -First 1
    }

    $runId   = "(unknown)"
    $runName = "(unknown)"

    if ($matchedRun) {
        $runId   = $matchedRun.id
        $runName = $matchedRun.name
    }

    $modifiedOn = $approvalCreated
    if ($a.lastModifiedOn) {
        $modifiedOn = [datetime]$a.lastModifiedOn
    }

    Write-Host "------------------------------------------------------------"
    Write-Host ("RunId           : {0}" -f $runId)
    Write-Host ("RunName         : {0}" -f $runName)
    Write-Host ("Approval Id     : {0}" -f $a.id)
    Write-Host ("ApprovalStatus  : {0}" -f $a.status)
    Write-Host ("CreatedOn       : {0}" -f $approvalCreated.ToString("u"))
    Write-Host ("LastModifiedOn  : {0}" -f $modifiedOn.ToString("u"))

    # ---- Steps: only show approved ones ----
    if ($a.steps -and $a.steps.Count -gt 0) {
        Write-Host "Approved steps / approvers:"
        foreach ($step in $a.steps) {

            if ($step.status -ne "approved") {
                continue  # skip pending/other statuses
            }

            $actualName  = $null
            $actualUpn   = $null
            $stepComment = $null
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

            # Safe display values
            $displayName = $actualName
            if ([string]::IsNullOrWhiteSpace($displayName)) {
                $displayName = "(unknown)"
            }

            $displayComment = $stepComment
            if ([string]::IsNullOrWhiteSpace($displayComment)) {
                $displayComment = "(none)"
            }

            Write-Host ("  Approver      : {0}" -f $displayName)
            if ($actualUpn) {
                Write-Host ("  Approver UPN  : {0}" -f $actualUpn)
            }
            if ($stepLastMod) {
                Write-Host ("  ApprovedOn    : {0}" -f $stepLastMod.ToString("u"))
            }
            Write-Host ("  Comment       : {0}" -f $displayComment)
        }
    } else {
        Write-Host "No step details returned for this approval."
    }
}

Write-Host ""
Write-Host "=== Role assignments approvals audit finished ==="