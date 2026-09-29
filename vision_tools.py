import os
import re
import json
import base64
import subprocess
import requests
import io
from PIL import Image
from dotenv import load_dotenv
from adb_tools import adb_screenshot, adb_tap

load_dotenv("/home/orangepi/xiaoju3_data/.env")
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
VISION_MODEL = os.environ.get("VISION_MODEL", "qwen3.8-omni-flash")

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
    """AI 看图 -> 识别元素像素坐标 -> 换算真实坐标 -> 自动点击（裁剪状态栏 + Bounding Box优化版）"""
    if not DASHSCOPE_API_KEY:
        return "❌ 未配置视觉 API Key，无法使用视觉点击功能。"
    
    # 1. 截图
    screenshot_result = adb_screenshot()
    if "失败" in screenshot_result:
        return screenshot_result
    image_path = "/tmp/adb_screen.png"
    if not os.path.exists(image_path):
        return "❌ 截图文件不存在，请检查 ADB 连接。"
    
    # 2. 获取屏幕真实分辨率
    screen_width, screen_height = get_screen_size()
    
    # 3. 核心优化：裁剪状态栏 + 压缩图片
    try:
        with Image.open(image_path) as img:
            # 裁剪掉顶部 100 像素的状态栏（避开干扰）
            top_crop = 100
            img = img.crop((0, top_crop, img.width, img.height))
            
            # 如果图片宽度大于 720，等比缩小到宽 720
            if img.width > 720:
                ratio = 720.0 / img.width
                new_size = (720, int(img.height * ratio))
                # 兼容旧版 Pillow
                if hasattr(Image, 'Resampling'):
                    resample_filter = Image.Resampling.LANCZOS
                else:
                    resample_filter = Image.LANCZOS
                img = img.resize(new_size, resample_filter)
            
            # 保存为 JPEG 并转为 base64
            buffer = io.BytesIO()
            img.convert("RGB").save(buffer, format="JPEG", quality=80)
            img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # 记录缩放比例，方便后续换算
            scale_ratio = img.width / screen_width
            cropped_top = top_crop
    except Exception as e:
        print(f"⚠️ 图片处理失败: {e}")
        return f"❌ 图片处理失败: {e}"

    # 4. 构造视觉模型请求（要求返回 Bounding Box 坐标框）
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DASHSCOPE_API_KEY}", "Content-Type": "application/json"}
    
    prompt = f"这是一个手机屏幕截图（已裁去顶部状态栏）。请仔细查找名为【{element_name}】的应用图标或按钮。特别警告：不要找天气、日历、时钟等桌面小组件！'{element_name}'通常是一个独立的App小图标（比如设置是一个灰色的齿轮，微信是绿色的气泡）。找到后，只返回一个 JSON，格式为：{{\"x1\": <左上角横坐标整数>, \"y1\": <左上角纵坐标整数>, \"x2\": <右下角横坐标整数>, \"y2\": <右下角纵坐标整数>}}，不要输出其他内容！"
    
    payload = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}]}],
        "temperature": 0.1
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
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