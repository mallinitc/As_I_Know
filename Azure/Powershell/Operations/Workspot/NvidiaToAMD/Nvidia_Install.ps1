  param(
    [Parameter(Mandatory = $true,HelpMessage="Enter the Driver installation path")]
    [ValidateNotNullorEmpty()]
    [string] $InstallationPath
        )

#if path already exist return failure
if (Test-Path $InstallationPath)
{
    Write-Error "Driver installation path already exist: $InstallationPath"
    exit 1
}

$InstallationPath="C:\AMD"
#Function to download the Nvidia driver from provided path

function DownloadNvidiaDriversFile
{
    param(
    [String] $downloadPath
    )
    $LocalPath = "C:\Windows\Temp\nvidia.zip"
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

#Download the Nvidia GPU drivers file
DownloadNvidiaDriversFile "###/nvidia.zip"

#Extract the downloaded zip to C:\AMDGPUDrivers
try {
    Expand-Archive -Path 'C:\Windows\Temp\nvidia.zip' -DestinationPath $InstallationPath
    Write-Host "Drivers file unzipped"
}
catch {
    Write-Error "Failed to unzip drivers"
    exit 1
}

#Clean up
Remove-Item -Path "C:\Windows\Temp\nvidia.zip"


#print the display adapter
pnputil /enum-drivers 

cd $InstallationPath
442.06\setup.exe -install

#Sleep some time for driver uninstall to complete
Sleep -Seconds 120

pnputil /delete-driver ((Get-WindowsDriver -online  | Where-Object {$_.ProviderName -eq "NVIDIA"}).Driver) /uninstall /force
