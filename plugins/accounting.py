# -*- coding: utf-8 -*-
"""小橘3号 · 记账本插件（功能文档 §7："帮我记一下账"直达功能）。

数据落盘 JSON（UTF-8）：默认 agent_state/account_book.json，
环境变量 XIAOJU3_ACCOUNT_BOOK 可覆盖路径（第二阶段规范 §6.2：新配置
键在本模块内 env 读取）。记录结构：
    [{"date": "2026-09-30", "amount": -28.0, "category": "餐饮",
      "note": "午饭", "ts": 1759190400.123}, ...]
金额自由口径：负数为支出、正数为收入，0 视为非法输入。

对外接口（供 intent_router 意图表以 "plugins.accounting:函数名"
延迟字符串引用，S5 接线零成本；全部返回面向用户的中文文本）：
- add_record(amount, category="", note="", date=None) -> str
- list_records(limit=20) -> str
- summarize(period="today"|"month"|"all") -> str
- delete_record(index) -> str

落盘为原子写（临时文件 + os.replace，失败清理半成品），读-改-写全程
持有模块级线程锁，并发追加不丢数据。import 零副作用（不建文件、
不打印），可独立离线单测（路径经 env 注入 tmp 目录）。
"""
import json
import math
import os
import threading
import time
from datetime import datetime

from xiaoju3 import AGENT_STATE_DIR

# 记账文件路径的 env 键（缺省落 xiaoju3.AGENT_STATE_DIR/account_book.json）
ACCOUNT_BOOK_ENV = "XIAOJU3_ACCOUNT_BOOK"

# 并发锁：add/delete 的读-改-写全程持有，多线程追加不丢记录
_LOCK = threading.Lock()


def get_book_path():
    """账本文件路径：env XIAOJU3_ACCOUNT_BOOK 优先，缺省落状态目录。"""
    return (os.environ.get(ACCOUNT_BOOK_ENV)
            or os.path.join(AGENT_STATE_DIR, "account_book.json"))


def _load_records(path):
    """读取全部记录；文件不存在或损坏返回空列表（不抛异常）。"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _dump_json(fp, records):
    """序列化出口（独立成函数便于单测注入失败，验证原子写回滚）。"""
    json.dump(records, fp, ensure_ascii=False, indent=2)


def _save_records(records, path):
    """原子写：先写临时文件再 os.replace，异常时清理半成品并向上抛。"""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            _dump_json(f, records)
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise


def _normalize_amount(amount):
    """金额校验与归一：数字 / 数字字符串 → float（保留符号，2 位小数）。

    非法（非数字、NaN/inf、布尔、0）一律返回 None，由调用方给中文报错。
    """
    if isinstance(amount, bool):
        return None
    if isinstance(amount, str):
        try:
            amount = float(amount.strip())
        except (ValueError, AttributeError):
            return None
    if isinstance(amount, int):
        amount = float(amount)
    if not isinstance(amount, float):
        return None
    if not math.isfinite(amount) or amount == 0:
        return None
    return round(amount, 2)


def _format_record(index, rec):
    """单条记录的用户可读行：`3. [2026-09-30] -28.00元 [餐饮] 午饭`。"""
    line = f"{index}. [{rec.get('date', '')}] {rec.get('amount', 0):+.2f}元"
    if rec.get("category"):
        line += f" [{rec['category']}]"
    if rec.get("note"):
        line += f" {rec['note']}"
    return line


def add_record(amount, category="", note="", date=None):
    """记一笔账：负数为支出、正数为收入；返回中文确认或 ❌ 中文报错。

    date：可选 "YYYY-MM-DD"，缺省记今天；格式非法返回中文错误串。
    """
    amt = _normalize_amount(amount)
    if amt is None:
        return ("❌ 金额无效：请给出数字金额，负数为支出、正数为收入，"
                "例如「记一笔午饭花了28元」。")
    date_str = datetime.now().strftime("%Y-%m-%d")
    if date is not None:
        try:
            date_str = datetime.strptime(str(date).strip(), "%Y-%m-%d")\
                .strftime("%Y-%m-%d")
        except ValueError:
            return "❌ 日期格式应为 YYYY-MM-DD，例如 2026-09-30。"
    category = str(category or "").strip()
    note = str(note or "").strip()
    record = {"date": date_str, "amount": amt, "category": category,
              "note": note, "ts": round(time.time(), 3)}
    path = get_book_path()
    try:
        with _LOCK:
            records = _load_records(path)
            records.append(record)
            _save_records(records, path)
    except Exception as e:
        return f"❌ 记账保存失败：{e}"
    sign_word = "支出" if amt < 0 else "收入"
    msg = (f"✅ 已记账（{sign_word}）：{date_str} {amt:+.2f} 元"
           + (f" [{category}]" if category else "")
           + (f" {note}" if note else ""))
    return msg


def list_records(limit=20):
    """列出最近的账（默认 20 笔），序号为账本全局编号（1 起），供删除引用。"""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, limit)
    records = _load_records(get_book_path())
    if not records:
        return "📒 账本还是空的，对我说「记一笔午饭花了28元」就能开始记账。"
    total = len(records)
    # 最新在上：倒序展示，但序号保留账本全局编号，delete_record 直接可用
    recent = list(enumerate(records))[-limit:]
    recent.reverse()
    lines = [f"📒 最近 {len(recent)} 笔账（共 {total} 笔，序号为账本编号）："]
    lines.extend(_format_record(i + 1, rec) for i, rec in recent)
    return "\n".join(lines)


# summarize 时段别名：英文口径为主，兼容常见中文说法
_PERIOD_ALIASES = {
    "today": "today", "今天": "today", "今日": "today",
    "month": "month", "本月": "month", "这个月": "month", "当月": "month",
    "all": "all", "全部": "all", "所有": "all",
}


def summarize(period="today"):
    """账本汇总：分类明细 + 收支结余的中文文本。

    period 取 "today" / "month" / "all"（兼容中文别名），其余返回中文报错。
    """
    key = _PERIOD_ALIASES.get(str(period).strip().lower(), None)
    if key is None:
        return "❌ 汇总口径仅支持 today（今天）/ month（本月）/ all（全部）。"
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    month_str = now.strftime("%Y-%m")
    label = {"today": "今天", "month": "本月", "all": "全部"}[key]
    records = _load_records(get_book_path())
    if key == "today":
        matched = [r for r in records if r.get("date") == today_str]
    elif key == "month":
        matched = [r for r in records
                   if str(r.get("date", "")).startswith(month_str)]
    else:
        matched = records
    if not matched:
        return f"📊 {label}暂无记账记录。"
    income = sum(r["amount"] for r in matched if r["amount"] > 0)
    expense = sum(r["amount"] for r in matched if r["amount"] < 0)
    balance = income + expense
    by_cat = {}
    for r in matched:
        cat = r.get("category") or "未分类"
        by_cat[cat] = by_cat.get(cat, 0.0) + r["amount"]
    lines = [f"📊 账本汇总（{label}，共 {len(matched)} 笔）：",
             f"收入：+{income:.2f} 元",
             f"支出：{expense:.2f} 元",
             f"结余：{balance:+.2f} 元",
             "分类明细："]
    for cat, amt in sorted(by_cat.items(), key=lambda kv: kv[1]):
        lines.append(f"· {cat}：{amt:+.2f} 元")
    return "\n".join(lines)


def delete_record(index):
    """按账本编号（list_records 展示的序号，从 1 起）删除一笔账。"""
    try:
        index = int(index)
    except (TypeError, ValueError):
        return "❌ 序号无效：请使用账本列表里展示的编号（从 1 开始）。"
    path = get_book_path()
    try:
        with _LOCK:
            records = _load_records(path)
            if not records:
                return "📒 账本还是空的，没有可删除的记录。"
            if not 1 <= index <= len(records):
                return (f"❌ 序号超出范围：账本共 {len(records)} 笔，"
                        f"编号 1–{len(records)}。")
            removed = records.pop(index - 1)
            _save_records(records, path)
    except Exception as e:
        return f"❌ 删除失败：{e}"
    return f"🗑️ 已删除第 {index} 笔：{_format_record(index, removed)}"
