import subprocess

def adb_screenshot():
    """通过 ADB 截取手机屏幕"""
    tmp_path = "/tmp/adb_screen.png"
    try:
        subprocess.run(f"adb exec-out screencap -p > {tmp_path}", shell=True, check=True)
        return f"✅ 手机屏幕截图已保存至: {tmp_path}"
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