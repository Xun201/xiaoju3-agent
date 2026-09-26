# run_link_log.py
import sys
import asyncio
import os
import glob

sys.path.append('/home/orangepi/xiaoju3-agent') 
sys.path.append('/home/orangepi/xiaoju3_data')

from config import CLOUD_KEY, CLOUD_URL
from plugins.link_logger import fetch_deepseek_url
from plugins.batch_logger import summarize_long_text

async def main(url):
    if not url.startswith("https://chat.deepseek.com/share/"):
        print("❌ 链接格式不对，必须以 https://chat.deepseek.com/share/ 开头")
        return
    
    data_dir = '/home/orangepi/xiaoju3-agent/data'
    os.makedirs(data_dir, exist_ok=True)

    # === 🛡️ 1. 确定当前是第几篇日志 ===
    existing_files = sorted(glob.glob(os.path.join(data_dir, "dev_log_*.md")))
    # 过滤掉总文件
    existing_files = [f for f in existing_files if not f.endswith("ALL_LOGS.md")]
    next_index = len(existing_files) + 1
    current_log_file = os.path.join(data_dir, f"dev_log_{next_index}.md")

    print(f"🚀 开始抓取链接内容，这将是第 {next_index} 篇日志...")
    raw_text = await fetch_deepseek_url(url)
    
    with open(os.path.join(data_dir, "raw_log_temp.txt"), "w", encoding="utf-8") as f:
        f.write(raw_text)
    print("💾 原始文本已保存到 data/raw_log_temp.txt")
    
    print("🧠 开始分片总结...")
    result = summarize_long_text(raw_text, CLOUD_KEY, CLOUD_URL)
    
    # === 📝 2. 保存新生成的日志 ===
    with open(current_log_file, "w", encoding="utf-8") as f:
        f.write(result)
    print(f"✅ 第 {next_index} 篇日志已生成！保存为 dev_log_{next_index}.md")

    # === 🔗 3. 与之前的日志合并成总日志 ===
    all_logs_file = os.path.join(data_dir, "ALL_LOGS.md")
    all_content = []

    # 读取旧的总日志（如果存在）
    if os.path.exists(all_logs_file):
        with open(all_logs_file, "r", encoding="utf-8") as f:
            all_content.append(f.read())
    
    # 最新的日志放在最前面（因为你的设定是倒叙）
    final_content = f"### 🆕 第 {next_index} 篇日志（最新）\n\n" + result + "\n\n---\n\n" + "\n\n".join(all_content)
    
    with open(all_logs_file, "w", encoding="utf-8") as f:
        f.write(final_content)
    print("🎉 已与之前所有日志合并！已更新 data/ALL_LOGS.md")
    
    print("--- 当前第 " + str(next_index) + " 篇日志前 500 字预览 ---")
    print(result[:500])

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("⚠️ 用法错误：请在命令后直接附加链接，例如：xiaoju3_link https://chat.deepseek.com/share/xxxxxx")
    else:
        target_url = sys.argv[1]
        asyncio.run(main(target_url))