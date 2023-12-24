#Install-Module -Name ImportExcel
$AllVMs=Import-Excel -Path C:\H_Skus\VMsList22.xlsx -WorksheetName 'Sheet2'
$Customers=$AllVms|Select 'Customer' -Unique

Foreach($Customer in $Customers)
{
        
    #Display total Vms per subscription & ask for input
    $Vms=$AllVms|Where-Object {($_.Customer -like $Customer.Customer)}
    $Subscriptionid = ($Vms|Select Subscription).subscription[0]
    $tenant = ($Vms|Select Tenant).Tenant[0]
    #Connect-AzAccount -Subscription $SubscriptionId -Tenant $tenant

    [System.Reflection.Assembly]::LoadWithPartialName('Microsoft.VisualBasic')
    [int]$ans=0
    $ans = [Microsoft.VisualBasic.Interaction]::InputBox("How many VMs per batch?", "There are $($vms.count) VMs")
    if($ans -notlike '0')
        {
            ##Batch wise creating background jobs
            $total=$vms.count
            if($ans -ge $total){ $ans=$total}
            $batch=$total/$ans
            $batch=[math]::Ceiling($batch)
            $a1=1
            $k=$ans
            $i=0
            do
            {
                $a1++
                $vms2=@()
                for($i=$i;$i -lt $k;$i++)
                {
                    $vms2+=$vms[$i]
                }
                foreach($vm in $vms2)
                {
                    $VMname=$vm.VMName
                    $AzVM = Get-AzVM -Name $VMname
                    
                    if(Get-AzVMSize -ResourceGroupName $AzVm.ResourceGroupName -VMName $VMName|Where-Object {$_.Name -like $vm.TargetSku})
                    {
                        $ostype=(Get-AzVM -ResourceGroupName $AzVm.ResourceGroupName  -Name $VMname).LicenseType
                        $size=(Get-AzVM -ResourceGroupName $AzVm.ResourceGroupName  -Name $VMname).HardwareProfile.VmSize
                        "Before upgrade :: $VMName   $ostype  $size" 
            
                        $Azvm.HardwareProfile.VmSize = $vm.TargetSku
                        Update-AzVM -VM $Azvm -ResourceGroupName $AzVm.ResourceGroupName -AsJob
                    }
                    else
                    {
                        
                        "'$($vm.TargetSku)' isn't available for '$VMName'.Exiting." 
                    }
                       
                }
                ##Wait
                Get-Job
                while (Get-Job -State "Running")
                {
                    Write-Host "Jobs are still running..."
                    Start-Sleep -s 5
                }
                #Results
                Get-Job | Receive-Job 
                Get-Job -State Completed|Remove-Job
                ##Verify Jobs
                foreach($vm in $vms2)
                {
                    $VMname=$vm.VmName
                    $AzVM = Get-AzVM -Name $VMname
                    $ostype=(Get-AzVM -ResourceGroupName $AzVm.ResourceGroupName -Name $VMname).LicenseType
                    $size=(Get-AzVM -ResourceGroupName $AzVm.ResourceGroupName -Name $VMname).HardwareProfile.VmSize
                    if(Get-AzVM -ResourceGroupName $AzVm.ResourceGroupName -Name $vmName|Where-Object {$_.HardwareProfile.VmSize -like $vm.TargetSku})
                    {
                        
                    
                        $ostype=(Get-AzVM -ResourceGroupName $AzVm.ResourceGroupName -Name $VMname).LicenseType
                        $size=(Get-AzVM -ResourceGroupName $AzVm.ResourceGroupName -Name $VMname).HardwareProfile.VmSize
                        "After upgrade :: $VMName   $ostype  $size" 

                    }
                    else
                    {
                        Write-Host -BackgroundColor Red -ForegroundColor Black "'$VMName' config to '$($vm.TargetSku)' is failed."
                    
                        "'$VMName' config to '$($vm.TargetSku)' is failed."
                    
                    }
                }
                $i=$k
                $k=$k+$ans
                if($k -ge $total) { $k=$total}

            }while($a1 -le $batch)
        }
        else
        {
            "Invalid input. Exiting" 
        }

}

