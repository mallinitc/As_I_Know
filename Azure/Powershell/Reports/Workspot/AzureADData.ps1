Connect-AzureAD

$Dir = $env:USERPROFILE+"\Logs\"
If(!(Test-Path $Dir))
{
      New-Item -ItemType Directory -Force -Path $Dir
}
$Excel = $Dir+"AzureAD.xlsx"

#AAD Users
$Output=@()
$Users=Get-AzureADUser
ForEach($User in $Users)
{
    $Output+=New-Object PsObject -Property @{
    Name=$User.DisplayName
    UserType=$User.UserType
    EmailId=$User.UserPrincipalName
    CreatedOn=$User.ExtensionProperty.createdDateTime
   
    }
}
$Output|Export-Excel -WorksheetName "Users" -Path $Excel -Append

#AAD Domains
$Output=@()
$Domains=Get-AzureADDomain
ForEach($Domain in $Domains)
{
    $Output+=New-Object PsObject -Property @{
    Name=$Domain.Name
    AuthenticationType=$Domain.AuthenticationType
    IsRoot=$Domain.IsRoot
    IsVerified=$Domain.IsVerified
    
    }
}
$Output|Export-Excel -WorksheetName "Domains" -Path $Excel -Append


