Option Explicit

Dim shell, fileSystem, projectFolder, command
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

projectFolder = fileSystem.GetParentFolderName(WScript.ScriptFullName)
command = Chr(34) & projectFolder & "\iniciar_mvp.bat" & Chr(34) & " --hidden"

' 0 = ventana oculta; False = no bloquear el acceso directo mientras corre el servidor.
shell.Run command, 0, False
