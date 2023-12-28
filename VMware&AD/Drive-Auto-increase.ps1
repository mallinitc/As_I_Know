#VM Disk Expansion
#VMWare VM - Citrix DDC


asnp *vmware*
asnp *citrix*
$VMName = Read-Host 'VM Hostname ?'
if (($VMName -like "TUSCA*") -or ($VMName -like "VCA*")) {
    $vc = "NAME"
    $ddc = "NAME"
}
else {
    $vc = "NAME"
    $ddc = "NAME"
}


Connect-VIServer $vc -User DOMAIN\ID -Password PASSWORD
$currentsize = (Get-HardDisk -VM $VMName).CapacityGB
Write-Host "The Current Capacity $currentsize"

$DeviceIDs = (Get-WmiObject win32_LogicalDisk -ComputerName $VMName | ? { $_.Caption -match "C" -or $_.Caption -match "P" }).DeviceID
$imageName = (Get-BrokerDesktop -HostedMachineName $VMName -AdminAddress $ddc).CatalogName

$deviceID = Read-Host 'Enter Drive Letter'
$deviceID1 = $deviceID + ":"

$NewSizeGB = Read-Host 'Enter New C drive Space'

 
Get-HardDisk -VM $VMName | ? { $_.Name -eq "Hard disk 1" } | Set-HardDisk -CapacityGB $NewSizeGB -Confirm:$false


 
disconnect-viserver -Server $vc -Confirm:$false

if ($deviceID -eq "C") {
    Invoke-Command -ComputerName $VMName -ScriptBlock { "rescan", "select volume C", "extend" | diskpart }
}
else {
    Invoke-Command -ComputerName $VMName -ScriptBlock { "rescan", "select volume P", "extend" | diskpart }
}

