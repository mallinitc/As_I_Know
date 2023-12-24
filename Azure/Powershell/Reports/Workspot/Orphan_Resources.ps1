#This collect the details of all Oprhan resources like Disks (managed & unmanaged), NICs, ResourceGroups,PublicIPs..etc

$Ws=import-csv -Path D:\WSData\AllCloudCustomers-190603.csv|Out-GridView -PassThru
Clear-AzContext -Scope CurrentUser -Force
Connect-AzAccount -Subscription $Ws.SubscriptionId -Tenant $Ws.TenantId
$Cus=$Ws.Customer
$dir=$env:USERPROFILE+"\Logs\Orphan\$cus\"
If(!(test-path $dir))
{
      New-Item -ItemType Directory -Force -Path $dir
}
$Excel=$Dir+"orphan.xlsx"
$Act=$Dir+"Activity.txt"
$Sum=$Dir+"Summary.txt"

"==============================================================================">> $Act
"Started :: "+(Get-Date) >> $Act
##Get all orphaned RG
$RGobj=@()
ForEach ($RG in Get-AzResourceGroup)
{
    If(!(Get-AzResource -ResourceGroupName $RG.ResourceGroupName))
    {
        $RGobj+=New-Object PsObject -Property @{
            Name=$RG.ResourceGroupName
            Location=$RG.Location
            State=$RG.ProvisioningState
        }
    }
}
If($RGobj.count)
{
    $RGobj|Export-Excel -WorksheetName "ResourceGroups" -Path $Excel
}
Else
{
    "There are no orphan ResourceGroups" >>$Act
}

"Checking for unattached Disks..">>$Act
$ManagedDisks = Get-AzDisk|Where-Object {$_.DiskState -like 'Unattached'}
$Diskobj=@()
If(($ManagedDisks))
{
$Count=$ManagedDisks|Out-GridView -PassThru
ForEach ($Md in $Count) {
    If( $null -eq $Md.ManagedBy )
    {
            "Deleting unattached Managed Disk with Id: $($md.Name)" >>$act
            #$md | Remove-AzDisk -Force -AsJob
            "Deleted unattached Managed Disk with Id: $($md.Name) " >>$act
            $when=Get-Date
            $diskobj += New-Object Psobject -Property  @{
                DiskName=$md.name
                DiskType=$md.Sku.Name
                DiskSize=$md.DiskSizeGB
                ResourceGroup=$md.ResourceGroupName
                Location=$md.Location
                Date=$when
            }
    }
 }
 
 "===================">>$Sum
 "Disks info...." +(Get-Date) >>$Sum
  "No.of Disks : $($ManagedDisks.count)">>$Sum
  [int[]]$A=($ManagedDisks).DiskSizeGB
 $TotalSize=($A|Measure-Object -Sum ).Sum
 $TotPrime=($ManagedDisks|Where-Object {$_.Sku.Name -like '*Premium*'}).count
 "Total Size in GB : $Totalsize">>$Sum
 "Total Premium Disks : $TotPrime" >>$Sum
}
Else
{
    "There are no orphan disks" >>$Act
}
If($DiskObj.count)
{
    $Diskobj|Export-Excel -WorksheetName "Disks" -Path $Excel 
}
"Done with unattached Disks..">>$Act

"Deleting unattached VHDs..">>$Act
$Vhdobj=@()
$StorageAccounts = Get-AzStorageAccount
ForEach($StorageAccount in $StorageAccounts){
    $StorageKey = (Get-AzStorageAccountKey -ResourceGroupName $StorageAccount.ResourceGroupName -Name $StorageAccount.StorageAccountName)[0].Value
    $Context = New-AzStorageContext -StorageAccountName $StorageAccount.StorageAccountName -StorageAccountKey $StorageKey
    $Containers = Get-AzStorageContainer -Context $Context
    if($Containers)
    {
        foreach($Container in $Containers){
        $Blobs = Get-AzStorageBlob -Container $Container.Name -Context $Context
        #Fetch all the Page blobs with extension .vhd as only Page blobs can be attached as disk to Azure VMs
        $Blobs | Where-Object {$_.BlobType -eq 'PageBlob' -and $_.Name.EndsWith('.vhd')} | ForEach-Object { 
            #If a Page blob is not attached as disk then LeaseStatus will be unlocked
            If($_.ICloudBlob.Properties.LeaseStatus -eq 'Unlocked')
            {
                "Deleting unattached VHD with Uri: $($_.ICloudBlob.Uri.AbsoluteUri)" >>$Act
                #$_ | Remove-AzStorageBlob -Force
                $Vhdobj += New-Object Psobject -Property  @{
                Name=$_.Name
                BlobType=$_.BlobType
                Length=$_.Length
                LastModified=$_.LastModified
                IsDeleted=$_.IsDeleted
                SAName=$_.Context.StorageAccountName
                }
                $_.ICloudBlob.Name >>$act
                "Deleted unattached VHD with Uri: $($_.ICloudBlob.Uri.AbsoluteUri)" >>$Act
            }
        }
    }
    }
    Else
    {
        "Zero containers" >>$Act
    }
}
If($VhdObj.count)
{
    $Vhdobj|Export-Excel -WorksheetName "Blobs" -Path $excel 
}

"Checking for unattached NICs..">>$Act
$Onics=Get-AzNetworkInterface | where-object { $_.VirtualMachine -eq $null }
$Onics.count
$Nicobj=@()
If(($Onics))
{
    $Count = $Onics|Select-Object name,ResourceGroupName,Location,IPconfigurations|Out-GridView -PassThru
    ForEach($One in $Count)
    {
        "Deleting unattached NIC: $($One.Name)" >>$Act 
        #$one| Remove-AzNetworkInterface -Force -AsJob
        "Deleted unattached NIC: $($One.Name)" >>$Act
        $Vnet=$One.Ipconfigurations.Subnet.Id
        $Vnet=$Vnet.split("/")[8]
        $Pip=$one.Ipconfigurations.PrivateIpAddress
        $When=Get-Date
        $Nicobj += New-Object Psobject -Property  @{
            Name=$One.Name
            VirtualNetwork=$Vnet
            PrimPrivIP=$Pip
            ResourceGroup=$one.ResourceGroupName
            Location=$One.Location
            Date=$When
        }
    }
    "Nics info..." +(Get-Date) >>$Sum
    "No.of NICs : $($Onics.count)" >>$Sum
}
Else
{
    "There are no orphan NICs" >>$Act
}
If($NicObj.count)
{
    $Nicobj|Export-Excel -WorksheetName "NICs" -Path $Excel 
}
"Done with unattached NICs..">>$Act

"Ended :: "+(Get-Date) >> $Act