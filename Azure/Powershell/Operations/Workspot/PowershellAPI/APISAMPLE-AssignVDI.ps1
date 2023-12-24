#####################################################################
# Sample script to assign a specific Workspot VDI Pool VM to a user #
#####################################################################
###########################
# Variable initialization #
$ApiClientId = "" #Workspot Control API Client ID
$ApiClientSecret = "" #Workspot Control API Client Secret
$WsControlUser = "" #Workspot Control Administrator user email address
$WsControlPass = "" #Workspot Control Administrator user password

$PoolName = "" #Name of target VDI Pool
$VmName = "" #Name of VDI VM to assign to user
$UserEmail = "" #Email address of user being assigned to VM
############################


$ApiClientPair = "$($ApiClientId):$($ApiClientSecret)"
$EncodedApiCreds = [System.Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes($ApiClientPair))
$HeaderAuthValue = "Basic $EncodedApiCreds"
$Headers = @{Authorization = $HeaderAuthValue}
$PostParameters = @{username=$WsControlUser;password=$WsControlPass;grant_type='password'}
$ApiReturn = Invoke-RestMethod -Uri "https://api.workspot.com/oauth/token" -Method Post -Body $PostParameters -Headers $Headers
$ApiToken = $ApiReturn.Access_Token
$Headers = @{Authorization =("Bearer "+ $ApiToken)}
$AssignUserUri = ("https://api.workspot.com/v1.0/users/$UserEmail/desktops").Replace('@', '%40')
  
$PoolList = (Invoke-RestMethod -Uri "https://api.workspot.com/v1.0/pools" -Method Get -Headers $Headers).DesktopPools
$PoolId = ($PoolList | Where-Object { $_.Name -like $PoolName}).Id
$VdiList = Invoke-RestMethod -Uri "https://api.workspot.com/v1.0/pools/$PoolId/desktops" -Method Get -Headers $Headers
$VmId = ($VdiList.Desktops | Where-Object {$_.Name -like $VmName}).Id

$PostParameters = @{desktopId = $VmId} | ConvertTo-Json
Invoke-RestMethod -Uri $AssignUserUri -Method Post -Headers $Headers -Body $PostParameters -ContentType 'application/json' 
