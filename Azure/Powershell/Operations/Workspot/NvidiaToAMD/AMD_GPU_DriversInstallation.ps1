
$InstallationPath="C:\AMD"
#Function to download the GPU driver from provided path
function DownloadAMDDriversFile
{
    param(
    [String] $downloadPath
    )
    $LocalPath = "C:\Windows\Temp\Radeon-Pro-Software-for-Enterprise-GA.zip"
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

#Download the AMD GPU drivers file
DownloadAMDDriversFile "####/AMD-Azure-NVv4-Driver-20Q4.zip"

#Extract the downloaded zip to C:\AMDGPUDrivers
try {
    Expand-Archive -Path 'C:\Windows\Temp\Radeon-Pro-Software-for-Enterprise-GA.zip' -DestinationPath $InstallationPath
    Write-Host "Drivers file unzipped"
}
catch {
    Write-Error "Failed to unzip drivers"
    exit 1
}

#Clean up
Remove-Item -Path "C:\Windows\Temp\Radeon-Pro-Software-for-Enterprise-GA.zip"

#print the display adapter
pnputil /enum-drivers 


#Run the installer in silent mode, installer does not rerurn any error
cd $InstallationPath
AMD-Azure-NVv4-Driver-20Q4\Setup.exe -INSTALL

#Sleep some time for driver installation to complete
Sleep -Seconds 120

#Check if installation is completed
if(get-process | ?{$_.path -eq "C:\AMDGPUDrivers\Radeon-Pro-Software-for-Enterprise-GA\Bin64\ATISetup.exe"}){
    #exe is running, what to do ?
    Write-Host "Installer is still running..."
	exit 1
}
else {
    Write-Host "Installation completed"
}


#Check if drivers are got installed
if(Get-WmiObject Win32_PnPSignedDriver| select devicename, driverversion | where {$_.devicename -like "*Radeon Instinct MI25 MxGPU*"}) {
    Write-Host "AMD drivers got installed"
    #Return success
    exit 0
}
else {
    Write-Error "AMD drivers not installed"
    exit 1
}
