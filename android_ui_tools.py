import re
import subprocess
from adb_tools import adb_tap

def ui_tap_element(element_name):
    """通过 Android 原生 UI 层级（uiautomator）精确定位并点击元素"""
    try:
        # 1. 导出当前屏幕的 UI 层级 XML
        print(f"🔍 [UI解析] 正在查找元素: {element_name}...")
        subprocess.run("adb shell uiautomator dump /sdcard/window_dump.xml", shell=True, check=True, capture_output=True)
        
        # 2. 读取 XML 内容
        result = subprocess.run("adb shell cat /sdcard/window_dump.xml", shell=True, capture_output=True, text=True, check=True)
        xml_content = result.stdout

        if not xml_content:
            return "❌ UI 解析失败：未获取到 XML 数据，请检查手机屏幕是否亮起。"

        # 3. 在 XML 中查找目标文本或描述
        # 匹配 text="设置" 或 content-desc="设置"
        pattern = rf'(text="{element_name}"|content-desc="{element_name}").*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
        match = re.search(pattern, xml_content, re.DOTALL)

        if not match:
            return f"❌ UI 层级中未找到【{element_name}】，请确认它目前在屏幕上可见，或者它没有文本/描述标签。"

        # 4. 提取坐标并计算中心点
        x1, y1, x2, y2 = map(int, match.groups()[-4:])
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        
        print(f"🎯 [UI解析] 找到【{element_name}】，边界框({x1},{y1})-({x2},{y2}) -> 实际坐标({center_x}, {center_y})")
        
        # 5. 执行点击
        return adb_tap(center_x, center_y)

    except Exception as e:
        return f"❌ UI 层级解析失败: {e}"