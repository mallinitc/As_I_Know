$Skus = @{Standard_NV6='Standard_NV6h';
      Standard_NV6_Promo='Standard_NV6h';
      Standard_D2s_v3='Standard_D2hs_v3';
      Standard_NV4as_v4='Standard_NV4ahs_v4';
      Standard_D4s_v3='Standard_D4hs_v3';
      Standard_NV12s_v3='Standard_NV12hs_v3'
    }


$Excel = "C:\H_Skus\" + "Output.xlsx"

$AllPools = Import-Excel -Path C:\H_Skus\Book4_VM.xlsx -WorksheetName 'USA'
$CustData = Import-Excel -Path 'C:\H_Skus\AzureCustomers-April2020.xlsx'

$Customers = $AllPools|Select 'Customer Name' -Unique


Foreach($Customer in $Customers.'Customer Name')
{
    $Customer = $Customer.ToString()
    [System.Collections.ArrayList] $Output=@()
    $Custpools = $AllPools |Where-Object {(($_.'Customer Name' -like $Customer) -and ($_.'Pool Type' -like 'Persistent'))}
    If(!($Custpools))
    {
        Continue
    }
    $Subscription = ($CustPools|Select Subscription -First 1).subscription
    $TenantId=($CustData|Where-Object {$_.SubscriptionId -like $Subscription}).TenantId
    Clear-AzContext -Force -Scope CurrentUser
    If(!(Connect-AzAccount -Subscription $Subscription -Tenant $TenantId))
    {
        Continue
    }
    $AllVMs = Get-AzVM
    Foreach($CustPool in $Custpools)
    {
        #VMs that matches Given DesktopName
        foreach($Sku in $Skus.Keys)
        {
            #Find VMs
            $SkusVMs=$AllVMs|Where-Object {($_.HardwareProfile.VmSize -like $Sku) -and ($_.location -notlike 'australiaeast')}

            foreach($Skuvm in $SkusVMs)
            {
                #Find if VM starts with Desktopname
                $SearchString=$CustPool.'Desktop Name'+'*'
                If($Skuvm.Name -like $SearchString)
                {
                    $TargetSku=$Skus[$Sku]
                    #Change the SKU here
                    $obj = New-Object PsObject -Property @{
                    Customer = $Customer
                    VMName = $Skuvm.Name
                    SKU = $Sku
                    TargetSku= $TargetSku
                    Subscription=$Subscription
                    Tenant=$TenantId
                    }
                    $Output.Add($obj) | Out-Null
                }
            }
        }
    }
    $Output | Select-Object Customer,VMName,Sku,TargetSku,Subscription,Tenant| Export-Excel -Path $Excel -Append -WorksheetName $Customer
    
}



