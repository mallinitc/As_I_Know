#Citrix User Logins - Report EMAIL


##----- Start of the script -----
$RptBody = $null


#=====================================================================================
$recipients = "EMAIL"
$fromEmail = "EMAIL"
$SMTPserver = "STRING"
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
#$RptHeader+= "<h2><font color='purple' face='cambria'>CAG connections Report - $currentTime </font></h2>"



$SQLServer = "<NAME>"
$SQLDBName = "NAME"
$SqlConnection = New-Object System.Data.SqlClient.SqlConnection
$SqlConnection.ConnectionString = "Server = $SQLServer; Database = $SQLDBName; trusted_connection=True"
$SqlConnection.Open()
$SqlCmd = New-Object System.Data.SqlClient.SqlCommand
$SqlCmd.Connection = $SqlConnection



$time1 = Get-Date
$time2 = $time1.AddHours(-1)

#####################################################################
$SqlQuery = "SELECT City,COUNT(UserName)as Count
  FROM [NAME].[dbo].[NAME]
  where Date  between '$time2' and '$time1'
  group by City"

$SqlCmd.CommandText = $SqlQuery
$SqlAdapter = New-Object System.Data.SqlClient.SqlDataAdapter
$SqlAdapter.SelectCommand = $SqlCmd
$DataSet = New-Object System.Data.DataSet
$SqlAdapter.Fill($DataSet)

$RptBody += "<h2><font color='#2F4F4F' face='cambria'><u>CAG Location Count</u> </font></h2>"
$RptBody += "<table border=0>"
$RptBody += "<tr>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Location</font></th>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Count</font></th>"
$RptBody += "</tr>"


foreach ($row in $DataSet.Tables[0].Rows) {
  $loc = $row[0].ToString().Trim()
  $count = $row[1].ToString().Trim()
  $RptBody += "<tr><td>$loc</td>" + "<td>$count</td></tr>"

}
$RptBody += "</table>"
$RptBody += "<br><br>"
 
#####################################################################

$SqlQuery = "SELECT Location,COUNT(UserName)as Count
  FROM [NAME].[dbo].[NAME]
  where Date  between '$time2' and '$time1'
  group by Location"

$SqlCmd.CommandText = $SqlQuery
$SqlAdapter = New-Object System.Data.SqlClient.SqlDataAdapter
$SqlAdapter.SelectCommand = $SqlCmd
$DataSet = New-Object System.Data.DataSet
$SqlAdapter.Fill($DataSet)

$RptBody += "<h2><font color='#556B2F' face='cambria'><u>CAG Site Count</u> </font></h2>"
$RptBody += "<table border=0>"
$RptBody += "<tr>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Site</font></th>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Count</font></th>"
$RptBody += "</tr>"


foreach ($row in $DataSet.Tables[0].Rows) {
  $loc = $row[0].ToString().Trim()
  $count = $row[1].ToString().Trim()
  $RptBody += "<tr><td>$loc</td>" + "<td>$count</td></tr>"

}
$RptBody += "</table>"
$RptBody += "<br><br>"
 
#####################################################################
$SqlQuery = "SELECT DHName,COUNT(UserName)as Count
  FROM [NAME].[dbo].[NAME]
  where Date  between '$time2' and '$time1'
  group by DHName"

$SqlCmd.CommandText = $SqlQuery
$SqlAdapter = New-Object System.Data.SqlClient.SqlDataAdapter
$SqlAdapter.SelectCommand = $SqlCmd
$DataSet = New-Object System.Data.DataSet
$SqlAdapter.Fill($DataSet)

$RptBody += "<h2><font color='#FF4500' face='cambria'><u>CAG DH-wise Count</u> </font></h2>"
$RptBody += "<table border=0>"
$RptBody += "<tr>"
$RptBody += "<th><font color='midnightblue' face='cambria'>DH Name</font></th>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Count</font></th>"
$RptBody += "</tr>"


foreach ($row in $DataSet.Tables[0].Rows) {
  $dhname = $row[0].ToString().Trim()
  $count = $row[1].ToString().Trim()
  $RptBody += "<tr><td>$dhname</td>" + "<td>$count</td></tr>"

}
$RptBody += "</table>"
$RptBody += "<br><br>"
 
#####################################################################

$SqlQuery = "SELECT UserName, max(LoginTime)as LoginTime,CONVERT(VARCHAR(10),LoginTime,10)AS Date, CONVERT(VARCHAR(10),LoginTime,108)As Time
  FROM [NAME].[dbo].[NAME]
  where Date  between '$time2' and '$time1'
  group by UserName,LoginTime"

$SqlCmd.CommandText = $SqlQuery
$SqlAdapter = New-Object System.Data.SqlClient.SqlDataAdapter
$SqlAdapter.SelectCommand = $SqlCmd
$DataSet = New-Object System.Data.DataSet
$SqlAdapter.Fill($DataSet)

$RptBody += "<h2><font color='#FF4500' face='cambria'><u>CAG Connections Details</u> </font></h2>"
$RptBody += "<table border=0>"
$RptBody += "<tr>"
$RptBody += "<th><font color='midnightblue' face='cambria'>User</font></th>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Date</font></th>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Time</font></th>"
$RptBody += "<th><font color='midnightblue' face='cambria'>Connection Type</font></th>"
$RptBody += "</tr>"


foreach ($row in $DataSet.Tables[0].Rows) {
  $name = $row[0].ToString().Trim()
  $datee = $row[2].ToString().Trim()
  $timee = $row[3].ToString().Trim()
  $RptBody += "<tr><td>$name</td>" + "<td>$datee</td>" + "<td>$timee</td>" + "<td>dCloud CAG</td>" + "</tr>"

}
$RptBody += "</table>"
$RptBody += "<br><br>"

$RptBody += "<br><br><h1><font color='#000080' face='cambria'>dCloud-Admins</font></h1><br>"

$RptFooter += "</body></html>"





$emailBody = $RptHeader + $RptBody + $RptFooter

send-mailmessage -from $fromEmail -to $recipients -subject "CAG Connections Report - dCloud | $currentTime" -body $emailBody -SmtpServer $SMTPserver -BodyAsHtml

