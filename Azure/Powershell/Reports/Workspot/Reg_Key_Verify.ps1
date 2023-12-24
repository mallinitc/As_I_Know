$Path1 = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AUrestart\'
$Path2 = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU\'
#$Path = 'HKLM:\SOFTWARE\Policies\Microsoft\'
$output = @()

If (Get-Item -Path $Path1 -ErrorAction SilentlyContinue)
{
    $output1 = "AUrestart :: Yes //"
}
else
{
    $output1 = "AUrestart :: No //"
}

If (Get-Item -Path $Path2 -ErrorAction SilentlyContinue)
{
    $val = Get-ItemPropertyValue -Path $Path2 -Name NoAutoUpdate
    $output2 =" AU :: Yes && Value :: $($val)"

}
else
{
    $output2 = " AU :: No "
}

Write-Output ($output1+$output2)