####################################################################################
# Sample script to remove a user's assignment from a specific Workspot VDI Pool VM #
####################################################################################
###########################
# Variable initialization #
$ApiClientId = "" #Workspot Control API Client ID
$ApiClientSecret = "" #Workspot Control API Client Secret
$WsControlUser = "" #Workspot Control Administrator user email address
$WsControlPass = "" #Workspot Control Administrator user password

$PoolName = "" #Name of target VDI Pool
$VmName = "" #Name of VDI VM to assign to user
$UserEmail = "" #Email address of user to remove from VM
############################

$ApiClientPair = "$($ApiClientId):$($ApiClientSecret)"
$EncodedApiCreds = [System.Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes($ApiClientPair))
$HeaderAuthValue = "Basic $EncodedApiCreds"
$Headers = @{Authorization = $HeaderAuthValue}
$PostParameters = @{username=$WsControlUser;password=$WsControlPass;grant_type='password'}
$ApiReturn = Invoke-RestMethod -Uri "https://api.workspot.com/oauth/token" -Method Post -Body $PostParameters -Headers $Headers
$ApiToken = $ApiReturn.Access_Token
$Headers = @{Authorization =("Bearer "+ $ApiToken)}
  
$PoolList = (Invoke-RestMethod -Uri "https://api.workspot.com/v1.0/pools" -Method Get -Headers $Headers).DesktopPools
$PoolId = ($PoolList | Where-Object { $_.Name -like $PoolName}).Id
$VdiList = Invoke-RestMethod -Uri "https://api.workspot.com/v1.0/pools/$PoolId/desktops" -Method Get -Headers $Headers
$VmId = ($VdiList.Desktops | Where-Object {$_.Name -like $VmName}).Id

$UnassignUserUri = ("https://api.workspot.com/v1.0/users/$UserEmail/desktops/$VmId").Replace('@', '%40')
Invoke-WebRequest -Uri $UnassignUserUri -Method Delete -Headers $Headers