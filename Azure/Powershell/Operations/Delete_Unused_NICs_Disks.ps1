#This gets the list of unused NICs & Disks (managed) and deletes them.

$Ws = import-csv -Path D:\WSData\AllCloudCustomers-190603.csv|Out-GridView -PassThru
Connect-AzAccount -Subscription $Ws.SubscriptionId -Tenant $Ws.TenantId
$Cus = $Ws.Customer
$Dir = $env:USERPROFILE+"\Logs\NICDISKs\$Cus\"
If(!(Test-Path $Dir))
{
      New-Item -ItemType Directory -Force -Path $Dir
}
$Niclog = $Dir+"NIC.csv"
$Disklog = $Dir+"Disk.csv"
$Act = $Dir+"Activity.txt"
$Sum = $Dir+"Summary.txt"

"==============================================================================">> $Act
"Started :: "+(Get-Date) >> $Act
$DeleteUnattachedDisks = 1
"Checking for unattached Disks..">>$Act
$ManagedDisks = Get-AzDisk|Where-Object {$_.DiskState -like 'Unattached'}
[PsObject[]]$Disksdata = @()
If(($ManagedDisks))
{
$Count = $ManagedDisks|Out-GridView -PassThru
ForEach ($Md in $Count) {

    If( $null -eq $Md.ManagedBy ){

        If($DeleteUnattachedDisks -eq 1){
            "Deleting unattached Managed Disk with Id: $($Md.Name)" >>$Act
            #$Md | Remove-AzDisk -Force -AsJob
            "Deleted unattached Managed Disk with Id: $($Md.Name) " >>$Act
            $When = Get-Date
            $Obj = New-Object -TypeName psobject
            $Obj | Add-Member -MemberType NoteProperty -Name DiskName -Value "$($Md.name)"
            $Obj | Add-Member -MemberType NoteProperty -Name DiskType -Value "$($Md.Sku.Name)"
            $Obj | Add-Member -MemberType NoteProperty -Name DiskSize -Value "$($Md.DiskSizeGB)"
            $Obj | Add-Member -MemberType NoteProperty -Name ResourceGroup -Value "$($Md.ResourceGroupName)"
            $Obj | Add-Member -MemberType NoteProperty -Name Location -Value "$($Md.Location)"
            $Obj | Add-Member -MemberType NoteProperty -Name Date -Value "$When"
            $Disksdata+=$Obj
        }
    }
 }
 
 "===================">>$Sum
 "Disks info...." +(Get-Date) >>$Sum
  "No.of Disks : $($ManagedDisks.count)">>$Sum
  [int[]]$A=($ManagedDisks).DiskSizeGB
 $TotalSize=($A|Measure-Object -Sum ).Sum
 $TotPrime=($ManagedDisks|Where-Object {$_.Sku.Name -like '*Premium*'}).count
 "Total Size in GB : $Totalsize">>$Sum
 "Total Premium Disks : $TotPrime" >>$Sum
}
Else
{
    "There are no orphan disks" >>$Act
}

                Get-Job
                While (Get-Job -State "Running")
                {
                    Write-Host "Jobs are still running..."
                    Start-Sleep -s 5
                }
                #Results
                Get-Job | Receive-Job 
                Get-Job -State Completed|Remove-Job

If(($Disksdata.count))
{$Disksdata|Export-Csv $Disklog  -Append -NoTypeInformation}
"Done with unattached Disks..">>$Act

"Checking for unattached NICs..">>$Act
$Onics=Get-AzNetworkInterface | where-object { $_.VirtualMachine -eq $null }
$Onics.count
[PsObject[]]$Nicdata=@()
If(($Onics))
{
    $Count = $Onics|Select-Object name,ResourceGroupName,Location,IPconfigurations|Out-GridView -PassThru
    ForEach($One in $Count)
    {
        "Deleting unattached NIC: $($One.Name)" >>$Act 
        #$One| Remove-AzNetworkInterface -Force -AsJob
        "Deleted unattached NIC: $($One.Name)" >>$Act
        $Vnet=$One.Ipconfigurations.Subnet.Id
        $Vnet=$Vnet.split("/")[8]
        $Pip=$One.Ipconfigurations.PrivateIpAddress
        $When=Get-Date
        $Obj = New-Object -TypeName psobject
        $Obj | Add-Member -MemberType NoteProperty -Name Name -Value "$($One.name)"
        $Obj | Add-Member -MemberType NoteProperty -Name VirtualNetwork -Value "$Vnet"
        $Obj | Add-Member -MemberType NoteProperty -Name PrimaryPrivateIP -Value "$Pip"
        $Obj | Add-Member -MemberType NoteProperty -Name ResourceGroup -Value "$($One.ResourceGroupName)"
        $Obj | Add-Member -MemberType NoteProperty -Name Location -Value "$($One.Location)"
        $Obj | Add-Member -MemberType NoteProperty -Name Date -Value "$When"
        $Nicdata+=$Obj
    }
    "Nics info..." +(Get-Date) >>$Sum
    "No.of NICs : $($onics.count)" >>$Sum
}
Else
{
    "There are no orphan NICs" >>$Act
}
                Get-Job
                while (Get-Job -State "Running")
                {
                    Write-Host "Jobs are still running..."
                    Start-Sleep -s 5
                }
                #Results
                Get-Job | Receive-Job 
                Get-Job -State Completed|Remove-Job

If(($Nicdata.count))
{ $Nicdata|Export-Csv $Niclog  -Append -NoTypeInformation }
"Done with unattached NICs..">>$Act
"Ended :: "+(Get-Date) >> $Act