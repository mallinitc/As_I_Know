#Author: mallikarjun
#Last Modified: 06-01-2022

#for TLS error
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$user = $env:USERNAME
$TranscriptFile = "C:\Powershell\OperationsAPI\Logs\RebootScript_$(Get-Date -Format MMddyyyyMMss)_$($user).txt"
Start-Transcript -Path $TranscriptFile

$mode = 'Enabled' #Enabled or Maintenance
$othermode = "Maintenance"
Function Get-Clusters($id) 
{
    $method = "GET"
    $route = "/v1.0/companies/$id/rdgateways/clusters";
    $uri = "$baseUrl$route";
    $authToken = C:\Powershell\OperationsAPI\HmacSignature.ps1 $emailId $route $method $null
    
    $Header = @{
            "authorization" = "WS $authToken"
            }

    $parameters = @{
        Method = $method
        Uri = $uri
        Headers = $Header
        }

    $output = Invoke-RestMethod @parameters

    return $output
}

Function Get-RDGateways($id, $clus_id,$reg_id)
{
    $method = "GET"
    $route = "/v1.0/companies/$id/rdgateways/clusters/$clus_id/regions/$reg_id/rdgateways";
    $uri = "$baseUrl$route";

    $authToken = C:\Powershell\OperationsAPI\HmacSignature.ps1 $emailId $route $method $null
    $Header = @{
        "authorization" = "WS $authToken"
    }
    $parameters = @{
        Method = $method
        Uri = $uri
        Headers = $Header
    }
    $output = Invoke-RestMethod @parameters
    return $output
}

Function Set-RDGHostMode($id, $clus_id,$reg_id,$host_id, $mode)
{
    $method = "POST"
    $route = "/v1.0/companies/$id/rdgateways/clusters/$clus_id/regions/$reg_id/rdgateways/$host_id/mode/$mode";
    $uri = "$baseUrl$route";

    $authToken = C:\Powershell\OperationsAPI\HmacSignature.ps1 $emailId $route $method $null
    $Header = @{
        "authorization" = "WS $authToken"
        }

    $parameters = @{
        Method = $method
        Uri = $uri
        Headers = $Header
        }

    $output=Invoke-RestMethod @parameters
    return $output
}

#Main
$emailId = ''
$baseUrl = "https://operations.workspot.com"

#Get Company details
$method = "GET"
$route = "/v1.0/companies";
$uri = "$baseUrl$route";
$authToken = C:\Powershell\OperationsAPI\HmacSignature.ps1 $emailId $route $method $null

$Header = @{
"authorization" = "WS $authToken"
}

$parameters = @{
Method = $method
Uri = $uri
Headers = $Header
}

$res= Invoke-RestMethod @parameters
$Orgs = $res.companyList|Where-Object{$_.state -like 'Customer'}|Sort-Object -Property name|Out-GridView -PassThru

ForEach($org in $Orgs)
{
    #Each selected Customer
    Write-Host "[INFO]  Processing the customer:" -NoNewline; Write-Host "  $($org.name)" -ForegroundColor Yellow
    Write-Host "[INFO]  $($org.name) : Getting the clusters..."
    $Clusters = (Get-Clusters -id $org.id).clusters
    $Clusters = $clusters|Select-Object name,clusterId, @{Name="Clus_RegionId"; Expression={ $_.regionalClusters.clusterRegionId}} |Sort-Object -Property name|Out-GridView -PassThru
    Foreach($Cluster in $Clusters)
    {
        #Each selected Cluster
        Write-Host "[INFO]  Processing the cluster:" -NoNewline; Write-Host "  $($Cluster.name)" -ForegroundColor Yellow
        Write-Host "[INFO]  $($org.name)/$($Cluster.name) : Getting the RDGateways..."
        $RDGateways = (Get-RDGateways -id $org.id -clus_id $Cluster.clusterId -reg_id $Cluster.Clus_RegionId).rdGateways
        $RDGateways = $RDGateways|Where-Object{$_.mode -like $othermode}|Select-Object name,id, lastRebootDate, region, status, mode, activeConnections,activeHTML5Connections, agentVersion|Sort-Object -Property name|Out-GridView -PassThru
        If($RDGateways.count -like 0)
        {
            Write-Host "All Servers in $($mode) mode" 
            break
        }
       

        ForEach($RDGHost in $RDGateways)
        {
            #Each Selected RDGHost in Maintenance Mode
            Write-Host "[INFO]  Processing the RDGHost:" -NoNewline; Write-Host "  $($RDGHost.name)" -ForegroundColor Yellow
            
                                      
            $res = Set-RDGHostMode -id $org.id -clus_id $Cluster.clusterId -reg_id $Cluster.Clus_RegionId -host_id $RDGHost.id -mode $mode
            If(($res.mode -notlike $mode) -and ($res))
            {
             Write-Host "[ERR]   $($org.name)/$($Cluster.name)/$($RDGHost.name): is not in $($mode) mode, so breaking" -ForegroundColor Red
             break
             }
             else
             {
             Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name): is in $($mode) mode." -ForegroundColor Green
                           
             }
  }
  }
  }
            


  Stop-Transcript