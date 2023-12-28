##----- Start of the script -----
$RptBody = $null
# Load Citrix PowerShell modules
Asnp Citrix.*

#=====================================================================================
$recipients = "NAME"
$fromEmail = "NAME"
$SMTPserver = "NAME"
$currentTime = Get-Date -Format "yyyy-MM-dd | hh:mm:ss tt"
$date1 = (get-date).Date
#=====================================================================================

$RptHeader = "<!DOCTYPE html>"
$RptHeader += "<html>"
$RptHeader += "<head>"
$RptHeader += "<style>"
$RptHeader += "table,th,td"
$RptHeader += "{ border:1px solid black; }"
$RptHeader += "</style>"
$RptHeader += "</head>"
$RptHeader += "<body>"
$RptHeader += "<h2><font color='purple' face='cambria'>Daily Health Status Report - $currentTime </font></h2>"


$SQLServer = "NAME"
$SQLDBName = "NAME"
$SqlConnection = New-Object System.Data.SqlClient.SqlConnection
$SqlConnection.ConnectionString = "Server = $SQLServer; Database = $SQLDBName; trusted_connection=True"
$SqlConnection.Open()
$SqlCmd = New-Object System.Data.SqlClient.SqlCommand
$SqlCmd.Connection = $SqlConnection
$SqlCmd1 = New-Object System.Data.SqlClient.SqlCommand
$SqlCmd1.Connection = $SqlConnection
 
$SqlQuery = "declare  @tempTable table(CPUDate date)
declare @LastLogin datetime
set @LastLogin = (SELECT TOP 1 [Date] FROM [NAME].[dbo].[NAME] where  State='Inuse' order by Date desc);
insert into @tempTable 
select  DISTINCT TOP 7 CAST (DATE AS DATE)  from Resource 
order by CAST (DATE AS DATE)  desc
;
With myCTE (VZID,HOSTNAME,CPUDATE,AVGCPU,AVGMEM) as 
(
SELECT VZID,HOSTNAME, cast([Date] as date),Round(AVG([CPU]),0),Round(AVG([Mem]),0)
	FROM [NAME].[dbo].[NAME]
	where  CAST(dATE AS dATE) IN (
	select  DISTINCT TOP 7 CAST (DATE AS DATE)  from Resource 
order by CAST (DATE AS DATE)  desc
	) and LEN(VZID) > 0 
	Group by cast([Date] as date),ID,HOSTNAME having Round(AVG([CPU]),0) >= 90 or Round(AVG([Mem]),0) >= 90 
	)
	select distinct VZID, HOSTNAME,AVG(avgcpu)as 'AVGCPU',AVG(AvgMem) as 'AVGMEM' from (select VZID, HOSTNAME ,c.CPUDATE, isnull(Round(Avg(Avgcpu),0),0) as 'AvgCPU', isnull(Round(Avg(AVGMEM),0),0) as 'AvgMem',
	 ROW_NUMBER() OVER (PARTITION BY [ID] ORDER BY c.CPUDATE ) as RowNumber
	 from myCTE c 
	 join @tempTable t on c.CPUDATE = cast(t.CPUDate as date)	
	group by c.CPUDATE,ID,HOSTNAME) as T where RowNumber >= 4 Group by VZID, HOSTNAME"

  
$SqlCmd.CommandText = $SqlQuery
$SqlAdapter = New-Object System.Data.SqlClient.SqlDataAdapter
$SqlAdapter.SelectCommand = $SqlCmd
$DataSet = New-Object System.Data.DataSet
$SqlAdapter.Fill($DataSet)


#Get CPU/MEM
$RptBody += "<h2><font color='purple' face='cambria'><u>High Cpu - Memory</u> </font></h2>"
$RptBody += "<table border=0>"
$RptBody += "<tr>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Machine Name</font></th>"
$RptBody += "<th><font color='midnightblue' face='cambria'>VZID</font></th>"
$RptBody += "<th><font color='midnightblue' face='cambria'>CPU</font></th>"
$RptBody += "<th><font color='midnightblue' face='cambria'>MEM</font></th>"
$RptBody += "</tr>"

foreach ($row in $DataSet.Tables[0].Rows) {    
    $hostname = $row[1].ToString().Trim()
    $vzid = $row[0].ToString().Trim()
    $cpu = $row[2].ToString().Trim()
    $mem = $row[3].ToString().Trim()

    $RptBody += "<tr><td>$hostname</td>" + "<td>$id</td>" + "<td>$cpu</td>" + "<td>$Mem</td> </tr>"
}
$RptBody += "</table>"
$RptBody += "<br><br>"


#Get unregistered VMs
$RptBody += "<b><font color='purple' face='cambria'><u> UNREGISTERED MACHINES</u></font></b><br><br>"
$unregVMs = Get-BrokerDesktop -AdminAddress NAME -MaxRecordCount 5000 -PowerActionPending $false | ? { ($_.RegistrationState -eq 'Unregistered') -and ($_.PowerState -eq 'On') }

$RptBody += "<table border=0>"
$RptBody += "<tr>"
$RptBody += "<th><font color='midnightblue' face='cambria'><u>Machine Name</u></font></th><th/>"
$RptBody += "<th><font color='midnightblue' face='cambria'><u>Desktop Group Name</u></font></th><th/>"
$RptBody += "<th><font color='midnightblue' face='cambria'><u>Reason for Last Deregistration</u></font></th>"
$RptBody += "</tr>"

foreach ($unregVM in $unregVMs) {
    $RptBody += "<tr><td>" + $unregVM.HostedMachineName + "</td>" + "<td/>" + "<td>" + $unregVM.DesktopGroupName + "</td>" + "<td/>" + "<td>" + $unregVM.LastDeregistrationReason + "</td></tr>"
    $hostname1 = "$($unregVM.HostedMachineName)"
    $vzid = "$($unregVM.AssociatedUserNames)"
    $reason = "Unregister"
    $Sql = "INSERT INTO [NAME].[dbo].[NAME] ([NAME],[Reason],[Date],[Vzid]) VALUES ('$hostname1','$reason','$date1','$vzid')"
    $SqlCmd.CommandText = $Sql
    $SqlCmd.ExecuteNonQuery()
 
}
$RptBody += "</table>"
$RptBody += "<br><br>"

$RptBody += "<b><font color='purple' face='cambria'><u> UNREGISTERED MACHINES</u></font></b><br><br>"
$unregVMs1 = Get-BrokerDesktop -AdminAddress NAME -MaxRecordCount 5000 -PowerActionPending $false | ? { ($_.RegistrationState -eq 'Unregistered') -and ($_.PowerState -eq 'On') }
$RptBody += "<table border=0>"
$RptBody += "<tr>"
$RptBody += "<th><font color='midnightblue' face='cambria'><u>Machine Name</u></font></th><th/>"
$RptBody += "<th><font color='midnightblue' face='cambria'><u>Desktop Group Name</u></font></th><th/>"
$RptBody += "<th><font color='midnightblue' face='cambria'><u>Reason for Last Deregistration</u></font></th>"
$RptBody += "</tr>"

foreach ($unregVM in $unregVMs1) {
    $RptBody += "<tr><td>" + $unregVM.HostedMachineName + "</td>" + "<td/>" + "<td>" + $unregVM.DesktopGroupName + "</td>" + "<td/>" + "<td>" + $unregVM.LastDeregistrationReason + "</td></tr>"
    $hostname1 = "$($unregVM.HostedMachineName)"
    $vzid = "$($unregVM.AssociatedUserNames)"
    $reason = "Unregister"
    $Sql = "INSERT INTO [NAME].[dbo].[NAME] ([NAME],[Reason],[Date],[Vzid]) VALUES ('$hostname1','$reason','$date1','$vzid')"
    $SqlCmd.CommandText = $Sql
    $SqlCmd.ExecuteNonQuery()
}
$RptBody += "</table>"
$RptBody += "<br><br>"

#Get maintenance mode VMs
$RptBody += "<b><font color='purple' face='cambria'><u> MACHINES IN MAINTENANCE MODE</u></font></b><br><br>"
$maintModeVMs = (Get-BrokerDesktop -AdminAddress NAME -MaxRecordCount 5000 | ? { $_.InMaintenanceMode -eq 'True' })

$RptBody += "<table border=0>"
$RptBody += "<tr>"
$RptBody += "<th><font color='midnightblue' face='cambria'><u>Machine Name</u></font></th><th/>"
$RptBody += "<th><font color='midnightblue' face='cambria'><u>Desktop Group Name</u></font></th><th/>"
$RptBody += "</tr>"

foreach ($maintModeVM in $maintModeVMs) {
    $RptBody += "<tr><td>" + $maintModeVM.HostedMachineName + "</td>" + "<td/>" + "<td>" + $maintModeVM.DesktopGroupName + "</td>" + "<td/>" + "</td></tr>"
    $hostname1 = "$($maintModeVM.HostedMachineName)"
    $vzid = "$($maintModeVM.AssociatedUserNames)"
    $reason = "Maintenance"
    $Sql = "INSERT INTO [NAME].[dbo].[NAME] ([Hostname],[Reason],[Date],[Vzid]) VALUES ('$hostname1','$reason','$date1','$vzid')"
    $SqlCmd.CommandText = $Sql
    $SqlCmd.ExecuteNonQuery()
}
$RptBody += "</table>"
$RptBody += "<b><font color='purple' face='cambria'><u> MACHINES IN MAINTENANCE MODE</u></font></b><br><br>"
$maintModeVMs1 = (Get-BrokerDesktop -AdminAddress NAME -MaxRecordCount 5000 | ? { $_.InMaintenanceMode -eq 'True' })

$RptBody += "<table border=0>"
$RptBody += "<tr>"
$RptBody += "<th><font color='midnightblue' face='cambria'><u>Machine Name</u></font></th><th/>"
$RptBody += "<th><font color='midnightblue' face='cambria'><u>Desktop Group Name</u></font></th><th/>"
$RptBody += "</tr>"

foreach ($maintModeVM in $maintModeVMs1) {
    $RptBody += "<tr><td>" + $maintModeVM.HostedMachineName + "</td>" + "<td/>" + "<td>" + $maintModeVM.DesktopGroupName + "</td>" + "<td/>" + "</td></tr>"
    $hostname1 = "$($maintModeVM.HostedMachineName)"
    $vzid = "$($maintModeVM.AssociatedUserNames)"
    $reason = "Maintenance"
    $Sql = "INSERT INTO [NAME].[dbo].[NAME] ([Hostname],[Reason],[Date],[Vzid]) VALUES ('$hostname1','$reason','$date1','$id')"
    $SqlCmd.CommandText = $Sql
    $SqlCmd.ExecuteNonQuery()
}
$RptBody += "</table>"
$RptBody += "<br><br>"

$RptBody += "<b><font color='purple' face='cambria'><u> High Profile Load time</u></font></b><br><br>"
$HighSacs = (Get-BrokerDesktop -AdminAddress NAME -DesktopCondition UPMLogonTime | select HostedMachineName, CatalogName, AssociatedUserNames)


$RptBody += "<table border=0>"
$RptBody += "<tr>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Machine Name</font></th><th/>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Desktop Group Name</font></th><th/>"
$RptBody += "<th><font color='midnightblue' face='cambria'>vzid</font></th><th/>"
$RptBody += "</tr>"

foreach ($HighSac in $HighSacs) {
    $RptBody += "<tr><td>" + $HighSAC.HostedMachineName + "</td>" + "<td/>" + "<td>" + $HighSAC.CatalogName + "</td>" + "<td/>" + "<td>" + $HighSAC.AssociatedUserNames + "</td>" + "<td/>" + "</td></tr>"
    $hostname1 = "$($HighSAC.HostedMachineName)"
    $vzid = "$($HighSAC.AssociatedUserNames)"
    $reason = "HighProfile"
    $Sql = "INSERT INTO [NAME].[dbo].[NAME] ([Hostname],[Reason],[Date],[Vzid]) VALUES ('$hostname1','$reason','$date1','$vzid')"
    $SqlCmd.CommandText = $Sql
    $SqlCmd.ExecuteNonQuery()
}
$RptBody += "</table>"
$RptBody += "<br><br>"

$RptBody += "<b><font color='purple' face='cambria'><u> High Profile Load time</u></font></b><br><br>"
$HighTpas = (Get-BrokerDesktop -AdminAddress NAME -DesktopCondition UPMLogonTime | select HostedMachineName, CatalogName, AssociatedUserNames)


$RptBody += "<table border=0>"
$RptBody += "<tr>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Machine Name</font></th><th/>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Desktop Group Name</font></th><th/>"
$RptBody += "<th><font color='midnightblue' face='cambria'>vzid</font></th><th/>"
$RptBody += "</tr>"

foreach ($HighTpa in $HighTpas) {
    $RptBody += "<tr><td>" + $HighTpa.HostedMachineName + "</td>" + "<td/>" + "<td>" + $HighTpa.CatalogName + "</td>" + "<td/>" + "<td>" + $HighTpa.AssociatedUserNames + "</td>" + "<td/>" + "</td></tr>"
    $hostname1 = "$($HighTpa.HostedMachineName)"
    $vzid = "$($HighTpa.AssociatedUserNames)"
    $reason = "HighProfile"
    $Sql = "INSERT INTO [NAME].[dbo].[NAME] ([Hostname],[Reason],[Date],[Vzid]) VALUES ('$hostname1','$reason','$date1','$vzid')"
    $SqlCmd.CommandText = $Sql
    $SqlCmd.ExecuteNonQuery()
}
$RptBody += "</table>"
$RptBody += "<br><br>"

$RptBody += "<h2><font color='purple' face='cambria'><u>Repeated Unreg/Maintenance</u> </font></h2>"
$RptBody += "<table border=0>"
$RptBody += "<tr>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Machine Name</font></th>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Reason</font></th>"
$RptBody += "</tr>"
    

$sqlQuery1 = "select distinct hostname, Reason FROM [NAME].[dbo].[NAME]
  where date > dateadd(dd,-2,getdate())
  group by hostname, Reason
  having count(Hostname)>1
  order by Reason desc"  
  
$sqlcmd1.commandText = $sqlQuery1
$SqlAdapter1 = New-Object System.Data.SqlClient.SqlDataAdapter
$SqlAdapter1.SelectCommand = $SqlCmd1
$DataSet1 = New-Object System.Data.DataSet
$SqlAdapter1.Fill($DataSet1)
        
foreach ($row1 in $DataSet1.Tables[0].Rows) {    
    $hostname = $row1[0].ToString().Trim()
    $Res = $row1[1].ToString().Trim()

    $RptBody += "<tr><td><font color='Red'>$hostname</font></td>" + "<td><font color='Red'>$Res</font></td>" + "</tr>"
}
$RptBody += "</table>"
$RptBody += "<br><br>"

$RptBody += "<br><br><font color='Darksilver' face='cambria'>NAME-NAME | NAME |NAME NAME</font><br>"
$RptBody += "</table>"

$RptFooter += "</body></html>"

$emailBody = $RptHeader + $RptBody + $RptFooter
#=====================================================================================
#=====================================================================================

send-mailmessage -from $fromEmail -to $recipients -subject "Daily Health Check | $currentTime" -body $emailBody -SmtpServer $SMTPserver -BodyAsHtml -Priority High


##----- End of the script -----

