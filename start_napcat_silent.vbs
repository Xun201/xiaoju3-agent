' 小橘3号 - NapCat 静默启动脚本（双击即后台运行，无黑框）
' 原理：WScript.Shell.Run 第二参 0 = 隐藏窗口，第三参 False = 不等待
' 注意：NapCat 的 launcher.bat 需要管理员权限 - 双击后会弹一次 UAC，
'       点【是】即可；之后 NapCat 常驻后台，与本脚本无关。
' 路径自定义：NapCat 不在 D:\NapCat 时，修改下面 Run 里的路径。
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d D:\NapCat && launcher.bat", 0, False
