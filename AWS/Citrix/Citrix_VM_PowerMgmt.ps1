#Citrix Xendesktop hosted on AWS Cloud

#Citrix VM - Power Management

#Prompting with below options
#If VM is running then do you want to power it off? YES/NO
#If VM is not running then do you want to power it on? YES/NO

function StartVM {
  $iid = $args[0]
  Start-EC2Instance -InstanceId $iid
  Start-Sleep -s 15

}

function StopVM {
  $iid = $args[0]
  Stop-EC2Instance -InstanceId $iid
  Start-Sleep -s 15

}


#$hostname = Read-Host -Prompt "Please enter hostname as in DDC!"

$a = new-object -comobject wscript.shell


[void][Reflection.Assembly]::LoadWithPartialName('Microsoft.VisualBasic')

$title = 'AWS Power Management'
$msg = 'Enter the hostname as in DDC (Ex: 10-11-12-13)'

$hostname = [Microsoft.VisualBasic.Interaction]::InputBox($msg, $title)
if ($hostname) {
  $hostname = $hostname.Trim()


  $DDC = "<IP>"



  $hostname = $hostname.Replace("<DOMAIN>\", "")
  $hostname = $hostname.Replace("-", ".")


  $instance = Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }
  if ($instance.Tags.Key.Contains("CTXInstance")) {


    if ($instance.State.Name.Value -notlike "Running") {
      #$next = Read-Host -Prompt "VM is not running. You want to start it. Yes/No"

      $intAnswer = $a.popup("VM $hostname is not running. You want to start it?", `
          0, "No", 4)
      If ($intAnswer -eq 6) {
        $a.popup("Starting the $hostname. Please wait for sometime.")
        StartVM $instance.InstanceId
      } 
      else {
        $a.popup("You answered No.Exiting the script")
      }
 

    }
    else {
      #Stopping the VM if its running
      #$next = Read-Host -Prompt "VM is running. You want to stop it. Yes/No"
      $a = new-object -comobject wscript.shell
      $intAnswer = $a.popup("VM $hostname is running. You want to stop it?", `
          0, "No", 4)
      If ($intAnswer -eq 6) {
        $type = $instance.Tags | ? { $_.key -eq "CTXInstance" } | select -expand Value

        if ($type -like 'ctxinfrastructure') {
          $a = new-object -comobject wscript.shell
          $intAnswer = $a.popup("VM $hostname is Citrix Infra Server. You still want to stop it?", `
              0, "No", 4)
          If ($intAnswer -eq 6) {

            $a.popup("Stopping the $hostname. Please wait for sometime.")
            StopVM $instance.InstanceId

          }

        }
        else {
          $a.popup("Stopping the $hostname. Please wait for sometime.")
          StopVM $instance.InstanceId
        }
      } 
      else {
        $a.popup("You answered No.Exiting the script")
      }

    }
    Start-Sleep -Seconds 5

    $status = (Get-EC2Instance | select -ExpandProperty RunningInstance | ? { $_.PrivateIPaddress -eq "$hostname" }).State.Name.Value

    $a.popup("The VM current status is '$status'")
  }

  elseif ($instance) {
    $a.popup("$hostname doesn't have CTXInstance tag. So exiting the script")
  }
  else {
    $a.popup("$hostname is not found. Exiting the script")
  }
}

else {

  $a.popup("No input is given. Exiting the script")

}