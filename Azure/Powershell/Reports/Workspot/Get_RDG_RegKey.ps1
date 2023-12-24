Function Get-WsAzVm {


	[CmdletBinding()]
	param (
		[Parameter(Mandatory = $false)]
		[ValidateScript({Test-Path $_})]
		[String]
		$RdgScript,
		[Parameter(Mandatory = $false)]
		[ValidateScript({Test-Path $_})]
		[String]
		$ReferenceFile,
		[Parameter(Mandatory = $true)]
		[String]
		$ResultFile,
		[Parameter(Mandatory = $true)]
		[String]
		$TranscriptFile,
		[Parameter(Mandatory = $true)]
		[ValidateSet('all','h_sku_offenders','rdg')]
		[String]
		$VmScope
	)

    Start-Transcript -Path $TranscriptFile
    Connect-AzAccount
    Connect-AzureAD

    If ($ReferenceFile) {
		$ReferenceFileEntries = Import-Excel -Path $ReferenceFile
	}

    Switch ($VmScope) {
        'all' {$GetAzureVmCommandPartialString = '$_.name -like "*"'}
        'h_sku_offenders' {$GetAzureVmCommandPartialString = '$_.HardwareProfile.VmSize -notlike "*h*"'}
        'rdg' {$GetAzureVmCommandPartialString = '$_.name -like "*rdg*" -or $_.name -like "*gw*" -or $_.name -like "*gateway*"'}
    }

    ForEach ($Tenant In Get-AzureADContract -All $true | Sort-Object -Property DisplayName) {
        $Customer = ($Tenant.DefaultDomainName.Split('.'))[0]
        $Results = @()
        Write-Host "Processing Tenant - $Customer"
    
        ForEach ($Subscription In Get-AzSubscription -TenantId $Tenant.CustomerContextId) {
            Write-Host "Processing Subscription -" $Subscription.Name
            Select-AzSubscription -TenantId $Tenant.CustomerContextId -SubscriptionId $Subscription.Id | Out-Null
    
            ForEach ($ResourceGroup In Get-AzResourceGroup) {
                ForEach ($Vm In Get-AzVM -ResourceGroupName $ResourceGroup.ResourceGroupName | Where-Object {$(Invoke-Expression $GetAzureVmCommandPartialString)} | Sort-Object -Property Name) {
                    Write-Host "Processing VM - $($Vm.Name)"
                    $VmCreateDate = $null
                    $VmLogs = Get-AzLog -ResourceId $Vm.Id -StartTime (Get-Date).AddDays(-89) -WarningAction Ignore
                    $VmStatus = Get-AzVM -ResourceGroupName $ResourceGroup.ResourceGroupName -Name $Vm.Name -Status
                    $VmTags = @()

                    # Process Azure VM logs for create date
                    If ($VmLogs | Where-Object {$_.OperationName.Value -eq 'Microsoft.Compute/virtualMachines/write' -and $_.SubStatus.Value -eq 'Created'}) {
                        $VmCreateDate = Get-Date ($VmLogs | Where-Object {$_.OperationName.Value -eq 'Microsoft.Compute/virtualMachines/write' -and $_.SubStatus.Value -eq 'Created'})[0].EventTimestamp -Format MM/dd/yyyy
                    }
    
                    # Process Azure VM tags
                    For ($i = 0; $i -le $Vm.Tags.Count; $i++) {
                        $VmTagKey = ($Vm.Tags.Keys -split '\s+')[$i]
                        $VmTagValue = ($Vm.Tags.Values -split '\s+')[$i]
    
                        If ($VmTagKey -or $VmTagValue) {
                            $VmTags += "$($VmTagKey):$($VmTagValue)"
                        }
                    }

                    If ($VmScope -eq 'h_sku_offenders') {
                        If ((($ReferenceFileEntries | Where-Object {$_.Customer -eq $Customer -and $_.VmName -eq $Vm.Name}).$('Convert Y/N') -ne 'N' `
                        -or !(($ReferenceFileEntries | Where-Object {$_.Customer -eq $Customer -and $_.VmName -eq $Vm.Name})))) {
                            $Results += [PSCustomObject]@{
                                Customer = $Customer
                                Notes = $(($ReferenceFileEntries | Where-Object {$_.Customer -eq $Customer -and $_.VmName -eq $Vm.Name}).Notes)
                                CSE = $(If ($ReferenceFileEntries) {($ReferenceFileEntries | Where-Object {$_.Customer -eq $Customer -and $_.VmName -eq $Vm.Name}).CSE})
                                VmName = $Vm.Name
                                PowerState = $VmStatus.Statuses[1].DisplayStatus
                                VmAgentVersion = $VmStatus.VmAgent.VmAgentVersion
                                VmAgentStatus =  $VmStatus.VMAgent.Statuses.DisplayStatus
                                $('CreateDate (< 90 days)') = $VmCreateDate
                                Region = $Vm.Location
                                VmSize = $Vm.HardwareProfile.VmSize
                                NewVmSize = ''
                                VmTags = ($VmTags | Out-String)
                                TenantId = $Tenant.CustomerContextId
                                SubscriptionName = $Subscription.Name
                                SubscriptionId = $Subscription.Id
                                AvailableVmSizes = ((Get-AzVMSize -Location $($Vm.Location) | Where-Object {$_.Name -like "*h*" -and $_.Name -notlike "Standard_H*"}).Name | Out-String)
                            }
                        }
                    }
                    ElseIf ($VmScope -eq 'all') {                  
                        $Results += [PSCustomObject]@{
                            Customer = $Customer
                            VmName = $Vm.Name
                            PowerState = $VmStatus.Statuses[1].DisplayStatus
                            VmAgentVersion = $VmStatus.VmAgent.VmAgentVersion
                            VmAgentStatus =  $VmStatus.VMAgent.Statuses.DisplayStatus
                            $('CreateDate (< 90 days)') = $VmCreateDate
                            Region = $Vm.Location
                            VmSize = $Vm.HardwareProfile.VmSize
                            VmTags = ($VmTags | Out-String)
                            OsDiskType = $Vm.StorageProfile.OsDisk.ManagedDisk.StorageAccountType
                            DataDiskType = $Vm.StorageProfile.DataDisks.ManagedDisk.StorageAccountType
                            TenantId = $Tenant.CustomerContextId
                            SubscriptionName = $Subscription.Name
                            SubscriptionId = $Subscription.Id
                            AvailableVmSizes = ((Get-AzVMSize -Location $($Vm.Location) | Where-Object {$_.Name -like "*h*" -and $_.Name -notlike "Standard_H*"}).Name | Out-String)
                        }
                    }
                    ElseIf ($VmScope -eq 'rdg') {
                        $InvokeScriptResult = (Invoke-AzVMRunCommand -ResourceGroupName $ResourceGroup.ResourceGroupName -Name $Vm.Name -CommandId 'RunPowerShellScript' -ScriptPath $RdgScript)

                        $Results += [PSCustomObject]@{
                            Customer = $Customer
                            VmName = $Vm.Name
                            PowerState = $VmStatus.Statuses[1].DisplayStatus
                            Result=$InvokeScriptResult.Value[0].Message
                            Region = $Vm.Location
                            VmSize = $Vm.HardwareProfile.VmSize
                            VmTags = ($VmTags | Out-String)
                            TenantId = $Tenant.CustomerContextId
                            SubscriptionName = $Subscription.Name
                            SubscriptionId = $Subscription.Id
                        }
                    }
                }
            }
        }
        
        $Results | Export-Csv -Path $ResultFile -NoTypeInformation -Append
    }
    
    Disconnect-AzureAD
    Disconnect-AzAccount
    Stop-Transcript
}

# Start variables, for convenience sake when running frequently
$JobString = 'Zulu_rdg_others' # 'all','h_sku_offenders','rdg' Append with CSP location for output file, e.g. 'rdg_us'
#$RdgScript = 'C:\Scripts\Reg_Key_Verify.ps1'
$RdgScript = 'C:\Scripts\Get_Zulu_Version.ps1'
$ResultFile = "C:\Scripts\Logs\Get_WsAzureVm_$($JobString)_$(Get-Date -Format MMddyyyy).csv"
$TranscriptFile = "C:\Scripts\Logs\Get_WsAzureVm_$($JobString)_$(Get-Date -Format MMddyyyyHHmmss).txt"
# End variables, for convenience sake when running frequently

#Get-WsAzVm -ResultFile $ResultFile -TranscriptFile $TranscriptFile -VmScope 'h_sku_offenders'
Get-WsAzVm -ResultFile $ResultFile -TranscriptFile $TranscriptFile -VmScope 'rdg' -RdgScript $RdgScript
#Get-WsAzVm -ResultFile $ResultFile -TranscriptFile $TranscriptFile -VmScope 'all'