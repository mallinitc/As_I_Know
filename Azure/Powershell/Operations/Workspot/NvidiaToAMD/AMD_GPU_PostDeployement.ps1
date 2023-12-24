$Hostname = hostname
$Driver = Get-WmiObject Win32_VideoController|?{$_.Name -like 'Radeon Instinct MI25 MxGPU'}

if ( $Driver | Select description,status,driverversion | select-string "Radeon Instinct MI25 MxGPU" | select-string status=OK)
{
    Write-Host "$($Hostname) + Success"
}
else
{
    If($Driver.ConfigManagerErrorCode)
    {
        Write-Host "$($Hostname) + Error + $($Driver.ConfigManagerErrorCode)"
    }
    Else
    {
        Write-Host "$($Hostname) + Error + No driver"
    }

}

$temp=cmd /c 'reg add "HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services" /v fEnableWddmDriver /t REG_DWORD /d 0 /f'
