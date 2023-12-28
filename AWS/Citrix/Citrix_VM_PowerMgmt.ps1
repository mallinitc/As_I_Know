﻿
#Citrix Xendesktop hosted on AWS Cloud

#Citrix VM - Power Management

#Prompting with below options
#If VM is running then do you want to power it off? YES/NO
#If VM is not running then do you want to power it on? YES/NO


set-awsproxy -hostname proxy.ebiz.verizon.com -port 80

if (!(Get-Module -Name AnyBox)) {
    Import-Module -Name AnyBox
}
asnp Citrix*

$sh = New-Object -ComObject "Wscript.Shell"


#$id='DOMAIN\'+$env:USERNAME
$id = $env:USERDOMAIN + '\' + $env:USERNAME


#Logs
$log = $env:USERNAME + ".txt"
[string]$log = "C:\PSscripts\PWRAPPLogs\" + $log
$TimeNow = Get-Date
$logtime = get-date $TimeNow -f "MM-dd-yy HH:mm:ss"


#[string]$error=$log+"_Error.txt"
#[string]$data=$log+"_Info.txt"


#Install-Module -Name AnyBox (Using domain credentials) 

#set DDC address
# $ddcname=Get-BrokerController -MaxRecordCount 1 | select -ExpandProperty DNSName
$ddcname = '<IP>'

#$ddcname=(Get-BrokerController -State Active)[0].MachineName
#$ddcname=$ddcname.Replace("VZADCLOUD\","").Replace("-",".")

Add-Type -AssemblyName PresentationFramework

#get user ID
#$id='QVENDOR\12345'

#$id='ADEBP\'+$env:USERNAME
#$id=$id.Replace("DOMAIN\","").Replace("-",".")
#$id='QVendor\'+$env:USERNAME
#$id=$id.Replace("Qvendor\","").Replace("-",".")


$vdi = Get-BrokerMachine -DesktopGroupName '<Name>' -AssociatedUserName $id -AdminAddress $ddcname | Select DesktopGroupName, MachineName, RegistrationState, InMaintenanceMode
$vdicount = $vdi | measure
$vdicount = $vdicount.Count      
If ($vdicount -gt 1) {
    $vdi = $vdi | Out-GridView -Title "Select VDI Name in List Below" -OutputMode Single
}
ElseIf ($vdicount -le 0) {
    #[System.Windows.MessageBox]::show('No VDI Assigned, Exiting')
    $sh.Popup("No VDI Assigned, Exiting", 5, "Power App", 4096)
    "$logtime :: Error :: No VDI Assigned - $id" >>$log
    exit
}
If ($vdi -eq $null) {
    #[System.Windows.MessageBox]::show('No VDI Selected, Exiting')
    $sh.Popup("No VDI Assigned, Exiting", 5, "Power App", 4096)
    "$logtime :: Error :: No VDI Assigned - $id" >>$log
    exit
}
$awsip = $vdi.MachineName.ToString()
$awsip = $awsip.Replace('<DOMAIN>\', '')
$awsip = $awsip.Replace('-', '.')
if (($vdi.registrationState -like 'Registered') -and ($vdi.InMaintenanceMode)) {
    Get-BrokerMachine -MachineName $vdi.MachineName -AdminAddress $ddcname | Set-BrokerMachine -InMaintenanceMode $false
    $sh.Popup("Maintenance Mode is disabled, Try again.", 5, "Power App", 4096)
    "$logtime :: Info :: $awsip Maintenance Mode is disabled- $id" >>$log
}



Write-Progress -Activity "Getting Instance Powerstate" -Id 100
#Write-host "Getting current AWS Instance information" -ForegroundColor Yellow

$awsinstanceid = (Get-EC2Instance -Filter @{name = "private-ip-address"; value = "$awsip" }).Instances | select -ExpandProperty InstanceId
$instancestate = (Get-EC2Instance -InstanceId $awsinstanceid).Instances.state.name
clear

If ($instancestate -eq "Stopped") {
    Start-EC2Instance -InstanceId $awsinstanceid
    $counter = 0
    do {
        $counter = $counter + 1
        Write-Progress -Activity "Starting Instance" -Id 100 -PercentComplete $counter
        $instancestate = (Get-EC2Instance -InstanceId $awsinstanceid).Instances.state.name
        sleep -Seconds 2  
    }
    until(($instancestate -eq 'running') -or ($counter -ge 100))
    $counter = 0
    do {
        $counter = $counter + 1
        Write-Progress -Activity "Checking for Citrix Registration" -Id 100 -PercentComplete $counter
        $ctxready = Get-BrokerMachine -MachineName $vdi.MachineName -AdminAddress $ddcname | select -ExpandProperty RegistrationState
        sleep -Seconds 3
    }
    until(($ctxready -eq 'Registered') -or ($counter -ge 100))
    #[System.Windows.MessageBox]::Show("Your Infosys - DTS Desktop is ready for connection.")
    if ($ctxready -eq 'Registered') {
        if ((Get-BrokerMachine -MachineName $vdi.MachineName -AdminAddress $ddcname).InMaintenanceMode) {
            Get-BrokerMachine -MachineName $vdi.MachineName -AdminAddress $ddcname | Set-BrokerMachine -InMaintenanceMode $false
        }
        $sh.Popup("Your DTS Desktop is ready for connection.", 20, "Power App", 4096)
        "$logtime :: Info :: VM is started from OFF state- Citrix Registration Success $id VM: $awsip" >>$log
    }
    else {
        $sh.Popup("Your DTS Desktop is offline. Please contact support team.", 20, "Power App", 4096)
        "$logtime :: Error :: VM is started from OFF state- Citrix Registration failed  $id VM: $awsip" >>$log
    }
} 
Elseif ($instancestate -eq "Running") {


    $msgboxinput = Show-AnyBox -Message 'Your  AWS instance is already running.  Would you like to ?' -Buttons 'Restart', 'Shutdown', 'Cancel' -Topmost -Timeout 120
    if ($msgboxinput.Restart) {
        Write-Host "Restarting"
        Restart-EC2Instance -InstanceId $awsinstanceid
        sleep -Seconds 15
        $counter = 0
        do { 
        
            $counter = $counter + 1
            Write-Progress -Activity "Restaring Instance" -Id 100 -PercentComplete $counter
            $instancestate = (Get-EC2Instance -InstanceId $awsinstanceid).Instances.state.name 
            $ctxready = Get-BrokerMachine -MachineName $vdi.MachineName -AdminAddress $ddcname | select -ExpandProperty RegistrationState
            sleep -Seconds 2
        }until(($ctxready -eq 'Registered') -or ($counter -ge 100))
        #[System.Windows.MessageBox]::Show("The Instance has been Restarted.")
        if ($ctxready -eq 'Registered') {
            if ((Get-BrokerMachine -MachineName $vdi.MachineName -AdminAddress $ddcname).InMaintenanceMode) {
                Get-BrokerMachine -MachineName $vdi.MachineName -AdminAddress $ddcname | Set-BrokerMachine -InMaintenanceMode $false
            }
            $sh.Popup("Your DTS Desktop is ready for connection.", 20, "Power App", 4096)
            "$logtime :: Info :: VM is restarted - Citrix Registration Success  $id VM: $awsip" >>$log
        }
        else {
            $sh.Popup("Your DTS Desktop is offline. Please contact support team.", 20, "Power App", 4096)
            "$logtime :: Error :: VM is restarted - Citrix Registration failed  $id VM: $awsip" >>$log
        }
    }
    if ($msgboxinput.Shutdown) {
        "Shutting down"
        Stop-EC2Instance -InstanceId $awsinstanceid
        $counter = 0
        do { 
            $counter = $counter + 1
            Write-Progress -Activity "Stopping Instance" -Id 100 -PercentComplete $counter
            $instancestate = (Get-EC2Instance -InstanceId $awsinstanceid).Instances.state.name 
            sleep -Seconds 3
        }until (($instancestate -eq 'stopped') -or ($counter -ge 100))
        #[System.Windows.MessageBox]::Show("The Instance has been shutdown.")
        $sh.Popup("The Instance has been shutdown.", 5, "Power App", 4096)
        "$logtime :: Info :: VM is powered off $id VM: $awsip" >>$log
    }
    if ($msgboxinput.Cancel) {
        Write-Host "Cancelling"
        Write-Host "$logtime :: Info :: Cancelled $id VM: $awsip" >>$log
        exit
    }
    if ($msgboxinput.TimedOut) {
        Write-Host "Timeout"
        "$logtime :: Info :: Timedout $id VM: $awsip" >>$log
        exit
    }
}
Else {
    #[System.Windows.MessageBox]::Show("The Instance is booting or shutting down. Run the applciation later.")
    $sh.Popup("Your Instance is booting or shutting down due to technical issue. So please contact Verizon Service Desk for help.", 5, "Power App", 4096)
    "$logtime :: Error :: The DTS Desktop : $awsip is booting or shutting due to technical issue" >>$log

}

exit

