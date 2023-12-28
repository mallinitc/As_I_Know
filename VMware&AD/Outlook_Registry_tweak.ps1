#Changing Outlook default OST Path

Add-PSSnapin *citrix*
Import-Module ActiveDirectory -ErrorAction silentlyContinue

$computers = gc C:\1.txt
$computers.count
foreach ($comp in $computers) {


    if ($comp -like "TUSCA*") {
        $DDC = 'NAME'
    }
    else {
        $DDC = 'NAME'
    }
    $user = (Get-BrokerDesktop -AdminAddress $DDC -MachineName "NAME\$comp").AssociatedUserNames
    $User = $User.Replace("NAME\", "")
    $user = $user.Trim()

    $id = Get-ADUser $user | select SID
    $SID = $id.SID.Value


    $path = $SID + "\SOFTWARE\Policies\Microsoft\Office\14.0"
    $path1 = $SID + '\SOFTWARE\Policies\Microsoft\Office\14.0\Outlook'
    $path2 = $SID + '\Software\Microsoft\Windows NT\CurrentVersion\Windows Messaging Subsystem\Profiles\'

    Invoke-Command -ComputerName $comp -ScriptBlock { New-PSDrive -PSProvider Registry -Name HKU -Root HKEY_USERS }


    $RegType = [Microsoft.Win32.RegistryHive]::Users 
    $RegKey = [Microsoft.Win32.RegistryKey]::OpenRemoteBaseKey($RegType, $comp)
    $Key = $RegKey.OpenSubKey($path1, $true)
    $Key2 = $RegKey.OpenSubKey($path2, $true)
    if ($key2) {
        $Key3 = $Regkey.DeleteSubKeyTree($path2)

    }

    if ($key) {

        $ValueName = "ForceOSTPath"
        $ValueData = “H:\%username%”
        $Key.SetValue($ValueName, $ValueData, [Microsoft.Win32.RegistryValueKind]::ExpandString)

        #New-ItemProperty -Path $test -Name ForceOSTPath -Value H:\Outlook\%username% -PropertyType ExpandString -Force

    }
    else {

        $key = $RegKey.CreateSubKey("$path\Outlook")
        $RegKey = $Regkey.OpenSubKey($path1, $true)

        $ValueName = "ForceOSTPath"
        $ValueData = “H:\%username%”
        $RegKey.SetValue($ValueName, $ValueData, [Microsoft.Win32.RegistryValueKind]::ExpandString)


        #New-Item -Path $test2 -Name outlook –Force
        #New-ItemProperty -Path $test -Name ForceOSTPath -Value H:\Outlook\%username% -PropertyType ExpandString -Force
    }

}