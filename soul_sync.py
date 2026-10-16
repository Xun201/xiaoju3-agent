# -*- coding: utf-8 -*-
"""小橘3号 · 灵魂同步（#319 批 2：回写 outbox+自回写闭环）。

设计稿 _dev/design_319_batch2_impl.md（D6-D9/D13/D14+S1-S5 已拍板）。
语义基准 landing v2 §十灵魂物流框架：本模块=干线（writeback+outbox）的
分身侧；仓储=agent_state/；可视化=soul.db 审计+conflicts。

数据域标注（soul_manifest 单一事实源已登记）：
- soul.db：SOUL_CORE（灵魂审计跟人走）——writeback_log 审计+conflicts 冲突
  预留（批 2 只建表只记 pending，判定留批 4）；
- soul_outbox.json：NOT_SOUL（设备私有投递态）——default deny 不进包；
- 回写包=export_bundle(v2=True, include_extensions=False) core-only 轻量包。

依赖方向：零 import main（#227 纪律续）。多端预留：device_id+protocol_version
字段、token 独立于设备、角色由 XIAOJU3_SOUL_CORE 配置定（不焊死拓扑）。
import 本模块零副作用（建表/队列读写均惰性）。
"""
import json
import os
import sqlite3
import threading
import time

from migration import export_bundle
from xiaoju3 import AGENT_STATE_DIR, PROJECT_ROOT

# ==================== 常量 ====================

SOUL_OUTBOX_FILE = "soul_outbox.json"       # NOT_SOUL：设备私有投递态
SOUL_DB_FILE = "soul.db"                    # SOUL_CORE：灵魂审计（跟人走）
PROTOCOL_VERSION = 1                        # 多端预留：请求体协议版本
BACKOFF_SCHEDULE = (60, 300, 1800, 7200)    # 退避秒数：1m→5m→30m→2h 封顶
BACKLOG_COUNT_THRESHOLD = 5                 # 积压件数阈值（§十.11 生活事件）
BACKLOG_AGE_THRESHOLD = 7200                # 最老件年龄阈值（秒）
DEFAULT_CORE_URL = ""                       # XIAOJU3_SOUL_CORE 注入（空=未启用）

_outbox_lock = threading.Lock()             # S2：心跳线程与退出链并发 flush

# 生活化积压提示（§十.11：outbox 满=生活事件，非技术故障——禁 ERROR 词族）
BACKLOG_ALERT_TEXT = (
    "⏳ 我这攒了几份备份还没送出去，等网络稳了我自己再试。")
# （2026-10-16 用户拍板软化版：小橘现处客气型，甜版抢跑；真到"爱粘着你"
#  模式可升级文案——与 #271 关系模式联动的文案分级留批 4+）


def _outbox_path(base_dir=None):
    base = base_dir or AGENT_STATE_DIR
    return os.path.join(base, *SOUL_OUTBOX_FILE.split("/"))


def _soul_db_path(base_dir=None):
    base = base_dir or AGENT_STATE_DIR
    return os.path.join(base, *SOUL_DB_FILE.split("/"))


# ==================== soul.db（S1：首次调用幂等建表） ====================

def init_soul_db(db_path=None):
    """幂等建表：soul_writeback_log 审计 + soul_conflicts 冲突预留。

    - conflicts.replica_trace 预留时间戳序列 JSON（§十.8 冲突=重放的剪辑素材）；
    - 批 2 只建表只记 pending，判定逻辑留批 4；
    - 重复调用零副作用。
    """
    path = db_path or _soul_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path)
    try:
        db.execute(
            "CREATE TABLE IF NOT EXISTS soul_writeback_log ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ts TEXT NOT NULL,"
            " device_id TEXT NOT NULL,"
            " direction TEXT NOT NULL DEFAULT 'recv',"
            " action TEXT NOT NULL,"
            " files_n INTEGER DEFAULT 0,"
            " bytes INTEGER DEFAULT 0,"
            " result TEXT NOT NULL,"
            " detail TEXT)")
        db.execute(
            "CREATE TABLE IF NOT EXISTS soul_conflicts ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " path TEXT NOT NULL,"
            " object_key TEXT,"
            " device_id TEXT NOT NULL,"
            " core_ts TEXT, replica_ts TEXT,"
            " core_sha TEXT, replica_sha TEXT,"
            " replica_trace TEXT,"
            " status TEXT NOT NULL DEFAULT 'pending',"
            " resolved_by TEXT,"
            " created_at TEXT, resolved_at TEXT)")
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_conflicts_status"
            " ON soul_conflicts(status)")
        db.commit()
    finally:
        db.close()
    return path


def log_writeback(device_id, action, result, files_n=0, bytes_n=0,
                  detail=None, db_path=None, direction="recv"):
    """审计一行（收包与投递共用；失败不影响主流程——审计尽力而为）。"""
    path = db_path or _soul_db_path()
    try:
        init_soul_db(path)
        db = sqlite3.connect(path)
        try:
            db.execute(
                "INSERT INTO soul_writeback_log"
                " (ts, device_id, direction, action, files_n, bytes, result, detail)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (time.strftime("%Y-%m-%d %H:%M:%S"), device_id, direction,
                 action, files_n, bytes_n, result, detail))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"⚠️ [灵魂同步] 审计写入失败（不影响主流程）: {e}")


# ==================== SoulOutbox（设备私有投递队列） ====================

class SoulOutbox:
    """待回写包队列（soul_outbox.json，原子写 tmp+replace）。

    - 分身本地数据永不因回写失败受损——outbox 只是副本投递；
    - 退避曲线 BACKOFF_SCHEDULE：attempts 1→60s，2→300s，3→1800s，≥4→7200s；
    - 积压阈值（件数≥5 或最老件>2h）触发生活化提示（§十.11）。
    """

    def __init__(self, path=None):
        self.path = path or _outbox_path()

    # ---- 存取（原子写） ----
    def _load(self):
        if not os.path.isfile(self.path):
            return []
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []   # 队列文件损坏按空处理（包本体仍在磁盘，可重新 enqueue）

    def _save(self, entries):
        tmp = self.path + ".tmp"
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    # ---- 队列操作 ----
    def enqueue(self, bundle_path, core_url, device_id=None, now=None):
        with _outbox_lock:
            entries = self._load()
            entry = {"bundle_path": bundle_path, "core_url": core_url,
                     "device_id": device_id or "", "attempts": 0,
                     "next_ts": (now or time.time()),
                     "created_at": (now or time.time())}
            entries.append(entry)
            self._save(entries)
            return entry

    def due(self, now=None):
        now = now or time.time()
        with _outbox_lock:
            return [e for e in self._load() if e.get("next_ts", 0) <= now]

    def all_entries(self):
        with _outbox_lock:
            return list(self._load())

    def mark_done(self, entry, now=None):
        with _outbox_lock:
            entries = self._load()
            entries = [e for e in entries
                       if not (e.get("bundle_path") == entry.get("bundle_path")
                               and e.get("created_at") == entry.get("created_at"))]
            self._save(entries)

    def mark_fail(self, entry, now=None):
        now = now or time.time()
        with _outbox_lock:
            entries = self._load()
            for e in entries:
                if (e.get("bundle_path") == entry.get("bundle_path")
                        and e.get("created_at") == entry.get("created_at")):
                    e["attempts"] = int(e.get("attempts", 0)) + 1
                    idx = min(e["attempts"], len(BACKOFF_SCHEDULE)) - 1
                    e["next_ts"] = now + BACKOFF_SCHEDULE[max(idx, 0)]
            self._save(entries)

    def backlog_alert(self, now=None):
        """积压超阈值 → 生活化提示文案（§十.11）；未超阈值返回 None。"""
        now = now or time.time()
        entries = self.all_entries()
        if not entries:
            return None
        oldest = min(e.get("created_at", now) for e in entries)
        if len(entries) >= BACKLOG_COUNT_THRESHOLD or (now - oldest) > BACKLOG_AGE_THRESHOLD:
            return BACKLOG_ALERT_TEXT
        return None


# ==================== 回写打包与投递 ====================

def make_writeback_bundle(path=None, base_dir=None, include_extensions=False):
    """core-only 轻量回写包（§十.9 迁移粒度=派半个人）。

    封装 migration.export_bundle(v2=True)——带 soul_meta sha256 校验链
    （端点侧 verify_soul_bundle_payload 消费的正是它）。
    返回 export_bundle v2 dict：{"ok","path","files","size","meta","report"}。
    """
    return export_bundle(path=path, base_dir=base_dir, v2=True,
                         include_extensions=include_extensions)


def writeback_once(entry, token=None, timeout=15, sync=False):
    """投递一个 outbox 条目（HTTP POST，标准 REST 多端可调）。

    - 202 → mark_done；409/4xx=配置类（S3：attempts 拉满封顶不盲试）；
      网络类 → mark_fail 正常退避；
    - 返回 ("done"/"deferred"/"config_error", detail)。
    （网络调用 2-b 接线 process_outbox 时启用；本批 2-a 仅定义契约。）
    """
    import requests
    headers = {"X-Soul-Token": token or ""}
    with open(entry["bundle_path"], "rb") as f:
        import base64
        payload = {
            "device_id": entry.get("device_id") or "",
            "protocol_version": PROTOCOL_VERSION,
            "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "include_extensions": False,
            "bundle": base64.b64encode(f.read()).decode("ascii"),
        }
    try:
        resp = requests.post(entry["core_url"].rstrip("/") + "/api/soul/writeback",
                             json=payload, headers=headers, timeout=timeout)
        return ("done" if resp.status_code == 202 else "config_error",
                f"HTTP {resp.status_code}")
    except Exception as e:
        return ("deferred", str(e)[:120])


def heartbeat_soul_tick(now=None):
    """心跳兜底（D6 拍板时机）：到期 outbox 投递+每日一次全量入队。

    - XIAOJU3_SOUL_CORE 未配置（缺省空）→ 返回 None，纯现状零行为；
    - 每日全量：.soul_daily_watermark 按天去重（NOT_SOUL 设备私有），
      固定名 backups/soul_daily.zip 覆盖写（不堆积）；
    - 返回状态串（有动作/告警时）或 None（心跳打印节流由调用方定）。
    """
    now = now or time.time()
    core = (os.environ.get("XIAOJU3_SOUL_CORE", "") or "").strip()
    if not core:
        return None
    token = (os.environ.get("XIAOJU3_SOUL_TOKEN", "") or "").strip()
    box = SoulOutbox()
    notes = []
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    wm_path = os.path.join(AGENT_STATE_DIR, ".soul_daily_watermark")
    try:
        with open(wm_path, encoding="utf-8") as f:
            last = f.read().strip()
    except OSError:
        last = ""
    if last != today:
        try:
            daily_path = os.path.join(PROJECT_ROOT, "backups",
                                      "soul_daily.zip")
            r = make_writeback_bundle(path=daily_path)
            box.enqueue(r["path"], core, device_id=manifest_device_id())
            with open(wm_path, "w", encoding="utf-8") as f:
                f.write(today)
            notes.append(f"每日全量入队（{r['size']}B）")
        except Exception as e:
            notes.append(f"每日全量打包失败: {e}")
    done = process_outbox(box, token=token)
    if done:
        notes.append(f"投递 {done} 件")
    alert = box.backlog_alert(now=now)
    if alert:
        notes.append(alert)
    return "；".join(notes) if notes else None


def manifest_device_id():
    """设备标识（soul_manifest.device_id 转发——queue entry 用）。"""
    import soul_manifest
    return soul_manifest.device_id()


def process_outbox(outbox=None, token=None, sync=False, total_timeout=10.0):
    """处理到期投递（sync=True 供退出链阻塞 flush，总超时强制返回）。"""
    box = outbox or SoulOutbox()
    start = time.time()
    done = 0
    for entry in box.due():
        if sync and (time.time() - start) > total_timeout:
            break   # 退出 flush 尽力而为：超时放行关机（锚锁死）
        state, detail = writeback_once(entry, token=token)
        if state == "done":
            box.mark_done(entry)
            done += 1
        elif state == "config_error":
            entry["attempts"] = len(BACKOFF_SCHEDULE) + 1   # S3：不盲试
            box.mark_fail(entry)
        else:
            box.mark_fail(entry)
    return done
