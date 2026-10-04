# -*- coding: utf-8 -*-
"""小橘3号 · uiautomator 界面元素精准点击。

按《架构设计文档》§5 安卓接管三件套之二：uiautomator dump 导出当前屏幕
UI 层级 → xml.etree 解析，按 text / content-desc 精确匹配 → 计算 bounds
中心点 → 调 adb_tap 点击。

导出优先 `adb exec-out uiautomator dump /dev/tty` 单次往返（dump 直吐
stdout，省去 pull 的第二次 adb 通信延迟）；exec-out 失败（返回码非 0 /
stdout 无 XML）时自动回退旧版「dump 到设备文件 + adb pull 拉取」两步法，
功能不退化。找不到元素时返回明确失败串，供模型按点击优先级（prompts.py
规则）回退 vision_tap_element。

文件 MD5 工具（2026-10-01 用户指令，任务 3 后半）：file_md5(path) 供
vision_tools 点击前后变化检测复用——stdlib hashlib 分块计算，文件不
存在/不可读等任何失败返回 None、不抛异常（调用方兜底降级）。
"""
import hashlib
import os
import re
import subprocess

import win_process
import tempfile
import xml.etree.ElementTree as ET

from adb_tools import adb_tap

# exec-out 单次往返命令：dump 到 /dev/tty 使 XML 直吐 stdout
EXEC_OUT_DUMP_CMD = "adb exec-out uiautomator dump /dev/tty"
# 回退路径（旧两步法）的 uiautomator 导出路径（设备侧 / 本地侧）
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


def strip_xml_noise(text):
    """剥离 exec-out 输出中首个 XML 声明（'<?xml' / '<?'）之前的噪声。

    部分设备 dump 到 /dev/tty 时会在 XML 前夹带日志行（如
    "UI hierchary dumped to: ..."）或编码前缀，定位到声明处截断。
    无声明或声明已在开头时原样返回。
    """
    if not text:
        return text
    idx = text.find("<?xml")
    if idx < 0:
        idx = text.find("<?")
    return text[idx:] if idx > 0 else text


def file_md5(path):
    """计算文件 MD5（2026-10-01 用户指令，任务 3 后半）：stdlib hashlib
    分块读取（65536 字节/块，防大文件占内存）。文件不存在/不可读/路径
    是目录等任何失败返回 None、不抛异常，由调用方兜底降级。"""
    try:
        md5 = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                md5.update(chunk)
        return md5.hexdigest()
    except Exception:
        return None


def _dump_ui_xml_exec_out():
    """exec-out 单次往返导出 UI 层级（失败抛异常 / 无 XML 返回 None）。

    返回码非 0 由 check=True 抛 CalledProcessError；返回码为 0 但 stdout
    无 XML（如部分设备只打 "ERROR: could not get idle state."）同样视为
    失败，返回 None 由上层回退两步法。
    """
    proc = subprocess.run(EXEC_OUT_DUMP_CMD,
                          shell=True, check=True, capture_output=True,
                          creationflags=win_process.creation_flags())
    # exec-out 输出为字节流，errors="replace" 容忍设备端编码噪声
    text = strip_xml_noise(proc.stdout.decode("utf-8", errors="replace"))
    if "<?xml" not in text and "<hierarchy" not in text:
        return None
    return text


def _dump_ui_xml_dump_pull():
    """旧两步法回退路径：dump 到设备文件 → adb pull 拉回本地再读取。"""
    # 1. 导出当前屏幕的 UI 层级 XML
    subprocess.run(f"adb shell uiautomator dump {REMOTE_DUMP_PATH}",
                   shell=True, check=True, capture_output=True,
                   creationflags=win_process.creation_flags())
    # 2. 拉取 XML 到本地再读取
    subprocess.run(f"adb pull {REMOTE_DUMP_PATH} {LOCAL_DUMP_PATH}",
                   shell=True, check=True, capture_output=True,
                   creationflags=win_process.creation_flags())
    with open(LOCAL_DUMP_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _dump_ui_xml():
    """导出当前屏幕 UI 层级 XML 文本（失败抛异常，由上层兜底）。

    优先 exec-out 单次往返（减少一次 adb 通信延迟）；exec-out 失败
    （返回码非 0 / 无 XML 输出）时自动回退旧版 dump+pull 两步法。
    """
    try:
        xml = _dump_ui_xml_exec_out()
        if xml:
            return xml
    except Exception:
        pass  # 设备不支持 exec-out dump 等 → 回退两步法
    return _dump_ui_xml_dump_pull()


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
