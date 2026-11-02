Set sh = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = folder
pythonw = folder & "\.venv\Scripts\pythonw.exe"
If fs.FileExists(pythonw) Then
    sh.Run """" & pythonw & """ """ & folder & "\app.py"" --open", 0, False
Else
    sh.Run """" & folder & "\Iniciar.cmd""", 1, False
End If
