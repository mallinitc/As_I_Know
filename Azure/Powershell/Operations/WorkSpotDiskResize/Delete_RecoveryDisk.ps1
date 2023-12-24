param (
    [string]$ReDisk,
    [string]$RePart
 )

Get-Partition -DiskNumber $ReDisk -PartitionNumber $RePart
Remove-Partition -DiskNumber $ReDisk -PartitionNumber $RePart -Confirm:$false