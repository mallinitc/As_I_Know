#Citrix XenDesktop hosted on AWS Cloud

#Citrix Catalog Power Management Script

<#Conditions
1. Make sure there is 10% VMs avaiable always (Powered on & ready to use)
2. If there is more than 10% avaiable, shut it them to 10%
3. If VM is locked for more than 15min then Disconnect the session
4. If VM is diconnected for more than 8hrs, then shut it down
#>

$DDC1 = "<IP>"

if (!((Test-Connection $DDC1 -Count 2 -Quiet) -and ((Get-Service -ComputerName $DDC1 -Name CitrixBrokerService).Status -like 'Running'))) {

    $DDC = "<IP>"
    $cat = "UnManaged Single Session VDA"
    $per = 100

    asnp *citrix*

    Write-Host "Executing the script in $DDC server"

    $total = (Get-BrokerDesktop -AdminAddress $DDC -DesktopGroupName $cat).Count

    [int]$count = ($total * $per) / 100
    $count

    $avl = (Get-BrokerDesktop -AdminAddress $DDC -DesktopGroupName $cat -SummaryState Available).Count

    if ($avl -lt $count) {

        #$count-$avl no.of VMs need to be started

        $hostnames = (Get-BrokerDesktop -AdminAddress $DDC -DesktopGroupName $cat -SummaryState Unregistered).MachineName

        $i = 1
        foreach ($hostname in $hostnames) {

            if ($i -le ($count - $avl)) {
                $i++
                $hostname = $hostname.Replace("<DOMAINNAME>\", "")
                $hostname = $hostname.Replace("-", ".")
                $vm = Get-BrokerDesktop -AdminAddress $DDC -IPAddress $hostname


                if (($vm.PowerState -ne "Unmanaged") -and ($vm.PowerState -ne $null)) {
                    if ($vm.DesktopKind -like 'Private') {
                        Set-BrokerPrivateDesktop -MachineName $vm.MachineName -InMaintenanceMode $true -AdminAddress $ddc
                    }
                    else {
                        Set-BrokerSharedDesktop -MachineName $vm.MachineName -InMaintenanceMode $true -AdminAddress $ddc
                    }
                    #PoweringOn Using Citrix Commands
                    New-BrokerHostingPowerAction -MachineName $vm.MachineName -Action Reset -AdminAddress $ddc
                    Start-Sleep -s 15

                    $status = (Get-BrokerDesktop -AdminAddress $DDC -IPAddress $hostname).PowerState
                    Write-Host "The VM current status is '$status'"


                }
                else {


                    #After adding a TAG called IP and value as its Private IP address
                    #$instance=Get-EC2Instance|select -ExpandProperty RunningInstance|?{$_.tags.Key -eq "IP" -and $_.Tags.Value -eq "10.118.124.130"}

                    #UsingPrivateIPaddress
                    $instance = Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }

                    if ($instance.State.Name.Value -notlike "Running") {

                        #Starting the VM if its not running
                        Start-EC2Instance -InstanceId $instance.InstanceId
                        Start-Sleep -s 15

                        $status = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }).State.Name.Value
                        Write-Host "The VM current status is '$status'"

                    }
                }
            }
            else {
                break
            }
        }
    }

    else {
        #$avl-$count no.of VMs need to be stopped
        $hostnames = (Get-BrokerDesktop -AdminAddress $DDC -DesktopGroupName $cat -SummaryState Available).MachineName
        $i = 1
        foreach ($hostname in $hostnames) {
            if ($i -le ($avl - $count)) {
                $i++
                $hostname = $hostname.Replace("<DOMAINNAME>\", "")
                $hostname = $hostname.Replace("-", ".")
                $vm = Get-BrokerDesktop -AdminAddress $DDC -IPAddress $hostname


                if (($vm.PowerState -ne "Unmanaged") -and ($vm.PowerState -ne $null)) {
                    if ($vm.DesktopKind -like 'Private') {
                        Set-BrokerPrivateDesktop -MachineName $vm.MachineName -InMaintenanceMode $true -AdminAddress $ddc
                    }
                    else {
                        Set-BrokerSharedDesktop -MachineName $vm.MachineName -InMaintenanceMode $true -AdminAddress $ddc
                    }
                    #PoweringOn Using Citrix Commands
                    New-BrokerHostingPowerAction -MachineName $vm.MachineName -Action Poweroff -AdminAddress $ddc
                    Start-Sleep -s 15

                    $status = (Get-BrokerDesktop -AdminAddress $DDC -IPAddress $hostname).PowerState
                    Write-Host "The VM current status is '$status'"


                }
                else {


                    #After adding a TAG called IP and value as its Private IP address
                    #$instance=Get-EC2Instance|select -ExpandProperty RunningInstance|?{$_.tags.Key -eq "IP" -and $_.Tags.Value -eq "10.118.124.130"}

                    #UsingPrivateIPaddress
                    $instance = Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }

                    if ($instance.State.Name.Value -like "Running") {

                        #Stopping the VM if its running
                        Stop-EC2Instance -InstanceId $instance.InstanceId
                        Start-Sleep -s 15

                        $status = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }).State.Name.Value
                        Write-Host "The VM current status is '$status'"

                    }
                }
            }
            else {
                break
            }
        }

    }


    ######Disconneted Conditions
    $hostnames = (Get-BrokerDesktop -AdminAddress $DDC -DesktopGroupName $cat -SummaryState Disconnected).MachineName

    foreach ($hostname in $hostnames) {

        $hostname = $hostname.Replace("<DOMAIN>\", "")
        $hostname = $hostname.Replace("-", ".")
        $instance = Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }

        $vm = Get-BrokerDesktop -AdminAddress $DDC -IPAddress $hostname
        $now = Get-Date
        $hrs = ($now - $vm.SessionStateChangeTime).Minutes
        if ($hrs -ge 8) {
            #Stopping if the VM is diconnected more than 8 hours

            Stop-EC2Instance -InstanceId $instance.InstanceId
            Start-Sleep -s 10

            $status = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }).State.Name.Value
            Write-Host "The VM current status is '$status'"

        }

    }


    ####Lock Conditions

    $hostnames = (Get-BrokerDesktop -AdminAddress $DDC -DesktopGroupName $cat | ? { $_.SessionState -eq 'Active' }).MachineName

    foreach ($hostname in $hostnames) {
        $hostname = $hostname.Replace("<DOMAIN>\", "")
        $hostname = $hostname.Replace("-", ".")  
 
        if ((Get-BrokerDesktop -AdminAddress $DDC -IPAddress $hostname).Protocol -like 'RDP') {

            $a = gwmi win32_process -computername $hostname | ? { $_.name -like "logonui.exe" }
            $time21 = $a | % { $_.ConvertToDateTime( $_.CreationDate ) } | Sort-Object -Descending
            if ($time21.count -gt 1) {
                $time2 = $time21[0]

                $time1 = Get-date
                $lock = ($time1 - $time2).Minutes
                if ($lock -ge 15) {
                    #VM is locked for more than 15 Miniutes here & so disconnecting 

                    #Get-BrokerSession -AdminAddress $DDC -HostedMachineName $hostname|Disconnect-BrokerSession

                    $b = qwinsta /server:$hostname | findstr 'rdp-tcp#'
                    $session = $b.Split(" ")[1]
                    tsdiscon  $session /server:$hostname

                }

            }
        }
        else {
            if ($a = gwmi win32_process -computername $hostname | ? { $_.name -like "logonui.exe" }) {
                $time2 = $a | % { $_.ConvertToDateTime( $_.CreationDate ) } | Sort-Object -Descending
                $time1 = Get-date
                $lock = ($time1 - $time2).Minutes

                if ($lock -ge 15) {
                    #VM is locked for more than 15 Miniutes here & so disconnecting 

                    Get-BrokerSession -AdminAddress $DDC -IPAddress $hostname | Disconnect-BrokerSession


                }
            }
        }



    }

}
else {
    "The Primary DDC server $DDC1 is running. So exiting the script"

}
