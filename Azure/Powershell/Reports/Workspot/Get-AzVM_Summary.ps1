$Ws = Import-Excel -Path C:\H_Skus\AzureCustomers-April2020.xlsx -WorksheetName 'USA CSP'|Out-GridView -PassThru
$Excel = "C:\H_Skus\Output.xlsx"
ForEach($Cust in $Ws)
{
    $Name=$Cust.Customer
    Clear-AzContext -Scope CurrentUser -Force
    Connect-AzAccount -Subscription $Cust.SubscriptionId -Tenant $Cust.TenantId
    $AllVms = Get-AzVM
    [System.Collections.ArrayList] $MainObj = @()
    ForEach ($Vm in $AllVms)
    {
        $Size=($Vm|select -ExpandProperty  HardwareProfile).VmSize
        #$OS=($Vm|select -ExpandProperty  OSProfile).OsType
        $obj = New-Object PsObject -Property @{
        Customer = $Cust.Customer
        VMName = $Vm.Name
        RGName = $vm.ResourceGroupName
        SKU = $Size
        Location = $vm.Location
        OSType = $vm.LicenseType
        }
        $MainObj.Add($obj) | Out-Null

    }
    $MainObj|Select-Object Customer,VMName,RGName,SKU,Location,OSType | Export-Excel -WorksheetName $Name -Path $Excel -Append
    
}