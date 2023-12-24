$Path = 'C:\AMD'
$AllVms = Get-Content $Path\Error43.txt
$AllAzVMs = Get-AzVM
#$newsize="Standard_NV16ahs_v4" #Please change the size accordingly



#Verifying AMD installation status
[System.Collections.ArrayList] $Jobobj = @()
Foreach( $VmName in $AllVms )
{
    $Vm =  $AllAzVMs|Where-Object{$_.Name -like $Vmname}
    $Job=Invoke-AzVMRunCommand  -ResourceGroupName $Vm.ResourceGroupName -VMName $Vmname -CommandId RunPowerShellScript -ScriptPath $Path\DevCon.ps1 -AsJob
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