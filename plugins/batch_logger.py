# plugins/batch_logger.py
import requests
import time

def summarize_long_text(text, api_key, cloud_url, chunk_size=4000):
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    summaries = []
    
    # ⚠️ 把 headers 定义提到循环外面
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if len(chunks) == 0:
        return "❌ 抓取到的文本为空，请检查链接是否正确。"

    print(f"🧠 开始分片总结，共 {len(chunks)} 片...")

    for i, chunk in enumerate(chunks):
        prompt = f"请阅读以下对话记录，提炼核心任务、遇到问题及解决方案：\n\n{chunk}"
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False
        }
        try:
            response = requests.post(cloud_url, headers=headers, json=payload, timeout=90)
            if response.status_code == 200:
                summaries.append(response.json()["choices"][0]["message"]["content"])
                print(f"✅ 第 {i+1}/{len(chunks)} 片总结完成。")
            else:
                print(f"⚠️ 第 {i+1} 片失败，状态码: {response.status_code}")
        except Exception as e:
            print(f"⚠️ 第 {i+1} 片网络异常: {e}")
        time.sleep(1)

    print("🔄 正在汇总最终日志...")
    # 你已经改好的“倒叙写小说”Prompt
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
    
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": final_prompt}], "stream": False}
    try:
        response = requests.post(cloud_url, headers=headers, json=payload, timeout=90)
        return response.json()["choices"][0]["message"]["content"] if response.status_code == 200 else "❌ 汇总失败。"
    except Exception as e:
        return f"❌ 汇总异常：{e}"