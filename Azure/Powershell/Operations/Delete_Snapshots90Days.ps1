#Operations - CSP

#This deletes snapshots that were created more than 90 days ago

#output file directory
$Dir = "C:\Scripts\Logs\Snapshots\"
If(!(Test-Path $Dir))
{
     New-Item -ItemType Directory -Force -Path $Dir
}
#output file
$Excel = $Dir + "SnapsDeleted_$(Get-Date -Format MMddyyyy).xlsx"
#transcription
$TranscriptFile = $Dir + "SnapsDeleted_$(Get-Date -Format MMddyyyy).txt"


Start-Transcript -Path $TranscriptFile

$Acc = Connect-AzAccount
$temp = Connect-AzureAD


ForEach ($Tenant In Get-AzureADContract -All $true | Sort-Object -Property DisplayName)
{
    $Customer = $Tenant.DisplayName
    Write-Host "Processing Tenant - $Customer"
    ForEach ($Subscription In Get-AzSubscription -TenantId $Tenant.CustomerContextId)
    {
        #Set Subscription
        Select-AzSubscription -TenantId $Tenant.CustomerContextId -SubscriptionId $Subscription.Id | Out-Null
        $now = Get-date
        [System.Collections.ArrayList] $Snapsobj = @()
        ForEach($snap in Get-AzSnapshot)
        {
            #Check 90 days
            If(($now - $snap.TimeCreated).Days -gt 90)
            {
                #True
                $obj = New-Object PsObject -Property @{
                    Customer = $Customer
                    Name = $snap.Name
                    Location = $snap.Location
                    RG = $snap.ResourceGroupName
                    TimeCreated = $snap.TimeCreated
                    OSType = $snap.OsType
                    DiskSizeGB = $snap.DiskSizeGB
                }
                $Snapsobj.Add($obj) | Out-Null
                $snap|Remove-AzSnapshot -Force -Confirm:$false -AsJob

            }#90
            
        }#Snap
        If($Snapsobj.count)
        {
            $Snapsobj | Select-Object Customer,Name,Location,RG,TimeCreated,OSType,DiskSizeGB | Export-Excel -Path $Excel -Append
        }
    }#Sub
}#Ten

Get-Job -State Completed|Remove-Job
Get-Job -State Failed|Remove-Job

while (Get-Job -State "Running")
{
    Write-Host "Jobs are still running..."
    Start-Sleep -s 5
}
Get-Job -State Completed|Remove-Job
Get-Job -State Failed|Remove-Job

Disconnect-AzureAD 
Disconnect-AzAccount
Stop-Transcript