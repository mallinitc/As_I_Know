#Citrix XenDesktop - Login issues - Script1

#Script1 - Reads all Login failures from DDC Server Event Logs and ingest them in DB
#Script2 - Reads those data & try to fix the VMs

$evt = Get-WinEvent -FilterHashtable @{"ProviderName" = "Citrix Broker Service"; "LogName" = "Application"; Level = 3; } -Computer <NAME> -MaxEvents 1 |
Select @{N = "ID"; E = { ([xml]$_.ToXml()).Event.EventData.Data[0].'#text' } },
@{N = "Image"; E = { ([xml]$_.ToXml()).Event.EventData.Data[1].'#text' } }, TimeCreated, Message, ID

if ($evt.Image -like 'SAC*') {
  $Loc = 'SAC'
  $DDC = '<NAME>'
}
else {
  $Loc = 'TPA'
  $DDC = '<NAME>'
}

$ID = $evt.Id
$user = $evt.ID
$user = $user.Replace("DOMAIN\", "")
$user = $user.Trim()
$EventTime = $evt.TimeCreated
$Image = $evt.Image
$msg = $evt.Message
$msg = $msg.Replace("'", "")


$SQLServer = "<NAME>"
$SQLDBName = "<NAME>"
$SqlConnection = New-Object System.Data.SqlClient.SqlConnection
$SqlConnection.ConnectionString = "Server = $SQLServer; Database = $SQLDBName; trusted_connection=True"
$SqlConnection.Open()
$SqlCmd = New-Object System.Data.SqlClient.SqlCommand
$SqlCmd.Connection = $SqlConnection



$time1 = Get-Date
$time2 = $time1.AddDays(-1)

#####################################################################
$SqlQuery = "SELECT *
  FROM [<NAME>].[dbo].[<NAME>]
  where EventCreated  between '$time2' and '$time1'"

$SqlCmd.CommandText = $SqlQuery
$SqlAdapter = New-Object System.Data.SqlClient.SqlDataAdapter
$SqlAdapter.SelectCommand = $SqlCmd
$DataSet = New-Object System.Data.DataSet
$SqlAdapter.Fill($DataSet)

$match = 0
foreach ($row in $DataSet.Tables[0].Rows) {
  $usr = $row[1].ToString().Trim()
  $evtID = $row[0].ToString().Trim()
  if (($user -eq $usr) -and ($evtID -eq $ID)) {
    $match = 1
  }
}
if ($match -eq 0) {

  $sqlsvr = "<NAME>"
  $database = "<NAME>"
  $table = "<NAME>"
  $conn = New-Object System.Data.SqlClient.SqlConnection
  $conn.ConnectionString = "Data Source=$sqlsvr;Initial Catalog=$database; Integrated Security=SSPI"
  $conn.Open()
  $cmd = $conn.CreateCommand()


  $cmd.CommandText = "INSERT INTO [<NAME>].[dbo].[<NAME>] ([EventID],[VZID],[Image],[Message],[Location],[EventCreated],[Resolved]) VALUES ('$id','$user','$Image','$msg','$Loc','$EventTime','0')"
  $cmd.ExecuteNonQuery()


}

#######################################################################
