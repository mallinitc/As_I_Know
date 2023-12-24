#operations - CSP
#This deletes orphan disks in Azure

#Output directory
$Dir ="C:\Scripts\Logs\Disks\"
If(!(Test-Path $Dir))
{
     New-Item -ItemType Directory -Force -Path $Dir
}

#output file
$Excel = $Dir + "Disks_$(Get-Date -Format MMddyyyy).xlsx"

#transcription file
$TranscriptFile = $Dir + "Disks_$(Get-Date -Format MMddyyyy).txt"


Start-Transcript -Path $TranscriptFile

Connect-AzAccount
Connect-AzureAD

ForEach ($Tenant In Get-AzureADContract -All $true | Sort-Object -Property DisplayName)
{
    $Customer = $Tenant.DisplayName
    Write-Host "Processing Tenant - $Customer"
    ForEach ($Subscription In Get-AzSubscription -TenantId $Tenant.CustomerContextId)
    {
        Write-Host "Processing Subscription -" $Subscription.Name
        #Set Subscription
        Select-AzSubscription -TenantId $Tenant.CustomerContextId -SubscriptionId $Subscription.Id | Out-Null
        $Now = Get-date

        Write-host "Getting all unattached Disks.."
        $Disks = Get-AzDisk|Where-Object {$_.DiskState -like 'Unattached'}
        [System.Collections.ArrayList] $Diskobj = @()

        #$Count=$ManagedDisks|Out-GridView -PassThru

        ForEach ($Disk in $Disks) {

            If(($Disk.ManagedBy  -eq  $null) -and (($now - $Disk.TimeCreated).Days -gt 7))
            {
                
                $obj = New-Object Psobject -Property  @{
                    Customer = $Customer
                    DiskName = $Disk.Name
                    DiskType = $Disk.Sku.Name
                    DiskSize = $Disk.DiskSizeGB
                    CreatedOn = $Disk.TimeCreated
                    ResourceGroup = $Disk.ResourceGroupName
                    Location = $Disk.Location
                    
                }#Obj
                $Diskobj.Add($obj) | Out-Null

                $Disk | Remove-AzDisk -Force -Asjob
            }#If
        }#ForDisks
        If($Diskobj.count)
        {
            $Diskobj | Select-Object Customer,DiskName,DiskType, DiskSize,CreatedOn,ResourceGroup,Location | Export-Excel -Path $Excel -Append
        }
        Write-host "Done with Disks.."
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