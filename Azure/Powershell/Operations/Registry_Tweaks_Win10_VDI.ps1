#Registry tweaks for Windows10 Best practices in VDI

Import-Module -Name PolicyFileEditor
$MachineDir = "$env:windir\system32\GroupPolicy\Machine\registry.pol"
#$UserDir = "$env:windir\system32\GroupPolicy\User\registry.pol"
Write-Host "All policies before modification"
Get-PolicyFileEntry -Path $MachineDir -All

$MachinePolicy = @()
    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = "EnableFirstLogonAnimation"
        Key = "software\Microsoft\Windows\CurrentVersion\Policies\System"
        Data = "0"
        Type = "DWord"
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = "Enable"
        Key = "software\Policies\Microsoft\PeerDist\Service"
        Data = "0"
        Type = "DWord"
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'Disabled'
        Key = 'software\Policies\Microsoft\Peernet'
        Data = "1"
        Type = "DWord"
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'ActivePowerScheme'
        Key = 'software\Policies\Microsoft\Power\PowerSettings'
        Data = '381b4222-f694-41f0-9685-ff5bb260df2e'
        Type = 'String'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'DisableAntiSpyware'
        Key = 'software\Policies\Microsoft\Windows Defender'
        Data = '0'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'DisableSR'
        Key = 'software\Policies\Microsoft\Windows NT\SystemRestore'
        Data = '1'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'SelectTransport'
        Key = 'software\Policies\Microsoft\Windows NT\Terminal Services'
        Data = '0'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'AutoDownload'
        Key = 'software\Policies\Microsoft\WindowsStore'
        Data = '2'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'DisableStoreApps'
        Key = 'software\Policies\Microsoft\WindowsStore'
        Data = '0'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'RemoveWindowsStore'
        Key = 'software\Policies\Microsoft\WindowsStore'
        Data = '1'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'DisableBranchCache'
        Key = 'software\Policies\Microsoft\Windows\BITS'
        Data = '1'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'DisablePeerCachingClient'
        Key = 'software\Policies\Microsoft\Windows\BITS'
        Data = '1'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'DisablePeerCachingServer'
        Key = 'software\Policies\Microsoft\Windows\BITS'
        Data = '1'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'DisableWindowsConsumerFeatures'
        Key = 'software\Policies\Microsoft\Windows\CloudContent'
        Data = '1'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'Enabled'
        Key = 'software\Policies\Microsoft\Windows\HotspotAuthentication'
        Data = '0'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'AllowCortana'
        Key = 'software\Policies\Microsoft\Windows\Windows Search'
        Data = '0'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'AllowCortanaAboveLock'
        Key = 'software\Policies\Microsoft\Windows\Windows Search'
        Data = '0'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'AllowSearchToUseLocation'
        Key = 'software\Policies\Microsoft\Windows\Windows Search'
        Data = '0'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'ConnectedSearchUseWeb'
        Key = 'software\Policies\Microsoft\Windows\Windows Search'
        Data = '0'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'DisableWebSearch'
        Key = 'software\Policies\Microsoft\Windows\Windows Search'
        Data = '1'
        Type = 'DWord'
    }

    $MachinePolicy += New-Object PsObject -Property @{
        ValueName = 'PreventIndexingOfflineFiles'
        Key = 'software\Policies\Microsoft\Windows\Windows Search'
        Data = '1'
        Type = 'DWord'
    }

    $i=0
    do
    {
        Set-PolicyFileEntry -Path $MachineDir -Key $MachinePolicy[$i].Key -ValueName  $MachinePolicy[$i].ValueName -Data $MachinePolicy[$i].Data -Type $MachinePolicy[$i].Type
        $i++
    }while($MachinePolicy.Count -gt $i)

#Set-PolicyFileEntry -Path $MachineDir-Key $RegPath -ValueName $RegName -Data $RegData -Type $RegType
Write-Host "All policies after modification"
Get-PolicyFileEntry -Path $MachineDir -All