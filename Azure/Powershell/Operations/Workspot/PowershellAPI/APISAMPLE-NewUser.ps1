##################################################################
# Sample script to create a new user account in Workspot Control #
##################################################################
###########################
# Variable initialization #
$ApiClientId = "" #Workspot Control API Client ID
$ApiClientSecret = "" #Workspot Control API Client Secret
$WsControlUser = "" #Workspot Control Administrator user email address
$WsControlPass = "" #Workspot Control Administrator user password

$Email = "" #Email address of user account to add to Workspot Control
$FirstName = "" #First name of new user to add to Workspot Control
$LastName = "" #Last name of new user to add to Workspot Control
############################

$ApiClientPair = "$($ApiClientId):$($ApiClientSecret)"
$EncodedApiCreds = [System.Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes($ApiClientPair))
$HeaderAuthValue = "Basic $EncodedApiCreds"
$Headers = @{Authorization = $HeaderAuthValue}
$PostParameters = @{username=$WsControlUser;password=$WsControlPass;grant_type='password'}
$ApiReturn = Invoke-RestMethod -Uri "https://api.workspot.com/oauth/token" -Method Post -Body $PostParameters -Headers $Headers
$ApiToken = $ApiReturn.Access_Token
$Headers = @{Authorization =("Bearer "+ $ApiToken)}
   
$User = @{
    email = $Email
    firstName = $FirstName
    lastName = $LastName
}
   
$UserJson = $User | ConvertTo-Json
$StatusUrl = (Invoke-RestMethod -Uri "https://api.workspot.com/v1.0/users" -Method Post -Headers $Headers -Body $UserJson -ContentType 'application/json').StatusUrl

Do {
    Start-Sleep -Seconds 5
    $StatusReturn = Invoke-RestMethod -Method GET -ContentType "application/json" -Uri $StatusUrl -Headers $Headers
} Until($StatusReturn.Status = "Succeeded")

$StatusReturn           #This will display the summary of the completed operation
$StatusReturn.Details   #If successful, this will display the new user account details
$StatusReturn.ErrorInfo #If not successful, this will display the error details