# -*- coding: utf-8 -*-
"""Windows 子进程控制台窗口抑制（2026-10-04 尾巴 A）。

现象：工具链子进程（adb / uiautomator / pip / playwright node driver）
在无控制台的冻结 exe 里每次创建都会闪黑框——子进程分配新 console 时
SW_HIDE 只能隐藏已创建的窗口，CREATE_NO_WINDOW 才从源头不建。

用法：subprocess.run(..., creationflags=win_process.creation_flags())；
非 Windows（os.name != "nt"）恒返回 0，跨平台零影响。
"""
import os

# Windows-only：子进程不继承/不创建控制台窗口
CREATE_NO_WINDOW = 0x08000000


def creation_flags():
    """按平台返回子进程 creationflags；非 Windows 恒 0（参数跨平台安全）。"""
    if os.name == "nt":
        return CREATE_NO_WINDOW
    return 0
