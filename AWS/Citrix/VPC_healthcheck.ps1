#Citrix Xendesktop on AWS cloud
#Script - DDC server health check

$DDC1 = "<DDC_IP>"

if (!((Test-Connection $DDC1 -Count 2 -Quiet) -and ((Get-Service -ComputerName $DDC1 -Name CitrixBrokerService).Status -like 'Running'))) {

    function StartVM {
        $iid = $args[0]
        Start-EC2Instance -InstanceId $iid
        Start-Sleep -s 25

    }

    function StopVM {
        $iid = $args[0]
        Stop-EC2Instance -InstanceId $iid
        Start-Sleep -s 15

    }



    $DDC = "<IP>"
    $temp = Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$ddc" }
    #$instance.Placement.AvailabilityZone
    Write-Host "Executing the script in $DDC server"

    $zones = (Get-EC2AvailabilityZone).ZoneName

    ###### Zones wise capacity ########
    foreach ($zone in $zones) {
        $Nowrunning = (Get-EC2Instance | Select-Object -ExpandProperty RunningInstance | ? { $_.Placement.AvailabilityZone -eq $zone } | ? { $_.tags.Key -eq "CTXInstance" -and $_.Tags.Value -eq "CTXDesktop" } | ? { $_.State.Name.Value -like 'Running' }).count
        $NotRunning = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.Placement.AvailabilityZone -eq $zone } | ? { $_.tags.Key -eq "CTXInstance" -and $_.Tags.Value -eq "CTXDesktop" } | ? { $_.State.Name.Value -notlike 'Running' }).count
        $total = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.Placement.AvailabilityZone -eq $zone } | ? { $_.tags.Key -eq "CTXInstance" -and $_.Tags.Value -eq "CTXDesktop" }).count

        $perc = ($Nowrunning / $total) * 100
        $perc = "{0:N2}" -f $perc

        Write-Host "Zone Name: $zone   Total instances: $total    Running: $Nowrunning   Not Running: $NotRunning   "   -NoNewline ; Write-host "Availability: $perc % "  -foregroundcolor "White" -backgroundcolor "Red"
    }


    ################


    $per = 40
    #$zone="us-west-2b"
    foreach ($zone in $zones) {

        $running = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.Placement.AvailabilityZone -eq $zone } | ? { $_.tags.Key -eq "CTXInstance" -and $_.Tags.Value -eq "CTXDesktop" } | ? { $_.State.Name.Value -like 'Running' }).count

        $total = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.Placement.AvailabilityZone -eq $zone } | ? { $_.tags.Key -eq "CTXInstance" -and $_.Tags.Value -eq "CTXDesktop" }).count

        [int]$avl = ($total * $per) / 100

        if ($running -lt $avl) {
            [int]$count = $avl - $running
            #$count=2

            $instids = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.Placement.AvailabilityZone -eq $zone } | ? { $_.State.Name.Value -notlike 'Running' } | ? { $_.tags.Key -eq "CTXInstance" -and $_.Tags.Value -eq "CTXDesktop" }).instanceId

            for ($i = 0; $i -lt $count; $i++) {

                StartVM $instids[$i]
                Sleep -Seconds 3
            }

        }

    }


    ####################Zone wise availability ###############
    foreach ($zone in $zones) {
        $Nowrunning = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.Placement.AvailabilityZone -eq $zone } | ? { $_.tags.Key -eq "CTXInstance" -and $_.Tags.Value -eq "CTXDesktop" } | ? { $_.State.Name.Value -like 'Running' }).count
        $NotRunning = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.Placement.AvailabilityZone -eq $zone } | ? { $_.tags.Key -eq "CTXInstance" -and $_.Tags.Value -eq "CTXDesktop" } | ? { $_.State.Name.Value -notlike 'Running' }).count
        $total = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.Placement.AvailabilityZone -eq $zone } | ? { $_.tags.Key -eq "CTXInstance" -and $_.Tags.Value -eq "CTXDesktop" }).count

        $perc = ($Nowrunning / $total) * 100
        $perc = "{0:N2}" -f $perc

        Write-Host "Zone Name: $zone   Total instances: $total    Running: $Nowrunning   Not Running: $NotRunning   "   -NoNewline ; Write-host "Availability: $perc % "  -foregroundcolor "White" -backgroundcolor "Red"
    }



    $Offzones = @()
    $Offzones = "us-west-2b", "us-west-2c"

    foreach ($zone in $zones) {

        if ((Get-EC2AvailabilityZone -ZoneName $zone).State -notlike "Available") {
            $Offzones += $zone
        }

    }

    foreach ($zone in $zones) {
        if ($Offzones -notcontains $zone) {
            $iids = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.Placement.AvailabilityZone -eq $zone } | ? { $_.State.Name.Value -notlike 'Running' } | ? { $_.tags.Key -eq "CTXInstance" -and $_.Tags.Value -eq "CTXDesktop" }).InstanceId

            foreach ($iid in $iids) {
                StartVM $iid
            }
        }
    }
    $zones - $Offzones
    #### Zone wise availability ####
    foreach ($zone in $zones) {

        if ($Offzones -notcontains $zone) {
            $Nowrunning = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.Placement.AvailabilityZone -eq $zone } | ? { $_.tags.Key -eq "CTXInstance" -and $_.Tags.Value -eq "CTXDesktop" } | ? { $_.State.Name.Value -like 'Running' }).count
            $NotRunning = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.Placement.AvailabilityZone -eq $zone } | ? { $_.tags.Key -eq "CTXInstance" -and $_.Tags.Value -eq "CTXDesktop" } | ? { $_.State.Name.Value -notlike 'Running' }).count
            $total = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.Placement.AvailabilityZone -eq $zone } | ? { $_.tags.Key -eq "CTXInstance" -and $_.Tags.Value -eq "CTXDesktop" }).count

            $perc = ($Nowrunning / $total) * 100
            $perc = "{0:N2}" -f $perc

            Write-Host "Zone Name: $zone   Total instances: $total    Running: $Nowrunning   Not Running: $NotRunning   "   -NoNewline ; Write-host "Availability: $perc % "  -foregroundcolor "White" -backgroundcolor "Red"
        }
        else {
            Write-Host "Zone Name: $zone   "   -NoNewline ; Write-host "OFFLINE"  -foregroundcolor "White" -backgroundcolor "Red"
        }
    }

}
else {

    "The primary DDC server $DDC1 is running. So exiting the script"
}