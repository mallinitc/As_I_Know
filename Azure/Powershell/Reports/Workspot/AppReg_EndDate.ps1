#This Script will fetch the Azure APP details and save it into excel file

$WSCustomers=Import-Csv -Path D:\WSData\AllCloudCustomers-190603.csv
$Dir=$env:USERPROFILE+"\Logs\APPS\"
If(!(Test-Path $Dir))
{
      New-Item -ItemType Directory -Force -Path $Dir
}
$Excel=$dir+"App_Data.xlsx"
$Output=@()
ForEach($Cust in $WSCustomers)
{
    If($Cust.Cloud -like 'US')
    {
        Clear-AzContext -Scope CurrentUser -Force
        Connect-AzAccount -Subscription $Cust.SubscriptionId -Tenant $Cust.TenantId
        
        If(Get-AzContext)
        {
            $Apps=Get-AzADApplication|Select-Object DisplayName, ObjectId
            ForEach($App in $Apps)
            {
                $Temp=Get-AzADAppCredential -ObjectId $App.ObjectId
                $Output += New-Object PsObject -Property @{
                    Subscription =$Cust.SubscriptionId
                    Customer=$Cust.Customer
                    Name = $App.DisplayName
                    KeyId = $Temp.KeyId
                    Start = $Temp.StartDate
                    End = $Temp.EndDate
                }

            }
        }

    }
}
$Output|Export-Excel -WorksheetName "PSData" -Path $Excel -Append

