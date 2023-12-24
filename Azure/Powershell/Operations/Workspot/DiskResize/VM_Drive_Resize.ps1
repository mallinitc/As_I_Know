$SubscriptionId = '####'
$TenantId = '###'

Connect-AzAccount -Subscription $SubscriptionId -Tenant $TenantId

$VmName = Read-host "Please enter the hostname:"
$VmName = $VmName.Trim()
$Vm = Get-AzVM -Name $VmName
[int]$Choice = Read-Host "`n 1. Add from Azure & Expand `n 2. Just expand only. `n`n Please enter your option"

switch($Choice)
{
                1 { Stop-AzVM -ResourceGroupName $Vm.ResourceGroupName -Name $VmName -AsJob -force -confirm:$false
                        while (Get-Job -State "Running")
                        {
                           Write-Host "The VM is being powered OFF. Please wait..." -ForegroundColor Cyan
                           Start-Sleep -s 5
                        }
                        Get-Job -State Completed|Remove-Job
                        Get-Job -State Failed|Remove-Job
                        $Disk= Get-AzDisk -ResourceGroupName $Vm.ResourceGroupName -DiskName $Vm.StorageProfile.OsDisk.Name
                        #DiskUpdate
                        $Disk.DiskSizeGB = 250
                        Update-AzDisk -ResourceGroupName $Vm.ResourceGroupName -Disk $Disk -DiskName $Disk.Name -confirm:$false
                        Start-AzVM -ResourceGroupName $Vm.ResourceGroupName -Name $VmName  -AsJob
                        while (Get-Job -State "Running")
                        {
                           Write-Host "The VM is being powered ON. Please wait..." -ForegroundColor Cyan
                           Start-Sleep -s 5
                        }
                        Get-Job -State Completed|Remove-Job
                        Get-Job -State Failed|Remove-Job
                        #DiskExpand
                        $Job = Invoke-AzVMRunCommand  -ResourceGroupName $Vm.ResourceGroupName -VMName $Vmname -CommandId RunPowerShellScript -ScriptPath D:\Work\DiskPart.ps1 -AsJob
                        while (Get-Job -State "Running")
                        {
                           Write-Host "The disk is being expanded. Please wait..." -ForegroundColor Cyan
                           Start-Sleep -s 5
                        }
                        $Output = Receive-Job -Job $job
                        $Output = $Output.Value[0].Message
                        Write-Host $Output
                        Get-Job -State Completed|Remove-Job
                        Get-Job -State Failed|Remove-Job
                        
                        }
                        
                2 {  
                        #DiskExpand
                        $Job = Invoke-AzVMRunCommand  -ResourceGroupName $Vm.ResourceGroupName -VMName $Vmname -CommandId RunPowerShellScript -ScriptPath D:\Work\DiskPart.ps1 -AsJob
                        while (Get-Job -State "Running")
                        {
                           Write-Host "The disk is being expanded. Please wait..." -ForegroundColor Cyan
                           Start-Sleep -s 5
                        }
                        $Output = Receive-Job -Job $job
                        $Output = $Output.Value[0].Message
                        Write-Host $Output
                        Get-Job -State Completed|Remove-Job
                        Get-Job -State Failed|Remove-Job
                      }
    default { Write-Host "You have entered an incorrect number. Please try again." }
}

