#This script is to resize VMs on Azure from one SKU to another.
#It reads the Selected Subscription and Resource Group
#Checks if the DataCenter Location of the selected Resource Group has the desired SKU - $newsize
#Lists all the VMs with SKU matching - $oldsize
#Performs Deallocation and Resize operation on the VMs one after the other.
#If VM already in deallocated state, the script proceeds with resize.


#Logs directory in \\user profile\logs --->folder




$dir = $env:USERPROFILE+"\Logs\"
If(!(test-path $dir))
{
      New-Item -ItemType Directory -Force -Path $dir
}
#Information logs -> <Dir>\DD_Mon_YY_HH;MM.txt
#Error logs -> <Dir>\DD_Mon_YY_HH;MM_ERROR.txt
$fname = Get-Date -Format "MMM_dd_yyyy_hh;mm"
$log = $dir+$fname+".txt"
$err = $dir+$fname+"_ERROR"+".txt"
[string[]]$baseinfo = @()
$newsize = "Standard_NV6_Promo"
$oldsize = "Standard_NV6"


#Display all the subscription Ids and Tenant Ids for the given account and allow user to choose the desired one
$ws = import-csv -Path C:\Users\Arjun\WSData\AllCloudCustomers-190603.csv|Out-GridView -PassThru


Connect-AzAccount -Subscription $Ws.SubscriptionId -Tenant $Ws.TenantId

[System.Object]$sub = Get-AzSubscription -SubscriptionId $ws.SubscriptionId -TenantId $ws.TenantId

$sid = $sub.Id
$tid = $sub.TenantId
$cus = $ws.Customer
$cusdom = $ws.CustomerDomain
$baseinfo += "Subscription ID:: $sid"
$baseinfo += "Tenant ID:: $tid"
$baseinfo += "Customer:: $cus"
$baseinfo += "Customer Domain:: $cusdom"


#Display all resource groups in the selected subscription and allow user to choose the desired one
[System.Object]$rg = Get-AzResourceGroup |Out-GridView -Title "Select the Resource Group" -PassThru

$rgname = $rg.ResourceGroupName
$loc = $rg.Location


$baseinfo += "Resource Group :: $rgname"
$baseinfo += "Location :: $loc"
$baseinfo += "Old Size :: $oldsize"
$baseinfo += "New Size:: $newsize"


    $baseinfo >> $log
    
    #Read all VMs with old size and exit if there is no VMs with old size
    $Vms = Get-AzVM -ResourceGroupName $rgname|Where-Object {$_.HardwareProfile.VmSize -like $oldsize}

       if($vms.count)
        {
        $tmp = $vms.count
              
        [System.Reflection.Assembly]::LoadWithPartialName('Microsoft.VisualBasic')
        [int]$ans = 0
        $ans = [Microsoft.VisualBasic.Interaction]::InputBox("How many VMs per batch?", "There are $tmp VMs with $oldsize")
        if($ans -notlike '0')
        {
            ##Batch wise creating background jobs
            $total = $vms.count
            if($ans -ge $total){ $ans=$total}
            $batch = $total/$ans
            $batch = [math]::Ceiling($batch)
            $a1 = 1
            $k = $ans
            $i = 0
            do
            {
                $a1++
                $vms2 = @()
                for($i=$i;$i -lt $k;$i++)
                {
                    $vms2+=$vms[$i]
                }
                foreach($vm in $vms2)
                {
                    $VMname = $vm.Name
                    
                    if(Get-AzVMSize -ResourceGroupName $rgname -VMName $VMName|Where-Object {$_.Name -like $newsize})
                    {
                        $ostype = (Get-AzVM -ResourceGroupName $rgname -Name $VMname).LicenseType
                        $size = (Get-AzVM -ResourceGroupName $rgname -Name $VMname).HardwareProfile.VmSize
                        "Before upgrade :: $VMName   $ostype  $size" >>$log
            
                        $vm.HardwareProfile.VmSize = $newsize
                        Update-AzVM -VM $vm -ResourceGroupName $rgname -AsJob
                    }
                    else
                    {
                        if(!((Get-Content  -Path $err -ErrorAction SilentlyContinue).Length)) { $baseinfo >> $err }
                        "'$newsize' isn't available for '$VMName'.Exiting." >> $err
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
                    $VMname = $vm.Name
                    $ostype = (Get-AzVM -ResourceGroupName $rgname -Name $VMname).LicenseType
                    $size = (Get-AzVM -ResourceGroupName $rgname -Name $VMname).HardwareProfile.VmSize
                    if(Get-AzVM -ResourceGroupName $rgname -Name $vmName|Where-Object {$_.HardwareProfile.VmSize -like $newsize})
                    {
                        Write-Host -BackgroundColor Green -ForegroundColor Black "'$VMName' config is changed to '$newsize'"
                    
                        $ostype = (Get-AzVM -ResourceGroupName $rgname -Name $VMname).LicenseType
                        $size = (Get-AzVM -ResourceGroupName $rgname -Name $VMname).HardwareProfile.VmSize
                        "After upgrade :: $VMName   $ostype  $size" >>$log

                    }
                    else
                    {
                        Write-Host -BackgroundColor Red -ForegroundColor Black "'$VMName' config to '$newsize' is failed."
                        if(!((Get-Content  -Path $err -ErrorAction SilentlyContinue).Length)) { $baseinfo >> $err }
                        "'$VMName' config to '$newsize' is failed." >> $err
                    
                    }
                }
                $i = $k
                $k = $k+$ans
                if($k -ge $total) { $k=$total}

            }while($a1 -le $batch)
        }
        else
        {
            "Invalid input. Exiting" >>$log
        }

              
    }
        else
        {
            Write-Host -BackgroundColor Red "No VMs are found with '$oldsize' config.Exiting."
            if(!((Get-Content  -Path $err -ErrorAction SilentlyContinue).Length)) { $baseinfo >> $err }
            "No VMs are found with '$oldsize' config.Exiting." >>$err

        }

