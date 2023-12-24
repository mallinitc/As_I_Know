$Path = 'C:\AMD'
$Vms = Get-Content $Path\mead_hunt_VMs.txt


foreach($vm in $VMs)
{

$AzVM = Get-AzVM -Name $vm
Remove-AzVMExtension -ResourceGroupName $AzVM.ResourceGroupName -VMName $AzVM.Name -Name Microsoft.Compute.BGInfo -Force
Remove-AzVMExtension -ResourceGroupName $AzVM.ResourceGroupName -VMName $AzVM.Name -Name Microsoft.CPlat.Core.RunCommandWindows -Force

}