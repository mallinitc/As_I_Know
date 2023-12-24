#Event Log Resize

$MyWindowsID = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$MyWindowsPrincipal = new-object System.Security.Principal.WindowsPrincipal($MyWindowsID)
$AdminRole = [System.Security.Principal.WindowsBuiltInRole]::Administrator

# Check to see if we are currently running "as Administrator"
If($MyWindowsPrincipal.IsInRole($AdminRole)) {
    Write-Host "Before the change.." -BackgroundColor Blue
    #Redundant command is redundant # Get-WinEvent -Listlog '*TerminalServices*/Operational'
    $AllEvents = Get-WinEvent -Listlog '*TerminalServices*/Operational'
    $AllEvents 
    ForEach($Event in $AllEvents) {
        [System.Object]$MaxSize='15728640'
        If($Event.LogName -like 'Microsoft-Windows-TerminalServices-Gateway/Operational'){ [System.Object]$MaxSize='131,072,000' }
        $Event.MaximumSizeInBytes = $MaxSize
        $Event.SaveChanges()
    }
    Write-Host "After the change.." -BackgroundColor Blue
    Get-WinEvent -Listlog '*TerminalServices*/Operational'
    $Sec=Get-WinEvent -ListLog 'Security'
    $Sec
    [System.Object]$MaxSize='131,072,000'
    $Sec.MaximumSizeInBytes = $MaxSize
    $Sec.SaveChanges()
    $Sec
}
Else{ Write-Host "Please run as a Administrator" -BackgroundColor Red }