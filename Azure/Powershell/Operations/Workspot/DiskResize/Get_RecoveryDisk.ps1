$line = reagentc /info| Select-String "^    Windows RE location:"| Out-String
$Redisk = $line.Split("\\")[5]
$Repart = $line.Split("\\")[6]
Write-Host "$Redisk && $Repart"