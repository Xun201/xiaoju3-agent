# plugins/link_logger.py
import asyncio
from playwright.async_api import async_playwright
import time

async def fetch_deepseek_url(url):
        # 清理 URL 尾部的锚点或乱码
    url = url.strip().split('#')[0] 
    """用 Playwright 打开 DeepSeek 分享链接，模拟滚动加载，提取全部对话文本"""
    print(f"🌐 正在打开链接，请稍候... (这可能需要 30-60 秒)")
    text_content = ""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 打开页面，等待网络空闲
        await page.goto(url, wait_until="networkidle", timeout=90000)
        await asyncio.sleep(3)
        
        # === 核心：模拟滚动，触发懒加载 ===
        last_height = await page.evaluate("document.body.scrollHeight")
        while True:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)  # 等待新内容加载
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        
        # 滚动到底后，提取全部文字
        text_content = await page.inner_text("body")
        await browser.close()
    
    # 清理掉网页自带的导航条、按钮等无用文字
    lines = text_content.split('\n')
    clean_lines = [l for l in lines if l.strip() and not l.startswith(('登录', '注册', '下载', '分享', '复制', '编辑'))]
    
    print(f"✅ 抓取完成，共提取 {len(clean_lines)} 行文本。")
    return "\n".join(clean_lines)