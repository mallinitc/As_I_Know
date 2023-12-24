#/v1.0/companies/:companyId/rdgateways/clusters/:clusterId/regions/:clusterRegionId/rdgateways/:rdgatewayId/installpatches


#HmacSignature.ps1 -> Dev team will give this script

$id = "####"
$clus_id = "####"
$reg_id = "####"
$host_id = "####"



#$emailId = '"####"'
$emailId = '"####"'

$method = "POST"
#$baseUrl = "https://operations.o1control.com";
$baseUrl = "https://operations.workspot.com"
$route = "/v1.0/companies/$id/rdgateways/clusters/$clus_id/regions/$reg_id/rdgateways/$host_id/installpatches";
$uri = "$baseUrl$route";


#$authToken = Invoke-Expression "& .\HmacSignature.ps1 $emailId $route $method $null";
$authToken = D:\work\operations_API\HmacSignature.ps1 $emailId $route $method $null


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
