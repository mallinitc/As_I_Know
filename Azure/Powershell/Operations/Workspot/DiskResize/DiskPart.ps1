$drive_letter = "C"
Get-Partition -DriveLetter $drive_letter
# get the partition sizes and then resize the volume
$size = (Get-PartitionSupportedSize -DriveLetter $drive_letter)
Resize-Partition -DriveLetter $drive_letter -Size $size.SizeMax
Get-Partition -DriveLetter $drive_letter