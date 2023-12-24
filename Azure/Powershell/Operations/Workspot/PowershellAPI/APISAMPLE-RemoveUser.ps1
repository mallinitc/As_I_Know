################################################################
# Sample script to remove a user account from Workspot Control #
################################################################
###########################
# Variable initialization #
$ApiClientId = "" #Workspot Control API Client ID
$ApiClientSecret = "" #Workspot Control API Client Secret
$WsControlUser = "" #Workspot Control Administrator user email address
$WsControlPass = "" #Workspot Control Administrator user password
   
$Email = "" # Email address of user account to remove from Workspot Control
############################


$ApiClientPair = "$($ApiClientId):$($ApiClientSecret)"
$EncodedApiCreds = [System.Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes($ApiClientPair))
$HeaderAuthValue = "Basic $EncodedApiCreds"
$Headers = @{Authorization = $HeaderAuthValue}
$PostParameters = @{username=$WsControlUser;password=$WsControlPass;grant_type='password'}
$ApiReturn = Invoke-RestMethod -Uri "https://api.workspot.com/oauth/token" -Method Post -Body $PostParameters -Headers $Headers
$ApiToken = $ApiReturn.Access_Token
$Headers = @{Authorization =("Bearer "+ $ApiToken)}
  
$RestUri = ("https://api.workspot.com/v1.0/users/$Email/").Replace('@', '%40')
$ReturnStatusCode = (Invoke-WebRequest -Uri $RestUri -Method Delete -Headers $Headers).StatusCode
If($ReturnStatusCode -eq 204) { Return("User $Email removed successfully") }
Else { Return("Removal of user $Email failed with status code $ReturnStatusCode.") }