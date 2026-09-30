#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_link_log · /gen_log 编排：DeepSeek 分享链接 → 开发日志。

处理流程（功能文档 §6）：校验链接（须为 chat.deepseek.com/share/ 分享页）
→ link_logger 无头浏览器抓取全文 → batch_logger 按约 4000 字分片总结并
以"倒叙说书人"风格汇总成篇 → 自动编号保存 dev_log_N.md 并倒序合并进
ALL_LOGS.md；原始文本同时落盘 raw_log_temp.txt 备查。

终端独立用法：python run_link_log.py <分享链接>
"""
import asyncio
import glob
import os
import re

from plugins.batch_logger import summarize_long_text
from plugins.link_logger import LinkFetchError, fetch_deepseek_url
from xiaoju3 import CLOUD_KEY, CLOUD_URL, PROJECT_ROOT

# 日志落盘目录：项目根 dev_logs/（.gitignore 已覆盖，运行数据不入仓库）
DATA_DIR = os.path.join(PROJECT_ROOT, "dev_logs")

# DeepSeek 分享链接前缀
SHARE_PREFIX = "https://chat.deepseek.com/share/"


def next_log_index(data_dir):
    """扫描 dev_log_N.md 确定下一篇编号（取现存最大 N + 1，防覆盖）。"""
    existing = glob.glob(os.path.join(data_dir, "dev_log_*.md"))
    indexes = []
    for path in existing:
        m = re.search(r"dev_log_(\d+)\.md$", os.path.basename(path))
        if m:
            indexes.append(int(m.group(1)))
    return (max(indexes) + 1) if indexes else 1


def merge_all_logs(data_dir, index, result):
    """与旧总日志合并：最新一篇放最前（倒叙），写入 ALL_LOGS.md。"""
    all_logs_file = os.path.join(data_dir, "ALL_LOGS.md")
    all_content = []
    if os.path.exists(all_logs_file):
        with open(all_logs_file, "r", encoding="utf-8") as f:
            all_content.append(f.read())

    final_content = (f"### 🆕 第 {index} 篇日志（最新）\n\n" + result
                     + "\n\n---\n\n" + "\n\n".join(all_content))
    with open(all_logs_file, "w", encoding="utf-8") as f:
        f.write(final_content)
    return all_logs_file


async def main(url, data_dir=None):
    """编排一次日志生成：成功返回日志正文；链接非法 / 抓取为空 /
    总结失败时返回 None（原因已打印），不落盘半成品日志。"""
    url = (url or "").strip()
    if not url.startswith(SHARE_PREFIX):
        print("❌ 链接格式不对，必须以 https://chat.deepseek.com/share/ 开头")
        return None

    data_dir = data_dir or DATA_DIR
    os.makedirs(data_dir, exist_ok=True)

    # === 1. 确定当前是第几篇日志 ===
    index = next_log_index(data_dir)
    current_log_file = os.path.join(data_dir, f"dev_log_{index}.md")

    print(f"🚀 开始抓取链接内容，这将是第 {index} 篇日志...")
    try:
        raw_text = await fetch_deepseek_url(url)
    except LinkFetchError as e:
        # 抓取失败（链接非法 / 缺 playwright / 浏览器异常）：不落盘任何半成品
        print(str(e))
        return None
    if not raw_text or not raw_text.strip():
        print("❌ 抓取到的文本为空，请检查链接是否正确。")
        return None

    raw_path = os.path.join(data_dir, "raw_log_temp.txt")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(raw_text)
    print(f"💾 原始文本已保存到 {raw_path}")

    # === 2. 分片总结 + 倒叙汇总 ===
    print("🧠 开始分片总结...")
    result = summarize_long_text(raw_text, CLOUD_KEY, CLOUD_URL)
    if result.startswith("❌"):
        print(result)
        return None

    # === 3. 保存新生成的日志 ===
    with open(current_log_file, "w", encoding="utf-8") as f:
        f.write(result)
    print(f"✅ 第 {index} 篇日志已生成！保存为 dev_log_{index}.md")

    # === 4. 与之前的日志合并成总日志（最新在最前，倒叙） ===
    merge_all_logs(data_dir, index, result)
    print(f"🎉 已与之前所有日志合并！已更新 {os.path.join(data_dir, 'ALL_LOGS.md')}")

    print("--- 当前第 " + str(index) + " 篇日志前 500 字预览 ---")
    print(result[:500])
    return result


def run_link_log(url, data_dir=None):
    """同步入口（供终端 CLI /gen_log 调用）。"""
    return asyncio.run(main(url, data_dir))


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("⚠️ 用法错误：请在命令后直接附加链接，例如：xiaoju3_link https://chat.deepseek.com/share/xxxxxx")
    else:
        run_link_log(sys.argv[1])
