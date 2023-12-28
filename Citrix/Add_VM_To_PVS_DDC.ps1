#Adding the VM to DDC Catalog & PVS Catalog
#VM is in VMware Vcenter


if ( (Get-PSSnapin -Name citrix.* -ErrorAction SilentlyContinue) -eq $null ) {
    Add-PsSnapin citrix.*
}
if ( (Get-PSSnapin -Name vmware.* -ErrorAction SilentlyContinue) -eq $null ) {
    Add-PsSnapin vmware.*
}
if ( (Get-PSSnapin -Name mclipssnapin -ErrorAction SilentlyContinue) -eq $null ) {
    Add-PsSnapin mclipssnapin
    #C:\Windows\Microsoft.NET\Framework\v4.0.30319\Installutil.exe “C:\Program Files\Citrix\Provisioning Services Console\MCLiPSSnapin.dll”
}
Connect-VIServer sacp1lsvcs900

$catalogName = $Template = "<NAME>"
$DDC1 = "<NAME>"
$hostname = "<NAME>"
$VC = "<NAME>"
$id = "<ID>"

$catalogid = (Get-BrokerCatalog -Name $catalogName -Adminaddress $DDC1 | select Name, Uid).Uid
$hypuid = (Get-BrokerHypervisorConnection -AdminAddress $DDC1).Uid
$hostedMid = (get-vm $hostname -server $VC).ExtensionData.Config.Uuid

New-BrokerMachine -CatalogUid $catalogid -HostedMachineId $hostedMid -HypervisorConnectionUid $hypuid -MachineName $hostname -AdminAddress $DDC1
Add-BrokerUser -Name "DOMAIN\$id" -Machine "VDSI\$hostname" -AdminAddress $DDC1
Add-BrokerMachine -MachineName "DOMAIN\$hostname" -DesktopGroup $catalogname -AdminAddress $DDC1

$PVS1 = "<NAME>"
$pvssite = "<NAME>"

$Mac = (Get-NetworkAdapter $hostname -server $VC).MacAddress
$a = Mcli-Run setupconnection -p server="$PVS1"
$b = Mcli-Add Device -r siteName="$pvsSite", CollectionName="$Template", DeviceName="$Hostname", devicemac="$MAC", copyTemplate=1
$c = Mcli-Run resetDeviceForDomain -p Devicename="$Hostname"

Get-ADComputer $hostname | Move-ADObject -TargetPath "OU=Desktop_D,OU=Desktop Tier,OU=SAC,OU=Cloud,DC=string,DC=string,DC=string,DC=com"

