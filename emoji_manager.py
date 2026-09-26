import requests
import os
import random
import json

EMOJI_DIR = "/mnt/agent/workspace/emoji_library"

def get_emoji_path(tag):
    """根据标签查找表情包，比如找'开心'"""
    if not os.path.exists(EMOJI_DIR):
        return None
    for filename in os.listdir(EMOJI_DIR):
        # 只要文件名里包含这个标签（比如 "开心.png" 或 "开心 猫猫.jpg"），就认为是这个表情
        if tag in filename:
            return os.path.join(EMOJI_DIR, filename)
    return None

def get_random_emoji():
    """随便拿一张表情包"""
    if not os.path.exists(EMOJI_DIR):
        return None
    files = os.listdir(EMOJI_DIR)
    if files:
        return os.path.join(EMOJI_DIR, random.choice(files))
    return None

def download_emoji(url, tag="unknow"):
    """下载图片到本地表情库"""
    if not os.path.exists(EMOJI_DIR):
        os.makedirs(EMOJI_DIR)
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            # 为了避免重名覆盖，用随机数命名
            filename = f"{tag}_{random.randint(1000, 9999)}.jpg"
            filepath = os.path.join(EMOJI_DIR, filename)
            with open(filepath, 'wb') as f:
                f.write(res.content)
            print(f"✅ 表情已保存到: {filepath}")
            return True
        else:
            print(f"❌ 表情下载失败，状态码: {res.status_code}")
            return False
    except Exception as e:
        print(f"❌ 表情下载出错: {e}")
        return False

EMOJI_LOG_FILE = "/mnt/agent/workspace/emoji_library/emoji_links.json"

def save_emoji_link(url):
    """只把图片链接存进记事本，不下载，绝对不卡"""
    try:
        os.makedirs(os.path.dirname(EMOJI_LOG_FILE), exist_ok=True)
        # 读取现有数据
        if os.path.exists(EMOJI_LOG_FILE):
            with open(EMOJI_LOG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = []
        # 加入新链接
        if url not in data:
            data.append(url)
        # 写回文件
        with open(EMOJI_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ 保存表情链接失败: {e}")
        return False
