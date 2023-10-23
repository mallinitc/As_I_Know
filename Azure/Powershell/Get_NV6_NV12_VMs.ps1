#This gets the list of all NV6 & NV12 VM details

$Custs=import-csv -Path D:\WSData\AllCloudCustomers-190603.csv|Out-GridView -PassThru
$Dir=$env:USERPROFILE+"\Logs\NV\"
If(!(test-path $Dir))
{
      New-Item -ItemType Directory -Force -Path $Dir
}
$Excel=$Dir+"NV6_NV12_Data.xlsx"
$Obj=@()
ForEach($Ws in $Custs)
{
    If(Connect-AzAccount -Subscription $Ws.SubscriptionId -Tenant $Ws.TenantId)
    {
        $Cus=$Ws.Customer
        $Vms=Get-AzVM |Where-Object { ($_.HardwareProfile.VmSize -eq 'Standard_NV6' -or $_.HardwareProfile.VmSize -eq 'Standard_NV12') }
        ForEach($vm in $vms)
        {
            $Obj+=New-Object PsObject -Property @{
                Customer=$Cus
                ResourceGroup=$Vm.ResourceGroupName
                VMName=$Vm.Name
                Location=$Vm.Location
                SKU=$Vm.HardwareProfile.VmSize
            }
        }
    }
    Else{Write-Error "Couldn't connect. Please try again!."}
}
$Obj|Export-Excel -WorksheetName "NV6_12Data" -Path $Excel -Append
