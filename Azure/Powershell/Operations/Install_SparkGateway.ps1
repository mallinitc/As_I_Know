#This is to automate Sparkgateway installation & configuration
#Keep all necessary files such as exe, reg, jks, gateway.conf, license in SOURCEPATH


$Path = 'C:\Program Files\Remote Spark\SparkGateway'
$SourcePath = 'C:\Users\superuser\Downloads'
$DateTimeStamp = $((Get-Date -Format yyyy_MM_dd_HH_MM).tostring())

#Zulu installation
Write-Verbose "Installing Zulu...." -Verbose
Start-Process msiexec.exe -Wait -ArgumentList "/I $SourcePath\zulu8.38.0.13_win_x64.msi /quiet"

#Create Java reg keys to pass while Sprakgateway installation
reg import $SourcePath\SparkDummyRegKey.reg

#SparkGateway installation
Write-Verbose "Installing SparkGateway...." -Verbose
Start-Process -Wait -FilePath "$SourcePath\SparkGateway-installer (5.8.0).exe" -ArgumentList '/S' -PassThru 

#Rename Service
Write-Verbose "Renaming the Service...." -Verbose
Get-Service -Name SparkGateway | Set-Service -DisplayName 'Workspot SparkGateway'

#Set Memory value
reg import C:\javaHeapvalue.reg

#Adding Firewall Rule
Write-Verbose "Addling the Firewall rule...." -Verbose
$FR = New-NetFirewallRule -DisplayName "WorkspotSparkGateway" -Direction Inbound -LocalPort 8443 -Protocol TCP -Action Allow -Profile Any

#Rename existing gateway & copy new file
Write-Verbose "Rename & Copy the gateway conf file...." -Verbose
Rename-Item $Path\gateway.conf -NewName gateway.conf.old_$DateTimeStamp -Force
Copy-Item -Path $SourcePath\gateway.conf -Destination $Path

#Copying Keystore file
Write-Verbose "Renaming keystore file...." -Verbose
Copy-Item -Path $SourcePath\keystore-workspot.jks -Destination $Path -Recurse -Force -Verbose

#License File
Write-Verbose "Copying License file...." -Verbose
Copy-Item -Path $SourcePath\License -Destination $Path\License  -Recurse -Force -Verbose

Write-Verbose "Creating Java env variables...." -Verbose
[System.Environment]::SetEnvironmentVariable("JAVA_HOME", "C:\Program Files\Zulu\zulu-8")
[System.Environment]::SetEnvironmentVariable("Path", [System.Environment]::GetEnvironmentVariable('Path', [System.EnvironmentVariableTarget]::Machine) + ";$($env:JAVA_HOME)\bin")

[System.Reflection.Assembly]::LoadWithPartialName('Microsoft.VisualBasic') | Out-Null
$CertPass = [Microsoft.VisualBasic.Interaction]::InputBox("Enter the Certificate Password", "Password")
Set-Location -Path $Path

Write-Verbose "Encrypting the cert password....Press ENTER key after 3 seconds" -Verbose
$CertPass = java -cp SparkGateway.jar com.toremote.gateway.Encryption $CertPass
$Line = Get-Content $Path\gateway.conf | Select-String keyStorePassword | Select-Object -ExpandProperty Line
$Content = Get-Content $Path\gateway.conf
ForEach($C in $Content)
{
    If($C -eq $Line)
    {
        $New = $Content.replace($Line,"keyStorePassword = $CertPass")
        Write-Verbose "Replacing Encrypted password" -Verbose
    }
}
$New|Set-Content $Path\gateway.conf

Write-Verbose "Starting the Workspot SparkGateway Service...." -Verbose
Start-Service -Name SparkGateway

Write-Verbose "Sleeping for 2 seconds...." -Verbose
Start-Sleep -Seconds 2

#Default IE with localhost URL
Write-Verbose "Opening IE with localhost site.." -Verbose
$IE = new-object -com internetexplorer.application
$IE.navigate2("https://localhost:8443")
$IE.visible=$true