$Ws = Import-Excel -Path D:\Inputfile.xlsx|Out-GridView -PassThru

$Vms = gc "D:\2.7.1_upgrade\2.7.1_upgrade\vms.txt"
$Vms.count

$SubscriptionID = '##'
$TenantId = '##'

Clear-AzContext -Scope CurrentUser -Force
Connect-AzAccount -Subscription $SubscriptionID -Tenant $TenantId

Foreach($Vm in $Vms)
 {
    
            $Vmname= $VM
            $Vmname= $Vmname.trim()
            write-host $VMname
            $AzVm = Get-AzVM -Name $Vmname
            Write-Host $AzVm
            $Out=Invoke-AzVMRunCommand  -ResourceGroupName $AzVm.ResourceGroupName -VMName $Vmname -CommandId RunPowerShellScript -ScriptPath "D:\2.7.1_upgrade\2.7.1_upgrade\271_upgrade.ps1" -AsJob
            write-host $Out
 }

 while (Get-Job -State "Running")
{
    Write-Host "Jobs are still running..."
    Start-Sleep -s 5
}
Get-Job -State Completed|Remove-Job
Get-Job -State Failed|Remove-Job
