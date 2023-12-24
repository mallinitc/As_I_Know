#Get all the list of orhpan Public IPs & delete them

$Ws = Import-Csv -Path D:\WSData\AllCloudCustomers-190603.csv|Out-GridView -PassThru
Clear-AzContext -Scope CurrentUser -Force
Connect-AzAccount -Subscription $Ws.SubscriptionId -Tenant $Ws.TenantId

$Cus = $Ws.Customer
$Dir = $env:USERPROFILE+"\Logs\PublicIPs\$cus\"
If(!(Test-Path $Dir))
{
      New-Item -ItemType Directory -Force -Path $Dir
}
$Act = $Dir+"PublicIPs.txt"
$Csv = $Dir+"PublicIPs.csv"

"==============================================================================">> $Act
"Started :: "+(Get-Date) >> $Act
$PIPs = Get-AzPublicIpAddress
$Out = @()
$Count = 0
ForEach($Pip in $PIPs)
{
    If($Pip.IpConfiguration)
    {
        $Nic = (Get-AzPublicIpAddress -Name $Pip.name).IpConfiguration.Id.Split("/")[8]
        If(Get-AzNetworkInterface -Name $Nic|Where-Object {$_.VirtualMachine -eq $null})
        {
            "NIC:  $Nic   IP: $($Pip.name)">>$Act
            $Count++
            $Out += New-Object PsObject -Property @{
                NIC = $nic
                IP = $Pip.name              
            }
        }
    }
    Else
    {
        "No NIC  IP: $($Pip.name)">>$Act
        $Count++
        $Out += New-Object PsObject -Property @{
            NIC = "NA"
            IP = $Pip.name           
        }
    }
}
$Count
"Total COUNT::  $Count">>$Act

$Out|Export-Csv $Csv -Append -NoTypeInformation
