################################################################################
# Sample script to run a Workspot Usage report (for up to a thirty day window) #
################################################################################
###########################
# Variable initialization #
$ApiClientId = "" #Workspot Control API Client ID
$ApiClientSecret = "" #Workspot Control API Client Secret
$WsControlUser = "" #Workspot Control Administrator user email address
$WsControlPass = "" #Workspot Control Administrator user password

$StartDate = "" #First date of range for report, format YYYY-MM-DD
$EndDate = "" #Last date of range for report, format YYYY-MM-DD
$CsvPath = "" #Full path for CSV output file, ie c:\temp\usagereport.csv
###########################

$ApiClientPair = "$($ApiClientId):$($ApiClientSecret)"
$EncodedApiCreds = [System.Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes($ApiClientPair))
$HeaderAuthValue = "Basic $EncodedApiCreds"
$Headers = @{Authorization = $HeaderAuthValue}
$PostParameters = @{username=$WsControlUser;password=$WsControlPass;grant_type='password'}
$ApiReturn = Invoke-RestMethod -Uri "https://api.workspot.com/oauth/token" -Method Post -Body $PostParameters -Headers $Headers
$ApiToken = $ApiReturn.Access_Token
$Headers = @{Authorization =("Bearer "+ $ApiToken)}

$ReportParams = @{
    end = $EndDate
    format = "CSV"
    start = $StartDate
}
$ReportParamsJson = $ReportParams | ConvertTo-Json

$ReportStatusUrl = (Invoke-RestMethod -Uri "https://api.workspot.com/v1.0/reports/generateusagereport" -Method Post -Headers $Headers -Body $ReportParamsJson -ContentType 'application/json').StatusUrl
Do {
    Start-Sleep -Seconds 5
    $StatusReturn = Invoke-RestMethod -Method GET -ContentType "application/json" -Uri $ReportStatusUrl -Headers $Headers
} Until($StatusReturn.Status -ne "InProgress")

$ReportObject = (Invoke-RestMethod $StatusReturn.Details.DownloadUrl) | ConvertFrom-CSV
$ReportObject | Export-CSV $CsvPath -NoTypeInformation