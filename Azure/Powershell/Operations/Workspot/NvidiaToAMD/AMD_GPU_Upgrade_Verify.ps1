$Hostname = hostname

if (Get-WmiObject Win32_VideoController | Select description,status,driverversion | select-string "Radeon Instinct MI25 MxGPU" | select-string status=OK)
{
    $Ver=(Get-WmiObject Win32_VideoController | Select description,status,driverversion | ?{$_.description -like  "Radeon Instinct MI25 MxGPU"}).driverversion
    Write-Host "$($Hostname) +  $($ver)"
}
else
{
    #Write-Host "'$Hostname' + Radeon Instinct MI25 MxGPU not loaded"
    Write-Host "$($Hostname) + Failed"
}