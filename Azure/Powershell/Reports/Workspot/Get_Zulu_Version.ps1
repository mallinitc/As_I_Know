#$Prod = Get-WmiObject -Class Win32_Product -Filter "Name like 'Azul%'"

$InstalledSoftware = Get-ChildItem "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall"

#foreach($obj in $InstalledSoftware){write-host $obj.GetValue('DisplayName') -NoNewline; write-host " - " -NoNewline; write-host $obj.GetValue('DisplayVersion')}

$Prod = $InstalledSoftware|?{$_.GetValue('DisplayName') -like '*Zulu*'}


If($prod)
{
    Write-Output $Prod.GetValue('DisplayVersion')
}
else
{
    Write-Output "NA"
}
