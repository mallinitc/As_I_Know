#VMs that are inactive more than 90 days
#Send an EMAIL to respective assinged users


asnp *citrix*
asnp *vmware*
Import-Module activedirectory -ErrorAction SilentlyContinue

$a1 = Disconnect-VIServer NAME -Confirm:$false
$a2 = Disconnect-VIServer NAME -Confirm:$false

$SQLServer = "NAME"
$SQLDBName = "NAME"
$SqlConnection = New-Object System.Data.SqlClient.SqlConnection
$SqlConnection.ConnectionString = "Server = $SQLServer; Database = $SQLDBName; trusted_connection=True"
$SqlConnection.Open()
$SqlCmd = New-Object System.Data.SqlClient.SqlCommand
$SqlCmd.Connection = $SqlConnection

$Logs = "C:\Scripts\Prod\NonUsage\" + [string](Get-Date).Day + [string](Get-Date).Month + [string](Get-Date).Year + ".txt"

$imagetype = 'Private'
$time = Get-Date

$macs = @()
$macs = (Get-BrokerDesktop -AdminAddress NAME  -DesktopKind Private -MaxRecordCount 5000 | ? { $_.LastConnectionTime -ne $null } | ? { ($time - $_.LastConnectionTime).Days -gt 90 }).HostedMachineName
$macs += (Get-BrokerDesktop -AdminAddress NAME  -DesktopKind Private -MaxRecordCount 5000 | ? { $_.LastConnectionTime -ne $null } | ? { ($time - $_.LastConnectionTime).Days -gt 90 }).HostedMachineName
$macs.Count
foreach ($mac in $macs) {
      if (($mac -like 'VCA*') -or ($mac -like 'TUSCA*')) {
            $Site = 'NAME'
            $DDC = 'NAME'
            $VC = 'NAME'
            $Des = 'NAME'
            $DOU = "OU=Deprovisioned,OU=SAC,OU=dCloud,DC=NAME,DC=NAME,DC=NAME,DC=NAME"
      }
      else {
            $Site = 'NAME'
            $DDC = 'NAME'
            $VC = 'NAME'
            $Des = 'NAME'
            $DOU = "OU=Deprovisioned,OU=NAME,OU=NAME,DC=NAME,DC=NAME,DC=NAME,DC=com"
      }

      $LastTime = (Get-BrokerDesktop -AdminAddress $DDC -HostedMachineName $mac).LastConnectionTime
      $LastUser = (Get-BrokerDesktop -AdminAddress $DDC -HostedMachineName $mac).LastConnectionUser
      $image = (Get-BrokerDesktop -AdminAddress $DDC -HostedMachineName $mac).CatalogName
      $ID = (Get-BrokerDesktop -AdminAddress $DDC -HostedMachineName $mac).AssociatedUserNames
      $ID = $ID.Replace("NAME\", "")
      $ID = $ID.Trim()


      if (!((Get-ADUser $ID -properties *).MemberOf | ? { $_ -match "CN=*GRW-RemoteAccess*" -or $_ -match "CN=SAC_GRW" -or $_ -match "CN=SAC_GRW" })) {
            Set-BrokerPrivateDesktop -MachineName "NAME\$mac" -InMaintenanceMode $true -AdminAddress $DDC

            Connect-VIServer $vc -ErrorAction silentlycontinue
            Stop-VM $mac -Server $VC -Confirm:$false
            start-sleep -s 30
            Remove-BrokerMachine -MachineName "NAME\$mac" -DesktopGroup $image -AdminAddress $DDC
            Remove-BrokerMachine -MachineName "NAME\$mac" -Force -AdminAddress $DDC
            Move-VM $mac -Destination $Des
            Get-ADComputer $mac | Move-ADObject -TargetPath $DOU

            #Disconnect-VIServer $vc -ErrorAction silentlycontinue
            ########################################


            $Name = (Get-ADUser $ID).GivenName
            $MailID = (Get-ADUser $ID -Properties * ).EmailAddress
            $mgr = (Get-ADUser (Get-ADUser $ID -Properties *).Manager).SamAccountName
            $mgrmail = (Get-ADUser $mgr -Properties * ).EmailAddress
  
            $body = "Dear <b>$Name</b> <br><br>"
            $body += "&nbsp&nbsp&nbsp This mail is to inform you that the dCloud virtual desktop with hostname $mac ($image) assigned to you, was last accessed on $LastTime by user $LastUser.<b>So we have powered off $mac and removed access.</b>
If you want to retain this machine or take data, please reach out dCloud team with in next 14 days.<br><br>

Please note that this machine will be permanently removed after 14 days.<br><br>"


            $body += "Regards<br>NAME (NAME)<br>"

            Send-MailMessage -From "NAME" -To $MailID, $mgrmail -Subject "dCloud Image Removal- Notification"  -Body $body -SmtpServer NAME -BodyAsHtml -Priority High

            "$ID     $MailID    $mgr  $image  $mac" + "         90 Days">>$Logs

            if (!(Get-BrokerDesktop -AdminAddress NAME -Filter "HostedMachineName -notlike '$mac'" -AssociatedUserName NAME\$ID)) {
                  if (!(Get-BrokerDesktop -AdminAddress NAME -Filter "HostedMachineName -notlike '$mac'" -AssociatedUserName NAME\$ID)) {
                        $filter1 = "NAME*"
                        $filter2 = "NAME*"
                        $filter3 = "NAME*"
                        $filter4 = "NAME*"
                        $filter5 = "NAME"
                        $filter6 = "NAME"
                        if (!((get-ADUser $ID -properties *).MemberOf | ? { $_ -match "CN=$filter1" -or $_ -match "CN=$filter2" -or $_ -match "CN=$filter3" -or $_ -match "CN=$filter4" -or $_ -match "CN=$filter5" -or $_ -match "CN=$filter6" })) {
                              $date2 = (get-date).adddays(15).Date

                              ###Deprovision Requests need to be updated in VDAPS
                              $SqlQuery = "SELECT RequestID
FROM [NAME].[dbo].[NAME]
WHERE UserID = (SELECT UserID
FROM [NAME].[dbo].[NAME]
where ID='$ID') AND ProjectID = 1 AND RequestTypeID = 1 AND IsActive = 1"

                              $SqlCmd.CommandText = $SqlQuery
                              $SqlAdapter = New-Object System.Data.SqlClient.SqlDataAdapter
                              $SqlAdapter.SelectCommand = $SqlCmd
                              $DataSet = New-Object System.Data.DataSet
                              $SqlAdapter.Fill($DataSet)
                              $SqlCmd.CommandText = $SqlQuery
                              $SqlCmd.ExecuteNonQuery()

                              foreach ($row in $DataSet.Tables[0].Rows) {
                                    $RequestID = $row[0].ToString().Trim()
                              }

                              $SqlQuery1 = "INSERT INTO [NAME].[dbo].[NAME]
           ([Site]
           ,[Catalog]
           ,[ImageType]
           ,[NewImage]
           ,[Hostname]
           ,[User]
           ,[ADGroup]
           ,[Date]
           ,[IsCompleted]
           )
           VALUES
           ('$Site','$image','$imagetype','$image','$mac','$ID','NULL','$date2','1')"

                              $SqlCmd.CommandText = $SqlQuery1
                              $SqlCmd.ExecuteNonQuery()

                              $SqlQuery2 = "INSERT INTO [NAME].[dbo].[NAME]
           ([VZID],[VMHostName],[CreatedDate],[Location],[IsCompleted],[Updateddate])
     VALUES
           ('$ID','$mac','$date2','$Site',0,getdate())"

                              $SqlCmd.CommandText = $SqlQuery2
                              $SqlCmd.ExecuteNonQuery()

                              $SqlQuery3 = "update [NAME].[dbo].[NAME]
	set statusid=16,
DeprovisionedDate = getdate()
	where userid in (select userid from userinfo where vzid='$ID' and isactive=1)
	and isactive=1"
                              $SqlCmd.CommandText = $SqlQuery3
                              $SqlCmd.ExecuteNonQuery()

                              ####Deprovision table
                              $SqlQuery4 = "INSERT INTO [NAME].[dbo].[NAME]
  (RequestID,StatusID,ActionID,Comments,RequestTypeID,CreatedDate,CreatedBy,UpdatedDate,UpdatedBy,IsActive)
 VALUES('$RequestID',16,1,'Non-Usage - Depriovisioned By admin',1,GETDATE(),1,GETDATE(),1,1)"
                              $SqlCmd.CommandText = $SqlQuery4
                              $SqlCmd.ExecuteNonQuery()
                        }
                  }
            }
      }
}



