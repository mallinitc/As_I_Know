Stop-Service -name *workspot*
Stop-process -name *workspot*
taskkill /IM msiexec.exe /f
msiexec.exe /i c:\programdata\workspotmsiupgrade\setup.msi /q /LOG "upgrade1.log"