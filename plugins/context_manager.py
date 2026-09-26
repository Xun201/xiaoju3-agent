def compress_context(messages, max_messages=20, keep_recent=10):
    """上下文压缩器"""
    if len(messages) <= max_messages:
        return messages

    print(f"🧠 上下文过长（{len(messages)} 条），触发记忆压缩...")

    system_prompt = messages[0]
    old_messages = messages[1:-keep_recent]
    recent_messages = messages[-keep_recent:]

    if not old_messages:
        return messages

    old_text = "\n".join([f"{m['role']}: {m['content']}" for m in old_messages])
    
    summary_prompt = [
        {"role": "system", "content": "你是一个记忆压缩助手。请把下面这段对话浓缩成一段50字以内的前情提要，保留关键事实、任务目标和重要细节，不要遗漏核心信息。"},
        {"role": "user", "content": old_text}
    ]

    try:
        from brain import ask_local, ask_cloud
        try:
            summary = ask_local(summary_prompt)
        except:
            summary = ask_cloud(summary_prompt)
    except Exception as e:
        print(f"⚠️ 摘要生成失败，直接截断旧记忆: {e}")
        summary = "（由于系统原因，早期对话记忆已丢失）"

    print(f"✅ 记忆压缩完成！摘要：{summary[:50]}...")

    compressed_messages = [system_prompt]
    compressed_messages.append({
        "role": "system",
        "content": f"【前情提要】：{summary}"
    })
    compressed_messages.extend(recent_messages)

    return compressed_messages
