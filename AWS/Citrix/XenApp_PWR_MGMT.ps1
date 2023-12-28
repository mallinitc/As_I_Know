#Citrix XenApp Environment hosted on AWS CLOUD

#XenApp Power mgmt


#1. Max sessions -then enable maintenance mode (or disable Logon)
#2.Disable Maintenance Mode ifsession count is zero
#3.Max sessions - bring new server up
#4. Zero sessions - Power it off
#Keep atleast 1 servers UP from ZeroSessSrv to accept new connections



asnp *citrix*


$DDC = (Get-BrokerController -State Active)[0].MachineName
$DDC = $DDC.Replace("DOMAIN\", "").Replace("-", ".")

if (!($DDC)) {
    #No DDC is Active
    "No Active DDC servers. Exiting the script.('$(Get-date)')" >> C:\temp\SessLogs\DDCERROR.txt
    exit
    
}

$sessPervm = 1


function StartVM {
    $iid = $args[0]
    Start-EC2Instance -InstanceId $iid
    Start-Sleep -s 60
    $Global:any++
}

function StopVM {
    $iid = $args[0]
    Stop-EC2Instance -InstanceId $iid
    Start-Sleep -s 15
    $Global:any++
}

function PowerOnNewVM {
    #POweringON New VM from available list
    $dgroup = $args[0]
    $Global:any++
    $AvlSrvs = (Get-BrokerMachine -DesktopGroupName $dgroup -AdminAddress $DDC -Filter "SessionCount -eq 0" | ? { $_.WindowsConnectionSetting -eq 'LogonEnabled' }).MachineName
    $res = 0
    foreach ($hostname in $AvlSrvs) {
        $hostname = $hostname.Replace("DOMAIN\", "")
        $hostname = $hostname.Replace("-", ".")

        $instance = Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }

        if ($instance.State.Name.Value -notlike "Running") {

            #Starting the VM if its not running
            $Global:info += "Powering on $hostname"
            StartVM $instance.InstanceId
            $status = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }).State.Name.Value
            $Global:info += "The VM current status of $hostname is '$status'"
            if ($status -eq 'Running') {
                Start-Sleep -s 60
                if ((Get-BrokerDesktop -AdminAddress $DDC -IPAddress $hostname).RegistrationState -like 'Registered') {
                    $Global:info += "$hostname is Registered so exiting the loop"
                    $res = 1
                    break
                }
            }
        }
    }
    return $res
}

do {
    $Global:info = @()
    $Global:err = @()
    $Global:any = 0

    $dgnames = (Get-BrokerDesktopGroup -AdminAddress $DDC -Name 'XenApp*').Name

    foreach ($dgname in $dgnames) {

        #$dgname="XenApp Script Dev Test - AWS East"
        $Global:info += "Working on $dgname"
        $total = (Get-BrokerDesktop -AdminAddress $DDC -DesktopGroupName $dgname).Count

        #1. Max sessions -then enable maintenance mode (or disable Logon)
        $MaxSessSrv = (Get-BrokerMachine -DesktopGroupName $dgname -AdminAddress $DDC -Filter "SessionCount -ge $sesspervm").MachineName

        foreach ($hostname in $MaxSessSrv) {
            $Global:info += "$hostname has max sessions so enabling maintenance mode"
            Set-BrokerMachine -AdminAddress $DDC -MachineName $hostname -InMaintenanceMode:$true
        }

        #2.Disable Maintenance Mode ifsession count is zero
        $MinSessSrv = (Get-BrokerMachine -DesktopGroupName $dgname -AdminAddress $DDC -InMaintenanceMode $true | ? { $_.SessionCount -eq 0 }).MachineName
        foreach ($hostname in $MinSessSrv) {
            Set-BrokerMachine -AdminAddress $DDC -MachineName $hostname -InMaintenanceMode:$false
        }


        #3.Max sessions - bring new server up

        $MinSessSrv = (Get-BrokerMachine -DesktopGroupName $dgname -AdminAddress $DDC -Filter "SessionCount -lt $sesspervm" | ? { $_.SessionCount -ne 0 }).MachineName.Count
        $ZeroSess = (Get-BrokerMachine -DesktopGroupName $dgname -AdminAddress $DDC -RegistrationState Registered | ? { $_.SessionCount -eq 0 }).MachineName.Count
        $MaxSessSrv = (Get-BrokerMachine -DesktopGroupName $dgname -AdminAddress $DDC -Filter "SessionCount -ge $sesspervm").MachineName.Count

        if ($total -eq $MaxSessSrv) {
            $Global:err += "All Servers are running with full capacity"

        }
        elseif ($MinSessSrv -ne 0) {
            $Global:info += "Server is avaible with minimal session count"
            #Check if all servers has n-1 connections
            $yes = 0
            $all = (Get-BrokerMachine -DesktopGroupName $dgname -AdminAddress $DDC -Filter "SessionCount -lt $sesspervm").MachineName
            foreach ($one in $all) {
                if ((Get-BrokerMachine -DesktopGroupName $dgname -AdminAddress $DDC -MachineName $one).SessionCount -eq ($sessPervm - 1)) {
                    $yes++
                }
            }
            if (($MinSessSrv -eq $yes) -and ($ZeroSess -eq 0)) {
                $Global:info += "All are running with n-1 connections. So powering on new one"
                $vm = Get-BrokerMachine -DesktopGroupName $dgname -AdminAddress $DDC -Filter "SessionCount -lt $sesspervm" | ? { $_.SessionCount -ne 0 }
                if ($vm.SessionCount -eq ($sessPervm - 1)) {
                    #PowerON VM
                    $a = PowerOnNewVM $dgname
                    if ($a -eq 1) {
                        $Global:info += "One VM is powered on from $dgname"
                    }
                    else {
                        $Global:err += "Unable to power on any VM from $dgname"
                    }

                } 
            }
            else {
                #Enable Maintenance Mode on the server-which has least min sessions
                $machine = (Get-BrokerMachine -DesktopGroupName $dgname -AdminAddress $DDC | ? { $_.SessionCount -ne 0 } | Select MachineName, SessionCount | Sort-Object -Property SessionCount).MachineName[0]
                Set-BrokerMachine -AdminAddress $DDC -MachineName $machine -InMaintenanceMode:$true

            }
        }
        elseif ($ZeroSess -ge 1) {
            $Global:info += "There are servers available  with 0 sessions"
        }
        else {
            $a = PowerOnNewVM $dgname
            if ($a -eq 1) {
                $Global:info += "One VM is powered on from $dgname"
            }
            else {
                $Global:err += "Unable to power on any VM from $dgname"
            }
        }


        #4. Zero sessions - Power it off

        $ZeroSessSrv = (Get-BrokerMachine -DesktopGroupName $dgname -AdminAddress $DDC | ? { ($_.SessionCount -eq 0) -and ($_.SummaryState -eq 'Available') }).MachineName
        $MinSessSrv = (Get-BrokerMachine -DesktopGroupName $dgname -AdminAddress $DDC -Filter "SessionCount -lt $sesspervm" | ? { ($_.SessionCount -ne 0) -and ($_.SummaryState -eq 'InUse') }).MachineName.Count

        $yes = 0
        $all = (Get-BrokerMachine -DesktopGroupName $dgname -AdminAddress $DDC -Filter "SessionCount -lt $sesspervm").MachineName
        foreach ($one in $all) {
            if ((Get-BrokerMachine -DesktopGroupName $dgname -AdminAddress $DDC -MachineName $one).SessionCount -eq ($sessPervm - 1)) {
                $yes++
            }
        }

        if ($MinSessSrv -ne $yes) {
            #Poweroff all ZeroSessSrv
            foreach ($hostname in $ZeroSessSrv) {

                $hostname = $hostname.Replace("VZADCLOUD\", "")
                $hostname = $hostname.Replace("-", ".")

                $instance = Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }

                if ($instance.State.Name.Value -like "Running") {

                    #Stopping the VM if its running
                    StopVM $instance.InstanceId
                    Start-Sleep -s 5

                    $status = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }).State.Name.Value
                    $Global:info += "The VM current status is '$status'"

                }

            }
        }
        else {
            #Keep atleast 1 servers UP from ZeroSessSrv to accept new connections
            $cnt = $ZeroSessSrv.count
            for ($i = 1; $i -lt $cnt; $i++) {
                $hostname = $ZeroSessSrv[$i]
                $hostname = $hostname.Replace("VZADCLOUD\", "")
                $hostname = $hostname.Replace("-", ".")
                $instance = Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }

                if ($instance.State.Name.Value -like "Running") {

                    #Stopping the VM if its running
                    Stop-EC2Instance -InstanceId $instance.InstanceId
                    Start-Sleep -s 15

                    $status = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }).State.Name.Value
                    $Global:info += "The VM current status is '$status'"

                }

            }


        }

        $Global:info += "Exiting Loop for $dgname"
        #Logs DesktopGroup wise
        if ($Global:any) {
            [string]$log = [string](Get-Date).Day + [string](Get-Date).Month + [string](Get-Date).Year + "_" + [string](Get-Date).Hour + "_" + [string](Get-Date).Minute + "_" + [string](Get-Date).Second

            [string]$error = $log + "_Error.txt"
            [string]$data = $log + "_Info.txt"

            if ($err) {
                $Global:err >>C:\temp\Logs\$error
            }

            $Global:info > C:\temp\Logs\$data
        }

    }

}while (1)