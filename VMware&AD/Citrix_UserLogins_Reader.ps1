#Citrix User Logins - Reader


Add-PSSnapin *citrix*
Set-ExecutionPolicy 1 -Force


$time = Get-Date
$output = @()
#XenApp Exisiting Sessions
#$output=Get-XASession | ?{$_.State -eq 'Active' -AND $_.Protocol -eq 'Ica'}|select ServerName,BrowserName,AccountName,LogOnTime
$output = Get-BrokerDesktop -AdminAddress NAME -MaxRecordCount 5000 -Filter "ClientAddress -like '192*'" -SessionState Active | select SessionUserName, CatalogName, ClientAddress, ClientName, SessionStateChangeTime
$output += Get-BrokerDesktop -AdminAddress NAME -MaxRecordCount 5000 -Filter "ClientAddress -like '192*'" -SessionState Active | select SessionUserName, CatalogName, ClientAddress, ClientName, SessionStateChangeTime


$sqlsvr = "NAME"
$database = "NAME"
$table = "NAME"
$conn = New-Object System.Data.SqlClient.SqlConnection
$conn.ConnectionString = "Data Source=$sqlsvr;Initial Catalog=$database; Integrated Security=SSPI"
$conn.Open()
$cmd = $conn.CreateCommand()



foreach ($row in $output) {
    #Write-Host "$row.SessionUserName   $row.CatalogName  $row.ClientAddress $row.ClientName, $row.SessionStateChangeTime"
    $vzid = $row.SessionUserName
    $vzid = $vzid.Trim()
    $vzid = $vzid.Replace("DOMAIN\", "")
    $Catalog = $row.CatalogName
    $EndIP = $row.ClientAddress
    $Login = $row.SessionStateChangeTime


    $id = $vzid

    if (((Get-Aduser $id -Properties *).Title -ne $null)) {
        while ((Get-Aduser $id -Properties *).Title -notlike '*Delivery Head*') {
            $Sname = @()
            $SName = Get-ADUser ((Get-Aduser $id -Properties *).Manager)
            if ($Sname -ne $null)
            { $id = $SName.SamAccountName }
            else { break; }

        }
    }
    $DHID = $id
    $Name = (Get-ADUser $id).Name
    $City = (Get-ADUser -Properties * $id).City
    $DHName = (Get-ADUser $DHID).Name

    if ($row.CatalogName -like 'SAC*') {
        $Site = 'SAC'
    }
    else { $Site = 'TPA' }

    #"$vzid  ++ $Name ++ $City  ++  $DHID  ++ $DHName"


    $cmd.CommandText = "INSERT INTO [NAME].[dbo].[NAME] ([Username],[CatalogName],[EndpointIP],[LoginTime],[Location],[Date],[City],[DHName],[DHID]) VALUES ('$vzid','$Catalog','$EndIP','$Login','$Site','$time','$City','$DHName','$DHID')"
    $cmd.ExecuteNonQuery()

}

