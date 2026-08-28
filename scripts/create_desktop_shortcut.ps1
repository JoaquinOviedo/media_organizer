$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "Photo Swipper Filter.lnk"
$WscriptPath = Join-Path $env:SystemRoot "System32\wscript.exe"
$VbsPath = Join-Path $ProjectRoot "iniciar_swipeclean.vbs"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $WscriptPath
$shortcut.Arguments = '"' + $VbsPath + '"'
$shortcut.WorkingDirectory = $ProjectRoot
$shortcut.Description = "Iniciar Photo Swipper Filter y abrirlo en el navegador"
$shortcut.IconLocation = (Join-Path $env:SystemRoot "System32\imageres.dll") + ",67"
$shortcut.Save()

Write-Output $ShortcutPath
