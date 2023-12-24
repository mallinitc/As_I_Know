######################################################################################
# Sample script to reassign a specific Workspot VDI Pool VM from one user to another #
######################################################################################
###########################
# Variable initialization #
$ApiClientId = "" #Workspot Control API Client ID
$ApiClientSecret = "" #Workspot Control API Client Secret
$WsControlUser = "" #Workspot Control Administrator user email address
$WsControlPass = "" #Workspot Control Administrator user password

$PoolName = "" #Name of target VDI Pool
$VmName = "" #Name of VDI VM to reassign to new user
$OldUserEmail = "" #Email address of user to remove from VM
$NewUserEmail = "" #Email address of user to add to VM
############################

$ApiClientPair = "$($ApiClientId):$($ApiClientSecret)"
$EncodedApiCreds = [System.Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes($ApiClientPair))
$HeaderAuthValue = "Basic $EncodedApiCreds"
$Headers = @{Authorization = $HeaderAuthValue}
$PostParameters = @{username=$WsControlUser;password=$WsControlPass;grant_type='password'}
$ApiHost = 'api.workspot.com'
$ApiReturn = Invoke-RestMethod -Uri "https://$ApiHost/oauth/token" -Method Post -Body $PostParameters -Headers $Headers
$ApiToken = $ApiReturn.Access_Token
$Headers = @{Authorization =("Bearer "+ $ApiToken)}
  
$PoolList = (Invoke-RestMethod -Uri "https://$ApiHost/v1.0/pools" -Method Get -Headers $Headers).DesktopPools
$PoolId = ($PoolList | Where-Object { $_.Name -like $PoolName}).Id
$VdiList = Invoke-RestMethod -Uri "https://$ApiHost/v1.0/pools/$PoolId/desktops" -Method Get -Headers $Headers
$VmId = ($VdiList.Desktops | Where-Object {$_.Name -like $VmName}).Id

$PostParameters = @{desktopId = $VmId} | ConvertTo-Json
$UnassignUserUri = ("https://$ApiHost/v1.0/users/$OldUserEmail/desktops/$VmId").Replace('@', '%40')
$RetvalRemove = Invoke-WebRequest -Uri $UnassignUserUri -Method Delete -Headers $Headers
If($RetvalRemove.StatusCode -eq 204) { Write-Output "`nSuccessfully removed user $OldUserEmail from $VmName" }
Else { Write-Output "`nRemoval process failed and returned the following:`n$RetvalRemove" }

$AssignUserUri = ("https://$ApiHost/v1.0/users/$NewUserEmail/desktops").Replace('@', '%40')
Invoke-RestMethod -Uri $AssignUserUri -Method Post -Headers $Headers -Body $PostParameters -ContentType 'application/json' 