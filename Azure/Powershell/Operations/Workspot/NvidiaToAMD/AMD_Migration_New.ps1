$Path = 'C:\AMD'
$AllVms = Get-Content $Path\'Error43.txt'
$AllAzVMs = Get-AzVM
$newsize="Standard_NV16ahs_v4" #Please change the size accordingly



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

#Changing VM SKU to AMD series
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
    "There are $($Count) VMs having issues in upgraing to AMD SKUs"
    $Ans = Read-Host "Do you want to Continue? Y/N"
    If($Ans -like 'N')
    {
        return
    }
}

#Create a Snapshot & Power on back
Foreach( $VmName in $AllVms )
{
    $Vm =  $AllAzVMs|Where-Object{$_.Name -like $Vmname}
    #Snapshot
    $Diskname = $Vm.StorageProfile.OsDisk.Name
    $VmDisk = Get-AzDisk -Name $Diskname -ResourceGroupName $Vm.ResourceGroupName
    $SnapshotName = "Pre_AMD_"+$Vmname
    $SnapshotConfig = New-AzSnapshotConfig -SourceUri $VmDisk.Id -CreateOption Copy -Location $VmDisk.Location
    $Snapshot = New-AzSnapshot -Snapshot $SnapshotConfig -SnapshotName $SnapshotName -ResourceGroupName $Vm.ResourceGroupName
    Start-AzVM  -Name $vmname -ResourceGroupName $vm.ResourceGroupName -AsJob
    
}
while (Get-Job -State "Running")
{
    Write-Host "Jobs are still running..."
    Start-Sleep -s 5
}
Get-Job -State Completed|Remove-Job
Get-Job -State Failed|Remove-Job


#Uninstalling Nvidia drivers
Foreach( $VmName in $AllVms )
{
    $Vm =  $AllAzVMs|Where-Object{$_.Name -like $Vmname}
    Invoke-AzVMRunCommand  -ResourceGroupName $Vm.ResourceGroupName -VMName $Vmname -CommandId RunPowerShellScript -ScriptPath $Path\Nvidia_GPU_DriversUnInstallation.ps1 -AsJob
}
while (Get-Job -State "Running")
{
    Write-Host "Jobs are still running..."
    Start-Sleep -s 5
}
Get-Job -State Completed|Remove-Job
Get-Job -State Failed|Remove-Job
Get-Job |Remove-Job -Force



#Installing AMD Drivers
Foreach( $VmName in $AllVms )
{
    $Vm =  $AllAzVMs|Where-Object{$_.Name -like $Vmname}
    #Installing AMD
    Invoke-AzVMRunCommand  -ResourceGroupName $Vm.ResourceGroupName -VMName $Vmname -CommandId RunPowerShellScript -ScriptPath $Path\AMD_GPU_DriversInstallation.ps1 -AsJob
}
while (Get-Job -State "Running")
{
    Write-Host "Jobs are still running..."
    Start-Sleep -s 5
}
Get-Job -State Completed|Remove-Job
Get-Job -State Failed|Remove-Job

#Verifying AMD installation status
[System.Collections.ArrayList] $Jobobj = @()
Foreach( $VmName in $AllVms )
{
    $Vm =  $AllAzVMs|Where-Object{$_.Name -like $Vmname}
    $Job=Invoke-AzVMRunCommand  -ResourceGroupName $Vm.ResourceGroupName -VMName $Vmname -CommandId RunPowerShellScript -ScriptPath $Path\AMD_GPU_PostDeployement.ps1 -AsJob
    $Jobobj.Add($Job)
}
while (Get-Job -State "Running")
{
    Write-Host "Jobs are still running..."
    Start-Sleep -s 5
}



[System.Collections.ArrayList] $ResultObj = @()
foreach($obj in $Jobobj)
{
    $Output = Receive-Job -Job $obj
    $Message = $Output.Value[0].Message
    $VmName = $Message.Split("+")[0]
    $VmName = $VmName.Trim()
    $Vm = $AllAzVMs | Where-Object{$_.Name -like $vmname}
    $NewAzVm = Get-AzVM -Name $Vmname -ResourceGroupName $vm.ResourceGroupName
    $UpdatedSize = ($NewAzVm).HardwareProfile.VmSize
    
    If ($Message -like '*Error*')
    {
        $Code = $Message.Split("+")[2]
        #Add it to the result table
        $newobj = New-Object Psobject -Property  @{
        Vmname = $VmName
        UpdatedSku = $UpdatedSize
        Status = "Error/$($Code)"
        }
        $ResultObj.Add($newobj)
    }
    Else
    {
        #Add it to the result table
        $newobj = New-Object Psobject -Property  @{
        Vmname = $VmName
        UpdatedSku = $UpdatedSize
        Status = 'Success'
        }
        $ResultObj.Add($newobj)
    }
    
}


#The Final Result
Write-Host "VMname       UpdatedSku       Result" -BackgroundColor Black
$ResultObj | % {
  $line = $_.Vmname + "   "+ $_.UpdatedSku +"  " + $_.status
  if ($_.status -like '*Success') {
    write-host $line 
   } else {
    write-host $line -ForegroundColor red
  }
}