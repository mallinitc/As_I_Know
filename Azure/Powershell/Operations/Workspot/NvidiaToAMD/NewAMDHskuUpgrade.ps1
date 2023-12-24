#Install-Module -Name ImportExcel
$AllVMs=Import-Excel -Path C:\AMD\AMDMigration.xlsx -Sheet 'Sheet8'
$Customers=$AllVms|Select 'Customer' -Unique

Foreach($Customer in $Customers)
{

    #Display total Vms per subscription & ask for input
    $Vms=$AllVms|Where-Object {($_.Customer -like $Customer.Customer)}
    $Subscriptionid = ($Vms|Select Subscription -Unique).subscription
    $tenant = ($Vms|Select Tenant -Unique).Tenant
    Connect-AzAccount -Subscription $SubscriptionId -Tenant $tenant
    $AllAzVMs = Get-AzVM
    $VmNames = $Vms.VMName
    #Installing AMD Drivers 
    Foreach( $VmName in $VmNames )
    {
        $Vm =  $AllAzVMs|Where-Object{$_.Name -like $Vmname}
        #Installing AMD
        Invoke-AzVMRunCommand  -ResourceGroupName $Vm.ResourceGroupName -VMName $Vmname -CommandId RunPowerShellScript -ScriptPath C:\AMD\AMD_GPU_DriversInstallation.ps1 -AsJob
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
    Foreach( $VmName in $VMnames )
    {
        $Vm =  $AllAzVMs|Where-Object{$_.Name -like $Vmname}
        $Job=Invoke-AzVMRunCommand  -ResourceGroupName $Vm.ResourceGroupName -VMName $Vmname -CommandId RunPowerShellScript -ScriptPath C:\AMD\AMD_GPU_Upgrade_Verify.ps1 -AsJob
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
    $vmname1=$Output.Value[0].Message
    $VmName=$Vmname1.Split("+")[0]
    $VmName=$VmName.Trim()
    $Version = $Vmname1.Split("+")[1]
    $Vm =  $AllAzVMs | Where-Object{$_.Name -like $vmname}
    $NewAzVm = Get-AzVM -Name $Vmname -ResourceGroupName $vm.ResourceGroupName
    $UpdatedSize= ($NewAzVm).HardwareProfile.VmSize
        #Add it to the result table
        $newobj = New-Object Psobject -Property  @{
        Vmname = $VmName
        UpdatedSku = $UpdatedSize
        Version = $Version
        }
        $ResultObj.Add($newobj)
    
}

Get-Job -State Completed|Remove-Job
Get-Job -State Failed|Remove-Job

#The Final Result
Write-Host "VMname       UpdatedSku       Result" -BackgroundColor Black
$ResultObj | % {
  $line = $_.Vmname + "   "+ $_.UpdatedSku +"  " + $_.version
  if ($_.version -like '*Failed') {
    write-host $line -ForegroundColor red
   } else {
    write-host $line 
  }
}

 }#Final