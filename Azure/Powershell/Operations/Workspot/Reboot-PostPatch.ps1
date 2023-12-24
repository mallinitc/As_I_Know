#Author: mallikarjun
#Last Modified: 06-01-2022

#for TLS error
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$user = $env:USERNAME
$TranscriptFile = "C:\Powershell\OperationsAPI\Logs\RebootScript_$(Get-Date -Format MMddyyyyMMss)_$($user).txt"
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

Function Restart-RDGHost($id, $clus_id,$reg_id,$host_id)
{

    $method = "POST"
    $route = "/v1.0/companies/$id/rdgateways/clusters/$clus_id/regions/$reg_id/rdgateways/$host_id/reboot";
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
$emailId = '#'
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
        $avlRDGs = $RDGateways|Where-Object{($_.status -like 'Ready') -and ($_.mode -like 'Enabled')}
        $avlRDGsCount = ($avlRDGs.name).count
        $RDGateways = $RDGateways|Where-Object{$_.mode -like 'Maintenance'}|Select-Object name,id, lastRebootDate, region, status, mode, activeConnections,activeHTML5Connections, agentVersion|Sort-Object -Property name|Out-GridView -PassThru

        ForEach($RDGHost in $RDGateways)
        {
            #Each Selected RDGHost in Maintenance Mode
            Write-Host "[INFO]  Processing the RDGHost:" -NoNewline; Write-Host "  $($RDGHost.name)" -ForegroundColor Yellow
            Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name) : Rebooting the server..."
            $mode = 'Maintenance' #Enabled or Maintenance
            [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms")
            $result = [System.Windows.Forms.MessageBox]::Show("Active Connections: $($RDGHost.activeConnections)`n Enabled Hosts: $($avlRDGsCount)`n Are you sure?" , "REBOOTING $($RDGHost.name)" , 4)
            If($result -eq 'No')
            {
                Write-Host "[ERR]   $($org.name)/$($Cluster.name)/$($RDGHost.name) still has active connections, so breaking.." -ForegroundColor Red
                break
            }
            else
            {
                #Reboot
                Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name) : Rebooting the server..."
                $res = Restart-RDGHost -id $org.id -clus_id $Cluster.clusterId -reg_id $Cluster.Clus_RegionId -host_id $RDGHost.id -mode $mode
                Start-Sleep -Seconds 60
                $Statusid = $res.statusURL.Split("/")[5]
                $Status = Get-Status -url_id $Statusid
                while(!($Status.endTime))
                {
                    Write-Host "[INFO]  Host: $($RDGHost.name) => Restart is still in-progress..."
                    Start-Sleep -Seconds 30
                    $Status = Get-Status -url_id $Statusid
                }
                If($Status.status -notlike 'Success')
                {
                    Write-Host "[ERR]   $($org.name)/$($Cluster.name)/$($RDGHost.name) : Restart is failed. So breaking.." -ForegroundColor Red
                    Write-Host "[ERR]   Error Info: $($Status.errorInfo)" -ForegroundColor Gray
                    break
                }
                else
                {
                    #Rechecking for patches
                    Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name) : Rechecking for patches..."
                    #Install patches
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
                        If($Status.statusDetail -like 'PATCH_NO_PENDING')
                        {
                            Write-Host "[INFO]  Host $($RDGHost.name) : No pending patches, so enabling the server mode now"
                            $mode = 'Enabled' #Enabled or Maintenance 
                            $res = Set-RDGHostMode -id $org.id -clus_id $Cluster.clusterId -reg_id $Cluster.Clus_RegionId -host_id $RDGHost.id -mode $mode
                            If(($res.mode -notlike 'Enabled') -and ($res))
                            {
                                Write-Host "[ERR]   $($org.name)/$($Cluster.name)/$($RDGHost.name): is not in Enabled mode, so breaking" -ForegroundColor Red
                                break
                            }
                            else
                            {
                                Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name): is in Enabled mode." -ForegroundColor Green
                                
                            }
                        }

                    }
                }

            }
            


        }
    }
}

Stop-Transcript