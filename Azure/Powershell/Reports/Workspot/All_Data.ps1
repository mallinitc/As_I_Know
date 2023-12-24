#Azure Inventory Script

Connect-AzAccount -Subscription $Cust.SubscriptionId -Tenant $Cust.TenantId
$Dir = "C:\H_Skus\"
If(!(Test-Path $Dir))
{
     New-Item -ItemType Directory -Force -Path $Dir
}
$Excel = $Dir + "AllData.xlsx"

#$Ws = Import-Csv -Path C:\AzCustList_Feb16_21\AzureCSP-USA_Customer_List.csv|Out-GridView -PassThru
$Ws = Import-Csv -Path C:\AzCustList_Feb16_21\AzureCSP-UK_CUstomer_List.csv|Out-GridView -PassThru

ForEach($Cust in $Ws)
{
       
    Clear-AzContext -Scope CurrentUser -Force
    If(!(Connect-AzAccount -Subscription $Cust.SubscriptionId -Tenant $Cust.TenantId))
    {
        $obj = New-Object PsObject -Property @{
              Customer = $Cust.Customer
              Name = $Cust.SubscriptionName
              SubscriptionId = $Cust.SubscriptionId
              TenantId = $Cust.TenantId
             }
        $obj | Select-Object Customer,Name,SubscriptionId,TenantId | Export-Excel -WorksheetName "FailedConnections" -Path $Excel -Append

        Continue
    }


    #Successful connections
    [System.Collections.ArrayList] $Connectionsobj = @()
    $AllCs = Get-AzSubscription
    ForEach ($OneC in $AllCs)
    {
       $obj = New-Object PsObject -Property @{
              Customer = $Cust.Customer
              Name = $OneC.Name
              SubscriptionId = $OneC.Id
              TenantId = $OneC.TenantId
              State = $OneC.State
            }
       $Connectionsobj.Add($obj) | Out-Null
        
    }
    If($Connectionsobj.count)
    {
        $Connectionsobj | Select-Object Customer,Name,SubscriptionId,TenantId,State | Export-Excel -WorksheetName "Connections" -Path $Excel -Append
    }

    #Get all orphaned RG
    [System.Collections.ArrayList] $RGobj = @()
    $AllRGs = Get-AzResourceGroup
    ForEach ($RG in $AllRGs)
    {
        If(!(Get-AzResource -ResourceGroupName $RG.ResourceGroupName))
        {
            $obj = New-Object PsObject -Property @{
                Customer = $Cust.Customer
                Name = $RG.ResourceGroupName
                Location = $RG.Location
                State = $RG.ProvisioningState
            }
            $RGobj.Add($obj) | Out-Null
        }
    }
    If($RGobj.count)
    {
        $RGobj | Select-Object Customer,Name,Location,State | Export-Excel -WorksheetName "OrphanRGs" -Path $Excel -Append
    }
    
    #All ResourceGroups
    [System.Collections.ArrayList] $RGobj = @()
    ForEach ($RG in $AllRGs)
    {
        
            $obj = New-Object PsObject -Property @{
                Customer = $Cust.Customer
                Name = $RG.ResourceGroupName
                Location = $RG.Location
                State = $RG.ProvisioningState
            }
            $RGobj.Add($obj) | Out-Null
    }
    $RGobj | Select-Object Customer,Name,Location,State | Export-Excel -WorksheetName "ResourceGroups" -Path $Excel -Append
    
    #Disks
    $ManagedDisks = Get-AzDisk | Where-Object {$_.DiskState -like 'Unattached'}
    [System.Collections.ArrayList] $Diskobj = @()
    If(($ManagedDisks))
    {
    $Count = $ManagedDisks
    ForEach ($Md in $Count) {
        If( $null -eq $Md.ManagedBy )
        {
                "Deleting unattached Managed Disk with Id: $($Md.Name)" 
                $md | Remove-AzDisk -Force -AsJob
                "Deleted unattached Managed Disk with Id: $($Md.Name) " 
                $When = Get-Date
                $obj = New-Object Psobject -Property  @{
                    Customer = $Cust.Customer
                    DiskName = $Md.name
                    DiskType = $Md.Sku.Name
                    DiskSize = $Md.DiskSizeGB
                    ResourceGroup = $Md.ResourceGroupName
                    Location = $Md.Location
                    Date = $When
                }
                $Diskobj.Add($obj) | Out-Null
        }
    }

    }
   
    If($DiskObj.count)
    {
        $Diskobj | Select-Object Customer,DiskName,DiskType,DiskSize,ResourceGroup,Location,Date | Export-Excel -WorksheetName "OrphanDisks" -Path $Excel -Append
    }
    
    [System.Collections.ArrayList] $SAobj = @()
    $StorageAccounts = Get-AzStorageAccount
    ForEach($StorageAccount in $StorageAccounts){
        $CurrentSAID = (Get-AzStorageAccount -ResourceGroupName $StorageAccount.ResourceGroupName -AccountName $StorageAccount.StorageAccountName).Id
        $usedCapacity = (Get-AzMetric -ResourceId $CurrentSAID -MetricName "UsedCapacity").Data
        $usedCapacityInMB = [math]::Round(($usedCapacity.Average / 1MB),2)
        $obj = New-Object Psobject -Property  @{
                    Customer = $Cust.Customer
                    StorageAccount = $StorageAccount.StorageAccountName
                    ResourceGroup = $StorageAccount.ResourceGroupName
                    Location = $StorageAccount.Location
                    Kind = $StorageAccount.Kind
                    CapacityinMB = $usedCapacityInMB
                }
                $SAobj.Add($obj) | Out-Null
       
    }
    If($SAObj.count)
    {
        $SAobj|Select-Object Customer,StorageAccount,ResourceGroup,Location,Kind,CapacityinMB | Export-Excel -WorksheetName "StorageAccount" -Path $Excel -Append
    }

    #Nics
    $AllNics = Get-AzNetworkInterface
    $Onics = $AllNics | where-object { $_.VirtualMachine -eq $null }
    $Onics.count
    [System.Collections.ArrayList] $Nicobj = @()
    If(($Onics))
    {
        $Count = $Onics|Select-Object name,ResourceGroupName,Location,IPconfigurations
        ForEach($One in $Count)
        {
            $Vnet = $One.Ipconfigurations.Subnet.Id
            $Vnet = $Vnet.split("/")[8]
            $Pip = $one.Ipconfigurations.PrivateIpAddress
            $When = Get-Date
            $obj = New-Object Psobject -Property  @{
                Customer = $Cust.Customer
                Name = $One.Name
                VirtualNetwork = $Vnet
                PrimPrivIP = $Pip
                ResourceGroup = $one.ResourceGroupName
                Location = $One.Location
                Date = $When
            }
            $One| Remove-AzNetworkInterface -Force
            $Nicobj.Add($obj) | Out-Null
        }

    }
   
    If($NicObj.count)
    {
        $Nicobj | Select-Object Customer,Name,VirtualNetwork,PrimPrivIP,ResourceGroup,Location,Date | Export-Excel -WorksheetName "OrphanNICs" -Path $Excel -Append
    }
    
    #App Registrations
    [System.Collections.ArrayList] $Output = @()
    $Apps = Get-AzADApplication|Select-Object DisplayName, ObjectId, ApplicationId
    ForEach($App in $Apps)
    {
        $Temp = Get-AzADAppCredential -ObjectId $App.ObjectId
        $Obj = New-Object PsObject -Property @{
        Customer = $Cust.Customer
        Name = $App.DisplayName
        ApplicationId = $App.ApplicationId
        KeyId = $Temp.KeyId
        Start = $Temp.StartDate
        End = $Temp.EndDate
        }
        $Output.Add($obj) | Out-Null
    }
    If($Output.Count)
    {
        $Output | Select-Object Customer,ApplicationId,KeyId,Name,Start,End | Export-Excel -WorksheetName "AppData" -Path $Excel -Append
    }
    #Automation Accounts
    [System.Collections.ArrayList] $Output = @()
    $Accs = Get-AzAutomationAccount
    ForEach($Acc in $Accs)
    {
        $Obj = New-Object PsObject -Property @{
        Customer = $Cust.Customer
        Name = $Acc.AutomationAccountName
        ResourceGroup = $Acc.ResourceGroupName
        Location = $Acc.Location
        Created = $Acc.CreationTime
        }
        $Output.Add($obj) | Out-Null
    }
    If($Output.Count)
    {
        $Output | Select-Object Customer,Name,ResourceGroup,Location,Created | Export-Excel -WorksheetName "Automation" -Path $Excel -Append
    }
    #RunBooks
    ForEach($Acc in $Accs)
    {
        $AllRBooks = Get-AzAutomationRunbook -ResourceGroupName $Acc.ResourceGroupName -AutomationAccountName $Acc.AutomationAccountName
        [System.Collections.ArrayList] $Output = @()
        ForEach($Rbook in $AllRBooks)
        {
            $Obj = New-Object PsObject -Property @{
            Customer = $Cust.Customer
            AAName = $Acc.AutomationAccountName
            ResourceGroup = $Acc.ResourceGroupName
            Name = $Rbook.Name
            RunbookType = $Rbook.RunbookType
            Jobcount = $Rbook.JobCount
            State = $Rbook.State
            Location = $Rbook.Location
            }
            $Output.Add($obj) | Out-Null
        }
        $Output | Select-Object Customer,AAName,Name,ResourceGroup,RunbookType,Jobcount,State,Location | Export-Excel -WorksheetName "RunBooks" -Path $Excel -Append
    }
    #NV6_NV12 VMS
    [System.Collections.ArrayList] $Output = @()
    $AllVms = Get-AzVM
    $Vms = $AllVms | Where-Object { ($_.HardwareProfile.VmSize -eq 'Standard_NV6' -or $_.HardwareProfile.VmSize -eq 'Standard_NV12') }
    ForEach($Vm in $Vms)
    {
        $Obj = New-Object PsObject -Property @{
        Customer = $Cust.Customer
        ResourceGroup = $Vm.ResourceGroupName
        VMName = $Vm.Name
        Location = $Vm.Location
        SKU = $Vm.HardwareProfile.VmSize
        }
        $Output.Add($obj) | Out-Null
    }
    If($Output.Count)
    {
        $Output | Select-Object Customer,ResourceGroup,VMName,Location,SKU | Export-Excel -WorksheetName "NV6_NV12_Data" -Path $Excel -Append
    }
    #Snapshots
    [System.Collections.ArrayList] $Output = @()
    $Snapshots = Get-AzSnapshot
    ForEach($Snapshot in $Snapshots)
    {
        $Obj = New-Object PsObject -Property @{
        Customer = $Cust.Customer
        ResourceGroup = $Snapshot.ResourceGroupName
        Name = $Snapshot.Name
        Location = $Snapshot.Location
        SKU = $Snapshot.Sku.Name
        TimeCreated = $Snapshot.TimeCreated
        DiskSizeGB = $Snapshot.DiskSizeGB
        Type = $Snapshot.OSType
        State = $Snapshot.ProvisioningState
        }
        $Output.Add($obj) | Out-Null
    }
    If($Output.Count)
    {
        $Output | Select-Object Customer,ResourceGroup,Name,Location,SKU,TimeCreated,DiskSizeGB,Type,State | Export-Excel -WorksheetName "Snapshots" -Path $Excel -Append
    }

    #LoadBalancers
    [System.Collections.ArrayList] $Output = @()
    $AllPips = Get-AzPublicIpAddress
    $Lbs = Get-AzLoadBalancer
    ForEach($Lb in $Lbs)
    {
        $VmIds = $Lb.BackendAddressPools.BackendIpConfigurations.Id
        $Vms = @()
        foreach($VmId in $VmIds)
        {
            $VMNicName = $VmId.Split("/")[8]
            $VId = ($AllNics | Where-Object {$_.Name -like $VMNicName}).VirtualMachine.Id
            $VMName = $VId.Split("/")[8]
            $Vms += $VMName -join "`r`n"
        }
        $Vms = $Vms -join ","
        $LbPiP = $Lb.FrontendIpConfigurations.PublicIpaddress.Id
        $LbpipName = $LbPip.split("/")[8]
        $LbPublicIp = ($AllPips | Where-Object {$_.Name -like $LbpipName}).IpAddress
        $Obj = New-Object PsObject -Property @{
        Customer = $Cust.Customer
        ResourceGroup = $Lb.ResourceGroupName
        Name = $Lb.Name
        Location = $Lb.Location
        SKU = $Lb.Sku.Name
        Type = $Lb.Type
        State = $Lb.ProvisioningState
        PublicIpAddress = $LbPublicIp
        LBVms = $Vms
        }
        $Output.Add($obj) | Out-Null

    }
    If($Output.Count)
    {
        $Output | Select-Object Customer,ResourceGroup,Name,Location,SKU,Type,State,PublicIpAddress,LBVms | Export-Excel -WorksheetName "LoadBalancers" -Path $Excel -Append
    }

    #VPN Gateway 
    [System.Collections.ArrayList] $Output = @()
    ForEach($Rg in $AllRGs)
    {
        $Vpns = Get-AzVirtualNetworkGateway -ResourceGroupName $Rg.ResourceGroupName
        ForEach($Vpn in $Vpns)
        {
            $VpnPiP = $Vpn.IpConfigurations.PublicIpAddress.Id
            $PipName = $VpnPiP.Split("/")[8]
            $Pip=($AllPips | Where-Object {$_.Name -like  $PipName}).IpAddress

            $Obj = New-Object PsObject -Property @{
            Customer = $Cust.Customer
            ResourceGroup = $Vpn.ResourceGroupName
            Name = $Vpn.Name
            Location = $Vpn.Location
            SKU = $Vpn.Sku.Name
            SKUCapacity = $Vpn.Sku.Capacity
            GatewayType = $Vpn.GatewayType
            VpnType = $Vpn.VpnType
            State = $Vpn.ProvisioningState
            PublicIPaddress = $Pip
            }
            $Output.Add($obj) | Out-Null
        }
    }
    If($Output.Count)
    {
        $Output | Select-Object Customer,ResourceGroup,Name,Location,SKU,SKUCapacity,GatewayType,VpnType,State,PublicIPaddress | Export-Excel -WorksheetName "VPNgateways" -Path $Excel -Append
    }

    #Public IPs
    [System.Collections.ArrayList] $Output = @()

    Foreach($Pip in $AllPips)
    {
        If($Pip.IpConfiguration) 
        { 
        $NICname = $Pip.IpConfiguration.Id.Split("/")[8]
        if(($AllNics | Where-Object {$_.Name -like $NICname}).VirtualMachine) {
        $VMName = ($AllNics | Where-Object {$_.Name -like $NICname}).VirtualMachine.Id.Split("/")[8] } 
        else {
        $VMName = 'NA'
        }
        } 
        else 
        { 
        $NICname = 'NA'
        $VMName = 'NA'
        }
    
        
        If(!($VMname)) { $VMName = 'NA' }
        $Obj = New-Object PsObject -Property @{
            Customer = $Cust.Customer
            ResourceGroup = $Pip.ResourceGroupName
            Name = $Pip.Name
            Location = $Pip.Location
            SKU = $Pip.Sku.Name
            IpAddress = $Pip.IpAddress
            Type = $Pip.PublicIpAddressVersion
            State = $Pip.ProvisioningState
            NIC = $NICname
            VM = $VMName
            FQDN = $Pip.DnsSettings.Fqdn
            }
            $Output.Add($obj) | Out-Null
    }
    If($Output.Count)
    {
        $Output | Select-Object Customer,ResourceGroup,Name,Location,SKU,Ipaddress,Type,State,NIC,VM,FQDN | Export-Excel -WorksheetName "PublicIps" -Path $Excel -Append
    }

    #NSG Details
    [System.Collections.ArrayList] $Output = @()
    $Nsgs = Get-AzNetworkSecurityGroup

        Foreach($Nsg in $Nsgs)
        {
            If(!(($Nsg.NetworkInterfaces).count))
            {
                $NsgNic = $Nsg.networkinterfaces.id.Split("/")[8]
                $NsgVm = ($AllNics | Where-Object {$_.Name -like $NsgNic}).VirtualMachine.Id.Split("/")[8]
            }
            else { $NsgVm = 'NA'}
            $Rule = $Nsg|Get-AzNetworkSecurityRuleConfig|Select-Object *|Select-Object Direction,Access,ProvisioningState,Name,Protocol,`
            @{n = "SourcePortRange";e={$_.SourcePortRange -join ","}},`
            @{n = "DestinationPortRange";e={$_.DestinationPortRange -join ","}},`
            @{n = "SourceAddressPrefix";e={$_.SourceAddressPrefix -join ","}},`
            @{n = "DestinationAddressPrefix";e={$_.DestinationAddressPrefix -join ","}}
            [System.Collections.ArrayList] $output = @()
            $i = 0
            if($Rule)
            {
                do
                {
                $Obj = New-Object PsObject -Property @{
                Customer = $cust.Customer
                ResourceGroup = $nSG.ResourceGroupName
                NSGName = $Nsg.Name
                VMName = $NsgVm
                RuleName = $Rule[$i].Name
                Direction = $Rule[$i].Direction
                Access = $Rule[$i].Access
                State = $Rule[$i].ProvisioningState
                Protocol = $Rule[$i].Protocol
                SourcePortRange = $Rule[$i].SourcePortRange
                DestinationRange = $Rule[$i].DestinationPortRange
                SourceAddressPrefix = $Rule[$i].SourceAddressPrefix
                DestinationAddressPrefix = $Rule[$i].DestinationAddressPrefix
                }
                $Output.Add($obj) | Out-Null
                $i++
                }While($i -lt $Rule.count)

                $Output | Select-Object Customer,ResourceGroup,VMName,NSGName,RuleName,Direction,Access,State,Protocol,SourcePortRange,`
                DestinationRange,SourceAddressPrefix,DestinationAddressPrefix | Export-Excel -WorksheetName "NSGRules" -Path $Excel -Append
            
            }
            else
            {
                $Obj = New-Object PsObject -Property @{
                Customer = $cust.Customer
                ResourceGroup = $nSG.ResourceGroupName
                NSGName = $Nsg.Name
                VMName = $NsgVm
                RuleName = 'NA'
                Direction = 'NA'
                Access = 'NA'
                State = 'NA'
                Protocol = 'NA'
                SourcePortRange = 'NA'
                DestinationRange = 'NA'
                SourceAddressPrefix = 'NA'
                DestinationAddressPrefix = 'NA'
            }
            $Output.Add($obj) | Out-Null
                $Output | Select-Object Customer,ResourceGroup,VMName,NSGName,RuleName,Direction,Access,State,Protocol,SourcePortRange,`
                DestinationRange,SourceAddressPrefix,DestinationAddressPrefix | Export-Excel -WorksheetName "NSGRules" -Path $Excel -Append
            }
    }

    #ROLES
    [System.Collections.ArrayList] $OutPut = @()
    Connect-AzureAD
    $Roles = Get-AzureADUser|?{$_.UserType -like 'Guest'}
    Foreach($role in $Roles)
    {
            $Obj = New-Object PsObject -Property @{
            Customer = $Cust.Customer
            DisplayName = $Role.DisplayName
            SignInName = $Role.UserPrincipalName
            Type = $Role.UserType
            }
            $Output.Add($obj) | Out-Null
            
    }
    If($Output.Count)
    {
        $Output | Select-Object Customer,DisplayName,SignInName,Type | Export-Excel -WorksheetName "Roles" -Path $Excel -Append
    }

    #VNET details
    [System.Collections.ArrayList] $Output = @()
    $AllVnets = Get-AzVirtualNetwork
    Foreach($Vnet in $AllVnets)
    {
        
        $Obj = New-Object PsObject -Property @{
            Customer = $Cust.Customer
            ResourceGroup = $Vnet.ResourceGroupName
            Name = $Vnet.Name
            Location = $Vnet.Location
            Address = $Vnet.AddressSpace.AddressPrefixes
            DNSservers = $Vnet.DhcpOptions.DnsServers
            State = $Vnet.ProvisioningState
            
            }
            $Output.Add($obj) | Out-Null
    }
    If($Output.Count)
    {
        $Output | Select-Object Customer,ResourceGroup,Name,Location,Address,DNSServers,State | Export-Excel -WorksheetName "VNets" -Path $Excel -Append
    }

    #VM details

    [System.Collections.ArrayList] $Output = @()
    Foreach($Vm in $AllVms)
    {
        
        $Obj = New-Object PsObject -Property @{
            Customer = $Cust.Customer
            ResourceGroup = $Vm.ResourceGroupName
            Name = $Vm.Name
            Location = $Vm.Location
            VMSize = $Vm.HardwareProfile.VmSize
            OSType = $Vm.LicenseType
            State = $Vm.ProvisioningState
            TagKeys = $Vm.Tags.Keys -join ","
            TagValues = $Vm.Tags.Values -join ","
            LicenseType = $Vm.LicenseType
            
            }
            $Output.Add($obj) | Out-Null
    }
    If($Output.Count)
    {
        $Output | Select-Object Customer,ResourceGroup,Name,Location,VMSize,OSType,State,TagKeys,TagValues | Export-Excel -WorksheetName "VMs" -Path $Excel -Append
    }

    #RouteTables
    [System.Collections.ArrayList] $Output = @()

    ForEach($Rtable in Get-AzRouteTable)
    {
        $Obj = New-Object PsObject -Property @{
        Customer = $Cust.Customer
        ResourceGroup = $Rtable.ResourceGroupName
        Name = $Rtable.Name
        Location = $Rtable.Location
        State = $Rtable.ProvisioningState
        }
        $Output.Add($obj) | Out-Null
    }
    If($Output.Count)
    {
        $Output | Select-Object Customer,ResourceGroup,Name,Location,State | Export-Excel -WorksheetName "RouteTables" -Path $Excel -Append
    }

    [System.Collections.ArrayList] $Output = @()
    foreach($vnet in $AllVnets) 
    { 
    
        $Subnets = Get-AzVirtualNetworkSubnetConfig -VirtualNetwork $vnet
        foreach($Subnet in $Subnets)
        {
            $Obj = New-Object PsObject -Property @{
            Customer = $Cust.Customer
            VNetName = $Vnet.Name
            RGName = $Vnet.ResourceGroupName
            Name = $Subnet.Name
            AddressPrefix = $Subnet.AddressPrefix
            State = $Subnet.ProvisioningState
            }
            $Output.Add($obj) | Out-Null
        }
    }
    If($Output.Count)
    {
        $Output | Select-Object Customer,VNetName,RGName,Name,AddressPrefix,State | Export-Excel -WorksheetName "Subnets" -Path $Excel -Append
    }
    
}