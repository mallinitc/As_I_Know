#/v1.0/companies/:companyId/rdgateways/clusters/:clusterId/regions/:regionId/rdgateways/:rdgatewayId

$id = "#"
$clus_id = '#'
$reg_id = '#'
#$host_id = '#'
$host_id = '#'

#/v1.0/companies/:companyId/rdgateways/clusters/:clusterId/regions/:regionId/rdgateways
$Name = "#"

#$emailId = '#'
$emailId = '#'

$method = "GET"
#$baseUrl = "https://operations.o1control.com";
$baseUrl = "https://operations.workspot.com"
$route = "/v1.0/companies/$id/rdgateways/clusters/$clus_id/regions/$reg_id/rdgateways/$host_id";
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



$Hst = Invoke-RestMethod @parameters
