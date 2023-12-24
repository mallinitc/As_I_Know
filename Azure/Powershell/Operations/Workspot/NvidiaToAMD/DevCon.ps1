$Hostname = hostname

#Function to download the GPU driver from provided path
function DownloadAMDDriversFile
{
    param(
    [String] $downloadPath
    )
    $LocalPath = "C:\Windows\Temp\devcon.exe"
    #Remove if any old file
	if (Test-Path $LocalPath)
	{
        Remove-Item -Path $LocalPath
	}

    Write-Host [$(Get-Date -Format o)]("Downloading GPU driver from url: $downloadPath")
    try {
    (New-Object System.Net.WebClient).DownloadFile($downloadPath,$LocalPath)
    Write-Host "Driver download completed"
    }
    catch {
        Write-Error "GPU driver download failed"
        exit 1
    }
}

$Driver = Get-WmiObject Win32_VideoController|?{$_.Name -like 'Radeon Instinct MI25 MxGPU'}

if ( $Driver | Select description,status,driverversion | select-string "Radeon Instinct MI25 MxGPU" | select-string status=OK)
{
    Write-Host "$($Hostname) + Success"
}
else
{
    If($Driver.ConfigManagerErrorCode)
    {
        Write-Host "$($Hostname) + Error + $($Driver.ConfigManagerErrorCode)"
        #Download the devcon file
		DownloadAMDDriversFile "https:##/devcon.exe"
		cd C:\Windows\Temp
		./devcon.exe restart PCI*1002*686C

    }
    Else
    {
        Write-Host "$($Hostname) + Error + No driver"
    }

}
