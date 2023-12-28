#Citrix XenDesktop hosted on AWS Cloud

#Citrix Catalog Power Management Script

#Linux VMs

<#Conditions
1. Make sure there is 10% VMs avaiable always (Powered on & ready to use)
2. If there is more than 10% avaiable, shut it them to 10%
3. If VM is locked for more than 15min then Disconnect the session
4. If VM is diconnected for more than 8hrs, then shut it down
#>


asnp *citrix*
asnp *posh*

function StopVM {
    $iid = $args[0]
    Stop-EC2Instance -InstanceId $iid
    Start-Sleep -s 5

}


$DDC = "<IP>"
#$dgname='DevOpsRHEL-W'


do {

    $dgnames = (Get-BrokerDesktopGroup -Name "Linux-*" -AdminAddress $DDC -InMaintenanceMode $false).Name
    foreach ($dgname in $dgnames) {
        $macs = Get-BrokerMachine -AdminAddress $DDC -DesktopGroupName $dgname  -RegistrationState Registered -SummaryState Available -SessionState $null
        $securePass = ConvertTo-SecureString "<Password>" -AsPlainText -Force
        $cred = New-Object System.Management.Automation.PSCredential ("FN-VAD", $securePass)


        foreach ($mac in $macs) {

            $hostname = $mac.MachineName
            $hostname = $hostname.Replace("ADCLOUD\", "")
            $hostname = $hostname.Replace("-", ".")
            #$hostname=''

            $0 = '$0'
            $cmd = "awk '{print $0/60;}' /proc/uptime"

            $ssh = New-SSHSession -ComputerName $hostname -Credential $cred -Force 
            if ($ssh) {

                $totmin = (Invoke-SSHCommand  -SSHSession $ssh -Command $cmd).OutPut
                Remove-SSHSession -SSHSession $ssh
                
                if ($totmin -ge 15) {
                    #ShutDown the machine

                    $instance = Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }
                    StopVM $instance.InstanceId
                    sleep -Seconds 5

                }
            }
            else {
                "No SSH access to $hostname machine"
            }
        }

        #Power off the Disconnected VMs for more than 3 days
        $macs = Get-BrokerMachine -AdminAddress $DDC -DesktopGroupName $dgname  -RegistrationState Registered -SummaryState Disconnected

        foreach ($mac in $macs) {
            $time = $mac.SessionStateChangeTime
            $time2 = Get-Date
            $duration = ($time2 - $time).TotalDays
            if ($duration -ge 3) {
                $hostname = $mac.MachineName
                Get-BrokerSession -AdminAddress $DDC -MachineName $hostname | Stop-BrokerSession 
                $hostname = $hostname.Replace("ADCLOUD\", "")
                $hostname = $hostname.Replace("-", ".")
                $instance = Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }
                StopVM $instance.InstanceId
                sleep -Seconds 5

            }
        }

    }

}while (1)