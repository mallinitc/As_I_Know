$line=reagentc /info| Select-String "^    Windows RE location:"| Out-String
$Redisk=$line.Split("\\")[5]
$Repart=$line.Split("\\")[6]
Write-Host "$Redisk && $Repart"
$Num1=($Redisk[($Redisk.length)-1])-48
$Num2=($Repart[($Repart.length)-1])-48



Get-Partition -DiskNumber '0' -PartitionNumber '3'

$num1=0
$num2=3
Get-Partition -DiskNumber $Num1 -PartitionNumber $Num2


Get-Partition -DiskNumber 0
$size = (Get-PartitionSupportedSize -DiskNumber 0 -PartitionNumber 2) #Not showing Unallocated
Resize-Partition -DiskNumber 0 -PartitionNumber 2 -Size $size.SizeMax
Get-Partition -DiskNumber 0

Diskpart
Select disk 0
Extend size=
Extend
