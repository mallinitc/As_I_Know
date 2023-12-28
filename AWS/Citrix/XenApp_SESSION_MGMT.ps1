#Citrix XenApp Environment hosted on AWS Cloud

#XenApp Session Mgmt (RDP & ICA Sessions)

#1.Lock Conditions - disconnected sessions if more than 10 min locked
#2.Disconnected sessions - Log off sessions if more than 2 Hrs disconnected

asnp *citrix*


$DDC = (Get-BrokerController -State Active)[0].MachineName
$DDC = $DDC.Replace("VZADCLOUD\", "").Replace("-", ".")

if (!($DDC)) {
    #No DDC is Active
    "No Active DDC servers. Exiting the script.('$(Get-date)')" >> C:\temp\SessLogs\DDCERROR.txt
    exit
    
}

do {

    $Global:info
    $Global:err

    $Global:info = @()
    $Global:err = @()
    $Global:any = 0


    #$dgnames=(Get-BrokerDesktopGroup -AdminAddress $DDC -Tag 'XenApp').Name
    $dgnames = "Retail Desktop"

    foreach ($dgname in $dgnames) {
        $Global:info += "Working on $dgname"

        #1.Lock Conditions

        $hostnames = (Get-BrokerSession -AdminAddress $DDC -DesktopGroupName $dgname | ? { $_.SessionState -eq 'Active' }).MachineName

        foreach ($hostname in $hostnames) {
            $hostname = $hostname.Replace("ADCLOUD\", "")
            $IP = $hostname.Replace("-", ".")

            $sess = Get-CimInstance win32_process -computername $hostname | ? { $_.name -like "logonui.exe" } | select *

            foreach ($ses in $sess) {
                $time2 = $ses.CreationDate
                $time1 = Get-date
                $lock = $time1 - $time2
                $locktime = $lock.TotalHours
                $sid = $ses.SessionId
                #"$sid $locktime   $time1   $time2"
                if (($locktime -gt 10) -and ($sid -ne 1)) {

                    $Global:any++
                    if ((Get-BrokerSession -AdminAddress $DDC -IPAddress $hostname).Protocol -like 'RDP') {
                        #RDP Session locked
                        $ses2 = Get-CimInstance win32_process -computername $hostname | ? { $_.name -like "rdpclip.exe" -and $_.SessionId -eq $sid }
                        $user = (Invoke-CimMethod -InputObject $ses2 -MethodName GetOwner -ComputerName $hostname | select User).User

                        $Global:info += "Disconnecting the RDP session ID $sid of $user in $hostname"
                        tsdiscon  $sid /server:$hostname
                    }
                    else {
                        #ICA Session locked
                        #Get the User ID
                        $ses2 = Get-CimInstance win32_process -computername $hostname | ? { $_.name -like "wfshell.exe" -and $_.SessionId -eq $sid }
                        $user = (Invoke-CimMethod -InputObject $ses2 -MethodName GetOwner -ComputerName $hostname | select User).User
                        $Global:info += "Disconnecting the ICA session of $user in $hostname"
                        Get-BrokerSession -AdminAddress $DDC -IPAddress $IP -BrokeringUserName ADCLOUD\$user -DesktopGroupName $dgname | Disconnect-BrokerSession
                    }

                }

            }
        }


        #2.Disconnected sessions

        $sessions = Get-BrokerSession -AdminAddress $DDC -DesktopGroupName $dgname | ? { $_.SessionState -eq 'Disconnected' }


        foreach ($sess in $sessions) {

            $date2 = $sess.SessionStateChangeTime
            $date1 = Get-date
            $duration = ($date1 - $date2).TotalHours
            if ($duration -gt 2) {
                $Global:any++
                #Logging off the user
                $user = $sess.UserName
                $hostname = $sess.MachineName
                $Global:info += "Logging off the ICA session of $user in $hostname"
                $sess | Stop-BrokerSession
            }
        }

        $Global:info += "Exiting Loop for $dgname"
        #Logs DesktopGroup wise

        if ($Global:any) {
            [string]$log = [string](Get-Date).Day + [string](Get-Date).Month + [string](Get-Date).Year + "_" + [string](Get-Date).Hour + "_" + [string](Get-Date).Minute + "_" + [string](Get-Date).Second

            [string]$error = $log + "_Error.txt"
            [string]$data = $log + "_Info.txt"

            if ($err) {
                $Global:err >>C:\temp\SessLogs\$error
            }

            $Global:info > C:\temp\SessLogs\$data

        }

    }



}while (1)