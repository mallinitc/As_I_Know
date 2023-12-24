#VM Migration - Workspot Pools
#Azure - Workspot

Param(
        [parameter(Mandatory=$True, HelpMessage = "Source VM Name")] [string] $SourceVmName,
        [parameter(Mandatory=$True, HelpMessage = "Source Pool")] [string] $SourcePool,
        [parameter(Mandatory=$True, HelpMessage = "Destination Pool")] [string] $DestPool
      )

Connect-AzAccount
Set-WorkspotApiCredentials -ApiClientId 6OjXbf0CfFzuwnAuZS5y -ApiClientSecret 1f3c3e16cb3bf83da863f969dd9af77fcfb00704 -WsControlUser aambastha@workspot.com -WsControlPass Anand@123
#Should we read Control API details also using PARAM ?
$Pools = Get-WorkspotVdiPool
If(!(( $Pools|Where-Object {$_.name -like $SourcePool}) -and (Get-WorkspotVdiPoolVm -PoolName $SourcePool|Where-Object {$_.name -like $SourceVmName}) -and ($Pools|Where-Object {$_.name -like $DestPool})))
{
    "Given Pool/VM details are incorrect."
    break
}

$SrcVm = Get-WorkspotVdiPoolVm -PoolName $SourcePool -VmName $SourceVmName
$ExistingEmailId = $SrcVm.email
$Creation = New-WorkspotVdiPoolVm -PoolName $DestPool
If($Creation.status -notlike 'Succeeded') {
Write-Host "VM Creation is Failed, Reason :: $($Creation.errorInfo)" -BackgroundColor Red
break }

$DestVm = Get-WorkspotVdiPoolVm -PoolName $DestPool -VmName $DestVmName

#AZURE PARTS
$Nics = Get-AzNetworkInterface
$Vmname = ($Nics |Where-Object{$_.IpConfigurations.PrivateIpAddress -eq $SrcVm.ipAddress}).VirtualMachine.Id
$Vmname = ($Vmname -split '/')|Select-Object -Last 1

$Vmname2 = ($Nics |Where-Object{$_.IpConfigurations.PrivateIpAddress -eq $DestVm.ipAddress}).VirtualMachine.Id
$Vmname2 = ($Vmname2 -split '/')|Select-Object -Last 1

$AllVms = Get-AzVM
$Vm = $AllVms |Where-Object {$_.Name -like $Vmname}
$Vm2 = $AllVms |Where-Object {$_.Name -like $Vmname2}

Stop-AzVM  -Name $vmname2 -ResourceGroupName $vm2.ResourceGroupName -Force
$Diskname = (Get-AzVM -Name $Vmname -ResourceGroupName $Vm.ResourceGroupName).StorageProfile.OsDisk.Name
$VmDisk = Get-AzDisk -Name $Diskname -ResourceGroupName $Vm.ResourceGroupName

#Create a snapshot from vm disk
$SnapshotName = $Vmname+"Snapshot"
If(Get-AzSnapshot -SnapshotName $SnapshotName -ResourceGroupName $Vm.ResourceGroupName -ErrorAction SilentlyContinue)
{
    $Snapshot = Get-AzSnapshot -SnapshotName $SnapshotName -ResourceGroupName $Vm.ResourceGroupName
}
Else
{
    $SnapshotConfig = New-AzSnapshotConfig -SourceUri $VmDisk.Id -CreateOption Copy -Location $VmDisk.Location
    $Snapshot = New-AzSnapshot -Snapshot $SnapshotConfig -SnapshotName $SnapshotName -ResourceGroupName $Vm.ResourceGroupName
}

If($Vm.Location -notlike $Vm2.Location)
{
    #Copy the snapshot to another region
    #$DeststorageAccountName='csarjundisks'
    #$DestSAContainer='snapshotcontainer'
    $DestBlobname=$vmname+'snapshotCopydisk'
    $DeststorageAccountName = Read-Host "Enter the Destination Storage Account Name"
    $DestSAContainer = Read-Host "Enter the Destination Storage Container Name"
    $SAccount = Get-AzStorageAccount -ResourceGroupName $Vm2.ResourceGroupName -Name $DeststorageAccountName 
    $Sas = Grant-AzSnapshotAccess -ResourceGroupName $Vm.ResourceGroupName -SnapshotName $Snapshot.Name -DurationInSecond 3600 -Access Read
    $SaKey = Get-AzStorageAccountKey -ResourceGroupName $Vm2.ResourceGroupName -Name $DeststorageAccountName
    $StorageContext = New-AzStorageContext -StorageAccountName $DeststorageAccountName -StorageAccountKey $SaKey[0].Value
    #New-AzStorageContainer -Context $StorageContext -Name $DestSAContainer -Permission Container
    Get-AzStorageContainer -Context $StorageContext -Name $DestSAContainer
    Start-AzStorageBlobCopy -AbsoluteUri $Sas.AccessSAS -DestContainer $DestSAContainer -DestContext $StorageContext -DestBlob $DestBlobname
    While((Get-AzStorageBlobCopyState -Context $StorageContext -Blob $DestBlobname -Container $DestSAContainer).Status -like 'Pending')
    {
        $Copy = Get-AzStorageBlobCopyState -Context $StorageContext -Blob $DestBlobname -Container $DestSAContainer
        Write-Progress -Activity "Copying snapshot" -Status "Bytes $($Copy.BytesCopied) of $($Copy.TotalBytes)" -PercentComplete (($Copy.BytesCopied / $Copy.TotalBytes) * 100)
        Start-Sleep -Seconds 10 
    }
    
    #Provide the size of the disks in GB. It should be greater than the VHD file size.
    #$diskSize = '128'
    $sourceVHDURI = (Get-AzStorageBlob -Container $DestSAContainer -Context $StorageContext -Blob $DestBlobname).ICloudBlob.uri.AbsoluteUri
    #Provide the storage type for Managed Disk. Premium_LRS or Standard_LRS.
    $StorageType = 'Premium_LRS'
    #Create a new disk from snapshotCopy
    $diskConfig = New-AzDiskConfig -AccountType $StorageType -Location $Vm2.location -CreateOption Import -StorageAccountId $SAccount.Id -SourceUri $SourceVHDURI
    $destdiskname=  $Vmname+"SnapchatCopy"
    $Disk = New-AzDisk -Disk $DiskConfig -ResourceGroupName $Vm2.resourceGroupName -DiskName $DestdiskName
}
Else
{
    #Create a new disk from snapshot
    $DiskConfig = New-AzDiskConfig -Location $Snapshot.Location -SourceResourceId $Snapshot.Id -CreateOption Copy
    $NewDiskName = "NewDiskFromSnapshot_"+$((Get-Date -Format yyyy_MM_dd_HH_MM).tostring())
    $Disk = New-AzDisk -Disk $DiskConfig -DiskName $NewDiskName -ResourceGroupName $Vm2.ResourceGroupName
}


# Set the VM configuration to point to the new disk  
Set-AzVMOSDisk -VM $Vm2 -ManagedDiskId $Disk.Id -Name $Disk.Name
# Update the VM with the new OS disk
Update-AzVM -VM $Vm2 -ResourceGroupName $Vm2.ResourceGroupName

# Start the VM
Start-AzVM -Name $Vm2.Name -ResourceGroupName $Vm2.ResourceGroupName
Start-Sleep -Seconds 15

#Get the AgentToken from Control & modify the script which is in C:\Temp\AgentRegistration.ps1-->Start-Process -FilePath "C:\Program files\WorkspotAgent\reregister_poolvm.bat" -ArgumentList "b1c9f763325ee21dee745b2edd4cfb33f563c74e"
Invoke-AzVMRunCommand -ResourceGroupName $Vm2.ResourceGroupName -VMName $Vm2.Name -CommandId RunPowerShellScript -ScriptPath C:\Temp\AgentRegistration.ps1
Start-Sleep -Seconds 5
Write-Host "The VM Status is $((Get-WorkspotVdiPoolVm -PoolName $DestPool -VmName $DestVmName).status)" -ForegroundColor Cyan -BackgroundColor Black
$RemoveOld = Read-Host "Do you want to remove Old(source) VM $($SourceVmName)) from the Pool $($SourcePool)) [Y/N]"
If($RemoveOld -match "[yY]") { Remove-WorkspotVdiPoolVm -PoolName $SourcePool -VmName $SourceVmName }
If((Get-WorkspotVdiPoolVm -PoolName $DestPool -VmName $DestVmName).status -like 'Ready')
{
    #VM assignment
    $NoUserAssign = New-Object System.Management.Automation.Host.ChoiceDescription '&No', 'No user assignment'
    $SameUserAssign = New-Object System.Management.Automation.Host.ChoiceDescription '&Same User', 'Same user from Old VM'
    $NewUserAssign = New-Object System.Management.Automation.Host.ChoiceDescription '&New User', 'Assign it to new User'
    $Options = [System.Management.Automation.Host.ChoiceDescription[]]($NoUserAssign, $SameUserAssign,$NewUserAssign)

    $Title = 'User Assignment'
    $Message = 'Do you want to assign New VM?'
    $Result = $host.ui.PromptForChoice($Title, $Message, $Options, 0)

    Switch($result)
    {
        0 {
            Write-Host "No assignment"
        }
        1 {
            Set-WorkspotVdiUserAssignment -PoolName $DestPool -UserEmail $ExistingEmailId -VmName $DestVmName
        }
        2 {
            $EmailId = Read-Host "Enter valid user email id"
            Set-WorkspotVdiUserAssignment -PoolName $DestPool -UserEmail $EmailId -VmName $DestVmName
        }
        Default {
            Write-Host "No assignment"
        }
    }
}
