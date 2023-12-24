#Author: mallikarjun
#Last Modified: 06-01-2022

#for TLS error
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$user = $env:USERNAME
$TranscriptFile = "C:\Powershell\OperationsAPI\Logs\WsPatchScript_$(Get-Date -Format MMddyyyyMMss)_$($user).txt"
Start-Transcript -Path $TranscriptFile

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

Function Get-RDGHost($id, $clus_id,$reg_id,$host_id)
{
    $method = "GET"
    $route = "/v1.0/companies/$id/rdgateways/clusters/$clus_id/regions/$reg_id/rdgateways/$host_id";
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

Function New-Snapshot($id, $clus_id,$reg_id,$host_id)
{

    $method = "POST"
    $route = "/v1.0/companies/$id/rdgateways/clusters/$clus_id/regions/$reg_id/rdgateways/$host_id/snapshot";
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

Function Get-Status($url_id)
{

    $method = "GET"
    $route = "/v1.0/operation/$url_id";
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

Function Install-WsPatches($id, $clus_id,$reg_id,$host_id)
{

    $method = "POST"
    $route = "/v1.0/companies/$id/rdgateways/clusters/$clus_id/regions/$reg_id/rdgateways/$host_id/installpatches";
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
        $RDGateways = $RDGateways|Select-Object name,id, lastRebootDate, region, status, mode, activeConnections,activeHTML5Connections, agentVersion|Sort-Object -Property name|Out-GridView -PassThru

        ForEach($RDGHost in $RDGateways)
        {
            #Each Selected RDGHost in Maintenance Mode
            Write-Host "[INFO]  Processing the RDGHost:" -NoNewline; Write-Host "  $($RDGHost.name)" -ForegroundColor Yellow
            Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name) : Changing the mode..."
            $mode = 'Maintenance' #Enabled or Maintenance
            If($RDGHost.mode -like 'Maintenance')
            {
                Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name) : is already in Maintenance"
            }
            else
            {
                #Changing the mode
                $RDGs = (Get-RDGateways -id $org.id -clus_id $Cluster.clusterId -reg_id $Cluster.Clus_RegionId).rdGateways
                #$avlRDGs = $RDGs|Where-Object{($_.status -like 'Ready') -and ($_.mode -like 'Enabled')}
                #$avlRDGsCount = ($avlRDGs.name).count
             
                #$res = Set-RDGHostMode -id $org.id -clus_id $Cluster.clusterId -reg_id $Cluster.Clus_RegionId -host_id $RDGHost.id -mode $mode
                
            }
                #Take Snapshot
                Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name) : Taking the snapshot"
                $res1 = New-Snapshot -id $org.id -clus_id $Cluster.clusterId -reg_id $Cluster.Clus_RegionId -host_id $RDGHost.id
                Start-Sleep -Seconds 60
                $Statusid = $res1.statusURL.Split("/")[5]
                $Status = Get-Status -url_id $Statusid
                while(!($Status.endTime))
                {
                    Write-Host "[INFO]  $($RDGHost.name) => Snapshot is in-progress"
                    Start-Sleep -Seconds 30
                    $Status = Get-Status -url_id $Statusid
                }
                If($Status.status -notlike 'Success')
                {
                    Write-Host "[ERR]   $($org.name)/$($Cluster.name)/$($RDGHost.name) : Snapshot is failed. So breaking.." -ForegroundColor Red
                    Write-Host "[ERR]   Error Info: $($Status.errorInfo)" -ForegroundColor Gray
                    break
                }
                else
                {
                    #Install patches
                    Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name) : Checking for patches..."
                    $res1 = Install-WsPatches -id $org.id -clus_id $Cluster.clusterId -reg_id $Cluster.Clus_RegionId -host_id $RDGHost.id
                    Start-Sleep -Seconds 60
                    $Statusid = $res1.statusURL.Split("/")[5]
                    $Status = Get-Status -url_id $Statusid
                    while(!($Status.endTime))
                    {
                        Write-Host "[INFO]  Host: $($RDGHost.name) => Patch installation is in-progress..."
                        Write-Host "[INFO]  Status: $($Status.statusDetail)"
                        Start-Sleep -Seconds 120
                        $Status = Get-Status -url_id $Statusid
                    }
                    If($Status.status -notlike 'Success')
                    {
                        Write-Host "[ERR]   $($org.name)/$($Cluster.name)/$($RDGHost.name) : Patching is failed. So breaking.." -ForegroundColor Red
                        Write-Host "[ERR]   Error Info: $($Status.errorInfo)" -ForegroundColor Gray
                        break
                    }
                    else
                    {
                        #Display final result
                        Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name) : ====> Result: $($Status.statusDetail)" -ForegroundColor Yellow

                    }
                }

            

        }
    }
}

Stop-Transcript