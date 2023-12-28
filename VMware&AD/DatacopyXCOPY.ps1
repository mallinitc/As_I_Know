$sc1 = Import-Csv C:\data1.csv -Header srcVM, desVM
foreach ($sc in $sc1) {
    $desVM = $sc.desVM
    $srcVM = $sc.srcVM

    $total = (get-WmiObject win32_logicaldisk -Computername $srcVM -Filter "DeviceID='D:'").Size / 1GB
    $free = (get-WmiObject win32_logicaldisk -Computername $srcVM -Filter "DeviceID='D:'").FreeSpace / 1GB
    $srcSize = $total - $free

    Get-Service WinRM -ComputerName $desVM | Start-Service

    Invoke-Command -ComputerName $desVM -ArgumentList $srcVM, $srcSize -AsJob -ScriptBlock {
        $srcVM1 = $args[0]
        $srcSize1 = $args[1]
        $Stme = Get-date
        net use T: /delete
        net use T: "\\$srcVM1\d$" /persistent:no /user:NAME\NAME NAME
        xcopy "T:\" "d:" /s /i /C /O /Y /D 
        net use T: /delete
        $Ctme = Get-date

        $total = (get-WmiObject win32_logicaldisk -Filter "DeviceID='D:'").Size / 1GB
        $free = (get-WmiObject win32_logicaldisk -Filter "DeviceID='D:'").FreeSpace / 1GB
        $desSize = $total - $free


        "Source Size is - $srcSize1  && Destination Size is $desSize  started at $Stme  and finished at $Ctme " >>D:\MigrationLogs.txt
    }
} 
