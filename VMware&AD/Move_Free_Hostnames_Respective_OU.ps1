#Import-Module activedirectory -ErrorAction SilentlyContinue

Param(
    [parameter(Mandatory = $true , Helpmessage = "SAC/TPA" )]
    $SiteName
)


if ($SiteName -eq "SAC") {
    $VC = "NAME"
}
else {
    $VC = "NAME"
    $SiteName = "NAME"
}  

$strm_OU = "OU=Desktop,OU=Desktop Tier,OU=$SiteName,OU=NAME,DC=NAME,DC=ent,DC=NAME,DC=com"

$strmD_OU = "OU=Desktop_D,OU=Desktop Tier,OU=$SiteName,OU=NAME,DC=NAME,DC=ent,DC=NAME,DC=com"

$wvm_OU = "OU=Dedicated VD,OU=$SiteName,OU=NAME,DC=NAME,DC=ent,DC=NAME,DC=com"

$pvd_OU = "OU=PvD,OU=$SiteName,OU=NAME,DC=NAME,DC=NAME,DC=NAME,DC=com"

$strm_hsts = Get-ADComputer -SearchBase $strm_OU -SearchScope 1 -filter "Name -like 'TUS*'" | select Name
$Strm_hsts.count
$strmD_hsts = Get-ADComputer -SearchBase $strmD_OU -SearchScope 1 -filter "Name -like 'TUS*'" | select Name
$strmD_hsts.Count
$wvm_hsts = Get-ADComputer -SearchBase $wvm_OU -SearchScope 1 -filter "Name -like 'TUS*'" | select Name
$wvm_hsts.count
$pvd_hsts = Get-ADComputer -SearchBase $pvd_OU -SearchScope 1 -filter "Name -like 'TUS*'" | select Name
$pvd_hsts.count

$VMS = get-vm -server $VC | where { $_.Name -like "TUS*" } | ForEach-Object { $_ -replace ' ' }

$count = 0
$Frehsts = gc c:\list.txt
foreach ($hst in $Frehsts) {
    $hst = $hst.Trim()
    $valid = $true
    $count++
    if (($hst -like "TUSCA*") -and ($SiteName -ne "SAC")) {
        Write-host "Site Name TPA and Hostname $hst is mismatched. So this host is not moved to dCloud OU"
        $valid = $false
    }
    if (($hst -like "TUSFL*") -and ($SiteName -ne "Tampa")) {
        Write-host "Site Name SAC and Hostname $hst is mismatched. So this host is not moved to dCloud OU"
        $valid = $false
    }

    if ($count -le 50 -and $valid) {
        Get-ADComputer $hst | Move-ADObject -TargetPath $strm_OU
    }
    elseif ($count -le 200 -and $valid) {
        Get-ADComputer $hst | Move-ADObject -TargetPath $strmD_OU
    }
    elseif ($count -le 400 -and $valid) {
        Get-ADComputer $hst | Move-ADObject -TargetPath $PvD_OU
    }
    else {
        Get-ADComputer $hst | Move-ADObject -TargetPath $wvm_OU
    }
}
