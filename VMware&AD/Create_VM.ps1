#Create a VM in VMWare VMware ESXi server
#Add VM to Citrix - DDC & PVS Catalogs


Param(
    [parameter(Mandatory = $true , Helpmessage = "SAC/TPA" )]
    $SiteName,
    [parameter(Mandatory = $true)]
    $TemplateName,
    [parameter(Mandatory = $true )]
    $hostname,
    [parameter(Mandatory = $true )]
    $imagetype,
    [parameter(Mandatory = $true )]
    $collectionid,
    [parameter(Mandatory = $true )]
    $diskLocatorID
)
   
  
if ($SiteName -eq "SAC") {
    $VC = "<NAME>"
    $PVS = "<NAME>"
    $Site = "<NAME>"
    $DC = "<NAME>"
    $xdsiteid = "<NAME>"
}
else {
    $VC = "<NAME>"
    $PVS = "<NAME>"
    $Site = "<NAME>"
    $DC = "<NAME>"
    $xdsiteid = "<NAME>"
}

if ($imagetype -eq "Streamed") {
    $cluster = "VDI Desktop VM - 1", "VDI Desktop VM - 2"
    $esx = (Get-DataCenter $DC | Get-Cluster -Name $cluster |  Get-VMHost -server $VC | ? { $_.ConnectionState -eq "Connected" -and ($_ | get-view).OverallStatus -eq "Green" } | Select Name, @{N = "TotalCPU"; E = { ($_ | get-vm | select Name, NumCpu | Measure NumCpu -sum).sum } } | ? { $_.TotalCPU -lt 70 } | sort TotalCPU | select -First 1).Name
}
elseif ($imagetype -eq "StreamedD") {
    $cluster = "VDI Desktop VM - 4", "VDI Desktop VM - 3"
    $esx = (Get-DataCenter $DC | Get-Cluster -Name $cluster |  Get-VMHost -server $VC | ? { $_.ConnectionState -eq "Connected" -and ($_ | get-view).OverallStatus -eq "Green" } | Select Name, @{N = "TotalCPU"; E = { ($_ | get-vm | select Name, NumCpu | Measure NumCpu -sum).sum } } | ? { $_.TotalCPU -lt 70 } | sort TotalCPU | select -First 1).Name
}
elseif ($imagetype -eq "PvD") {
    $cluster = "VDI Desktop VM - 5"
    $esx = (Get-DataCenter $DC | Get-Cluster -Name $cluster |  Get-VMHost -server $VC | ? { $_.ConnectionState -eq "Connected" -and ($_ | get-view).OverallStatus -eq "Green" } | Select Name, @{N = "TotalCPU"; E = { ($_ | get-vm | select Name, NumCpu | Measure NumCpu -sum).sum } } | ? { $_.TotalCPU -lt 70 } | sort TotalCPU | select -First 1).Name
}
else {
    $cluster = "VDI Desktop VM - 5", "VDI Desktop VM - 3"
    $esx = (Get-DataCenter $DC | Get-Cluster -Name $cluster |  Get-VMHost -server $VC | ? { $_.ConnectionState -eq "Connected" -and ($_ | get-view).OverallStatus -eq "Green" } | Select Name, @{N = "TotalCPU"; E = { ($_ | get-vm | select Name, NumCpu | Measure NumCpu -sum).sum } } | ? { $_.TotalCPU -lt 70 } | sort TotalCPU | select -First 1).Name
}

$datastore = (Get-VMHost $esx -server $VC | get-Datastore | ? { $_.Name -notMatch "local" -and $_.FreeSpaceMB -gt 102400 } | Sort-Object -Descending -Property FreeSpaceMB | Select-Object -Property Name, FreeSpaceMB -First 1).Name

$loc = $TemplateName + "_vms"
write-host $esx
write-host $datastore

if ($esx -match "verizon" -and $Datastore -ne $null) {
    $date = get-date
    if ($TemplateName -notmatch "Existing") {
        #write-host "$sitename $esx $datastore $templatename $loc $hostname"
        write-host "$hostname"
        $j = New-VM -Name $hostname -VMHost $esx -Datastore $datastore -Template $TemplateName -Location $loc -Server $VC

        $k = Get-VM $hostname | Get-VMResourceConfiguration | Set-VMResourceConfiguration -MemLimitMB $null

        if (get-vm $hostname -ErrorAction SilentlyContinue) { AC C:\Logs\AutoProvision\$id.txt -Value "VM Creation is in Process   - $sitename  -  $TemplateName  -  $hostname  -  $date" }
        else { exit }

        $Mac = (Get-NetworkAdapter $hostname -server $VC).MacAddress

        $a = Mcli-Run setupconnection -p server="$PVS"

        $e = Mcli-Run MarkDown -p DeviceName=$Hostname -ErrorAction SilentlyContinue
        $del = Mcli-Delete Device -p DeviceName=$hostname -ErrorAction SilentlyContinue
        if ($imagetype -eq "PvD") {
            if ($a -ne $null) {
                #PVD Image Adding to PVS
                New-HardDisk -vm $hostname -CapacityGB 25 -Datastore $datastore -StorageFormat Thin
                Mcli-Add DeviceWithPersonalvDisk -r devicename="$Hostname", collectionid="$collectionid", collectionName="$TemplateName", xdsiteId="$xdsiteid", pvdDriveLetter=x, diskLocatorID="$diskLocatorID", deviceMac="$MAC"
                $c = Mcli-Run resetDeviceForDomain -p Devicename="$Hostname"
            }
            else { AC C:\Logs\AutoProvision\$id.txt -Value "PVD drive create Failed check the VM status" }
        }
        else {
            #Streamed and $StreamedD VM adding to PVS
            $b = Mcli-Add Device -r siteName="$Site", CollectionName="$TemplateName", DeviceName="$Hostname", devicemac="$MAC", copyTemplate=1
            $c = Mcli-Run resetDeviceForDomain -p Devicename="$Hostname"
        }
        if (mcli-get device -p devicename="$hostname" -ErrorAction SilentlyContinue) { $true }
        else { AC C:\Logs\AutoProvision\$id.txt -Value "VM Created in VC but not in Pvs   - $sitename  -  $TemplateName  -  $hostname  -  $date" }
    } 
    else {
        #Writable VM
        $x = New-VM -Name $hostname -server $VC -VMHost $esx -Datastore $datastore -Template $TemplateName -OsCustomizationspec "windows7" -Location $loc
        if (get-vm $hostname -ErrorAction SilentlyContinue) { AC C:\Logs\AutoProvision\$id.txt -Value "VM Creation is in Process   - $sitename  -  $TemplateName  -  $hostname  -  $date" }
        else { exit }

        $k = Get-VM $hostname -server $VC | Get-VMResourceConfiguration | Set-VMResourceConfiguration -MemLimitMB $null
        $g = Start-VM $hostname -Server $VC
    }

}

else {
    AC C:\Logs\ProvisionErrorLog.txt -Value "Not enough resource to create $imagetype Machines - $(get-date)"
    Send-mailMessage -To "EMAIL" -From "EMAIL" -smtpserver "smtp.verizon.com" -Subject "No Free Resource available in $cluster to create Machines through AutoProvision Tool"
    exit
}
