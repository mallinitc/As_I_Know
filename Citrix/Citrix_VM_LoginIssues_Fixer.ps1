#Citrix XenDesktop - Login Issues - Fixing through Powershell

#This reads the DDC server Event Logs & depends on the Event IDs - Script will fix the VM login issues




##Restart Function

function RestartVM {
  $vm = $args[0]

  if ((Get-VM $vm -Server $VC).Powerstate -like 'Poweredon') {
    Restart-VM -VM $VM  -Server $VC -runAsync -Confirm:$false
  }
  else {
    Start-VM -VM $VM -Server $VC  -runAsync -Confirm:$false
  }
  Start-Sleep -Seconds 90;

  $count = 0
  do {

    if (Test-Connection -ComputerName $vm -Count 2) {
      $count
      $Global:Log += "The machine restarted & is online now"
      break
    }
    else {
      $count++
      if ($count -eq 7) {
        Invoke-WmiMethod -Class Win32_Process -ComputerName "$endmac" -Name Create -ArgumentList "C:\Windows\System32\msg.exe * The Restart operation is taking more than usual time. Please reach out Admins through VoIP/mobile"
        $Global:Log += "Restart taking loner time"
        break
      }
      Start-Sleep -Seconds 15;
    }

  }while ($Count -le 6);

}


###RegistrationCheck function
function RegVM {
  $vm = $args[0]

  $count = 0
  do {

    if ((Get-BrokerDesktop -AdminAddress $ddc -HostedMachineName $vm).RegistrationState -like 'Registered') {
      $count
      $Global:result = 1
      $Global:Log += "The machine is registered"
      break
    }
    else {
      $count++
      if ($count -eq 7) {
        Invoke-WmiMethod -Class Win32_Process -ComputerName "$endmac" -Name Create -ArgumentList "C:\Windows\System32\msg.exe * The VM Registration is taking more than usual time. Please reach out Admins through VoIP/mobile"
        $Global:Log += "VM Registration is taking more than usual time"
        break
      }
      Start-Sleep -Seconds 15;
    }

  }while ($Count -le 6);

}

##Function Updating the Table
function UpdateTable {
  $res = $args[0]
  $eventID = $args[1]
  $usrID = $args[2]
  $hst = $args[3]
  $time = Get-Date

  $SQLServer = "<NAME>"
  $SQLDBName = "<NAME>"
  $SqlConnection = New-Object System.Data.SqlClient.SqlConnection
  $SqlConnection.ConnectionString = "Server = $SQLServer; Database = $SQLDBName; trusted_connection=True"
  $SqlConnection.Open()
  $SqlCmd = New-Object System.Data.SqlClient.SqlCommand
  $SqlCmd.Connection = $SqlConnection


  if ($res -eq 1) {

    $sqlquery = "Update [<NAME>].[dbo].[<TABLE>]
Set Resolved=1, Hostname='$hst', ResolvedTime='$time',ActionTaken='$Global:Log'
where EventID='$eventID' and VZID='$usrID'" 

    $SqlCmd.CommandText = $SqlQuery
    $SqlCmd.ExecuteNonQuery() 
  }
  else {
    $sqlquery = "Update [<NAME>].[dbo].[<NAME>]
Set Resolved=0, Hostname='$hst', ResolvedTime='$time',ActionTaken='$Global:Log'
where EventID='$eventID' and VZID='$usrID'" 

    $SqlCmd.CommandText = $SqlQuery
    $SqlCmd.ExecuteNonQuery() 
  }
}



$Global:result = 0
[string]$Global:Log = @()

$SQLServer = "<NAME>"
$SQLDBName = "<NAME>"
$SqlConnection = New-Object System.Data.SqlClient.SqlConnection
$SqlConnection.ConnectionString = "Server = $SQLServer; Database = $SQLDBName; trusted_connection=True"
$SqlConnection.Open()
$SqlCmd = New-Object System.Data.SqlClient.SqlCommand
$SqlCmd.Connection = $SqlConnection


#####################################################################
$SqlQuery = "SELECT *
  FROM [<NAME>].[dbo].[<NAME>]
  where Resolved=0"

$SqlCmd.CommandText = $SqlQuery
$SqlAdapter = New-Object System.Data.SqlClient.SqlDataAdapter
$SqlAdapter.SelectCommand = $SqlCmd
$DataSet = New-Object System.Data.DataSet
$SqlAdapter.Fill($DataSet)

$match = 0
foreach ($row in $DataSet.Tables[0].Rows) {
  $usr = $row[1].ToString().Trim()
  $evtID = $row[0].ToString().Trim()
  $Loc = $row[5].ToString().Trim()
  $Image = $row[3].ToString().Trim()

  if ($Loc -like 'SAC') {
    $DDC = '<NAME>'
    $VC = '<NAME>'
  }
  else {
    $DDC = '<NAME>'
    $VC = '<NAME>'
  }

  Disconnect-VIServer $VC -Confirm:$false
  Connect-VIServer $VC -Force

  $cat = (Get-BrokerDesktopGroup -PublishedName $image -AdminAddress $ddc).Name
  $machine = Get-BrokerDesktop -AdminAddress $ddc -AssociatedUserName <DOMAIN>\$usr -CatalogName $cat
  $vm = $machine.HostedMachineName
  #$endmac=$machine.ClientName
  $endmac = '<NAME>'
  $name = (Get-ADUser $usr).GivenName



  Invoke-WmiMethod -Class Win32_Process -ComputerName "$endmac" -Name Create -ArgumentList "C:\Windows\System32\msg.exe * Hello! $($name) We are working on your machine to fix the login issue. Please wait..."
  $Global:Log += "Started"

  if ($EvtID -eq '1105') {

    if ($machine.DesktopKind -like "Private") {
      if ((Get-BrokerDesktop -AdminAddress $ddc -HostedMachineName $vm).RegistrationState -eq 'Registered') {
        Set-BrokerPrivateDesktop -MachineName "DOMAIN\$vm" -InMaintenanceMode $false -AdminAddress $ddc
        $Global:Log += "Disabled mainteneace mode on $vm"
        $Global:result = 1
      }
      else {
        #Checking if machine is powered OFF
        RestartVM $vm
        RegVM $vm
        if ($Global:result -eq 1) {
          Set-BrokerPrivateDesktop -MachineName "DOMAIN\$vm" -InMaintenanceMode $false -AdminAddress $ddc
          $Global:Log += "Disabled mainteneace mode on $vm"
        }
      }
    }
    else {
      #Readonly-checking if any VM is assinged at all
      if ((Get-BrokerDesktop -AdminAddress $ddc -HostedMachineName $vm).RegistrationStatus -eq 'Registered') {
        Set-BrokerSharedDesktop -MachineName "DOMAIN\$vm" -InMaintenanceMode $false -AdminAddress $ddc
        $Global:Log += "Disabled mainteneace mode on $vm"
        $Global:result = 1
      }
      else {
        #Checking if the delivary Group is under maintenance mode
        if ((Get-BrokerDesktopGroup -AdminAddress $ddc -Name $cat).InMaintenanceMode) {
          Invoke-WmiMethod -Class Win32_Process -ComputerName "$endmac" -Name Create -ArgumentList "C:\Windows\System32\msg.exe * Hello! $($name) The Catalog $($cat) you are trying to access is under MaintenanceMode. Please reach out dCloud Support team"
          $Global:Log += "Catalog is under Maintenance"
        }
        else {
          #If catalog is not under Maintenance mode & read only VM is Unregistered. Have to restart to relase the current VM

        }
      }

    }
    if ($Global:result -eq 1) {
      Invoke-WmiMethod -Class Win32_Process -ComputerName "$endmac" -Name Create -ArgumentList "C:\Windows\System32\msg.exe * Hello! $($name) we have disabled Maintenance Mode on your machine. Please try accessing now."
      UpdateTable $Global:result $evtID $usr $vm
      $Global:Log += "Issue is Fixed"
    }
    else {
      Invoke-WmiMethod -Class Win32_Process -ComputerName "$endmac" -Name Create -ArgumentList "C:\Windows\System32\msg.exe * Hello! $($name) The issue couldn't be fixed. Please reach out dCloud Support team"
      UpdateTable $Global:result $evtID $usr $vm
      $Global:Log += "issue couldn't be fixed"
    }

  }

  elseif ($EvtID -eq '1101') {
    ### Machine is under iSYS repair page and unregister in DDC
    if (!(Test-Connection -ComputerName $vm -Count 2)) {
      Invoke-WmiMethod -Class Win32_Process -ComputerName "$endmac" -Name Create -ArgumentList "C:\Windows\System32\msg.exe * Hello! $($name) The VM is unreachable via network. Please wait while we restart your machine.This may take around 5 min."
      ##Machine Restart
      RestartVM $vm
      RegVM $vm

    }
    else {
      #Machine is pingable
      #Need to Check Overall status
      $OverallStatus = (Get-VM $vm | select *).extensionData.OverallStatus;
      if ($OverallStatus -ne "green") {
        Invoke-WmiMethod -Class Win32_Process -ComputerName "$endmac" -Name Create -ArgumentList "C:\Windows\System32\msg.exe * Hello! $($name) VMware tools is not in running status. So we are restarting your machine. Please wait while we restart your machine.This may take around 5 min."
        #Machine Reboot


      }

    }
  }

  elseif ($EvtID -eq '1102') {
    #RestartVM
    RestartVM $vm
    RegVM $vm
  }

}#End ofEvtLOgs

