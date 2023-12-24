#Author: mallikarjun
#Last Modified: 31-01-2022

#HmacSignature.ps1 -> Dev team will give u this script

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

Function Update-Certificate($id, $clus_id,$reg_id,$host_id)
{

    $method = "POST"
    $baseUrl = "https://operations.workspot.com"
    $route = "/v1.0/companies/$id/rdgateways/clusters/$clus_id/regions/$reg_id/rdgateways/$host_id/updatecertificate";
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

    $output= Invoke-RestMethod @parameters
    return $output

}

#Main
$emailId = '###'
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
        $RDGateways = $RDGateways|Select-Object name,id, lastRebootDate, region, status, mode, activeConnections,activeHTML5Connections, agentVersion|Sort-Object -Property name|Out-GridView -PassThru

        ForEach($RDGHost in $RDGateways)
        {
            #Each Selected RDGHost in Maintenance Mode
            Write-Host "[INFO]  Processing the RDGHost:" -NoNewline; Write-Host "  $($RDGHost.name)" -ForegroundColor Yellow
            $Hst = Get-RDGHost -id $org.id -clus_id $Cluster.clusterId -reg_id $Cluster.Clus_RegionId -host_id $RDGHost.id
            If($Hst.certExpiration -notlike '*2023')
            {
                Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name) : Changing the mode..."
                $mode = 'Maintenance' #Enabled or Maintenance
                If($RDGHost.mode -like 'Maintenance')
                {
                    Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name) : is already in Maintenance"
                }
                else
                {
                    [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms")
                    $result = [System.Windows.Forms.MessageBox]::Show("Active Connections: $($RDGHost.activeConnections)`n Do you want keep the RDG in maintenance?" , "$($RDGHost.name)" , 4)
                    If($result -eq 'No')
                    {
                        Write-Host "[WAR]   $($org.name)/$($Cluster.name)/$($RDGHost.name) Continuing..."
                    }
                    else
                    {
                        #Changing the mode
                        $mode = 'Maintenance' #Enabled or Maintenance
                        $res = Set-RDGHostMode -id $org.id -clus_id $Cluster.clusterId -reg_id $Cluster.Clus_RegionId -host_id $RDGHost.id -mode $mode
                    }
                
                }

                #updating Certificate
                Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name) : Updating the certificate..."
                $res = Update-Certificate -id $org.id -clus_id $Cluster.clusterId -reg_id $Cluster.Clus_RegionId -host_id $RDGHost.id -mode $mode
                Start-Sleep -Seconds 5
                $Statusid = $res.statusURL.Split("/")[5]
                $Status = Get-Status -url_id $Statusid
                while(!($Status.endTime))
                {
                    Write-Host "[INFO]  Host: $($RDGHost.name) => Certificate update is still in-progress..."
                    Start-Sleep -Seconds 3
                    $Status = Get-Status -url_id $Statusid
                }
                If($Status.status -notlike 'Success')
                {
                    Write-Host "[ERR]   $($org.name)/$($Cluster.name)/$($RDGHost.name) : Certificate Update is failed." -ForegroundColor Red
                    Write-Host "[ERR]   Error Info: $($Status.errorInfo)" -ForegroundColor Gray
                    break
                }
                else
                {
                    Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name) : $($Status.statusDetail)" -ForegroundColor Yellow
                }
            }
            Else
            {
                #Already updated
                Write-Host "[INFO]  $($org.name)/$($Cluster.name)/$($RDGHost.name) : Certificate is already updated" -ForegroundColor Yellow
            }
        


        }
    }
}

Stop-Transcript