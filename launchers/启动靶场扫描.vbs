Option Explicit

Dim fso, shell, baseDir, projectDir, exePath, appName
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

appName = ChrW(&H9776) & ChrW(&H573A) & ChrW(&H626B) & ChrW(&H63CF) & _
          ChrW(&H52A9) & ChrW(&H624B) & ".exe"
baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectDir = fso.GetParentFolderName(baseDir)
exePath = fso.BuildPath(baseDir, appName)
If Not fso.FileExists(exePath) Then
    exePath = fso.BuildPath(projectDir, ".artifacts\dist\" & appName)
End If

If Not fso.FileExists(exePath) Then
    MsgBox "Executable not found. Run scripts\build_windows.ps1 first, or place the EXE beside this launcher.", _
           vbExclamation, appName
    WScript.Quit 1
End If

shell.CurrentDirectory = baseDir
shell.Run Chr(34) & exePath & Chr(34), 0, False
