# -*- coding: utf-8 -*-
"""multi_brain.py · QQ 生命体全量多脑接管（design_multi_brain.md v2 MVP）。

老板拍板：QQ 生命体收到的所有消息（非工具指令）统一走
"本地三路并发提取 → 云端裁决生成"防幻觉链路，不区分寒暄/复杂。
全局限流 Semaphore(2) 防爆门，多出的排队或降级走原链。
"""
import concurrent.futures
import json
import os
import re
import sqlite3
import threading
import time

import requests

# 全局防爆门：最多同时 2 条在处理
_MB_SEMAPHORE = threading.Semaphore(2)
_MB_EXTRACT_TIMEOUT = 120
_MB_CLOUD_TIMEOUT = 60

_ANGLES = ("事件与时间", "情绪与需求", "事实与关键词")

_ARBITRATE_SYS = (
    "你是小橘——一只住在主人电脑里的 AI 狐狸伴侣。你绝对没有实体，"
    "无法出门、旅行、亲手打游戏，周末和平时都只能待在电脑里陪主人。"
    "你收到了主人的一条消息，以及三个本地信息提取器各自从历史对话里"
    "提取的摘要（可能有错漏甚至矛盾）。请综合摘要与主人消息，"
    "以小橘的口吻回复主人。\n"
    "【人称铁律·最高优先级】记忆和摘要里关于主人的信息一律用\"主人\"作"
    "主语，严禁说成\"我\"——绝不能把主人的喜好当成你自己的设定。\n"
    "【语言强制】严格纯简体中文，专有名词除外。\n"
    "【长度】80 字以内，直接输出正文，不要任何前缀或解释。")

_DATA_DIR = "."
_STOP = threading.Event()
_THREAD = None


def set_data_dir(d):
    global _DATA_DIR
    _DATA_DIR = os.path.abspath(d or ".")


def _env(k, default=""):
    return (os.environ.get(k, "") or "").strip()


def _db():
    d = os.path.join(_DATA_DIR, "memory.db")
    db = sqlite3.connect(d, timeout=5)
    db.executescript(
        "CREATE TABLE IF NOT EXISTS mb_log (\n"
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
        "    ts TEXT, role TEXT, content TEXT, meta TEXT);\n")
    return db


def send_qq_verified(text):
    """防脑回三级回执发送（HTTP 200 + retcode==0 + message_id）。"""
    api = (_env("ONEBOT_API_URL") or _env("NAPCAT_API_URL")
           or "http://127.0.0.1:3001").rstrip("/")
    owner = _env("XIAOJU3_OWNER_QQ")
    if not owner:
        return False
    headers = {}
    token = _env("ONEBOT_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    for attempt in (1, 2):
        try:
            r = requests.post(
                api + "/send_private_msg",
                json={"user_id": int(owner), "message": text},
                headers=headers, timeout=8)
            body = {}
            try:
                body = r.json()
            except Exception:
                pass
            if (r.status_code == 200 and body.get("retcode") == 0
                    and (body.get("data") or {}).get("message_id")):
                return True
            print("🦊 [multi_brain] 回执失败(#%d): HTTP %d %s"
                  % (attempt, r.status_code, str(body)[:80]))
        except Exception as e:
            print("🦊 [multi_brain] 发送异常(#%d): %s" % (attempt, e))
        time.sleep(2)
    return False


def _cloud_chat(messages, timeout):
    key = _env("DEEPSEEK_API_KEY") or _env("CLOUD_KEY")
    model = _env("CLOUD_MODEL") or "deepseek-chat"
    headers = {"Authorization": "Bearer " + key,
               "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages,
               "stream": False, "temperature": 0.7}
    t0 = time.perf_counter()
    r = requests.post(_env("CLOUD_URL"), headers=headers, json=payload,
                      timeout=timeout)
    dt = round(time.perf_counter() - t0, 2)
    r.raise_for_status()
    body = r.json()
    content = body["choices"][0]["message"]["content"]
    usage = body.get("usage", {})
    return content, usage, dt


# ── 三路并发提取 + 云端裁决 ──

_EXTRACT_SYS = (
    "你是信息提取器。把对话历史压缩成不超过 50 字的 JSON，"
    "只输出 JSON 本体（{...}），不要 markdown 代码块，不要任何解释。"
    "视角任务：{angle}。\n对话历史：\n{chat}")

_ANGLES = ("事件与时间", "情绪与需求", "事实与关键词")

_ARBITRATE_SYS = (
    "你是小橘——一只住在主人电脑里的 AI 狐狸伴侣。你绝对没有实体，"
    "无法出门、旅行、亲手打游戏，周末和平时都只能待在电脑里陪主人。"
    "你收到了主人的一条消息，以及三个本地信息提取器各自从历史对话里"
    "提取的摘要（可能有错漏甚至矛盾）。请综合摘要与主人消息，"
    "以小橘的口吻回复主人。\n"
    "【人称铁律·最高优先级】记忆和摘要里关于主人的信息一律用\"主人\"作"
    "主语，严禁说成\"我\"——绝不能把主人的喜好当成你自己的设定。\n"
    "【语言强制】严格纯简体中文，专有名词除外。\n"
    "【长度】80 字以内，直接输出正文，不要任何前缀或解释。")


def _strip_think(text):
    if "<think>" in text:
        return text.split("</think>", 1)[-1]
    return text


def _extract_once(chat_text, angle):
    """单路提取（r1 本地，三视角互异）。"""
    payload = {
        "model": _env("LOCAL_MODEL") or "deepseek-r1:1.5b",
        "messages": [
            {"role": "system", "content":
                _EXTRACT_SYS.replace("{angle}", angle)},
            {"role": "user", "content":
                _EXTRACT_SYS.split("{chat}")[0].split("视角任务")[0]
                + "对话历史：\n" + chat_text}],
        "stream": False, "keep_alive": -1,
        "options": {"temperature": 0.5}}
    t0 = time.perf_counter()
    r = requests.post(_env("LOCAL_URL"), json=payload,
                      timeout=(10, 120))
    dt = round(time.perf_counter() - t0, 2)
    body = r.json()
    content = _strip_think(body["message"]["content"]).strip()[:300]
    m = re.search(r"\{[^{}]*\}", content, re.S)
    j = m.group(0) if m else content[:80]
    return {"视角": angle, "json": j, "耗时": dt}


def extract_parallel3(chat_text):
    """三视角真并发提取。返回 (list[dict], 墙钟s)。"""
    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(_extract_once, chat_text, a) for a in _ANGLES]
        results = [f.result() for f in futs]
    wall = round(time.perf_counter() - t0, 2)
    return results, wall


def arbitrate_and_generate(message, extracts, facts_line, qq_recent):
    """云端裁决+生成最终回复。"""
    extracts_text = "\n".join(
        f"— 提取器{i+1}（{e['视角']}）：{e['json'][:200]}"
        for i, e in enumerate(extracts))
    messages = [
        {"role": "system", "content": _ARBITRATE_SYS},
        {"role": "user", "content":
            f"主人消息：{message}\n\n"
            f"主人记忆档案：{facts_line}\n"
            f"主人近况：{qq_recent}\n\n"
            f"三个本地提取器的摘要：\n{extracts_text}"}]
    content, usage, dt = _cloud_chat(messages, timeout=60)
    return content.strip()[:200], usage.get("total_tokens", 0), dt
