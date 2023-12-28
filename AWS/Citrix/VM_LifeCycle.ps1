#Citrix XenDesktop environment hosted on AWS Cloud
#VM Life Cycle

asnp citrix*
$ec2 = @()
#$HostNames = @()
$kill = @()
$old = @()

#All Name tags start with VZ-Citrix
$NameTagPrefix = "Citrix-"

$ImageID = Read-Host -Prompt 'Input AMI Number'
$delete = Read-Host -Prompt 'Delete the stacks or just put VMs into Maintenance Mode (D or M)?'

#Get desktop group names to generate tag names to search for
$DeskTopGroupNames = Get-BrokerDesktopGroup | Select-Object -ExpandProperty name

#Get properties for all instances with VZ-Citrix* name tag and matching ImageID number
for ($i = 0; $i -lt $DeskTopGroupNames.count; $i++) {
    
    $ec2 += Get-EC2Instance -Filter @{Name = 'tag:Name'; Values = $NameTagPrefix + $DeskTopGroupNames[$i] }
    
}



#$ec2 += Get-EC2Instance -Filter @{Name = 'tag:Name'; Values = "Citrix-POS-Dev"}
$old = $ec2.instances | Where-Object { $_.imageID -eq $ImageID } | Select-Object   instanceID, PrivateIPAddress

#Generate host names from private IP address property
for ($i = 0; $i -lt $old.Count; $i++) {
   
    $machine = "adcloud\" + $old[$i].PrivateIpAddress -replace "[.]", '-'

    #Put machines in maintenance mode
    Set-BrokerMachineMaintenanceMode -InputObject $machine -MaintenanceMode $true

    if ($delete -eq "d" -or $delete -eq "D") {
        Stop-EC2Instance -InstanceID $old[$i].instanceID
    }
    else {
        #Check for active or disconnected sessions.  If no session shut down the machine
        $session = Get-BrokerSession -MachineName $machine
        if ($session -eq $null) {
            Stop-EC2Instance -InstanceID $old[$i].instanceID
        }
    }
   
} 


#Delete the stack if requested
if ($delete -eq "d" -or $delete -eq "D") {
    Write-Host "Going to delete all EC2 instances built with " $ImageID
    $confirm = Read-Host -Prompt 'Are you sure this is what you want to do ? (y/n)'
    if ($confirm -eq "y" -or $confirm -eq "Y") {
        #Get list of all stacks that start with CTX-CFStack
        $sn = get-cfnstack | Where-Object StackName -Match CTX-CFStack

        #Feed in the instanceIDs and get name of the stacks that they belong to
        for ($j = 0; $j -lt $old.Count; $j++) {
            for ($i = 0; $i -lt $sn.Count; $i++) {
                $sr = Get-CFNStackResourceSummary -StackName $sn[$i].StackName | Where-Object ResourceType -EQ AWS::EC2::Instance | Select-Object -ExpandProperty PhysicalResourceID 
                if ($sr -contains $old[$j].instanceID) {
                    # Write-Host "Kill this one"
                    $kill += $sn[$i].StackName
        
                }
            }
        }
        #Remove dupicate values from the list of stacks to kill
        $kill = $kill | Select-Object -Unique

        #Remove machines from Desktop Groups and Catalogs
        for ($i = 0; $i -lt $old.Count; $i++) {
            $machine = "vzadcloud\" + $old[$i].PrivateIpAddress -replace "[.]", '-'
            $dg = Get-BrokerMachine -MachineName $machine | Select-Object -ExpandProperty DesktopGroupName
            Remove-BrokerMachine -MachineName $machine -DesktopGroup $dg

            #Remove from catalog
            Remove-BrokerMachine -MachineName $machine
        }

        #Whack the Stacks
        if ($kill.count -eq 1) {
            # Write-Host $kill
            Remove-CFNStack -StackName $kill
        }
        else {
            for ($i = 0; $i -lt $kill.Count; $i++) {
                Remove-CFNStack -StackName $kill[$i] 
            }
        }
    }

}
