# -*- coding: utf-8 -*-
"""小橘3号 · uiautomator 界面元素精准点击。

按《架构设计文档》§5 安卓接管三件套之二：uiautomator dump 导出当前屏幕
UI 层级 → adb pull 拉取 XML → xml.etree 解析，按 text / content-desc 精确
匹配 → 计算 bounds 中心点 → 调 adb_tap 点击。
找不到元素时返回明确失败串，供模型按点击优先级（prompts.py 规则）回退
vision_tap_element。
"""
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from adb_tools import adb_tap

# uiautomator 导出路径（设备侧 / 本地侧）
REMOTE_DUMP_PATH = "/sdcard/window_dump.xml"
LOCAL_DUMP_PATH = os.path.join(tempfile.gettempdir(), "window_dump.xml")


def parse_bounds(bounds):
    """解析 uiautomator bounds 属性 '[x1,y1][x2,y2]' → (x1, y1, x2, y2)。

    格式非法返回 None。
    """
    nums = re.findall(r'-?\d+', bounds or "")
    if len(nums) != 4:
        return None
    x1, y1, x2, y2 = map(int, nums)
    return x1, y1, x2, y2


def find_element_center(xml_content, element_name):
    """在 UI 层级 XML 中按 text / content-desc 精确匹配元素。

    命中返回 bounds 中心点 (center_x, center_y)（文档序首个命中），
    找不到 / XML 为空或非法返回 None。
    """
    if not xml_content:
        return None
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return None

    for node in root.iter("node"):
        if node.get("text") == element_name or node.get("content-desc") == element_name:
            bounds = parse_bounds(node.get("bounds", ""))
            if bounds:
                x1, y1, x2, y2 = bounds
                return (x1 + x2) // 2, (y1 + y2) // 2
    return None


def _dump_ui_xml():
    """导出并拉取当前屏幕 UI 层级，返回 XML 文本（失败抛异常，由上层兜底）。"""
    # 1. 导出当前屏幕的 UI 层级 XML
    subprocess.run(f"adb shell uiautomator dump {REMOTE_DUMP_PATH}",
                   shell=True, check=True, capture_output=True)
    # 2. 拉取 XML 到本地再读取
    subprocess.run(f"adb pull {REMOTE_DUMP_PATH} {LOCAL_DUMP_PATH}",
                   shell=True, check=True, capture_output=True)
    with open(LOCAL_DUMP_PATH, "r", encoding="utf-8") as f:
        return f.read()


def ui_tap_element(element_name):
    """通过 Android 原生 UI 层级（uiautomator）精确定位并点击元素"""
    try:
        print(f"🔍 [UI解析] 正在查找元素: {element_name}...")
        xml_content = _dump_ui_xml()

        if not xml_content:
            return "❌ UI 解析失败：未获取到 XML 数据，请检查手机屏幕是否亮起。"

        # 3. 在 XML 中查找目标文本或描述并计算中心点
        center = find_element_center(xml_content, element_name)
        if not center:
            return f"❌ UI 层级中未找到【{element_name}】，请确认它目前在屏幕上可见，或者它没有文本/描述标签。"

        center_x, center_y = center
        print(f"🎯 [UI解析] 找到【{element_name}】-> 实际坐标({center_x}, {center_y})")

        # 4. 执行点击
        return adb_tap(center_x, center_y)
    except Exception as e:
        return f"❌ UI 层级解析失败: {e}"
