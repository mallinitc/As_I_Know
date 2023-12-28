##Streamed / AD group

$users=(Get-ADGroupMember NAME).SamAccountName
foreach($user in $users)
{
    $usr=$user.Trim()

    (Get-ADUser $usr -Properties *).EmailAddress
}


##StreamedD

$users=(Get-BrokerDesktop -AdminAddress NAME -CatalogName "NAME").AssociatedUserNames
foreach($user in $users)
{
    $usr=$user.Trim()
    $usr=$usr.Replace("VDSI\","")
    (Get-ADUser $usr -Properties *).EmailAddress
}