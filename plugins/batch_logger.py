# -*- coding: utf-8 -*-
"""plugins/batch_logger · 长文分片总结与"倒叙说书人"汇总。

按《架构设计文档》§5 /《功能文档》§6：长文按约 4000 字分片逐片总结，
再按"倒叙说书人"风格汇总成篇。

云端调用优先经 brain.ask_cloud（函数内延迟导入，避免循环依赖，且便于
测试注入替身模块）；brain 缺席时回退参考实现的直连 requests 方式。
"""
import time


def _ask_cloud(messages, api_key, cloud_url):
    """单轮云端调用：成功返回回复文本，失败返回 None。

    - 优先 brain.ask_cloud（延迟导入；brain 失败时返回 ⚠️/❌ 开头的
      优雅降级提示串，此处视为本片失败）；
    - brain 缺席时按参考实现直连 requests.post(cloud_url)。
    """
    try:
        import brain
    except ImportError:
        brain = None

    if brain is not None and hasattr(brain, "ask_cloud"):
        try:
            reply = brain.ask_cloud(messages)
        except Exception:
            return None
        if isinstance(reply, str) and reply[:1] in ("⚠", "❌"):
            return None
        return reply

    # 参考实现的直连调用方式
    try:
        import requests
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-chat", "messages": messages, "stream": False}
        response = requests.post(cloud_url, headers=headers, json=payload, timeout=90)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        print(f"⚠️ 云端返回状态码: {response.status_code}")
        return None
    except Exception as e:
        print(f"⚠️ 云端调用异常: {e}")
        return None


def summarize_long_text(text, api_key, cloud_url, chunk_size=4000):
    """长文按 chunk_size 分片逐片总结，再按"倒叙说书人"风格汇总成篇。"""
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    if not chunks:
        return "❌ 抓取到的文本为空，请检查链接是否正确。"

    print(f"🧠 开始分片总结，共 {len(chunks)} 片...")
    summaries = []

    for i, chunk in enumerate(chunks):
        prompt = f"请阅读以下对话记录，提炼核心任务、遇到问题及解决方案：\n\n{chunk}"
        summary = _ask_cloud([{"role": "user", "content": prompt}], api_key, cloud_url)
        if summary:
            summaries.append(summary)
            print(f"✅ 第 {i + 1}/{len(chunks)} 片总结完成。")
        else:
            print(f"⚠️ 第 {i + 1} 片总结失败。")
        time.sleep(1)

    if not summaries:
        return "❌ 所有分片总结均失败。"

    print("🔄 正在汇总最终日志...")
    # "倒叙说书人"风格汇总 Prompt
    final_prompt = (
        "你是一位会讲故事的记录者（说书人）。下面是一份AI智能体开发的流水账碎片总结。\n"
        "请你仔细阅读这些碎片，先根据内容的逻辑关联，**推断并排序出它们发生的时间先后**。\n"
        "然后，请你用**倒叙（从最新的事件开始写，一直追溯到最早的事件）**的方式，"
        "像讲故事一样，把整个开发过程娓娓道来。\n"
        "语气要口语化、生动一点，把踩坑描述成遭了老罪，把修复bug描述成绝地反击。\n\n"
        "格式要求：\n"
        "# 小橘3号开发故事（倒叙）\n"
        "## 🎬 结局：最新的状态\n"
        "## 🚧 历险：中间踩过的坑\n"
        "## 🚀 起源：最早发生的事\n"
        "## 💡 预告：下一轮要做什么\n\n"
        "以下是你需要整理的碎片信息：\n" + "\n\n".join(summaries)
    )

    final = _ask_cloud([{"role": "user", "content": final_prompt}], api_key, cloud_url)
    if not final:
        return "❌ 汇总失败。"
    return final
