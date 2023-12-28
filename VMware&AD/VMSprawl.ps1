#VMSprawl

#VMs that are present in ESXi servers but not part of DDC/PVS Catalogs & Vice-versa

asnp *citrix*
asnp vmware.* -ErrorAction SilentlyContinue
Connect-VIServer NAME, NAME -Force
Add-PSSnapin mclipssnapin

#Reading all hosts in VC and testing if it exists in PVS and DDC.

$hostnames = @()
$hostnames = (get-vm *).Name
foreach ($hostname in $hostnames) {
    $hostname = $hostname.Trim()
    if (($hostname -like 'TUSCA*') -or ($hostname -like 'VCA*')) {
        $DDC = 'NAME'
        $PVS = 'NAME'
    }
    else {
        $DDC = 'NAME'
        $PVS = 'NAME'
    }
    $tmp = Mcli-Run setupconnection -p server="$PVS"
    #if(!((mcli-get device -p devicename="$hostname" -ErrorAction SilentlyContinue) -or (Get-BrokerMachine -MachineName "VDSI\$hostname" -AdminAddress $DDC)))
    if (!(Get-BrokerMachine -MachineName "NAME\$hostname" -AdminAddress $DDC)) {
        $image = (Get-VM $hostname).Folder.Name
        "`t$hostname`t`t$image" >>C:\VC_result.txt
    }
}



#Reading all hosts in DDC and testing if it exists in PVS and VC.
$hostnames = @()
$DDCHosts = (Get-BrokerDesktop * -AdminAddress NAME -MaxRecordCount 5000 -CatalogName SAC_Aara).MachineName
$DDCHosts += (Get-BrokerDesktop * -AdminAddress NAME -MaxRecordCount 5000).MachineName
$hostnames = $DDCHosts.Replace("NAME\", "")
foreach ($hostname in $hostnames) {
    $hostname = $hostname.Trim()
    if ($hostname -match "TUSCA*") {
        $DDC = 'NAME'
        $PVS = 'NAME'
    }
    else {
        $DDC = 'NAME'
        $PVS = 'NAME'
    }
    $tmp = Mcli-Run setupconnection -p server="$PVS"
    if (!((mcli-get device -p devicename="$hostname" -ErrorAction SilentlyContinue) -or (Get-VM $hostname -ErrorAction SilentlyContinue))) {
        $image = (Get-BrokerMachine -MachineName "VDSI\$hostname" -AdminAddress $DDC).CatalogName
        Write-Host "`t$hostname`t`t$image">>C:\DDC_result.txt
    }
}

#Reading all hosts in PVS and testing if it exists in VC and DDC.

$hostnames = @()

$a = Mcli-Run setupconnection -p server="NAME"
$VMs = Mcli-Get device -f devicename

$b = Mcli-Run setupconnection -p server="NAME"
$VMs += Mcli-Get device -f devicename

for ($i = 4; $i = $i + 3) {
    $Sub = $SAC_VMs[$i]
    if ($Sub -eq $null) { break }
    $VM = $Sub.Replace("deviceName:", "")
    $VM = $VM.Trim()
    if (($VM -match "TUSCA*") -or ($VM -match "TUSF*"))
    { $hostnames += $VM }
}
foreach ($hostname in $hostnames) {
    $hostname = $hostname.Trim()
    if ($hostname -match "TUSCA*") { $DDC = 'NAME' }else { $DDC = 'NAME' }
    if (!((Get-BrokerMachine -MachineName "NAME\$hostname" -AdminAddress $DDC) -or (Get-VM $hostname -ErrorAction SilentlyContinue))) {
        $image = (Get-BrokerMachine -MachineName "NAME\$hostname" -AdminAddress $DDC).CatalogName
        Write-Host "`t$hostname`t`t$image">>C:\PVS_result.txt
    }
}


#After Warning Alerts && Deleting the VMs
$hostnames = gc c:\SAC.txt
foreach ($hostname in $hostnames) {

    Stop-VM $hostname -Confirm:$false
    start-sleep -s 30

    $image = (Get-BrokerDesktop  -AdminAddress $DDC -MachineName "NAME\$hostname").CatalogName
    Set-BrokerPrivateDesktop -MachineName "NAME\$hostname" -InMaintenanceMode $true -AdminAddress $DDC
    if ((Get-BrokerDesktop -HostedMachineName $hostname -AdminAddress $DDC).PowerState -eq "ON")
    { $a = Stop-VM $hostname -server $VC -Confirm:$false }
    #start-sleep -s 30
    Remove-BrokerMachine -MachineName "NAME\$hostname" -DesktopGroup $image -AdminAddress $DDC
    Remove-BrokerMachine -MachineName "NAME\$hostname" -Force -AdminAddress $DDC
    Mcli-Run setupconnection -p server="$PVS"
    Mcli-Run MarkDown -p DeviceName="$Hostname"
    Start-Sleep -s 10
    Mcli-Delete Device -p DeviceName="$Hostname"
    Remove-VM $hostname -DeletePermanently -confirm:$false
    Move-VM $hostname -Destination $Des
}