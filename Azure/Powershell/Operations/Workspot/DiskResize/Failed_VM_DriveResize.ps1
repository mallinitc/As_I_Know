$SubscriptionId = '######'
$TenantId = '####'

Connect-AzAccount -Subscription $SubscriptionId -Tenant $TenantId

$VmName = Read-host "Please enter the hostname:"
$VmName = $VmName.Trim()
$Vm = Get-AzVM -Name $VmName

$Job = Invoke-AzVMRunCommand  -ResourceGroupName $Vm.ResourceGroupName -VMName $Vmname -CommandId RunPowerShellScript -ScriptPath D:\Work\Get_RecoveryDisk.ps1 -AsJob
while (Get-Job -State "Running")
{
    Write-Host "Getting the recoverydisk details. Please wait..." -ForegroundColor Cyan
    Start-Sleep -s 5
}
$Output = Receive-Job -Job $job
$ReInfo = $Output.Value[0].Message
Write-Host " $ReInfo " -ForegroundColor Yellow -BackgroundColor DarkRed
#$Num1=$ReInfo.Split("&&")[0]
#$Num2=$ReInfo.Split("&&")[2]
#$RecDisk = $Num1.Trim()
#$RecPart = $Num2.Trim()

$RecDisk = Read-host "Please enter the Recovery Disk Number"
$RecPart = Read-host "Please enter the Recovery Disk Partition Number"

$Job = Invoke-AzVMRunCommand  -ResourceGroupName $Vm.ResourceGroupName -VMName $Vmname -CommandId RunPowerShellScript -Parameter @{"ReDisk" = "$RecDisk";"RePart" = "$RecPart"} -ScriptPath D:\Work\Delete_RecoveryDisk.ps1 -AsJob
while (Get-Job -State "Running")
{
    Write-Host "Deleting the recoverydisk. Please wait..." -ForegroundColor Cyan
    Start-Sleep -s 5
}
$Output = Receive-Job -Job $job
$DeletedDiskInfo = $Output.Value[0].Message
Write-Host "Deleted Disk is `n`n`n $($DeletedDiskInfo)" -ForegroundColor Red

#DiskExpand
$Job = Invoke-AzVMRunCommand  -ResourceGroupName $Vm.ResourceGroupName -VMName $Vmname -CommandId RunPowerShellScript -ScriptPath D:\Work\DiskPart.ps1 -AsJob
while (Get-Job -State "Running")
{
    Write-Host "The disk is being expanded. Please wait..." -ForegroundColor Cyan
    Start-Sleep -s 5
}
$Output = Receive-Job -Job $job
$Output = $Output.Value[0].Message
Write-Host $Output -ForegroundColor Green
Get-Job -State Completed|Remove-Job
Get-Job -State Failed|Remove-Job