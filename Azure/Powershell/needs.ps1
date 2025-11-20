param(
  [string]$Project = "$(System.TeamProject)",
  [string]$TargetPipelineName = "SBX-role-assignments-ado"
)

$ErrorActionPreference = 'Stop'

$orgUrl   = "$(System.CollectionUri)"  # e.g. https://dev.azure.com/yourorg/
$patToken = $env:SYSTEM_ACCESSTOKEN
if (-not $patToken) { throw "SYSTEM_ACCESSTOKEN not available. Enable 'Allow scripts to access OAuth token'." }

$headers = @{ Authorization = "Bearer $patToken" }

# 1) Find the pipeline definition ID by name
$pipeListUrl = "$orgUrl$Project/_apis/pipelines?api-version=7.1-preview.1"
$pipeList    = Invoke-RestMethod -Uri $pipeListUrl -Headers $headers -Method Get

$targetDef = $pipeList.value | Where-Object { $_.name -eq $TargetPipelineName } | Select-Object -First 1
if (-not $targetDef) {
    throw "Pipeline '$TargetPipelineName' not found in project '$Project'."
}
$pipelineId = $targetDef.id
Write-Host "Found pipeline '$TargetPipelineName' with id $pipelineId"

# 2) Find recent runs of that pipeline (last 24 hours, adjust as you like)
$since = (Get-Date).AddDays(-1).ToUniversalTime().ToString("o")
$runsUrl = "$orgUrl$Project/_apis/pipelines/$pipelineId/runs?api-version=7.1-preview.1"
$runs    = Invoke-RestMethod -Uri $runsUrl -Headers $headers -Method Get

$recentRuns = $runs.value | Where-Object { $_.createdDate -ge $since }

if (-not $recentRuns) {
    Write-Host "No runs for pipeline '$TargetPipelineName' in the last 24 hours."
    return
}

Write-Host "Found $($recentRuns.Count) recent runs for '$TargetPipelineName'."

# Prepare output collection
$report = @()

foreach ($run in $recentRuns) {
    $runId       = $run.id
    $runName     = $run.name
    $runState    = $run.state
    $runResult   = $run.result
    $runCreated  = $run.createdDate
    $runUrl      = $run._links.web.href

    Write-Host "Processing run $runId ($runName) state=$runState result=$runResult"

    # 3) Get run details to see input parameters
    $runDetailsUrl = "$orgUrl$Project/_apis/pipelines/$pipelineId/runs/$runId?api-version=7.1-preview.1"
    $runDetails    = Invoke-RestMethod -Uri $runDetailsUrl -Headers $headers -Method Get

    # For YAML pipelines, parameters appear under runDetails.resources or runDetails.templateParameters
    $paramsObj = $runDetails.templateParameters
    # In your case should include Action, RoleName, GroupName, ChangeNumber, etc.

    # Flatten parameters into a simple hash table
    $paramsFlat = @{}
    if ($paramsObj) {
        $paramsObj.PSObject.Properties | ForEach-Object {
            $paramsFlat[$_.Name] = $_.Value
        }
    }

    # 4) Query approvals and filter those associated with this run
    $approvalsBody = @{
        approvalsFilter = "all"
    } | ConvertTo-Json

    $approvalsUrl = "$orgUrl$Project/_apis/pipelines/approvals?api-version=7.1-preview.1"
    $approvalsAll = Invoke-RestMethod -Uri $approvalsUrl -Headers $headers -Method Post `
                                      -Body $approvalsBody -ContentType 'application/json'

    # Filter approvals that are linked to this run (pipelineReference.run.id)
    $runApprovals = $approvalsAll.approvals | Where-Object {
        $_.pipelineReference.run.id -eq $runId
    }

    if (-not $runApprovals) {
        Write-Host "  No approvals for run $runId."
        continue
    }

    foreach ($appr in $runApprovals) {
        $whoName  = $appr.approver.displayName
        $whoMail  = $appr.approver.uniqueName
        $status   = $appr.status
        $when     = $appr.approvedOn
        $comments = $appr.comments

        Write-Host "  Approval: $status by $whoName <$whoMail> at $when"

        # Only include approved ones (skip rejected if you want)
        if ($status -ne 'approved') { continue }

        $report += [pscustomobject]@{
            RunId         = $runId
            PipelineName  = $TargetPipelineName
            RunUrl        = $runUrl
            RunState      = $runState
            RunResult     = $runResult
            RunCreated    = $runCreated

            ApproverName  = $whoName
            ApproverEmail = $whoMail
            ApprovalTime  = $when
            ApprovalStatus= $status
            ApprovalComment = $comments

            # key pipeline parameters
            Action        = $paramsFlat['Action']
            RoleName      = $paramsFlat['RoleName']
            GroupName     = $paramsFlat['GroupName']
            ChangeNumber  = $paramsFlat['ChangeNumber']
        }
    }
}

if ($report.Count -eq 0) {
    Write-Host "No approved runs with approvals in the time window."
} else {
    Write-Host "==== Summary of approvals ===="
    $report | Format-Table RunId, ApproverName, Action, RoleName, GroupName, ChangeNumber, ApprovalTime

    # Save as CSV or JSON artifact
    $outDir = "approvals-report"
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null

    $csvPath  = Join-Path $outDir "approvals_$(Get-Date -Format yyyyMMdd_HHmmss).csv"
    $jsonPath = Join-Path $outDir "approvals_$(Get-Date -Format yyyyMMdd_HHmmss).json"

    $report | Export-Csv -NoTypeInformation -Path $csvPath
    $report | ConvertTo-Json -Depth 5 | Out-File $jsonPath

    Write-Host "Saved approvals report to:"
    Write-Host " - $csvPath"
    Write-Host " - $jsonPath"
}