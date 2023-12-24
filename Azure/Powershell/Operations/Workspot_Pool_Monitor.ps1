#This script monitors Workspot pools & report if any pool is in Failed state and VMs list which are in Error/Failed state

Write-host "Started"
Import-Module WorkspotAPI

$Ol = New-object -comobject "outlook.application"
$FromMail = ($ol.Session.Accounts|Where-Object {$_.SmtpAddress -like '*workspot.com'}).smtpAddress

If($Frommail.count -ne 1)
{
    "There are multiple outlooks profiles are found. So please enter valid email adaress and password"
     $FromMail = 'mallikarjunar@workspot.com'
   
}
Write-host "Outlook details collected"

Set-WorkspotApiCredentials -ApiClientId "" -ApiClientSecret "" -WsControlUser "" -WsControlPass ""
"Connected to Control"

$Pools = Get-WorkspotVdiPool
$Pool_out = @()
$Vm_out = @()
ForEach($Pool in $Pools)
{
    $Vm = Get-WorkspotVdiPoolVm -PoolName $Pool.Name|Where-Object {($_.Status -like "Failed") -or ($_.Status -like 'Ready')}|Select-Object Name, PoolName, Status
    ForEach($Vm1 in $Vm)
    {
        $Vm_out += New-Object PsObject -Property @{
        Name = $Vm1.Name
        PoolName = $Vm1.PoolName
        Status = $Vm1.Status
        }
    }
    If($Pool.Status -like 'Failed')
    {
        "POOL STATUS :: $($Pool.name)  $($Pool.Status)"
        $Pool_out += New-Object PsObject -Property @{
        Name = $Pool.Name
        Status = $Pool.Status
        }
    }
}
If(!($Pool_out -or $Vm_out))
{
    Write-host "No errors"
    "No errors at $(Get-date)" >> C:\TNP_Monitor\Logs.txt
    exit
}
# Create a POOL DataTable
$Pooltable = New-Object system.Data.DataTable "POOL"
$Col1 = New-Object system.Data.DataColumn Name,([string])
$Col2 = New-Object system.Data.DataColumn Status,([string])
$Pooltable.columns.add($Col1)
$Pooltable.columns.add($Col2)

# Add content to the DataTable
For($i=0;$i -lt $Pool_out.Count;$i++)
{
    $Row = $Pooltable.NewRow()
    $Row.Name = $Pool_out[$i].Name
    $Row.Status = $Pool_out[$i].status
    $Pooltable.Rows.Add($Row)
}
Write-host "Table defined"
# Create an HTML version of the DataTable
$Html = "<table id='tabid'><tr><th>PoolName</th><th>Status</th></tr>"
ForEach ($Row in $Pooltable.Rows)
{ 
    $Html += "<tr><td>" + $Row[0] + "</td>"+"<td>" + $Row[1] + "</td>"+"</tr>"
}
$Html += "</table>"

# Create a VM DataTable
$Vmtable = New-Object system.Data.DataTable "VM"
$Col1 = New-Object system.Data.DataColumn Name,([string])
$Col2 = New-Object system.Data.DataColumn Status,([string])
$Col3 = New-Object system.Data.DataColumn PoolName,([string])
$Vmtable.columns.add($Col1)
$Vmtable.columns.add($Col2)
$Vmtable.columns.add($Col3)

# Add content to the DataTable
For($i=0;$i -lt $Vm_out.Count;$i++)
{
    $Row = $Vmtable.NewRow()
    $Row.Name = $Vm_out[$i].Name
    $Row.Status = $Vm_out[$i].Status
    $Row.Poolname = $Vm_out[$i].Poolname
    $Vmtable.Rows.Add($Row)
}

# Create an HTML version of the DataTable
$Html2 ="</br></br></br></br>"
$Html2 += "<table id='tabid'><tr><th>VMName</th><th>Status</th><th>PoolName</th></tr>"
foreach ($Row in $VmTable.Rows)
{ 
    $Html2 += "<tr><td>" + $Row[0] + "</td>"+"<td>" + $Row[1] + "</td>"+"<td>" + $Row[2] + "</td></tr>"
}
$Html2 += "</table>"

$Body2 = "
<style>
#tabid {
  font-family: 'Trebuchet MS', Arial, Helvetica, sans-serif;
  border-collapse: collapse;
  width: 50%;
}

#tabid td, #Job th {
  border: 1px solid #ddd;
  padding: 4px;
}

#tabid tr:nth-child(even){background-color: #FF5733;}

#tabid tr:hover {background-color: #ddd;}

#tabid th {
  padding-top: 5px;
  padding-bottom: 5px;
  text-align: left;
  background-color: #FF5733;
  color: white;
}
</style>"

Write-host "sending an email"

$Now = (Get-Date -Format g).ToString()
$Sub ="TNP Monitor Report:`t"+ $Pool_out.count +" Pools  and "+$Vm_out.count +" VMs in Failed/Error State:`t"+$Now
$Body = "<!DOCTYPE html> <html>Team,<br />Please find the Pool & VM status details  below:<br /><br /></br>" +$Body2+ $Html+"<br /><br /></br>"+$Html2+"</body></html>"
$Account = $Ol.Session.Accounts | Where-Object { $_.SmtpAddress -eq $Frommail }
$Mail = $Ol.CreateItem(0)

$Mail.recipients.add("example@workspot.com") | out-null
$Mail.subject = $Sub
$Mail.HTMLbody = $Body
$Mail.SendUsingAccount = $Account
$Mail.Send()
Write-host "Email is sent"