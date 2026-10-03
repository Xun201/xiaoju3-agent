# -*- coding: utf-8 -*-
"""小橘3号 · 开机自启注册表工具（安装器方案步 A4a，docs/INSTALLER_STEP_A4_DESIGN.md §三）。

HKCU Run 键（零 UAC、任务管理器"启动"页原生可见可关）：
    SUBKEY = Software\\Microsoft\\Windows\\CurrentVersion\\Run
    VALUE_NAME = "Xiaoju3"，值为 target_command() 生成的启动命令串。

触发点分工：装时 Inno [Registry] 写（同键同格式，最后写入者胜）；程序内
complete 勾选/设置页走本模块；卸载 Inno [UninstallRun] 删值（容错）。

平台守卫：winreg 延迟 import + 四函数入口 `os.name != "nt"` 直接返回——
香橙派 Linux 侧零操作（与 ensure_napcat 的 POSIX 跳过同款口径）。
"""
import os
import sys

_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Xiaoju3"


def target_command():
    """自启命令串：frozen → exe 自身（desktop 角色免参数，开机即弹控制台）；
    非 frozen → pythonw 无黑框形态 + desktop_launcher.py 全路径（与启动链
    同口径，复用 _windowless_python 解析）。路径一律双引号（容忍空格）。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    from desktop_launcher import _windowless_python  # 延迟导入：避免拉全链
    py = _windowless_python()
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "desktop_launcher.py")
    return f'"{py}" "{script}"'


def read():
    """读当前自启命令串；未写入/键不存在/非 Windows 返回 None。"""
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SUBKEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return value
    except FileNotFoundError:
        return None
    except OSError:
        return None


def write():
    """写/覆盖自启键。成功 True；失败（非 Windows/权限等）False——
    自启非关键路径，失败由调用方降级为 warning 不阻塞。"""
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _SUBKEY) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ,
                              target_command())
        return True
    except OSError:
        return False


def remove():
    """删自启键（幂等：值不存在时返回 False，不抛错）。删除执行成功 True。"""
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SUBKEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False   # 幂等：值本就不存在，已是目标态
    except OSError:
        return False


def is_enabled():
    """自启是否已启用（read 命中即启用）。"""
    return read() is not None
