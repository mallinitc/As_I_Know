#Create a VM in XenServer
#Add it to PVS & DDC Citrix Catalog


Param(
    
    [parameter(Mandatory = $true)]
    $TemplateName,
    [parameter(Mandatory = $true )]
    $hostname,
    [parameter(Mandatory = $true )]
    $imagetype,
    [parameter(Mandatory = $true )]
    $xc,
    [parameter(Mandatory = $true )]
    $pvs1,
    [parameter(Mandatory = $true )]
    $pvssite,
    [parameter(Mandatory = $true )]
    $DC
)


Add-PSSnapin *citrix*, *pvs*, *xen*, *mcli* -ErrorAction silentlyContinue
Import-Module ActiveDirectory -ErrorAction silentlyContinue

$XC = ""

$xenserver = Connect-XenServer -Server "$xc" -UserName "root" -Password "PASS" -SetDefaultSession

$pvsSite = 'SDC'

if ($imagetype -eq 'streamed') {
    $templateUuid = "NAME"
    $PVScollection = "NAME"
    $diskLocatorID = "NAME"
}
if ($imagetype -eq 'pvd') {

    $templateUuid = "NAME"
    $PVScollection = "NAME"
    $collectionid = "NAME"
    $diskLocatorID = "NAME"
}

Invoke-XenVM -Uuid "$templateUuid" -XenAction Clone -NewName "$hostname" -Async -PassThru | Wait-XenTask -ShowProgress
$MACHINE = Get-XenVM | where { $_.name_label -eq "$hostname" }
#$sr = Get-XenSR -Name "Local Storage"


Invoke-XenVM -VM $MACHINE -XenAction Provision
$VMVifs = (get-xenvm | where { $_.name_label -eq "$hostname" } | select *).Vifs
$oparef = $VMVifs | select * -ExpandProperty opaque_ref
$Mac = (Get-XenVIF | Where-Object { $_.opaque_ref -eq $oparef }).mac


#PVS

$a = Mcli-Run setupconnection -p server="$pvs1"



$siteid = "NAME"

#LocalStorage of NAME: NAME (based on Tags)
$SRLocal1UId = "NAME"
 
#$Site="SDC"

if ($imagetype -eq "pvd") {

    # RECHECK
    New-XenVDI -NameLabel $hostname -VirtualSize 6GB -SR $(Get-XenSR -Uuid $SRLocal1UId)
    New-XenVBD -VM $(Get-XenVM -Name $hostname) -VDI $(Get-XenVDI -Name $hostname) -Mode RW -Type Disk -Userdevice "0"

    Mcli-Add DeviceWithPersonalvDisk -r devicename="$Hostname", collectionName="$PVScollection", pvdDriveLetter=p, deviceMac="$MAC", siteId="$siteid", diskLocatorID="$diskLocatorID"
    $c = Mcli-Run resetDeviceForDomain -p Devicename="$Hostname"

}
else {
    #Read-Only VMs
    Mcli-Add Device -r siteName="$pvssite", CollectionName="$PVScollection", DeviceName="$hostname", devicemac="$MAC", siteId="$siteid", copyTemplate=1
    #diskLocatorID="$diskLocatorID"

    Mcli-Run resetDeviceForDomain -p Devicename="$hostname"

}

#Get-XenSession | Disconnect-XenServer  -ErrorAction SilentlyContinue

Mcli-Add Device -r siteName="SDC", CollectionName="$PVScollection", DeviceName="$hostname", devicemac="$MAC", siteId="$siteid", copyTemplate=1

#Mcli-Add Device -r siteName="SDC",CollectionName="Win7_VMs",DeviceName="NAME",devicemac="NAME",siteId="NAME"
