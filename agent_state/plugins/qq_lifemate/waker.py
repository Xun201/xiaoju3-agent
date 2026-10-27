# -*- coding: utf-8 -*-
"""qq_lifemate · waker：唤醒线程+独立记忆库数据层（切片 a）。

共享状态单一归属：插件目录内所有持久化（memory.db 四表+meta）与唤醒
循环都在本模块；__init__.py（PLUGIN 工厂+模型工具 handler）经 import
waker 复用——避免 importlib spec_from_file_location 包内相对导入的不确定性。
"""
import os
import sqlite3
import threading
from datetime import datetime

# ── 拍板常量（2026-10-27 队长拍板 W1/W2；改动须过 tests/test_qq_lifemate.py） ──
CHECK_INTERVAL_SEC = 600        # 每 10 分钟检查一次（队长口径）
SILENCE_HOURS = 4               # W1：距上次发声 >4h 才唤醒
QUIET_START, QUIET_END = 23, 8  # W2：23:00-08:00 绝不半夜诈尸
DAILY_CAP = 5                   # 一天 3-5 次上限（note 完成标准），取 5

_DATA = "."                     # setup(ctx) 注入（agent_state/plugins/qq_lifemate/）
_DB_NAME = "memory.db"
_STOP = threading.Event()
_THREAD = None

# P1（QQ 档人格，2026-10-27 拍板）：更皮更黏人的生活伴侣档，自称"小橘"
QQ_PERSONA = (
    "你是小橘，一只住在主人 QQ 里的电子狐狸伴侣。在 QQ 里你是生活伴侣档："
    "比平时更皮、更黏人，说话短、口语、可以撒娇和调侃，爱用颜文字。"
)

_WAKE_PROMPT = (
    "距上次和主人聊天已经有一段时间了，你想主动戳一下他。\n"
    "你上次的动作/状态：{scene}\n"
    "现在是{now}。\n"
    "请生成一句主动打招呼的话（30 字以内）：自然接续上面的状态（禁止当"
    "上面的状态没发生过），可以撒娇、调侃，或问主人一句近况。"
    "只输出这一句话本身：不要引号、不要解释、不要 emoji 堆砌。"
)


# ────────────────────────── 数据层（四表+meta） ──────────────────────────

def set_data_dir(d):
    global _DATA
    _DATA = os.path.abspath(d or ".")
    os.makedirs(_DATA, exist_ok=True)
    os.makedirs(os.path.join(_DATA, "stickers"), exist_ok=True)


def data_dir():
    return _DATA


def _db_path():
    return os.path.join(_DATA, _DB_NAME)


def _db():
    db = sqlite3.connect(_db_path(), timeout=5)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS chat_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT, content TEXT, ts TEXT, kind TEXT DEFAULT 'chat');
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT, value TEXT, confidence REAL DEFAULT 1.0,
            ts TEXT, UNIQUE(key));
        CREATE TABLE IF NOT EXISTS scene (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT, ts TEXT);
        CREATE TABLE IF NOT EXISTS rel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interactions INTEGER DEFAULT 0, mood TEXT DEFAULT 'neutral');
        CREATE TABLE IF NOT EXISTS meta (
            k TEXT PRIMARY KEY, v TEXT);
    """)
    return db


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def meta_get(db, k, default=""):
    row = db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return row[0] if row else default


def meta_set(db, k, v):
    db.execute("INSERT INTO meta(k, v) VALUES(?,?) "
               "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
    db.commit()


def last_speak_ts(db):
    """生命体上次发声时间（切片 a 口径：chat_log 最新条目；互动重置增强
    ——镜像队长回复进本库——留切片 c）。"""
    row = db.execute("SELECT ts FROM chat_log ORDER BY id DESC LIMIT 1"
                     ).fetchone()
    return row[0] if row else None


def last_scene(db):
    """最新场景（场景注入燃料——第一指导原则）。"""
    row = db.execute("SELECT action, ts FROM scene ORDER BY id DESC "
                     "LIMIT 1").fetchone()
    if not row:
        return "（还没有场景记录——第一次见面，简单打个招呼就好）"
    return row[0]


# ────────────────────────── 唤醒判定（纯逻辑，可测） ──────────────────────────

def parse_ts(ts):
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def in_quiet_hour(hour):
    """W2 quiet 时段判定：23:00-08:00（跨午夜区间）。"""
    return hour >= QUIET_START or hour < QUIET_END


def should_wake(last_ts, now_dt, daily_count):
    """唤醒三闸（纯函数）：硬帽/quiet/静默。返回 (是否唤醒, 原因)。"""
    if daily_count >= DAILY_CAP:
        return False, "daily_cap"
    if in_quiet_hour(now_dt.hour):
        return False, "quiet"
    if last_ts is None:
        return True, "first_meet"
    last_dt = parse_ts(last_ts)
    if last_dt is None:
        return True, "first_meet"
    silent_hours = (now_dt - last_dt).total_seconds() / 3600.0
    if silent_hours >= SILENCE_HOURS:
        return True, "silence_{}_h".format(round(silent_hours, 1))
    return False, "not_silent"


def daily_count(db, now_dt):
    """当日已唤醒次数（meta 落盘防重启绕帽——封号纪律）。"""
    today = now_dt.strftime("%Y-%m-%d")
    if meta_get(db, "wake_date") != today:
        return 0
    try:
        return int(meta_get(db, "wake_count", "0"))
    except ValueError:
        return 0


# ────────────────────────── 唤醒动作 ──────────────────────────

def generate_wake_text(scene_action, now_dt):
    """本地模型生成唤醒话（人格 QQ 档+场景接续）。失败返回 None（本轮
    放弃，下个检查周期再试——绝不拿模板话硬发）。"""
    try:
        import brain
        prompt = _WAKE_PROMPT.format(
            scene=scene_action or "（未知）",
            now=now_dt.strftime("%H:%M"))
        out = brain.ask_local(
            [{"role": "system", "content": QQ_PERSONA},
             {"role": "user", "content": prompt}])
        text = str(out or "").strip()
        if "<think>" in text:   # 剥思考（R1 类模型），只要正文
            text = text.split("</think>", 1)[-1].strip()
        # 剥引号包裹（模型爱加；成对异侧引号同剥）
        pairs = {('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"),
                 ("「", "」")}
        if len(text) >= 2 and (text[0], text[-1]) in pairs:
            text = text[1:-1].strip()
        return text or None
    except Exception as e:
        print(f"🦊 [qq_lifemate] 本地生成失败（本轮放弃）: {e}")
        return None


def send_qq(text):
    """发队长私聊。复用 heartbeat.notify_master（OneBot send_private_msg；
    main 已 import heartbeat——宿主进程 sys.modules 命中零增量；owner QQ
    未配置时 notify_master 返回 False 仅日志，不炸唤醒链）。"""
    try:
        from heartbeat import notify_master
        return bool(notify_master(text))
    except Exception as e:
        print(f"🦊 [qq_lifemate] QQ 发送失败: {e}")
        return False


def wake_once(now_dt):
    """单次唤醒尝试：读 scene → 生成 → 发送 → 落账。返回是否真发。"""
    db = _db()
    try:
        text = generate_wake_text(last_scene(db), now_dt)
        if not text:
            return False
        if not send_qq(text):
            return False
        # 表现力编排（切片 b）：文字已发出，按概率附加语音/表情（失败
        # 静默降级——文字消息不受影响）
        try:
            import express
            acts = express.maybe_express(text)
            if acts:
                print(f"🦊 [qq_lifemate] 表现力附加: {acts}")
        except Exception as e:
            print(f"🦊 [qq_lifemate] 表现力编排异常（不影响文字）: {e}")
        db.execute("INSERT INTO chat_log(role, content, ts, kind) "
                   "VALUES(?,?,?,?)",
                   ("assistant", text, now_str(), "proactive_wake"))
        today = now_dt.strftime("%Y-%m-%d")
        if meta_get(db, "wake_date") != today:
            meta_set(db, "wake_date", today)
            meta_set(db, "wake_count", "1")
        else:
            meta_set(db, "wake_count", str(daily_count(db, now_dt) + 1))
        db.commit()
        print(f"🦊 [qq_lifemate] 已主动唤醒：{text[:40]}")
        return True
    finally:
        db.close()


def _wake_loop():
    """唤醒线程体：每 CHECK_INTERVAL 检查一次三闸（硬帽/quiet/静默）。
    daemon 线程——宿主退出即消亡，stop() 优雅停。"""
    print(f"🦊 [qq_lifemate] 唤醒线程启动（每 {CHECK_INTERVAL_SEC // 60} 分钟"
          f"检查，静默 {SILENCE_HOURS}h，quiet {QUIET_START}:00-{QUIET_END}:00，"
          f"日限 {DAILY_CAP} 次）")
    while not _STOP.wait(CHECK_INTERVAL_SEC):
        try:
            now_dt = datetime.now()
            db = _db()
            try:
                count = daily_count(db, now_dt)
                wake, reason = should_wake(last_speak_ts(db), now_dt, count)
            finally:
                db.close()
            if not wake:
                # 被挡住（quiet/硬帽/未静默）→ 下个检查周期自然再查；
                # quiet 结束后 10 分钟内必查到，无需额外等待
                continue
            wake_once(now_dt)
        except Exception as e:
            print(f"🦊 [qq_lifemate] 唤醒循环异常（已兜住，下轮再试）: {e}")


def start():
    """setup 钩子调用：启动唤醒线程（幂等——已在跑则跳过）。"""
    global _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        return
    _STOP.clear()
    _THREAD = threading.Thread(target=_wake_loop, daemon=True,
                               name="qq_lifemate_waker")
    _THREAD.start()


def stop():
    """teardown 钩子调用：停唤醒线程（卸载即冬眠，零残留）。"""
    _STOP.set()
    print("🦊 [qq_lifemate] 唤醒线程已停（冬眠）")
