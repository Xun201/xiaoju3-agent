# plugins/dev_logger.py
from playwright.sync_api import sync_playwright
import re
import time
import requests

def fetch_deepseek_share(url):
    """抓取 DeepSeek 分享链接的文字和图片链接"""
    print(f"Fetching DeepSeek link: {url}")
    text_content = ""
    images = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(3)
            
            text_content = page.inner_text("body")
            img_elements = page.eval_on_selector_all("img", "els => els.map(e => e.src)")
            images = [src for src in img_elements if src.startswith("http")]
            found_links = re.findall(r'(https?://[^\s]+)', text_content)
            
            browser.close()
        return text_content, images, found_links
    except Exception as e:
        print(f"Fetch error: {e}")
        return f"Fetch error: {e}", [], []

def generate_dev_log(text_content, image_descriptions, api_key, cloud_url):
    """调用大模型生成日志（带长度限制和防爆护栏）"""
    
    # 1. 核心防护：限制文本长度，只保留最新的一部分，防止Token爆炸
    # 假设一个汉字占1个token，我们限制最多 20000 个字符（大约2万token，非常安全）
    MAX_TEXT_LENGTH = 20000
    if len(text_content) > MAX_TEXT_LENGTH:
        print(f"⚠️ 对话内容过长（{len(text_content)} 字），已自动截断至前 {MAX_TEXT_LENGTH} 字以保护 API。")
        # 保留前 15000 字和后 5000 字（开头和结尾通常最重要）
        text_content = text_content[:15000] + "\n\n[...中间内容过长已截断...]\n\n" + text_content[-5000:]
    
    # 2. 构建精简 Prompt
    prompt = "你是一个项目开发日志提炼助手。请根据以下对话记录，按 Markdown 格式输出开发日志。\n"
    prompt += "结构要求：\n# 小橘3号开发日志\n## 🎯 今日目标\n## ✅ 完成的事\n## 🐛 踩的坑与解法\n## 💡 下次要做\n"
    prompt += "---\n对话记录：\n"
    prompt += text_content + "\n\n"
    if image_descriptions:
        prompt += "图片描述：\n" + "\n".join(image_descriptions)
    
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }
    
    # 3. 核心防护：把超时时间从 60 秒提升到 180 秒（3分钟），给大模型足够的时间阅读
    try:
        response = requests.post(cloud_url, headers=headers, json=payload, timeout=180)
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Generate log failed (may be timeout): {str(e)}"