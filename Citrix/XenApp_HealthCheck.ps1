#XenApp Server HealthChecks


$srvs = gc C:\temp\hosts.txt
foreach ($srv in $srvs) {
    #$srv
    if (Test-Connection -ComputerName $srv -Quiet) {

        #ZoneDataCollector
        $ZDC = (Get-XAZone).DataCollector
        if ($ZDC -eq $srv) { $ZDC = 'Yes' }else { $ZDC = 'No' }


        #Citrix Services status
        $IMA = (Get-Service -ComputerName $srv -Name IMAService).Status
        $MFCOM = (Get-Service -ComputerName $srv -Name MFCOM).Status
        $XTE = (Get-Service -ComputerName $srv -Name CitrixXTEServer).Status

        #C drive free space
        $FreSpce = (Get-WmiObject Win32_LogicalDisk -ComputerName $srv -Filter "DeviceID='C:'").FreeSpace
        $FreSpce = $FreSpce / 1024 / 1024 / 1024
        $FreSpce = "{0:N2}" -f $FreSpce + "GB"

        #Load using QFARM
        $Load = (Get-XAServerLoad -ServerName $srv).Load / 100 
        $Load = "{0:N2}" -f $Load + "%"

        #Published Applications count
        if ((Get-XAApplication -ServerName $srv | Select BrowserName).count) {
            $PubAppCount = (Get-XAApplication -ServerName $srv | Select BrowserName).count
        }
        else { $PubAppCount = 0 }

        #Current Active Sessions
        if ((Get-XASession -ServerName sacp1leevfa14v | ? { $_.state -eq 'Active' }).count) {
            $ActSessCount = (Get-XASession -ServerName $srv | ? { $_.state -eq 'Active' }).count
        }
        else { $ActSessCount = 0 }

        #LHC size
        $lhcpath = "\\" + $srv + "\C$\Program Files (x86)\Citrix\Independent Management Architecture\imalhc.mdb"
        $lhcMB = (Get-Item -Path $lhcpath).Length / 1024 / 1024
        $lhcMB = "{0:N2}" -f $lhcMB + "MB"

        #Load Evaluators
        $LoadEval = (Get-XALoadEvaluator -ServerName $srv).LoadEvaluatorName

        #ICAPort 1494 enabled or not
        $Socket = New-Object Net.Sockets.TcpClient
        $Socket.Connect($srv, 1494)
        if ($socket.Connected) { $ICAPort = 'Enabled' }else { $ICAPort = 'Disabled' }

    }
    else {
        $IMA = $MFCOM = $XTE = $Frespace = $Load = $PubAppcount = $ACtSessCount = $lhcMB = $LoadEval = $ICAPort = 'No_Info'
    }

    Write-Host "$Srv`t$ZDC`t$IMA`t$MFCOM`t$XTE`t$FreSpce`t$Load`t$PubAppCount`t$ActSessCount`t$lhcMB`t$ICAport`t$LoadEval"
}