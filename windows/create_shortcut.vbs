Set objShell = WScript.CreateObject("WScript.Shell")
strStartMenu = objShell.SpecialFolders("StartMenu")
Set objShortCut = objShell.CreateShortcut(strStartMenu & "\nvfPostprocessor.lnk")
objShortCut.TargetPath = WScript.Arguments(0)
objShortCut.Save