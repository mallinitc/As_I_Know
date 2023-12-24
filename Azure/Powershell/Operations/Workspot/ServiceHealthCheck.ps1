
Clear-AzContext -Scope CurrentUser -Force

$Cust = Import-Csv -Path C:\AzCustList_Feb16_21\AzureCSP-USA_Customer_List.csv|Out-GridView -PassThru

Connect-AzAccount -Subscription $Cust.SubscriptionId -Tenant $Cust.TenantId


$ActionGroupName = 'HA_WS' #max_length of the name is 12 char. Make sure you identify with the customer name
$HealthAlertName = 'HA_WS-Alert' #Make sure you identify with the customer name ex. 'customername-alert'

$RGgroup=(Get-AzResource |Group-Object ResourceGroupName |Sort-Object Count -Descending)[0]
$RGgroup.Name


#Creating an ActionGroup
$emails = @('support@workspot.com') 
$rgName = $RGgroup.Name
$emailReceivers = @()

foreach ($email in $emails) {
    $emailReceiver = New-AzActionGroupReceiver -EmailReceiver -EmailAddress $email -Name $email
    $emailReceivers += $emailReceiver
}

Set-AzActionGroup -ResourceGroupName $rgName -Name $ActionGroupName -ShortName $ActionGroupName -Receiver $emailReceivers


$actiongroup = Get-AzActionGroup -Name $ActionGroupName -ResourceGroup $rgName -WarningAction Ignore
$actiongroup.Id
 

New-AzResourceGroupDeployment -Name $HealthAlertName -ResourceGroupName $rgName  `
-TemplateFile "C:\Scripts\Service_health\csoperations.json" `
-activityLogAlertName $HealthAlertName `
-actionGroupResourceId $actiongroup.Id


$cust.customer >>C:\temp\logs.txt