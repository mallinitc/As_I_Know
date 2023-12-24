$Path = 'D:\AMD_Migration'
$AllVms = Get-Content $Path\Vms.txt
$AllAzVMs = Get-AzVM
$newsize="Standard_NV6h" #Please change the size accordingly


#Power off all VMs
Foreach( $VmName in $AllVms )
{
    $Vm =  $AllAzVMs|Where-Object{$_.Name -like $Vmname}
    #Deallocating
    Stop-AzVM  -Name $vmname -ResourceGroupName $vm.ResourceGroupName -Force -AsJob
}
while (Get-Job -State "Running")
{
    Write-Host "Jobs are still running..."
    Start-Sleep -s 5
}
Get-Job -State Completed|Remove-Job
Get-Job -State Failed|Remove-Job

#Changing VM SKU to Nvidia series
Foreach( $VmName in $AllVms )
{
    $Vm =  $AllAzVMs|Where-Object{$_.Name -like $Vmname}
    If($vm.HardwareProfile.VmSize -notlike $newsize)
    {
        #Resizing
        $size=$vm.HardwareProfile.VmSize
        $vm.HardwareProfile.VmSize = $newsize
        Update-AzVM -VM $vm -ResourceGroupName $Vm.ResourceGroupName -AsJob
    }
}
while (Get-Job -State "Running")
{
    Write-Host "Jobs are still running..."
    Start-Sleep -s 5
}
Get-Job -State Completed|Remove-Job
Get-Job -State Failed|Remove-Job

#verifying SKUs update
$AllAzVMs2 = Get-AzVM
[int]$Count = 0
Foreach( $VmName in $AllVms )
{
    $Vm =  $AllAzVMs2|Where-Object{$_.Name -like $Vmname}
    $Size = $Vm.HardwareProfile.VmSize
    If($Size -notlike $newsize)
    {
        Write-Host " $($vmname) is still $($size)" -ForegroundColor Cyan -BackgroundColor Red
        $Count++ 
    }
}

If( $Count )
{
    "There are $($Count) VMs having issues in upgraing to Nvidia SKUs"
    $Ans = Read-Host "Do you want to Continue? Y/N"
    If($Ans -like 'N')
    {
        return
    }
}

$AllAzVMs = Get-AzVM
Foreach( $VmName in $AllVms )
{
    $Vm =  $AllAzVMs|Where-Object{$_.Name -like $Vmname}
    $SnapshotName = "Pre_AMD_"+$Vmname
    
    If(!(Get-AzSnapshot -SnapshotName $SnapshotName -ResourceGroupName $Vm.ResourceGroupName))
    {
        "No snapshot is found with Given name for $($vmname) " 
                    
    }
    Else 
    { 
        $Snapshot = Get-AzSnapshot -SnapshotName $SnapshotName -ResourceGroupName $Vm.ResourceGroupName

        #Create a new disk from snapshot
        $DiskConfig = New-AzDiskConfig -Location $Snapshot.Location -SourceResourceId $Snapshot.Id -CreateOption Copy
        $NewDiskName = "disk-"+$Vmname+$((Get-Date -Format yyyy_MM_dd).tostring())
        $Disk = New-AzDisk -Disk $DiskConfig -DiskName $NewDiskName -ResourceGroupName $Vm.ResourceGroupName

        # Set the VM configuration to point to the new disk  
        Set-AzVMOSDisk -VM $Vm -ManagedDiskId $Disk.Id -Name $Disk.Name
        # Update the VM with the new OS disk
        Update-AzVM -VM $Vm -ResourceGroupName $Vm.ResourceGroupName -AsJob
    }
    
}

while (Get-Job -State "Running")
{
    Write-Host "Jobs are still running..."
    Start-Sleep -s 5
}
Get-Job -State Completed|Remove-Job
Get-Job -State Failed|Remove-Job

#Power on all VMs
Foreach( $VmName in $AllVms )
{
    $Vm =  $AllAzVMs|Where-Object{$_.Name -like $Vmname}
    # Start the VM
    Start-AzVM -Name $VmName -ResourceGroupName $Vm.ResourceGroupName -AsJob
}
while (Get-Job -State "Running")
{
    Write-Host "Jobs are still running..."
    Start-Sleep -s 5
}
Get-Job -State Completed|Remove-Job
Get-Job -State Failed|Remove-Job