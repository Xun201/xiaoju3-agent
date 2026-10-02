# -*- coding: utf-8 -*-
"""小橘3号 · 表情包收藏与配图回复闭环（架构设计文档 §5 / §10 #6、功能文档 §5）。

- save_emoji_link(url)：收到非 @ 图片消息时把链接追加进本地"小仓库"——
  落盘 agent_state/emoji_links.json（文件名与参考实现一致，位置收敛到
  统一配置的 agent_state 隔离区），去重 + 容量截断（滚动保留最新
  MAX_EMOJI_LINKS 条，防链接无限膨胀）。
- download_emoji(url, tag)：从链接下载图片到本地表情库 xiaoju3_data/emoji/
  （数据根，目录自动创建；文件名 = 安全化标签 + URL MD5 哈希，同链接同名天然去重；
  扩展名按响应 Content-Type 推断、默认 .png）；超时/失败返回 None，
  绝不抛异常。
- get_emoji_path(tag) / get_random_emoji()：按标签 / 随机从本地表情库取图，
  签名与参考实现一致，供 brain.translate_emoji 函数内延迟导入对接；库为空
  或标签未命中时返回 None，调用方据此优雅降级。
- 闭环兜底（架构 §10 #6）：get_emoji_path 未命中标签时，从收藏链接库取最新
  一条经 download_emoji 下载到本地，成功后 translate 链路自然可用；下载失败
  优雅返回 None，不阻断回复链。
"""
import hashlib
import json
import os
import random
import re

import requests

from xiaoju3 import AGENT_STATE_DIR, PROJECT_ROOT

# 本地表情库目录（数据根 xiaoju3_data/emoji/，下载时自动创建；双根口径：
# download_emoji 运行时落盘，frozen 下 _MEIPASS 只读不可写，故不落 assets）
EMOJI_DIR = os.path.join(PROJECT_ROOT, "xiaoju3_data", "emoji")

# 链接收藏仓库（agent_state 隔离区，运行数据不入仓库）
EMOJI_LOG_FILE = os.path.join(AGENT_STATE_DIR, "emoji_links.json")

# 收藏容量上限：滚动保留最新 N 条（环境变量可覆盖）
MAX_EMOJI_LINKS = int(os.environ.get("MAX_EMOJI_LINKS", "500"))

# Content-Type → 扩展名（推断失败 / 缺失一律默认 .png）
_CONTENT_TYPE_EXT = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg",
    "image/gif": ".gif", "image/webp": ".webp",
}


def _ext_from_content_type(content_type):
    """按响应 Content-Type 推断扩展名；缺失 / 未知 / 非字符串默认 .png。"""
    ctype = str(content_type or "").split(";")[0].strip().lower()
    return _CONTENT_TYPE_EXT.get(ctype, ".png")


def _lookup_emoji(tag):
    """纯查找：按标签在本地表情库找文件（不做任何下载副作用）。"""
    if not os.path.exists(EMOJI_DIR):
        return None
    for filename in os.listdir(EMOJI_DIR):
        # 只要文件名里包含这个标签（比如 "开心.png" 或 "开心 猫猫.jpg"），就认为是这个表情
        if tag in filename:
            return os.path.join(EMOJI_DIR, filename)
    return None


def _latest_stored_link():
    """取收藏链接库里最新一条（兜底下载源）；库空 / 损坏返回 None。"""
    try:
        with open(EMOJI_LOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            return str(data[-1])
    except Exception:
        pass
    return None


def get_emoji_path(tag):
    """根据标签查找表情包，比如找'开心'。

    本地库缺失该标签时触发下载兜底：从收藏链接库取最新一条下载到本地
    （文件名 = 标签 + URL 哈希），成功后 translate 链路自然可用；失败返回 None。
    """
    path = _lookup_emoji(tag)
    if path:
        return path
    url = _latest_stored_link()
    if url:
        downloaded = download_emoji(url, tag)
        if downloaded:
            # 正常按标签回查（文件名含标签）；标签含特殊字符被安全化时
            # 直接用下载返回的落盘路径兜底
            return _lookup_emoji(tag) or downloaded
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
    """下载图片到本地表情库（xiaoju3_data/emoji/，目录自动创建）。

    文件名 = 安全化标签 + URL MD5 哈希 + 扩展名：同链接同名覆盖（天然去重、
    不产生随机重名文件）；扩展名按响应 Content-Type 推断、默认 .png。
    成功返回落盘路径；网络异常 / 非 200 / 写盘失败一律返回 None，绝不抛异常
    （回复链路降级口径）。
    """
    try:
        os.makedirs(EMOJI_DIR, exist_ok=True)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            print(f"❌ 表情下载失败，状态码: {res.status_code}")
            return None
        ext = _ext_from_content_type(res.headers.get("Content-Type"))
        url_hash = hashlib.md5(str(url).encode("utf-8")).hexdigest()[:12]
        safe_tag = re.sub(r'[\\/:*?"<>|\s]+', "_", str(tag)).strip("._") or "unknow"
        filename = f"{safe_tag}_{url_hash}{ext}"
        filepath = os.path.join(EMOJI_DIR, filename)
        with open(filepath, 'wb') as f:
            f.write(res.content)
        print(f"✅ 表情已保存到: {filepath}")
        return filepath
    except Exception as e:
        print(f"❌ 表情下载出错: {e}")
        return None


def save_emoji_link(url):
    """只把图片链接存进记事本，不下载，绝对不卡。去重 + 容量截断。"""
    try:
        os.makedirs(os.path.dirname(EMOJI_LOG_FILE), exist_ok=True)
        # 读取现有数据
        if os.path.exists(EMOJI_LOG_FILE):
            with open(EMOJI_LOG_FILE, 'r', encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = []
        if not isinstance(data, list):
            data = []
        # 加入新链接（去重）
        if url not in data:
            data.append(url)
        # 容量截断：只保留最新 MAX_EMOJI_LINKS 条
        if len(data) > MAX_EMOJI_LINKS:
            data = data[-MAX_EMOJI_LINKS:]
        # 写回文件
        with open(EMOJI_LOG_FILE, 'w', encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ 保存表情链接失败: {e}")
        return False
