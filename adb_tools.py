# -*- coding: utf-8 -*-
"""小橘3号 · ADB 原语（截图 / 点击 / 滑动）。

按《架构设计文档》§5 安卓接管三件套之一：subprocess 调 adb。
截图路径取系统临时目录（Linux 部署目标下即 /tmp/adb_screen.png，与参考
实现一致），经 os.path 拼接以兼容 Windows 与 Linux。
"""
import os
import subprocess
import tempfile

# 截图落盘路径（vision_tools 亦从此路径读取）
SCREENSHOT_PATH = os.path.join(tempfile.gettempdir(), "adb_screen.png")


def adb_screenshot():
    """通过 ADB 截取手机屏幕"""
    try:
        subprocess.run(f"adb exec-out screencap -p > {SCREENSHOT_PATH}", shell=True, check=True)
        return f"✅ 手机屏幕截图已保存至: {SCREENSHOT_PATH}"
    except Exception as e:
        return f"❌ ADB 截图失败: {e}"


def adb_tap(x, y):
    """模拟点击手机屏幕坐标"""
    try:
        subprocess.run(f"adb shell input tap {x} {y}", shell=True, check=True)
        return f"✅ 已模拟点击坐标: ({x}, {y})"
    except Exception as e:
        return f"❌ ADB 点击失败: {e}"


def adb_swipe(x1, y1, x2, y2, duration=300):
    """模拟滑动手机屏幕"""
    try:
        subprocess.run(f"adb shell input swipe {x1} {y1} {x2} {y2} {duration}", shell=True, check=True)
        return f"✅ 已模拟滑动: 从({x1},{y1})到({x2},{y2})"
    except Exception as e:
        return f"❌ ADB 滑动失败: {e}"
