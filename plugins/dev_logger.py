# -*- coding: utf-8 -*-
"""plugins/dev_logger · 旧版日志生成器（文档口径：保留、不接线）。

已被 link_logger + batch_logger 组合替代（架构设计文档 §5：已实现·未接线），
按参考实现保留函数签名与行为。第二阶段将 playwright 路径补全为真实渲染
链路：无头 chromium 打开分享页 → 剥离 script/style 噪声节点 → 分段滚动
触发懒加载直至到底 → 提取正文与图片链接。playwright 做函数内延迟导入，
缺库或浏览器内核缺失时返回中文提示字符串，不影响模块 import。
"""
import re
import time

# 与 link_logger 保持一致的抓取护栏（同步实现，参数独立可测）
RENDER_WAIT_SECONDS = 3.0  # 打开后先等待渲染
SCROLL_WAIT_SECONDS = 2.0  # 每次滚动后等待懒加载
MAX_SCROLL_STEPS = 60      # 滚动步数硬上限，防死循环

# 页面内剥离噪声节点的 JS：script/style 等不参与正文，返回剥离后的页面高度
_STRIP_NOISE_JS = (
    "(() => {"
    "document.querySelectorAll('script, style, noscript, template')"
    ".forEach(el => el.remove());"
    "return document.body ? document.body.scrollHeight : 0;})()"
)


def fetch_deepseek_share(url):
    """抓取 DeepSeek 分享链接的文字和图片链接。

    返回 (text_content, images, found_links)；失败时首元素为错误提示字符串。
    """
    print(f"Fetching DeepSeek link: {url}")

    try:
        # 延迟导入：playwright 缺库时优雅降级，不让模块 import 失败
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return f"❌ 缺少 playwright 库，无法抓取分享页：{e}", [], []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(RENDER_WAIT_SECONDS)

                # 剥离 script/style 等噪声节点后再滚动，避免干扰到底判断
                last_height = page.evaluate(_STRIP_NOISE_JS)
                for _ in range(MAX_SCROLL_STEPS):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(SCROLL_WAIT_SECONDS)  # 等待新内容懒加载
                    new_height = page.evaluate("document.body.scrollHeight")
                    if new_height == last_height:
                        break  # 高度不再增长：已滚动到底
                    last_height = new_height

                text_content = page.inner_text("body")
                img_elements = page.eval_on_selector_all(
                    "img", "els => els.map(e => e.src)")
            finally:
                browser.close()
        images = [src for src in img_elements if src.startswith("http")]
        found_links = re.findall(r"(https?://[^\s]+)", text_content)
        return text_content, images, found_links
    except Exception as e:
        print(f"Fetch error: {e}")
        msg = str(e)
        if "playwright install" in msg or "Executable doesn't exist" in msg:
            return ("❌ 浏览器内核缺失，请先执行 python -m playwright install chromium 后重试。",
                    [], [])
        return f"Fetch error: {e}", [], []


def generate_dev_log(text_content, image_descriptions, api_key, cloud_url):
    """调用大模型生成日志（带长度限制和防爆护栏）。"""

    # 1. 核心防护：限制文本长度，只保留最新的一部分，防止 Token 爆炸
    #    假设一个汉字占 1 个 token，限制最多 20000 个字符（约 2 万 token，安全）
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

    # 3. 核心防护：超时 180 秒（3 分钟），给大模型足够时间阅读
    try:
        import requests
        response = requests.post(cloud_url, headers=headers, json=payload, timeout=180)
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Generate log failed (may be timeout): {str(e)}"
