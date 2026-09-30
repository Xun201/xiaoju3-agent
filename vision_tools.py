# -*- coding: utf-8 -*-
"""小橘3号 · 云端视觉模型点击。

按《架构设计文档》§5 安卓接管三件套之三：ADB 截图 → 发视觉模型
（OpenAI 兼容 chat/completions 格式）识别元素 Bounding Box 像素坐标 →
换算真实屏幕坐标 → adb_tap 点击。模型名与密钥来自 xiaoju3 配置
（VISION_MODEL / VISION_KEY，.env → 环境变量优先），未配置时返回清晰
中文提示串，不崩溃。

与参考实现的差异：依赖白名单无 Pillow，跳过"裁剪状态栏 + 压缩缩放"
优化，直接发送截图 PNG base64；缩放比经 PNG 头解析实际宽度换算
（screencap 原图与屏幕等分辨率时恒为 1），坐标换算公式保持参考实现
结构（center / scale_ratio + cropped_top，此处无裁剪 cropped_top=0）。
"""
import base64
import json
import os
import re
import subprocess

import requests

from adb_tools import adb_screenshot, adb_tap, SCREENSHOT_PATH
from xiaoju3 import VISION_MODEL, VISION_KEY

# 视觉端点：OpenAI 兼容 chat/completions（环境变量可覆盖，默认与参考实现一致）
VISION_URL = os.environ.get(
    "VISION_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
)


def _png_size(path):
    """读取 PNG 头部 IHDR 的宽高（stdlib 实现，替代 Pillow）。失败返回 None。"""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if len(head) >= 24 and head[:8] == b"\x89PNG\r\n\x1a\n":
            width = int.from_bytes(head[16:20], "big")
            height = int.from_bytes(head[20:24], "big")
            if width > 0 and height > 0:
                return width, height
    except Exception:
        pass
    return None


def get_screen_size():
    """获取手机屏幕的物理分辨率"""
    try:
        result = subprocess.run("adb shell wm size", shell=True, capture_output=True, text=True)
        match = re.search(r'(\d+)x(\d+)', result.stdout)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    return 1080, 2400


def vision_tap_element(element_name):
    """AI 看图 -> 识别元素像素坐标 -> 换算真实坐标 -> 自动点击"""
    if not VISION_KEY:
        return "❌ 未配置视觉 API Key，无法使用视觉点击功能。"
    if not VISION_MODEL:
        return "❌ 未配置视觉模型 VISION_MODEL，无法使用视觉点击功能。"

    # 1. 截图
    screenshot_result = adb_screenshot()
    if "失败" in screenshot_result:
        return screenshot_result
    if not os.path.exists(SCREENSHOT_PATH):
        return "❌ 截图文件不存在，请检查 ADB 连接。"

    # 2. 获取屏幕真实分辨率，换算缩放比（无裁剪，cropped_top=0）
    screen_width, _screen_height = get_screen_size()
    png_size = _png_size(SCREENSHOT_PATH)
    scale_ratio = (png_size[0] / screen_width) if png_size else 1.0
    cropped_top = 0

    # 3. 截图转 base64（PNG 原样发送，不经 Pillow 压缩）
    try:
        with open(SCREENSHOT_PATH, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return f"❌ 图片处理失败: {e}"

    # 4. 构造视觉模型请求（要求返回 Bounding Box 坐标框）
    headers = {"Authorization": f"Bearer {VISION_KEY}", "Content-Type": "application/json"}

    prompt = f"这是一个手机屏幕截图（已裁去顶部状态栏）。请仔细查找名为【{element_name}】的应用图标或按钮。特别警告：不要找天气、日历、时钟等桌面小组件！'{element_name}'通常是一个独立的App小图标（比如设置是一个灰色的齿轮，微信是绿色的气泡）。找到后，只返回一个 JSON，格式为：{{\"x1\": <左上角横坐标整数>, \"y1\": <左上角纵坐标整数>, \"x2\": <右下角横坐标整数>, \"y2\": <右下角纵坐标整数>}}，不要输出其他内容！"

    payload = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}},
        ]}],
        "temperature": 0.1,
    }

    try:
        response = requests.post(VISION_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        resp_json = response.json()

        if "choices" not in resp_json:
            return f"❌ 视觉模型返回异常: {resp_json}"
        content = resp_json["choices"][0]["message"]["content"]

        # 5. 提取 JSON 像素坐标（Bounding Box）
        match = re.search(r'\{.*"x1".*"y1".*"x2".*"y2".*\}', content, re.DOTALL)
        if not match:
            return f"❌ 视觉模型未能识别出坐标。回复内容：{content}"

        coord = json.loads(match.group(0))

        # 6. 计算框的中心点并换算成手机真实像素坐标
        center_x = (coord["x1"] + coord["x2"]) / 2
        center_y = (coord["y1"] + coord["y2"]) / 2

        real_x = int(center_x / scale_ratio)
        real_y = int(center_y / scale_ratio) + cropped_top

        print(f"🎯 视觉模型解析：模型识别框({coord['x1']},{coord['y1']})-({coord['x2']},{coord['y2']}) -> 实际屏幕中心坐标({real_x}, {real_y})")

        # 7. 执行点击
        return adb_tap(real_x, real_y)

    except Exception as e:
        return f"❌ 视觉模型调用失败: {e}"
