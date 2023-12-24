<#
	.SYNOPSIS
		This module provides functions to make easy use of the Workspot API
		
	.DESCRIPTION
		The functions in this module give the user a simplified ability 
		to use the Workspot Control API capabilities from PowerShell.  
		
		Use Get-Help with the -Full parameter to review documentation of each 
		function in this module.
		
		This module provides three ways to handle credentials and authentication:
		 1- After importing the module, run Set-WorkspotApiCredentials to 
		save your API credentials to the local machine in the current user 
		profile. Other functions will call Get-WorkspotApiToken and retrieve
		an AuthToken automatically using those stored credentials. This is the 
		best way to use the module to work with Workspot API at interactive 
		PowerShell consoles and to run scripts locally.

		 2- Include the full set of API and Workspot Control credentials in each
		individual function call. The function will call Get-WorkspotApiToken and 
		retrieve its own AuthToken by passing those credentials. If the design goal 
		is to leverage the Workspot API with orchestration this would be a more 
		resilient way to perform those function calls.

		 3- Use Get-WorkspotApiToken with either stored or passed credentials to get
		your AuthToken, then include it when calling other functions. This would be
		the most efficient way to use this module in a script that makes many API calls,
		to reduce execution time.
		
	.FUNCTIONALITY
		Function Get-WorkspotApiModuleHelp			- Displays this module help/summary.
		Function Set-WorkspotApiCredentials			- Saves credentials to be used by Get-WorkspotApiToken.		
		Function Get-WorkspotApiToken				- Retrieves an oAuth token for Workspot API calls. This function is 
													 primarily used by other functions that need to authenticate to API.
		Function Get-WorkspotApiStatus 				- Waits for completion of asynchronous Workspot API operation.  This 
													 function is primarily for use by other functions in this module that 
													 perform API calls with asynchronous operations. 
		Function Get-WorkspotActiveUserReport		- Retrieves active user report from Control.
		Function Get-WorkspotVdiPool				- Gets details of Workspot VDI Pools from Control.	
		Function Get-WorkspotVdiPoolVm				- Gets details of VDI computers from specific Workspot VDI Pool.
		Function Get-WorkspotUser					- Gets details Workspot Control user.
		Function Get-WorkspotLicenseInfo			- Gets details of Workspot license information from Control.
		Function New-WorkspotVdiPoolVm				- Creates new VDI computer within a Workspot VDI Pool.
		Function New-WorkspotUser					- Creates new user in Workspot Control.	
		Function Set-WorkspotUserCostCenter			- Sets the Cost Center value for the specified user.
		Function Set-WorkspotVdiTags				- Sets tag pairs for specified VDI Computer.
		Function Set-WorkspotVdiUserAssignment		- Assigns Workspot user to a VDI Pool, or to a specific VDI Computer.	
		Function Remove-WorkspotVdiUserAssignment	- Removes assignment for Workspot user from the specified VDI Computer.
		Function Remove-WorkspotUser				- Deletes user account from Workspot Control.
		Function Remove-WorkspotVdiPoolVm			- Deletes a VDI Computer from a Workspot VDI Pool.
		Function Restart-WorkspotVdiPoolVm			- Issues the "reboot" command in Control for the specified VDI Computer.

		
	.NOTES
		Author: Joe Semmelrock, joe@workspot.com
		2018-10-30  Released
		2018-11-08  Added Get-WorkspotLicenseInfo, updated comments.
		2018-12-19  Fixed return for 3 functions. (Remove-WorkspotVdiUserAssignment, Remove-WorkspotUser, and Remove-WorkspotVdiPoolVm)
					Improved Get-WorkspotActiveUserReport to include the date the user was last logged in
					Added -CreateAsynchronously switch to New-WorkspotVdiPoolVm to end the function without waiting for the new VM build
					Added return handling for a failed VM lookup in Remove-WorkspotVdiPoolVm
					Fixed examples for New-WorkspotUser
		2019-06-29  Added Restart-WorkspotVdiPoolVm
					Added Set-WorkspotUserCostCenter
					Added Set-WorkspotVdiTags
					Improved output from Get-WorkspotApiStatus
					Added support for providing VM Name for New-WorkspotVdiPoolVm
					Added variable delay to Get-WorkspotApiStatus with -StatusDelay parameter
					Fixed some inconsistencies in the comment-based help and examples
		2019-07-09  Improved Set-WorkspotApiCredentials by adding credential validation before saving them
					Improved Get-WorkspotUser by communicating error status to shell (in addition to return value)
					Improved Get-WorkspotActiveUserReport by communicating error status to shell (in addition to return value)
					Removed unused parameter from Get-WorkspotLicenseInfo
#>

Function Get-WorkspotApiModuleHelp {
	Get-Help Get-WorkspotApiModuleHelp -Full
}

Function Set-WorkspotApiCredentials {
    <#
        .SYNOPSIS
			Set-WorkspotApiCredential saves credential info for Workspot API Token retrieval
        .DESCRIPTION
			Used to store the four Workspot Control credentials necessary for 
			API token creation: username/password, client ID and client secret.  
			These will be retrieved by Get-WorkspotApiToken.
        .OUTPUTS
			None
        .EXAMPLE
			Set-WorkspotApiCredentials
        .EXAMPLE
			Set-WorkspotApiCredentials -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
		.PARAMETER ApiClientId
			API Client ID from Workspot Control
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control
		.PARAMETER WsControlUser
			Workspot Control administrator email
		.PARAMETER WsControlPass
			Workspot Control administrator password
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
    #>   
    
    Param(
        [parameter(Mandatory=$True, HelpMessage = "Enter the API Client ID from Workspot Control")] [string]
        $ApiClientId,
        [parameter(Mandatory=$True, HelpMessage = "Enter the API Client Secret from Workspot Control")] [string]
        $ApiClientSecret,
        [parameter(Mandatory=$True, HelpMessage = "Enter the Workspot Control administrator email")] [string]
        $WsControlUser,
        [parameter(Mandatory=$True, HelpMessage = "Enter the Workspot Control administrator password")] [string]
		$WsControlPass,
		[string] $ApiHost = "api.workspot.com"
    )
	
	Try {
		$TestAuthToken = Get-WorkspotApiToken -ApiClientId $ApiClientId -ApiClientSecret $ApiClientSecret -WsControlUser $WsControlUser -WsControlPass $WsControlPass -ApiHost $ApiHost
		If ($TestAuthToken.GetType().Name -eq 'String') {
			Write-Host 'Tested credentials successfully. Proceeding.'
			[Environment]::SetEnvironmentVariable("WorkspotAPIClientId",$ApiClientId,"User")
			[Environment]::SetEnvironmentVariable("WorkspotAPIClientSecret",$ApiClientSecret,"User")
			[Environment]::SetEnvironmentVariable("WorkspotAPIControlUser",$WsControlUser,"User")
			[Environment]::SetEnvironmentVariable("WorkspotAPIControlPasswd",$WsControlPass,"User")	
		}
		Else {
			Write-Host 'Failed to aquire authtoken with provided credentials. Halting without saving credentials.'
			Return($TestAuthToken)
		}
	}
	Catch [System.Net.WebException] { Return($_) }
	Catch { Return($TestAuthToken) }
}

Function Get-WorkspotApiToken {
    <#
        .SYNOPSIS
			Get-WorkspotApiToken retrieves an oAuth token for Workspot API calls
        .DESCRIPTION
			Used to generate an authentication token to be used for API
			calls to Workspot Control. 
			There are four Workspot Control credentials necessary for token 
			creation: username/password, client ID and client secret.  

			Run Set-WorkspotApiCredentials before this or other Workspot 
			API functions to set your API credentials, in lieu of specifying 
			credentials as parameters
		.OUTPUTS
			System.String. Get-WorkspotApiToken returns an oAuth token 
			to be used to make API calls to Workspot Control.
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
        .EXAMPLE
			$AuthToken = Get-WorkspotApiToken
        .EXAMPLE
			$AuthToken = Get-WorkspotApiToken -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
    #>
    
    Param(
        [string] $ApiHost = "api.workspot.com",
        [string] $ApiClientId = "",
        [string] $ApiClientSecret = "",
        [string] $WsControlUser = "",
        [string] $WsControlPass = ""
    )

    If(!$ApiClientId)     { $ApiClientId     = [Environment]::GetEnvironmentVariable("WorkspotAPIClientId","User") }
    If(!$ApiClientSecret) { $ApiClientSecret = [Environment]::GetEnvironmentVariable("WorkspotAPIClientSecret","User") }
    If(!$WsControlUser)   { $WsControlUser   = [Environment]::GetEnvironmentVariable("WorkspotAPIControlUser","User") }
    If(!$WsControlPass)   { $WsControlPass   = [Environment]::GetEnvironmentVariable("WorkspotAPIControlPasswd","User") }

    If((!$ApiClientId) -or (!$ApiClientSecret) -or (!$WsControlUser) -or (!$WsControlPass)) { 
        Write-Output "Missing credentials to retrieve API token." 
        Write-Output "Either run function Set-WorkspotApiCredentials to save your credentials, or add credentials in parameters to the API function."
        Break
    }

    $RestUri = "https://$ApiHost/oauth/token"
    $ApiClientPair = "$($ApiClientId):$($ApiClientSecret)"
    $EncodedApiCreds = [System.Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes($ApiClientPair))
    $HeaderAuthValue = "Basic $EncodedApiCreds"
    $Headers = @{Authorization = $HeaderAuthValue}
    $PostParameters = @{username=$WsControlUser;password=$WsControlPass;grant_type='password'}
    Try {
		$ApiReturn = Invoke-RestMethod -Uri $RestUri -Method Post -Body $PostParameters -Headers $Headers
		$ApiToken = $ApiReturn.Access_Token
		If ($ApiToken) { Return($ApiToken) }
		Else { Return($ApiReturn) }
	}
	Catch [System.Net.WebException] { Return($_) }
}

Function Get-WorkspotApiStatus { 
    <#
        .SYNOPSIS
			Checks status of pending Workspot API operation until complete
        .DESCRIPTION
			When Workspot API calls return a status URL for an asyncronous
			operation, the URL can be sent to Get-WorkspotApiStatus.  This function 
			will check the status, wait until it is complete, and then return 
			the output.
			
			Running Set-WorkspotApiCredentials before running this function 
			will allow Get-WorkspotApiStatus to get its own oAuth token without 
			the need to specify AuthToken or API credentials.
        .OUTPUTS
			JSON object containing status of completed Workspot API operation
		.PARAMETER StatusUrl
			URL for status of asyncronous operation from another Workspot API call
		.PARAMETER StatusDelay
			Delay in seconds between each status check. Default is 5.
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
		.EXAMPLE
			Get-WorkspotApiStatus -StatusUrl $StatusUrl
		.EXAMPLE
			Get-WorkspotApiStatus -StatusUrl $StatusUrl -AuthToken $AuthToken
        .EXAMPLE
			Get-WorkspotApiStatus -StatusUrl $StatusUrl -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
    #>
    Param(        
        [parameter(Mandatory=$True, HelpMessage = "Enter the Status URL from another Workspot API call.")] 
        [string] $StatusUrl,
		[int] $StatusDelay = 5,
        [string] $ApiHost = "api.workspot.com",
		[string] $AuthToken = "",
        [string] $ApiClientId = "",
        [string] $ApiClientSecret = "",
        [string] $WsControlUser = "",
        [string] $WsControlPass = ""
    )
	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
		"ApiClientId" = $ApiClientId
		"ApiClientSecret" = $ApiClientSecret
		"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
    If(!$AuthToken) {
		#Call Get-WorkspotApiToken to get a token if no -AuthToken was passed.
		#Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
        $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
	$CallingCommand = (Get-PsCallStack)[1].Command
	$CallingArgs = (Get-PsCallStack)[1].Arguments
	$ArgString = ""
	If (($CallingCommand.Split('-')[0])){
		$DisplayActivity = "$CallingCommand"
		$DisplayOperation = (("$CallingArgs").TrimEnd('}')).TrimStart('{')
		$ParamArray = ((("$CallingArgs").TrimEnd('}')).TrimStart('{').Replace(' ','')).Split(',')
		ForEach ($Param in $ParamArray) {
			$ParamName = $Param.Split('=') | Select-Object -First 1
			$ParamValue = $Param.Split('=') | Select-Object -Last 1
			$ArgString += "-$ParamName $ParamValue "
		}
		$ArgString = $ArgString.TrimEnd(' ')
		$DisplayOperation = $ArgString
	}
	Else {
		$DisplayActivity = "Workspot API call"
		$DisplayOperation = $StatusUrl
	}
	$Headers = @{Authorization =("Bearer "+ $AuthToken)}
	$i = 1
	Write-Host "`n`rChecking status of $DisplayActivity $ArgString"
	Write-Host "Status URL - $StatusUrl`n`r"
	Try {
		Do {
			Start-Sleep -Seconds $StatusDelay
			Write-Progress -Activity "Waiting for completion of $DisplayActivity $ArgString" -CurrentOperation  $StatusUrl -Status "Current status = $($StatusReturn.Status) - Checking again in $StatusDelay seconds" -PercentComplete $i
			If ($i -lt 90) {$i++}
			$StatusReturn = Invoke-RestMethod -Method GET -ContentType "application/json" -Uri $StatusUrl -Headers $Headers
			If ($StatusReturn.Status -eq "InProgress") {
				Write-Host "$(Get-Date -Format hh:MM:ss) - Checking status of '$DisplayActivity $DisplayOperation' - Current Status = '$($StatusReturn.Status)' - Checking again in $StatusDelay seconds"
			}
			Else {
				Write-Host "$(Get-Date -Format hh:MM:ss) - Checking status of '$DisplayActivity $DisplayOperation' - Current Status = '$($StatusReturn.Status)'"
			}
		} While($StatusReturn.Status -eq "InProgress")
		Write-Progress -Activity $DisplayActivity -CurrentOperation $DisplayOperation -Status "Current Status = $($StatusReturn.Status) - Checking again in $StatusDelay seconds." -Completed
		Return ($StatusReturn)
	}
	Catch [System.Net.WebException] { Return($_) }
}

Function Get-WorkspotActiveUserReport {
     <#
        .SYNOPSIS
			Retrieve active user report for Workspot
        .DESCRIPTION
			Uses an API call to Workspot to retrieve a usage status report
			for an up-to thirty day window.  Returns the full report in JSON format
			and optionally saves it to a CSV file specified in -OutputCSV parameter.
			
			Running Set-WorkspotApiCredentials before running this function 
			will allow Get-WorkspotActiveUserReport to get its own oAuth token 
			without the need to specify credentials.
        .OUTPUTS
			System.String. Output is in JSON format. If the API call succeeds, the returned value will be the 
			entire usage report. If it fails, instead the output will contain information returned from the
			API Call.
			
			System.Net.WebException. If API call throws an exception, returns the entire exception.
		.PARAMETER StartDate
			First date of the up-to-thirty-day range, format YYYY-MM-DD
		.PARAMETER EndDate
			Last date of the up-to-thirty-day range, format YYYY-MM-DD
		.PARAMETER OutputCsv
			Optional CSV file path. If specified, a CSV of the report will be created at this path
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
        .EXAMPLE
			Get-WorkspotActiveUserReport -$StartDate = "2018-09-23" -$EndDate = "2018-10-19"
        .EXAMPLE
			Get-WorkspotActiveUserReport -$StartDate = "2018-09-23" -$EndDate = "2018-10-19" -OutputCSV .\WorkspotUsage.csv
        .EXAMPLE
			Get-WorkspotActiveUserReport -$StartDate = "2018-09-23" -$EndDate = "2018-10-19" -OutputCSV .\WorkspotUsage.csv -AuthToken $AuthToken
        .EXAMPLE
			Get-WorkspotActiveUserReport -$StartDate = "2018-09-23" -$EndDate = "2018-10-19" -OutputCSV .\WorkspotUsage.csv -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
    #>
    Param(
        [parameter(Mandatory=$True, HelpMessage = "Enter the first date of the up-to-thirty-day range, format YYYY-MM-DD")]
		[string] $StartDate,
		
        [parameter(Mandatory=$True, HelpMessage = "Enter the last date of the up-to-thirty-day range, format YYYY-MM-DD")]
		[string] $EndDate,
		
        [string] $OutputCsv,
        [string] $ApiHost = "api.workspot.com",
		[string] $AuthToken = "",
		[string] $ApiClientId = "",
		[string] $ApiClientSecret = "",
		[string] $WsControlUser = "",
		[string] $WsControlPass = ""
    )
	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
		"ApiClientId" = $ApiClientId
		"ApiClientSecret" = $ApiClientSecret
		"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
    If(!$AuthToken) {
		#Call Get-WorkspotApiToken to get a token if no -AuthToken was passed.
		#Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
        $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
    $Headers = @{Authorization =("Bearer "+ $AuthToken)}
    $ApiPath = "v1.0/reports/generateusagereport" 
    $RestUri = "https://$ApiHost/$ApiPath"

    $ReportParams = @{
        end = $EndDate
        format = "CSV"
        start = $StartDate
    }
    $ReportParamsJson = $ReportParams | ConvertTo-Json
    Try {
		$ReportReturn = (Invoke-RestMethod -Uri $RestUri -Method Post -Headers $Headers -Body $ReportParamsJson -ContentType 'application/json')
		If($ReportReturn.StatusUrl) { 
			$StatusReturn = Get-WorkspotApiStatus -AuthToken $AuthToken -StatusUrl $ReportReturn.StatusUrl
			If($StatusReturn.Details.DownloadUrl) {
				If($OutputCsv) {
					(Invoke-RestMethod $StatusReturn.Details.DownloadUrl) | ConvertFrom-CSV | Export-CSV $OutputCsv -NoTypeInformation
				}
				$Return = (Invoke-WebRequest $StatusReturn.Details.DownloadUrl) | ConvertFrom-CSV
			}
			Else { $Return = $StatusReturn }
		}
		Else { $Return = $ReportReturn }
	}
	Catch [System.Net.WebException] { 
		Return $_ 
	}
	Return($Return)
}

Function Get-WorkspotVdiPool {
     <#
        .SYNOPSIS
			Gets details of Workspot VDI Pools from Control
        .DESCRIPTION
			Uses Workspot API to retrieve VDI Pool info from Workspot Control.
			If PoolName is not specified this returns JSON details of all pools
			for the authenticated user.  If PoolName is specified only the 
			details for that specific pool are returned.
			
			Running Set-WorkspotApiCredentials before running this function 
			will allow Get-WorkspotVdiPool to get its own oAuth token without 
			the need to specify credentials.
        .OUTPUTS
			System.String. Output is in JSON format. If the API call succeeds, the details returned will
			be a list of all VDI Pools for the authenticated Workspot Control account, with Pool detail
			values also included within each Pool value.  If PoolName parameter is included and that pool
			is found, the returned value will be the details for only that specific VDI Pool instead.
			
			System.Net.WebException. If API call throws an exception, returns the entire exception.
			
			System.String. If VmName is provided but not found, output is "Failed to find pool named $PoolName."
		.PARAMETER PoolName
			Specific Workspot VDI Pool.  If not specified, this function returns details of all pools.
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
        .EXAMPLE
			Get-WorkspotVdiPool
        .EXAMPLE
			Get-WorkspotVdiPool -PoolName "AzEastPool"
        .EXAMPLE
			$PoolList = Get-WorkspotVdiPool
        .EXAMPLE
			$Pool = Get-WorkspotVdiPool -PoolName "AzEastPool" -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
    #>    
    Param(
        [string] $PoolName,
        [string] $ApiHost = "api.workspot.com",
		[string] $AuthToken = "",
		[string] $ApiClientId = "",
		[string] $ApiClientSecret = "",
		[string] $WsControlUser = "",
 		[string] $WsControlPass = ""
    )
	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
		"ApiClientId" = $ApiClientId
		"ApiClientSecret" = $ApiClientSecret
		"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
    If(!$AuthToken) {
		#Call Get-WorkspotApiToken to get a token if no -AuthToken was passed.
		#Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
        $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
    $Headers = @{Authorization =("Bearer "+ $AuthToken)}
    $ApiPath = "v1.0/pools"
    $RestUri = "https://$ApiHost/$ApiPath"
    Try {
		$PoolList = (Invoke-RestMethod -Uri $RestUri -Method Get -Headers $Headers).DesktopPools
		If($PoolName) {
			$PoolId = ($PoolList | Where-Object { $_.Name -like $PoolName}).Id
			If($PoolId) {
				$PoolIdRestUri = "$RestUri/$PoolId"
				Return(Invoke-RestMethod -Uri $PoolIdRestUri -Method Get -Headers $Headers)
			}
			Else { Return("Failed to find pool named $PoolName") }
		}
		Else { Return($PoolList) }
	}
	Catch [System.Net.WebException] { Return($_) }
}

Function Get-WorkspotVdiPoolVm {
     <#
        .SYNOPSIS
			Gets details of VDI computers from specific Workspot VDI Pool
        .DESCRIPTION
			Uses Workspot API to retrieve details of VDI within a specified
			Workspot VDI pool.  If VmName is specified, this will instead retrieve
			details of that one specific VDI computer.

			Running Set-WorkspotApiCredentials before running this function 
			will allow Get-WorkspotVdiPoolVm to get its own oAuth token 
			without the need to specify credentials.
        .OUTPUTS
			System.String. Output is in JSON format. If the API call succeeds, the details returned will
			be a list of VDI Computers in the pool, with Computer detail values also included within 
			each Computer value.  If VmName parameter is included and that machine is found, the return 
			will be the details for that specific Computer instead.
			
			System.Net.WebException. If API call throws an exception, returns the entire exception.
			
			System.String. If VmName is provided but not found, output is "Failed to find $VmName in $PoolName."
		.PARAMETER PoolName
			Name of Workspot VDI Pool to get computer details for.
		.PARAMETER VmName
			Name of a specific Workspot VDI Computer. If not specified, this function returns details of all VDI Computers in the pool.
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId 
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
        .EXAMPLE
			Get-WorkspotVdiPoolVm -PoolName "AzEastPool"
		.EXAMPLE
			Get-WorkspotVdiPoolVm -PoolName "AzEastPool" -VmName "AzEastVdi-03"
        .EXAMPLE
			$VdiJson = Get-WorkspotVdiPoolVm -PoolName "AzEastPool"
    #>   
    Param(
        [parameter(Mandatory=$True, 
			HelpMessage = "Enter the name of Workspot VDI Pool to get computer details for.")] 
			[string] $PoolName,
		[string] $VmName,
        [string] $ApiHost = "api.workspot.com",
		[string] $AuthToken = "",
		[string] $ApiClientId = "",
		[string] $ApiClientSecret = "",
 		[string] $WsControlUser = "",
 		[string] $WsControlPass = ""
    )
	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
		"ApiClientId" = $ApiClientId
		"ApiClientSecret" = $ApiClientSecret
		"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
    If(!$AuthToken) {
		#Call Get-WorkspotApiToken to get a token if no -AuthToken was passed.
		#Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
        $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
    $Headers = @{Authorization =("Bearer "+ $AuthToken)}
	
	$GetPool = Get-WorkspotVdiPool -AuthToken $AuthToken -ApiHost $ApiHost -PoolName $PoolName 
    If ($GetPool.Id) {
		$PoolId = (Get-WorkspotVdiPool -AuthToken $AuthToken -ApiHost $ApiHost -PoolName $PoolName).Id
    	$ApiPath = "v1.0/pools/$PoolId/desktops"
    	$RestUri = "https://$ApiHost/$ApiPath"

    	Try { 
			$Return = Invoke-RestMethod -Uri $RestUri -Method Get -Headers $Headers
			If($Return.Desktops) {
				If($VmName) { 
					$VmDetails = $Return.Desktops | Where-Object {$_.Name -like $VmName} #Compare VmName to Workspot vdi names first
					If($VmDetails) { Return $VmDetails }
					Else {
						$VmDetails = $Return.Desktops | Where-Object {($_.Fqdn).SubString(0,($VmName.Length)) -like $VmName} #If VmName isn't found, now check FQDN
						If($VmDetails) { Return $VmDetails }
						Else { Return("Failed to find $VmName in $PoolName") }
					}
				}
				Else { Return($Return.Desktops) }
			}
			Else { Return($Return) }
		}
		Catch [System.Net.WebException] { Return($_) }
	}
	Else {
		Write-Host "Unable to determine the Pool ID for $PoolName"
		Return($GetPool)
	}
}

Function Get-WorkspotUser {
    <#
        .SYNOPSIS
			Gets details Workspot Control user
        .DESCRIPTION
			Uses Workspot API to retrieve details of specified Workspot user.
			
			Running Set-WorkspotApiCredentials before running this function 
			will allow Get-WorkspotUser to get its own oAuth token without 
			the need to specify credentials.
        .OUTPUTS
			System.String. Output is in JSON format. If the API call succeeds, the details returned include
			the user details along with their VDI Pool/VM assignments. If there is an error, the details 
			for that error will be included.
			
			System.Net.WebException. If API call throws an exception, returns the entire exception.
		.PARAMETER UserEmail
			Email address of Workspot Control user to get details for.
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
        .EXAMPLE
			Get-WorkspotUser -UserEmail "ExampleUser@workspot.com"
        .EXAMPLE
			UserInfo = Get-WorkspotUser -UserEmail "ExampleUser@workspot.com"
        .EXAMPLE
			Get-WorkspotUser -UserEmail "ExampleUser@workspot.com" -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
    #>   
    Param(
        [parameter(Mandatory=$True, 
			HelpMessage = "Enter the email address of Workspot Control user to get details for.")]
			[string] $UserEmail,
		[string] $ApiHost = "api.workspot.com",
		[string] $AuthToken = "",
		[string] $ApiClientId = "",
		[string] $ApiClientSecret = "",
 		[string] $WsControlUser = "",
 		[string] $WsControlPass = ""
    )
	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
		"ApiClientId" = $ApiClientId
		"ApiClientSecret" = $ApiClientSecret
		"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
    If(!$AuthToken) {
		#Call Get-WorkspotApiToken to get a token if no -AuthToken was passed.
		#Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
        $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
    $Headers = @{Authorization =("Bearer "+ $AuthToken)}
    $ApiPath = ("v1.0/users/$UserEmail/").Replace('@', '%40')
    $RestUri = "https://$ApiHost/$ApiPath"

	Try { $Return = (Invoke-RestMethod -Uri $RestUri -Method Get -Headers $Headers)}
	Catch [System.Net.WebException] { $Return = $_}
	If ($Return.ErrorDetails) { Write-Host "Workspot Get User API returned error: $($Return.ErrorDetails.Message)"}
	Return($Return)
}

Function Get-WorkspotLicenseInfo {
	<#
		.SYNOPSIS
			Gets details of Workspot license information from Control
	   	.DESCRIPTION
		   	Uses Workspot API to retrieve license info from Workspot Control.
		   	The return value will be a JSON formatted license count.
		   
		   	Running Set-WorkspotApiCredentials before running this function 
		   	will allow Get-WorkspotLicenseInfo to get its own oAuth token without 
		   	the need to specify credentials.
	   	.OUTPUTS
		   	System.Object. If the API call succeeds, the value returned will contain all
		   	Workspot license information for the authenticated Workspot Control account.
		   
		   	System.Net.WebException. If API call throws an exception, returns the entire exception.		   
	   	.PARAMETER ApiHost 
		   	Address of host for Workspot API. Default is production environment, "api.workspot.com".
	   	.PARAMETER ApiClientId
		   	API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
	   	.PARAMETER ApiClientSecret
		   	API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
	   	.PARAMETER WsControlUser
		   	Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
	   	.PARAMETER WsControlPass
		   	Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
	   	.EXAMPLE
		   	Get-WorkspotLicenseInfo
	   	.EXAMPLE
		   	Get-WorkspotLicenseInfo -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
   	#>    
   	Param(
	    [string] $ApiHost = "api.workspot.com",
	    [string] $AuthToken = "",
	    [string] $ApiClientId = "",
	    [string] $ApiClientSecret = "",
	    [string] $WsControlUser = "",
	    [string] $WsControlPass = ""
   	)
   	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
	   	"ApiClientId" = $ApiClientId
	   	"ApiClientSecret" = $ApiClientSecret
	   	"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
   	If(!$AuthToken) {
	    #Call Get-WorkspotApiToken to get a token if no -AuthToken was passed. 
	    #Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
 	    $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
    $Headers = @{Authorization =("Bearer "+ $AuthToken)}
    $ApiPath = "v1.0/licenses"
    $RestUri = "https://$ApiHost/$ApiPath"
    Try {
	    $ApiReturn = Invoke-RestMethod -Uri $RestUri -Method Get -Headers $Headers
	    If($ApiReturn.Licenses) { Return($ApiReturn.Licenses) }
	    Else { Return($ApiReturn) }
	    }
    Catch [System.Net.WebException] { Return($_) }
}

#TODO Change the status operation to check and display the desktop status each loop.
Function New-WorkspotVdiPoolVm { 
    <#
        .SYNOPSIS
			Creates new VDI computer within a Workspot VDI Pool
        .DESCRIPTION
			Uses Workspot API to add a new VDI computer within a specific
			Workspot VDI Pool.  Optionally, a name can be specified for the
			new VDI computer.  
			The API call to create a VDI computer is an asyncronous operation,
			and this function calls Get-WorkspotApiStatus to wait for 
			completion, then this function returns the full status.

			Running Set-WorkspotApiCredentials before running this function 
			will allow New-WorkspotVdiPoolVm to get its own oAuth token without 
			the need to specify credentials.
        .OUTPUTS
			System.String. Output is in JSON format. If the API call succeeds, output 
			will be the final status of the operation as produced by Get-WorkspotApiStatus.  
			
			System.String. Output is in JSON format. If the API call fails, 
			output will instead the returned error details from that call
			
			System.Net.WebException. If API call throws an exception, returns the entire exception.
		.PARAMETER PoolName
			Name of Workspot Control VDI Pool in which to create a new VDI Computer.
		.PARAMETER VmName
			Optional.  New computer name for the VDI Computer being created.
		.PARAMETER CreateAsynchronously
			Switch to allow function to complete without waiting for VM to finish creating.
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
        .EXAMPLE
			New-WorkspotVdiPoolVm  -PoolName "AzEastPool"
        .EXAMPLE
			New-WorkspotVdiPoolVm  -PoolName "AzEastPool" -CreateAsynchronously
        .EXAMPLE
			New-WorkspotVdiPoolVm  -PoolName "AzEastPool" -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
    #>   
    Param(
        [parameter(Mandatory=$True, 
			HelpMessage = "Enter the name of Workspot Control VDI Pool in which to create a new VDI Computer.")]
			[string] $PoolName,
		[switch] $CreateAsynchronously = $false,
		[string] $VmName,
        [string] $ApiHost = "api.workspot.com",
		[string] $AuthToken = "",
		[string] $ApiClientId = "",
		[string] $ApiClientSecret = "",
 		[string] $WsControlUser = "",
 		[string] $WsControlPass = ""
    )
	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
		"ApiClientId" = $ApiClientId
		"ApiClientSecret" = $ApiClientSecret
		"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
    If(!$AuthToken) {
		#Call Get-WorkspotApiToken to get a token if no -AuthToken was passed.
		#Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
        $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
    $Headers = @{Authorization =("Bearer "+ $AuthToken)}
    $PoolId = ((Get-WorkspotVDIPool -AuthToken $AuthToken -ApiHost $ApiHost) | Where-Object {$_.Name -like "$PoolName"}).Id
    $ApiPath = "v1.0/pools/$PoolId/desktops"
    $RestUri = "https://$ApiHost/$ApiPath"
	
	#Removed PoolId checking. The web call to the API service will return an appropriate error via exception.
    $CreateDesktopBody=@{}
    If($VmName) {$CreateDesktopBody += @{computerName=$VmName} }
    $PostParameters = $CreateDesktopBody | ConvertTo-Json
	Try { 
		$Return = (Invoke-RestMethod -Uri $RestUri -Method Post -Body $PostParameters -Headers $Headers -ContentType 'application/json')
		If($Return.StatusUrl) { 
			If($CreateAsynchronously) { Return($Return) }
			Else { Return(Get-WorkspotApiStatus -AuthToken $AuthToken -StatusUrl $Return.StatusUrl -StatusDelay 15) }
		}
		Else { Return ($Return) }
	}
	Catch [System.Net.WebException] { Return($_) }	
}

Function New-WorkspotUser {
    <#
        .SYNOPSIS
			Creates new user in Workspot Control
        .DESCRIPTION
			Uses Workspot API to add a new user to Workspot Control.
			Optionally, a VDI Pool can be specified to be assigned to this
			new user.
			
			The email address for this user will be checked in Active Directory,
			and this API call will fail if it is not found.

			Running Set-WorkspotApiCredentials before running this function 
			will allow New-WorkspotUser to get its own oAuth token without
			the need to specify credentials.
        .OUTPUTS
			System.String. Output is in JSON format. If the API call succeeds, output will
			be the final status of the operation as produced by Get-WorkspotApiStatus.  
			
			System.String. Output is in JSON format. If the API call fails, 
			output will instead the returned error details from that call
			
			System.Net.WebException. If API call throws an exception, returns the entire exception.
		.PARAMETER Email
			Email address of new Workspot user, must already exist in AD.
		.PARAMETER FirstName
			First name of new Workspot user.
		.PARAMETER LastName
			Last name of new Workspot user.
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
        .EXAMPLE
			New-WorkspotUser -Email "exampleuser@workspot.com" -FirstName "Jane" -LastName "Doe"
		.EXAMPLE
			New-WorkspotUser -Email "exampleuser@workspot.com" -FirstName "Jane" -LastName "Doe" -PoolName "AzEastPool"
        .EXAMPLE
			New-WorkspotUser -Email "exampleuser@workspot.com" -FirstName "Jane" -LastName "Doe" -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
    #>   
    Param(
        [parameter(Mandatory=$True, 
			HelpMessage = "Enter the email address of new Workspot user.  Note: account must already exist in AD.")]
			[string] $UserEmail,
		[parameter(Mandatory=$True, 
			HelpMessage = "Enter the first name of new Workspot user.")]
			[string] $FirstName,
		[parameter(Mandatory=$True, 
			HelpMessage = "Enter the last name of new Workspot user.")]
			[string] $LastName,
		[string] $ApiHost = "api.workspot.com",
		[string] $AuthToken = "",
		[string] $ApiClientId = "",
		[string] $ApiClientSecret = "",
 		[string] $WsControlUser = "",
 		[string] $WsControlPass = ""
    )
	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
		"ApiClientId" = $ApiClientId
		"ApiClientSecret" = $ApiClientSecret
		"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
    If(!$AuthToken) {
		#Call Get-WorkspotApiToken to get a token if no -AuthToken was passed.
		#Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
        $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
    $Headers = @{Authorization =("Bearer "+ $AuthToken)}
    $ApiPath = "v1.0/users"
    $RestUri = "https://$ApiHost/$ApiPath"

    $User = @{
        email = $UserEmail
        firstName = $FirstName
        lastName = $LastName
	}
	
	If ($PoolName) { 
		$PoolId = (Get-WorkspotVdiPool -PoolName $PoolName -AuthToken $AuthToken -ApiHost $ApiHost).Id
    	If($PoolId) {$User += @{poolId = $PoolId}}
	}	
	
	$UserJson = $User | ConvertTo-Json
    Try { 
		$Return = (Invoke-RestMethod -Uri $RestUri -Method Post -Headers $Headers -Body $UserJson -ContentType 'application/json')
		If($Return.StatusUrl) { Return(Get-WorkspotApiStatus -AuthToken $AuthToken -StatusUrl $Return.StatusUrl) }
		Else { Return ($Return) }
	}
	Catch [System.Net.WebException] { Return($_) }	
}

Function Set-WorkspotUserCostCenter { 
    <#
        .SYNOPSIS
			Assigns Workspot user to a specified Cost Center
        .DESCRIPTION
			Uses Workspot API to assign a Workspot user to a specified Cost Center.

			Running Set-WorkspotApiCredentials before running this function 
			will allow it to get its own oAuth token without the need to 
			specify credentials when calling this function.
        .OUTPUTS
			System.String. Output is in JSON format. If the API call succeeds, 
			output will be updated user details.
			
			System.String. Output is in JSON format. If the API call fails, 
			output will instead the returned error details from that call.
			
			System.Net.WebException. If API call throws an exception, returns the entire exception.
		.PARAMETER CostCenter
			Name of Cost Center that the Workspot useruser will be assigned to.
		.PARAMETER UserEmail
			Email of Workspot user to be assigned to the specified Cost Center.
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
        .EXAMPLE
			Set-WorkspotUserCostCenter -CostCenter "IT" -UserEmail "exampleuser@workspot.com" 
		.EXAMPLE
			Set-WorkspotUserCostCenter -CostCenter "10-092" -UserEmail "exampleuser@workspot.com" -AuthToken $AuthToken 
        .EXAMPLE
			Set-WorkspotUserCostCenter -CostCenter "Finance" -UserEmail "exampleuser@workspot.com" -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
    #>  
    Param(
        [parameter(Mandatory=$True, 
			HelpMessage = "Enter the Cost Center the user will be assigned to.")] 
			[string] $CostCenter,
        [parameter(Mandatory=$True, 
			HelpMessage = "Enter the email of Workspot user to be assigned to the Cost Center.")] 
			[string] $UserEmail, 
		[string] $ApiHost = "api.workspot.com",        
		[string] $AuthToken = "",
		[string] $ApiClientId = "",
		[string] $ApiClientSecret = "",
 		[string] $WsControlUser = "",
 		[string] $WsControlPass = ""
    )
	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
		"ApiClientId" = $ApiClientId
		"ApiClientSecret" = $ApiClientSecret
		"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
    If(!$AuthToken) {
		#Call Get-WorkspotApiToken to get a token if no -AuthToken was passed.
		#Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
        $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
    $Headers = @{Authorization =("Bearer "+ $AuthToken)}
    
    $ApiPath = ("v1.0/users/$UserEmail/assignCostCenter").Replace('@', '%40')
	$RestUri = "https://$ApiHost/$ApiPath"
	$PostParameters = @{costCenter = $CostCenter} | ConvertTo-Json
	Try { $Return = (Invoke-RestMethod -Uri $RestUri -Method Post -Headers $Headers -Body $PostParameters -ContentType 'application/json')}
	Catch [System.Net.WebException] { $Return = $_}	
	Return($Return) 
}

#TODO Add switch to function to retain all previous tags
Function Set-WorkspotVdiTags { 
    <#
        .SYNOPSIS
			Sets tags for specific Workspot VDI Computer
        .DESCRIPTION
			Uses Workspot API to set the tags on the specified VDI 
			computer in a Workspot VDI Pool.  This will remove all 
			existing tags and set only the specified tags.

			Running Set-WorkspotApiCredentials before running this function 
			will allow Set-WorkspotVdiTags to get its own oAuth token 
			without the need to specify credentials.
        .OUTPUTS
			System.String. Output is in JSON format. Output.StatusCode of 200 is successful.
			Output.StatusCode.400 is an error, and will contain details.
			
			System.Net.WebException. If API call throws an exception, output is the entire exception.
		.PARAMETER PoolName
			Name of Workspot VDI Pool containing VDI Computer to be tagged.	
		.PARAMETER VmName
			Name of VDI Computer to be tagged.
		.PARAMETER Tags
			Hashtable of name and value pairs to use as tags.
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
        .EXAMPLE
			Set-WorkspotVdiTags -PoolName "AzEastPool" -VmName "AzEastVdi-03" -Tags @{"dept" = "IT"; "created" = "2019_06_29"}
        .EXAMPLE
			Set-WorkspotVdiTags -PoolName "AzEastPool" -VmName "AzEastVdi-03" -Tags @{"dept" = "IT"; "created" = "2019_06_29"} -AuthToken $AuthToken 
        .EXAMPLE
			Set-WorkspotVdiTags -PoolName "AzEastPool" -VmName "AzEastVdi-03" -Tags @{"dept" = "IT"; "created" = "2019_06_29"} -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
    #>  
    Param(        
		[parameter(Mandatory=$True, 
			HelpMessage = "Enter the name of Workspot VDI Pool containing VDI Computer.")] 
			[string] $PoolName,     
		[parameter(Mandatory=$True, 
			HelpMessage = "Enter the name of VDI Computer.")] 
			[string] $VmName,  		
		[parameter(Mandatory=$True, 
			HelpMessage = 'Enter the tags and values as a hashtable. Example -  @{"dept" = "IT"; "created" = "2019_06_29"}')] 
			[hashtable] $Tags,  		
		[string] $ApiHost = "api.workspot.com",
		[string] $AuthToken = "",
		[string] $ApiClientId = "",
		[string] $ApiClientSecret = "",
 		[string] $WsControlUser = "",
 		[string] $WsControlPass = ""
    )
	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
		"ApiClientId" = $ApiClientId
		"ApiClientSecret" = $ApiClientSecret
		"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
    If(!$AuthToken) {
		#Call Get-WorkspotApiToken to get a token if no -AuthToken was passed.
		#Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
        $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
    $Headers = @{Authorization =("Bearer "+ $AuthToken)}

    $VdiPoolVmReturn = Get-WorkspotVdiPoolVm -AuthToken $AuthToken -ApiHost $ApiHost -PoolName $PoolName -VmName $VmName
    $PoolId = $VdiPoolVmReturn.PoolId
	$VmId = $VdiPoolVmReturn.Id

	If ($PoolId -and $VmId) {
		$ApiPath = "v1.0/pools/$PoolId/desktops/$VmId/tags"
		$RestUri = "https://$ApiHost/$ApiPath"
		$TagArray = @()
		$KeyList = $Tags.Keys | Sort-Object
		ForEach ($TagName in $KeyList) {
			$TagValue = $Tags[$TagName]
			$TagArray += @{name = $TagName; value = $TagValue}
		}
		$PostParameters = @{
			desktopId = $VmId
			poolId = $PoolId
			tags = $TagArray
			} | ConvertTo-Json -Depth 4
		Try { $Return = (Invoke-RestMethod -Uri $RestUri -Method Post -Headers $Headers -Body $PostParameters -ContentType 'application/json')}
		Catch [System.Net.WebException] { $Return = $_}
		Return($Return)
	}
	Else {
		Return("Failed to find VM Id for $VmName in $PoolName.")
	}
}

Function Set-WorkspotVdiUserAssignment { 
    <#
        .SYNOPSIS
			Assigns Workspot user to a VDI Pool, or to a specific VDI Computer
        .DESCRIPTION
			Uses Workspot API to add a Workspot user to a specified VDI Pool.
			When VmName is also specified, the user will be assigned to that
			particular VM.

			Running Set-WorkspotApiCredentials before running this function 
			will allow it to get its own oAuth token without the need to 
			specify credentials when calling this function.
        .OUTPUTS
			System.String. Output is in JSON format. If the User Assignment API call succeeds, 
			output will be the final status of the operation as produced by Get-WorkspotApiStatus. 
			If VmName is also specified, the successful output will instead be updated user details.
			
			System.String. Output is in JSON format. If the API call fails, 
			output will instead the returned error details from that call
			
			System.Net.WebException. If API call throws an exception, returns the entire exception.
			
			System.String. If a VM Name is provided and not found, returns "Failed to find VM Id for $VmName."
		.PARAMETER PoolName
			Name of Workspot VDI Pool containing the VDI Computer that the user will be assigned to.
		.PARAMETER UserEmail
			Email of Workspot user to be assigned to the VDI Computer.
		.PARAMETER VmName
			Optional. If VmName is specified, the user will be assigned to that specific Workspot VDI Computer.
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
        .EXAMPLE
			Set-WorkspotVdiUserAssignment -PoolName "AzEastPool" -UserEmail "exampleuser@workspot.com" 
        .EXAMPLE
			Set-WorkspotVdiUserAssignment -PoolName "AzEastPool" -VmName "AzEastVdi-03" -UserEmail "exampleuser@workspot.com"
        .EXAMPLE
			Set-WorkspotVdiUserAssignment -PoolName "AzEastPool" -VmName "AzEastVdi-03" -UserEmail "exampleuser@workspot.com" -AuthToken $AuthToken 
        .EXAMPLE
			Set-WorkspotVdiUserAssignment -PoolName "AzEastPool" -VmName "AzEastVdi-03" -UserEmail "exampleuser@workspot.com" -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
    #>  
    Param(
        [parameter(Mandatory=$True, 
			HelpMessage = "Enter the name of Workspot VDI Pool containing the VDI Computer that the user will be assigned to.")] 
			[string] $PoolName,
        [parameter(Mandatory=$True, 
			HelpMessage = "Enter the email of Workspot user to be assigned to the VDI Computer.")] 
			[string] $UserEmail, 
        [string] $VmName,
		[string] $ApiHost = "api.workspot.com",        
		[string] $AuthToken = "",
		[string] $ApiClientId = "",
		[string] $ApiClientSecret = "",
 		[string] $WsControlUser = "",
 		[string] $WsControlPass = ""
    )
	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
		"ApiClientId" = $ApiClientId
		"ApiClientSecret" = $ApiClientSecret
		"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
    If(!$AuthToken) {
		#Call Get-WorkspotApiToken to get a token if no -AuthToken was passed.
		#Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
        $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
    $Headers = @{Authorization =("Bearer "+ $AuthToken)}
    
    If($VmName) {
        $ApiPath = ("v1.0/users/$UserEmail/desktops").Replace('@', '%40')
        $RestUri = "https://$ApiHost/$ApiPath"
        $VmId = (Get-WorkspotVdiPoolVm -PoolName $PoolName -VmName $VmName -ApiHost $ApiHost -AuthToken $AuthToken).Id
        If($VmId) {
            $PostParameters = @{desktopId = $VmId} | ConvertTo-Json
			Try { $Return = (Invoke-RestMethod -Uri $RestUri -Method Post -Headers $Headers -Body $PostParameters -ContentType 'application/json')}
			Catch [System.Net.WebException] { $Return = $_}	
			Return($Return) 
        }
        Else {
            Return("Failed to find VM Id for $VmName in $PoolName")
        }
    }
    Else {
        $ApiPath = ("v1.0/users/$UserEmail/pools").Replace('@', '%40')
        $RestUri = "https://$ApiHost/$ApiPath"
        $PoolId = (Get-WorkspotVdiPool -PoolName $PoolName -AuthToken $AuthToken -ApiHost $ApiHost).Id
        $PostParameters = @{poolId=$PoolId} | ConvertTo-Json
		Try { 
			$Return = (Invoke-RestMethod -Uri $RestUri -Method Post -Headers $Headers -Body $PostParameters -ContentType 'application/json')
			If($Return.StatusUrl) { Return(Get-WorkspotApiStatus -AuthToken $AuthToken -StatusUrl $Return.StatusUrl) }
			Else { Return ($Return) }
		}
		Catch [System.Net.WebException] { Return($_) }	
	}    
}

Function Remove-WorkspotVdiUserAssignment { 
    <#
        .SYNOPSIS
			Removes assignment for Workspot user from the specified VDI Computer
        .DESCRIPTION
			Uses Workspot API to remove a Workspot user from a specified VDI computer.

			Running Set-WorkspotApiCredentials before running this function 
			will allow Remove-WorkspotVdiUserAssignment to get its own oAuth token 
			without the need to specify credentials.
        .OUTPUTS
			System.String. Output is in JSON format. Output.StatusCode of 204 is successful.
			StatusCode 204 won't include any details or messages, all other results will.
			
			System.Net.WebException. If API call throws an exception, output is the entire exception.
			
			System.String. If the provided VM Name is not found, output is "Failed to find VM Id for $VmName."
		.PARAMETER PoolName
			Name of Workspot VDI Pool containing the VDI Computer that the user will be un-assigned from.
		.PARAMETER VmName
			Name of Workspot VDI Computer that user will be un-assigned from.
		.PARAMETER UserEmail
			Email of Workspot user to be un-assigned from the VDI Computer.
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
        .EXAMPLE
			Remove-WorkspotVdiUserAssignment -PoolName "AzEastPool" -VmName "AzEastVdi-03" -UserEmail "exampleuser@workspot.com"
        .EXAMPLE
			Remove-WorkspotVdiUserAssignment -PoolName "AzEastPool" -VmName "AzEastVdi-03" -UserEmail "exampleuser@workspot.com" -AuthToken $AuthToken 
        .EXAMPLE
			Remove-WorkspotVdiUserAssignment -PoolName "AzEastPool" -VmName "AzEastVdi-03" -UserEmail "exampleuser@workspot.com" -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
    #>  
    Param(
        [parameter(Mandatory=$True, 
			HelpMessage = "Enter the name of Workspot VDI Pool containing the VDI Computer that the user will be un-assigned from.")] 
			[string] $PoolName,
        [parameter(Mandatory=$True, 
			HelpMessage = "Enter the name of Workspot VDI Computer that user will be un-assigned from")] 
			[string] $VmName,
        [parameter(Mandatory=$True, 
			HelpMessage = "Enter the email of Workspot user to be un-assigned from the VDI Computer.")] 
			[string] $UserEmail, 
        [string] $ApiHost = "api.workspot.com",
		[string] $AuthToken = "",
		[string] $ApiClientId = "",
		[string] $ApiClientSecret = "",
 		[string] $WsControlUser = "",
 		[string] $WsControlPass = ""
    )
	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
		"ApiClientId" = $ApiClientId
		"ApiClientSecret" = $ApiClientSecret
		"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
    If(!$AuthToken) {
		#Call Get-WorkspotApiToken to get a token if no -AuthToken was passed.
		#Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
        $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
    $Headers = @{Authorization =("Bearer "+ $AuthToken)}
    $VmId = (Get-WorkspotVdiPoolVm -PoolName $PoolName -VmName $VmName -ApiHost $ApiHost -AuthToken $AuthToken).Id
    If($VmId) {
        $ApiPath = ("v1.0/users/$UserEmail/desktops/$VmId").Replace('@', '%40')
        $RestUri = "https://$ApiHost/$ApiPath"
		Try { $Return = (Invoke-WebRequest -Uri $RestUri -Method Delete -Headers $Headers)}
		Catch [System.Net.WebException] { $Return = $_}	
		Return($Return) 
    }
    Else { Return("Failed to find VM Id for $VmName in $PoolName.") }

}

Function Remove-WorkspotUser { 
    <#
        .SYNOPSIS
			Deletes user account from Workspot Control
        .DESCRIPTION
			Uses Workspot API to delete the specified user account from Workspot Control.

			Running Set-WorkspotApiCredentials before running this function 
			will allow Remove-WorkspotUser to get its own oAuth token without 
			the need to specify credentials when calling this function.
        .OUTPUTS
			System.String. Output is in JSON format. Output.StatusCode of 204 is successful.
			StatusCode 204 won't include any details or messages, all other results will.
			
			System.Net.WebException. If API call throws an exception, output is the entire exception.
		.PARAMETER UserEmail 
			Email address of user to be deleted from Workspot Control.
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
        .EXAMPLE
			Remove-WorkspotUser -UserEmail "exampleuser@workspot.com"
        .EXAMPLE
			Remove-WorkspotUser -UserEmail "exampleuser@workspot.com" -AuthToken $AuthToken 
        .EXAMPLE
			Remove-WorkspotUser -UserEmail "exampleuser@workspot.com" -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
    #>  
    Param(
        [parameter(Mandatory=$True, 
			HelpMessage = "Enter the email address of user to be deleted from Workspot Control.")] 
			[string] $UserEmail, 
        [string] $ApiHost = "api.workspot.com",
		[string] $AuthToken = "",
        [string] $ApiClientId = "",
		[string] $ApiClientSecret = "",
 		[string] $WsControlUser = "",
 		[string] $WsControlPass = ""
    )
	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
		"ApiClientId" = $ApiClientId
		"ApiClientSecret" = $ApiClientSecret
		"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
    If(!$AuthToken) {
		#Call Get-WorkspotApiToken to get a token if no -AuthToken was passed.
		#Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
        $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
    $Headers = @{Authorization =("Bearer "+ $AuthToken)}
    $ApiPath = ("v1.0/users/$UserEmail/").Replace('@', '%40')
    $RestUri = "https://$ApiHost/$ApiPath"

    Try { $Return = (Invoke-WebRequest -Uri $RestUri -Method Delete -Headers $Headers)}
	Catch [System.Net.WebException] { $Return = $_}
	Return($Return) 
}

Function Remove-WorkspotVdiPoolVm { 
    <#
        .SYNOPSIS
			Deletes a VDI Computer from a Workspot VDI Pool
        .DESCRIPTION
			Uses Workspot API to delete the specified VDI computer
			from within a Workspot VDI Pool.

			Running Set-WorkspotApiCredentials before running this function 
			will allow Remove-WorkspotVdiPoolVm to get its own oAuth token 
			without the need to specify credentials.
        .OUTPUTS
			System.String. Output is in JSON format. Output.StatusCode of 204 is successful.
			StatusCode 204 won't include any details or messages, all other results will.
			
			System.Net.WebException. If API call throws an exception, output is the entire exception.
		.PARAMETER PoolName
			Name of Workspot VDI Pool containing VDI Computer to be deleted.	
		.PARAMETER VmName
			Name of VDI Computer to be deleted.
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
        .EXAMPLE
			Remove-WorkspotVdiPoolVm -PoolName "AzEastPool" -VmName "AzEastVdi-03"
        .EXAMPLE
			Remove-WorkspotVdiPoolVm -PoolName "AzEastPool" -VmName "AzEastVdi-03" -AuthToken $AuthToken 
        .EXAMPLE
			Remove-WorkspotVdiPoolVm -PoolName "AzEastPool" -VmName "AzEastVdi-03" -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
    #>  
    Param(        
		[parameter(Mandatory=$True, 
			HelpMessage = "Enter the name of Workspot VDI Pool containing VDI Computer to be deleted.")] 
			[string] $PoolName,     
		[parameter(Mandatory=$True, 
			HelpMessage = "Enter the name of VDI Computer to be deleted.")] 
			[string] $VmName,  		
        [string] $ApiHost = "api.workspot.com",
		[string] $AuthToken = "",
		[string] $ApiClientId = "",
		[string] $ApiClientSecret = "",
 		[string] $WsControlUser = "",
 		[string] $WsControlPass = ""
    )
	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
		"ApiClientId" = $ApiClientId
		"ApiClientSecret" = $ApiClientSecret
		"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
    If(!$AuthToken) {
		#Call Get-WorkspotApiToken to get a token if no -AuthToken was passed.
		#Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
        $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
    $Headers = @{Authorization =("Bearer "+ $AuthToken)}

    $VdiPoolVmReturn = Get-WorkspotVdiPoolVm -AuthToken $AuthToken -ApiHost $ApiHost -PoolName $PoolName -VmName $VmName
    $PoolId = $VdiPoolVmReturn.PoolId
    $VmId = $VdiPoolVmReturn.Id
	If ($PoolId -and $VmId) {
		$ApiPath = "v1.0/pools/$PoolId/desktops/$VmId"
		$RestUri = "https://$ApiHost/$ApiPath"

		#TODO Determine why this is Invoke-WebRequest and not RestMethod.
		#TODO When API returns an error value, this is throwing an exception instead of just returning the value.  Stop that.
		Try { $Return = (Invoke-WebRequest -Uri $RestUri -Method Delete -Headers $Headers)}
		Catch [System.Net.WebException] { $Return = $_}
		Return($Return)
	}
	Else {
		Return("Failed to find VM Id for $VmName in $PoolName.")
	}
}

Function Restart-WorkspotVdiPoolVm { 
    <#
        .SYNOPSIS
			Restarts the specified Workspot VDI computer
        .DESCRIPTION
			Uses Workspot API to restart the specified VDI computer
			from within a Workspot VDI Pool.

			Running Set-WorkspotApiCredentials before running this function 
			will allow Restart-WorkspotVdiPoolVm to get its own oAuth token 
			without the need to specify credentials.
        .OUTPUTS
			System.String. Output is in JSON format. Output.StatusCode of 204 is successful.
			StatusCode 204 won't include any details or messages, all other results will.
			
			System.Net.WebException. If API call throws an exception, output is the entire exception.
		.PARAMETER PoolName
			Name of Workspot VDI Pool containing VDI Computer to be deleted.	
		.PARAMETER VmName
			Name of VDI Computer to be deleted.
		.PARAMETER ApiHost 
			Address of host for Workspot API. Default is production environment, "api.workspot.com".
        .PARAMETER ApiClientId
			API Client ID from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER ApiClientSecret
			API Client Secret from Workspot Control. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlUser
			Workspot Control administrator email. Default is the value set by Set-WorkspotApiCredentials.
        .PARAMETER WsControlPass
			Workspot Control administrator password. Default is the value set by Set-WorkspotApiCredentials.
        .EXAMPLE
			Restart-WorkspotVdiPoolVm -PoolName "AzEastPool" -VmName "AzEastVdi-03"
        .EXAMPLE
			Restart-WorkspotVdiPoolVm -PoolName "AzEastPool" -VmName "AzEastVdi-03" -AuthToken $AuthToken 
        .EXAMPLE
			Restart-WorkspotVdiPoolVm -PoolName "AzEastPool" -VmName "AzEastVdi-03" -ApiClientId "B7KZJDRZ1vXnqsVdbe43" -ApiClientSecret "If0NYMk89DIQBppR0oCmBwxndm17A1QiuglA70uo" -WsControlUser "exampleadmin@workspot.com" -WsControlPass "P@ssw0rd" 
    #>  
    Param(        
		[parameter(Mandatory=$True, 
			HelpMessage = "Enter the name of Workspot VDI Pool containing VDI Computer to be restarted.")] 
			[string] $PoolName,     
		[parameter(Mandatory=$True, 
			HelpMessage = "Enter the name of VDI Computer to be restarted.")] 
			[string] $VmName,  		
        [string] $ApiHost = "api.workspot.com",
		[string] $AuthToken = "",
		[string] $ApiClientId = "",
		[string] $ApiClientSecret = "",
 		[string] $WsControlUser = "",
 		[string] $WsControlPass = ""
    )
	$ApiCredentialHash = @{ #Set up hash of all credentials passed in as parameters
		"ApiClientId" = $ApiClientId
		"ApiClientSecret" = $ApiClientSecret
		"WsControlUser" = $WsControlUser
		"WsControlPass" = $WsControlPass
	}
    If(!$AuthToken) {
		#Call Get-WorkspotApiToken to get a token if no -AuthToken was passed.
		#Any credentials from parameters will take precedence over values stored by Set-WorkspotApiCredentials.
        $AuthToken = Get-WorkspotApiToken -ApiHost $ApiHost @ApiCredentialHash
    }
    $Headers = @{Authorization =("Bearer "+ $AuthToken)}

    $VdiPoolVmReturn = Get-WorkspotVdiPoolVm -AuthToken $AuthToken -ApiHost $ApiHost -PoolName $PoolName -VmName $VmName
    $PoolId = $VdiPoolVmReturn.PoolId
    $VmId = $VdiPoolVmReturn.Id
	If ($PoolId -and $VmId) {
		$ApiPath = "v1.0/pools/$PoolId/desktops/$VmId/reboot"
		$RestUri = "https://$ApiHost/$ApiPath"

		Try { 
			$Return = (Invoke-RestMethod -Uri $RestUri -Method Post -Headers $Headers)
			If($Return.StatusUrl) { 
				If($CreateAsynchronously) { Return($Return) }
				Else { Return(Get-WorkspotApiStatus -AuthToken $AuthToken -StatusUrl $Return.StatusUrl) }
			}
			Else { Return ($Return) }
		}
		Catch [System.Net.WebException] { $Return = $_}
	}
	Else {
		Return("Failed to find VM Id for $VmName in $PoolName.")
	}
}

