#for TLS error
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Get-WmiObject -Class Win32_Product | where name -like '*Workspot*Agent*'|select Name, Version


Stop-Service -name "workspot Gateway Agent"
Stop-process -name *workspotgatewayAgent*
#echo "Service and Process Stopped"
$url = "https://wsprereleasebinaries.blob.core.windows.net/agent/Windows/1.7.2.642/WorkspotGatewayAgentSetup.msi"
$output = (Get-Location).Path+"WorkspotGatewayAgentSetup.msi"
## Download Location is C:\Packages\Plugins\Microsoft.CPlat.Core.RunCommandWindows\1.1.5\Downloads\WorkspotGatewayAgentSetup.msi
$start_time = Get-Date
$Temp=Invoke-WebRequest -Uri $url -OutFile $output
# Install Agent
$arguments = "/i $($output) /q /l*v upgrade.log"
Start-Process "msiexec.exe" $arguments -Wait -PassThru
Start-Service -name "workspot gateway Agent"

Get-WmiObject -Class Win32_Product | where name -like '*Workspot*Agent*'|select Name, Version


#Remove files

#$url = "https://download.workspot.com/WorkspotAgentSetup64(2.4.5.1451).exe"
#$file1 = (Get-Location).Path+"\WorkspotAgentSetup.exe"

#$url = "https://download.workspot.com/WorkspotAgentSetup(2.8.0.1814).msi"
#$file2 = (Get-Location).Path+"\WorkspotAgentSetup28.msi"

#$url = "https://wsprereleasebinaries.blob.core.windows.net/gatewayagent/WIndows/1.7.1.637/WorkspotGatewayAgentSetup.msi"
$file3 = (Get-Location).Path+"\WorkspotGatewayAgentSetup.msi"

#Remove-Item -Path $file3 -Force

Remove-Item * -Recurse -Force -Include '*.ps1'