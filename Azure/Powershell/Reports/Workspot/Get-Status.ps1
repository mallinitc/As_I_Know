$url_id="#"

#/v1.0/operation/7f#

#$emailId = '#'
$emailId = '#'

$method = "GET"
#$baseUrl = "https://operations.o1control.com";
$baseUrl = "https://operations.workspot.com"
$route = "/v1.0/operation/$url_id";
$uri = "$baseUrl$route";


#$authToken = Invoke-Expression "& .\HmacSignature.ps1 $emailId $route $method $null";
$authToken = C:\Powershell\OperationsAPI\HmacSignature.ps1 $emailId $route $method $null


$Header = @{
"authorization" = "WS $authToken"
}



$parameters = @{
Method = $method
Uri = $uri
Headers = $Header
}



Invoke-RestMethod @parameters | ConvertTo-Json -Depth 5;
#Invoke-RestMethod @parameters
