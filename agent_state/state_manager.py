# -*- coding: utf-8 -*-
"""小橘3号 · 状态外置层：SQLite 长期记忆 + 会话落盘。

按《架构设计文档》§4：long_term.db 长期记忆（memories 表）与
save_conversation 会话 JSON 落盘（只保留最近 MAX_MESSAGES 条）。
当前为脚手架，不接入对话主链路，但模块本身完整可用。
路径基于统一配置 xiaoju3.AGENT_STATE_DIR，也支持显式传参以便测试。
"""
import os
import json
import re
import sqlite3
import time
from datetime import datetime

from xiaoju3 import AGENT_STATE_DIR, MAX_MESSAGES


# ==================== 记忆 V2（#297 批 1：三乘子召回，2026-10-13） ====================
# 参数唯一口径 = 实验室 exp01-04（design_297_memory_merge_v2.md §1.6），照搬不加戏
RECALL_DEPTH = 2         # 扩散深度（exp02）
RECALL_DECAY = 0.5       # 每跳激活衰减（exp02）
RECALL_THRESHOLD = 0.05  # 激活剪枝阈值（exp02）
RECALL_GAIN = 0.30       # 召回使用增益（exp01）
WEIGHT_MAX = 3.0         # 权重上限（2026-10-13 拍板③：增益后夹钳，睡眠回放侧批 2 同款）
SEED_MAX = 12            # 单次召回种子候选上限（防超长消息全表扫；滑窗词元多，8 会截掉尾部有效词）

# 种子切分（朴素零依赖口径，2026-10-13 拍板②先跑）：中文连续段按虚词表
# 切短，ASCII/数字连续段直接作候选
_WORD_SPLIT_RE = re.compile(
    r'[的吗呢吧是在我你他要有很都就还也不没啊呀哦么及与和为得时这那哪嘛呗'
    r'个们地着过被把让从向往于而且或若虽但会能]')


def _seed_candidates(query):
    """用户消息 → 种子候选词（保序去重，上限 SEED_MAX）。

    中文段先（虚词切分→整段词），长段（≥4 字）再补 2 字滑窗词元——虚词
    表切不细的复合词（如「毕业答辩准备」）也能出「答辩」级词元；噪声
    词元 LIKE 不命中即无害。ASCII/数字段殿后。无候选返回空列表，由调用
    方回退时间序（旧行为零副作用，不劣于现状）。
    """
    text = str(query or "")
    out = []
    for seg in re.findall(r'[\u4e00-\u9fa5]{2,}', text):
        for word in _WORD_SPLIT_RE.split(seg):
            if len(word) >= 2 and word not in out:
                out.append(word)
    tail = []
    for seg in re.findall(r'[\u4e00-\u9fa5]{4,}', text):
        for i in range(len(seg) - 1):
            w = seg[i:i + 2]
            if w not in out and w not in tail:
                tail.append(w)
    for seg in re.findall(r'[A-Za-z0-9]{2,}', text):
        if seg not in out:
            out.append(seg)
    return (out + tail)[:SEED_MAX]


class StateManager:
    """长期记忆与会话历史的持久化管理器。"""

    # todos 表 DDL（2026-10-04 拆库）：memory_db 与分离 todos.db 共用一份，
    # 两库表结构严格一致。note（2026-10-05 待办说明折叠 #239）：浅色小字
    # 展示的"淡淡说明"——主任务放 content，细则/说明放 note
    _TODOS_DDL = '''
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            source_url TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done')),
            priority TEXT NOT NULL DEFAULT 'P1',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            done_at DATETIME,
            note TEXT DEFAULT ''
        )
    '''

    def __init__(self, base_dir=None):
        # 默认取统一配置；显式传参便于测试隔离
        self.base_dir = base_dir if base_dir is not None else AGENT_STATE_DIR
        self.identity_file = os.path.join(self.base_dir, "identity.json")
        self.memory_db = os.path.join(self.base_dir, "long_term.db")
        # 待办独立拆库（2026-10-04）：XIAOJU3_TODOS_DB_PATH 指向共享
        # todos.db（双目录部署的两版共用，正式版记待办不再被覆盖）——
        # 未设时 todos 仍存 memory_db（向后兼容，既有库零迁移）。读取
        # 时机：本模块 import 晚于 xiaoju3 的 .env 加载（:164），.env 值
        # 可直达 os.environ。
        self.todos_db = (os.environ.get("XIAOJU3_TODOS_DB_PATH")
                         or "").strip() or self.memory_db
        self._init_db()
        if self.todos_db != self.memory_db:
            self._init_separated_todos_db()

    def _init_db(self):
        """初始化长期记忆数据库（SQLite；todos 表仅在未拆库时承载待办）"""
        os.makedirs(self.base_dir, exist_ok=True)
        conn = sqlite3.connect(self.memory_db)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                content TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute(self._TODOS_DDL)
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status, id)
        ''')
        # 旧库迁移（尾巴 C）：ALTER ADD COLUMN 带默认值——既有行自动 P1
        cols = [row[1] for row in cursor.execute("PRAGMA table_info(todos)")]
        if "priority" not in cols:
            cursor.execute("ALTER TABLE todos ADD COLUMN priority TEXT NOT NULL DEFAULT 'P1'")
        # note 列迁移（2026-10-05 待办说明折叠 #239）：旧库补列，既有行默认 ''
        if "note" not in cols:
            cursor.execute("ALTER TABLE todos ADD COLUMN note TEXT DEFAULT ''")
        # effective_priority 列迁移（2026-10-07 时间老化/梯队递补）：
        # NULL=未老化，显示层 COALESCE 回原档
        if "effective_priority" not in cols:
            cursor.execute(
                "ALTER TABLE todos ADD COLUMN effective_priority TEXT DEFAULT NULL")
        # category 列迁移（2026-10-15 待办分类）：''=普通待办；
        # 「维护单」=独立可做不阻塞主线修完就了事的小活（#331 首例）
        if "category" not in cols:
            cursor.execute("ALTER TABLE todos ADD COLUMN category TEXT DEFAULT ''")
        # 固定优先级（2026-10-30 队长拍板）：pin=1 不参与老化/递补
        if "pin" not in cols:
            cursor.execute("ALTER TABLE todos ADD COLUMN pin INTEGER NOT NULL DEFAULT 0")
        # ===== 记忆 V2 schema（#297 批 1，2026-10-13）：memories 幂等补
        # 7 列 + 四表（todos note 列先例同款）。schema 不受开关控制——
        # 加列全带默认值向后兼容（旧代码不读新列照常工作），开关只控行为
        mem_cols = [row[1] for row in cursor.execute("PRAGMA table_info(memories)")]
        for col_sql in (
            "ALTER TABLE memories ADD COLUMN weight REAL NOT NULL DEFAULT 1.0",
            "ALTER TABLE memories ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE memories ADD COLUMN last_access TEXT",
            "ALTER TABLE memories ADD COLUMN activation REAL NOT NULL DEFAULT 0.0",
            "ALTER TABLE memories ADD COLUMN emotion_tag TEXT NOT NULL DEFAULT 'neutral'",
            "ALTER TABLE memories ADD COLUMN sink_status TEXT NOT NULL DEFAULT 'active'",
            "ALTER TABLE memories ADD COLUMN emotional_impact REAL NOT NULL DEFAULT 0.0",
        ):
            col = col_sql.split("ADD COLUMN ")[1].split()[0]
            if col not in mem_cols:
                cursor.execute(col_sql)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_edge (
                from_id INTEGER NOT NULL,
                to_id INTEGER NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                coactivation_count INTEGER NOT NULL DEFAULT 0,
                last_activated TEXT,
                PRIMARY KEY (from_id, to_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sleep_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                before REAL,
                after REAL,
                timestamp TEXT NOT NULL
            )
        ''')
        # 幂等闸 KV：睡眠/召回审计状态属记忆库——不走 get_meta/set_meta
        # （那连的是 todos_meta=todos.db，拆库后跨库）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_meta
            (key TEXT PRIMARY KEY, value TEXT)
        ''')
        conn.commit()
        conn.close()

    def _init_separated_todos_db(self):
        """分离模式初始化：todos.db 建表 + 索引 + WAL + 一次性自动迁移。

        - 自动迁移：todos_db 待办为空且 memory_db 有行 → 单事务按列名
          搬入（保 id；源库只读不写，天然作备份）；迁移完成写
          todos_meta 标记（幂等——此后用户清空共享库也不会复活旧行）。
        - 失败语义：任何 SQLite 错误 → 本次回退本地库（self.todos_db =
          self.memory_db，数据功能不丢、可能滞后），打印 ⚠️ 不抛出——
          绝不让拆库故障阻塞应用启动；下次启动自动重试。
        """
        os.makedirs(os.path.dirname(self.todos_db), exist_ok=True)
        conn = sqlite3.connect(self.todos_db, timeout=5.0)
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(self._TODOS_DDL)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status, id)")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS todos_meta "
                "(key TEXT PRIMARY KEY, value TEXT)")
            # note 列迁移（2026-10-05 #239）：旧共享库补列，既有行默认 ''
            cols = [row[1] for row in
                    conn.execute("PRAGMA table_info(todos)")]
            if "note" not in cols:
                conn.execute("ALTER TABLE todos ADD COLUMN note TEXT DEFAULT ''")
            # effective_priority 列迁移（2026-10-07 时间老化/梯队递补）
            if "effective_priority" not in cols:
                conn.execute(
                    "ALTER TABLE todos ADD COLUMN effective_priority TEXT DEFAULT NULL")
            # category 列迁移（2026-10-15 待办分类）：同 _init_db 口径
            if "category" not in cols:
                conn.execute("ALTER TABLE todos ADD COLUMN category TEXT DEFAULT ''")
            # pin 固定优先级迁移（2026-10-30 队长拍板）：同 _init_db 口径
            if "pin" not in cols:
                conn.execute("ALTER TABLE todos ADD COLUMN pin INTEGER NOT NULL DEFAULT 0")
            conn.commit()
            target_count = conn.execute(
                "SELECT COUNT(*) FROM todos").fetchone()[0]
            migrated = 0
            if target_count == 0:
                src_conn = sqlite3.connect(self.memory_db)
                try:
                    src_rows = src_conn.execute(
                        "SELECT id, content, source_url, status, created_at,"
                        " done_at, priority FROM todos ORDER BY id").fetchall()
                finally:
                    src_conn.close()
                if src_rows:
                    try:
                        conn.executemany(
                            "INSERT INTO todos (id, content, source_url,"
                            " status, created_at, done_at, priority)"
                            " VALUES (?, ?, ?, ?, ?, ?, ?)",
                            [tuple(r) for r in src_rows])
                        migrated = len(src_rows)
                        print(f"📦 [待办拆库] 已迁移 {migrated} 条待办 → "
                              f"{self.todos_db}")
                    except sqlite3.Error:
                        conn.rollback()   # 源库只读未动；目标保持空库
                        raise
            conn.execute(
                "INSERT OR IGNORE INTO todos_meta (key, value)"
                " VALUES ('migrated', ?)", (str(migrated),))
            conn.commit()
        except sqlite3.Error as e:
            self.todos_db = self.memory_db   # 回退本地库：功能不丢、数据或滞后
            print(f"⚠️ [待办拆库] todos.db 初始化失败，本次回退本地库: {e}")
        finally:
            conn.close()

    def save_memory(self, category, content, emotion_tag=None,
                    emotional_impact=None):
        """保存一条长期记忆（#297 批 1 扩签名：情绪打标，旧调用零改动——
        emotion_tag/emotional_impact 缺省走 neutral/0.0）。

        内容去重（2026-10-30 队长拍板根治）：同 content 已存在→UPDATE 刷新
        timestamp（鲜活度回写，注入排序靠前）而非插新行——生产实锤 10 条
        重复"明日方舟"（同句重复"记住"每几分钟一条）。UPDATE 优先模式
        （rowcount==0 才 INSERT）天然原子，记住链/summary_facts/人格沉淀
        全部写入方统一受保护。"""
        tag = emotion_tag or 'neutral'
        impact = emotional_impact if emotional_impact is not None else 0.0
        conn = sqlite3.connect(self.memory_db)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE memories SET timestamp = CURRENT_TIMESTAMP,"
            " emotion_tag = ?, emotional_impact = ? WHERE content = ?",
            (tag, impact, content))
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO memories (category, content, emotion_tag,"
                " emotional_impact) VALUES (?, ?, ?, ?)",
                (category, content, tag, impact))
            conn.commit()
            conn.close()
            print(f"💾 [状态外置层] 已保存记忆: {category}")
        else:
            conn.commit()
            conn.close()
            print(f"💾 [状态外置层] 记忆已存在，刷新鲜活度: {category}")

    def get_recent_memories(self, limit=5):
        """获取最近几条记忆，用于注入 Prompt"""
        conn = sqlite3.connect(self.memory_db)
        cursor = conn.cursor()
        cursor.execute("SELECT category, content FROM memories ORDER BY timestamp DESC LIMIT ?", (limit,))
        results = cursor.fetchall()
        conn.close()
        return results

    # ==================== 记忆 V2 三乘子召回（#297 批 1） ====================

    @staticmethod
    def _seed_hits(conn, query):
        """种子候选 LIKE 命中（含 pending_sink——种子被想起即复活，exp04
        wake_round 语义）；返回原始行元组列表，空候选/零命中返回 []。"""
        cands = _seed_candidates(query)
        if not cands:
            return []
        sql = ("SELECT id, category, content, weight, emotion_tag, sink_status"
               " FROM memories WHERE "
               + " OR ".join("content LIKE ?" for _ in cands))
        return conn.execute(sql, [f"%{c}%" for c in cands]).fetchall()

    @staticmethod
    def _spread_pure(conn, seed_ids):
        """扩散激活纯读版（exp02/04 同口径：RECALL_DEPTH/DECAY/THRESHOLD；
        种子自身激活 1.0、不被邻居回注防自激——exp03 修正后语义）。"""
        gained = {s: 1.0 for s in seed_ids}
        frontier = {s: 1.0 for s in seed_ids}
        for _ in range(RECALL_DEPTH):
            nxt = {}
            for nid, act in frontier.items():
                for nb, ew in conn.execute(
                        "SELECT to_id, weight FROM memory_edge WHERE from_id=?"
                        " UNION SELECT from_id, weight FROM memory_edge"
                        " WHERE to_id=?", (nid, nid)).fetchall():
                    if nb in seed_ids:
                        continue
                    inject = act * RECALL_DECAY * ew
                    if inject < RECALL_THRESHOLD:
                        continue
                    nxt[nb] = max(nxt.get(nb, 0.0), inject)
                    gained[nb] = max(gained.get(nb, 0.0), inject)
            frontier = nxt
            if not frontier:
                break
        return gained

    def recall_memories(self, query, limit=5):
        """三乘子召回（#297 批 1）：种子 LIKE → 扩散激活 →
        weight × activation × mood_factor 排序；返回 [(category, content)]
        ——与 get_recent_memories 同形态，消费方 block 格式逐字节不变。

        - 无种子命中 → 回退时间序 TOP limit（旧行为零副作用，不劣于现状）；
        - 种子命中 pending_sink → 复活回 active（被想起即回活跃区）；
        - 落库（每轮一次）：TOP 内种子使用增益（weight+0.30 夹钳
          WEIGHT_MAX，拍板③ / access_count+1 / last_access 刷新）、
          gained activation+审计 log、gained 节点对共激活+1（边权唯一
          生长来源，拍板①召回共激活）；
        - mood_factor 走 mood.mood_factor_for（P 维档位表，异常→1.0）。
        """
        conn = sqlite3.connect(self.memory_db)
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            seeds = self._seed_hits(conn, query)
            if not seeds:
                return conn.execute(
                    "SELECT category, content FROM memories"
                    " ORDER BY timestamp DESC LIMIT ?",
                    (limit,)).fetchall()
            seed_ids = {r[0] for r in seeds}
            # 复活（先于打分：刚复活的种子本轮即参与排序）
            for row in seeds:
                if row[5] == "pending_sink":
                    conn.execute(
                        "UPDATE memories SET sink_status='active'"
                        " WHERE id=?", (row[0],))
            conn.commit()
            gained = self._spread_pure(conn, list(seed_ids))
            # mood 因子：一次读档，逐 tag 查表（mood 缺席/异常→1.0 中性旁路）
            try:
                import mood as _mood
                _state = _mood.load_mood()
            except Exception:
                _mood = None
                _state = None

            def _mf(tag):
                if _mood is None:
                    return 1.0
                try:
                    return _mood.mood_factor_for(tag, _state)
                except Exception:
                    return 1.0

            all_rows = conn.execute(
                "SELECT id, category, content, weight, emotion_tag"
                " FROM memories WHERE sink_status='active' OR id IN (%s)"
                % ",".join("?" * len(seed_ids)),
                list(seed_ids)).fetchall()
            scored = []
            for rid, cat, content, w, tag in all_rows:
                act = gained.get(rid, 0.0)
                scored.append((round(w * act * _mf(tag), 6),
                               rid, cat, content))
            scored.sort(key=lambda r: -r[0])
            top = scored[:limit]
            # ---- 落库段（每轮召回一次；失败不影响返回）----
            try:
                for _score, rid, _cat, _content in top:
                    if rid in seed_ids:
                        # 使用增益（种子级；MIN 夹钳 WEIGHT_MAX=拍板③）
                        conn.execute(
                            "UPDATE memories SET weight ="
                            " MIN(weight + ?, ?), access_count ="
                            " access_count + 1, last_access = ?"
                            " WHERE id = ?",
                            (RECALL_GAIN, WEIGHT_MAX, now, rid))
                for nid, act in gained.items():
                    conn.execute(
                        "UPDATE memories SET activation=? WHERE id=?",
                        (round(act, 4), nid))
                    conn.execute(
                        "INSERT INTO activation_log (node_id, timestamp,"
                        " source) VALUES (?, ?, ?)",
                        (nid, now, "recall_seed" if nid in seed_ids
                         else "recall_spread"))
                for u, v in conn.execute(
                        "SELECT from_id, to_id FROM memory_edge").fetchall():
                    if u in gained and v in gained:
                        conn.execute(
                            "UPDATE memory_edge SET coactivation_count ="
                            " coactivation_count + 1, last_activated = ?"
                            " WHERE from_id=? AND to_id=?", (now, u, v))
                conn.commit()
            except sqlite3.Error as e:
                print(f"⚠️ [记忆V2] 召回落库失败（已跳过）: {e}")
            return [(cat, content) for (_s, _r, cat, content) in top]
        finally:
            conn.close()

    # ==================== 待办清单（DeepSeek 链接提取，docs/TODO_EXTRACT_DESIGN.md §2） ====================

    @staticmethod
    def _normalize_todo(content):
        """待办去重口径：去全部空白后全等比较。"""
        return "".join(str(content or "").split())

    @staticmethod
    def _normalize_priority(value):
        """优先级归一：P0-P5 之外的输入一律回落 P1（LLM 输出容错）。"""
        text = str(value or "").strip().upper()
        return text if text in ("P0", "P1", "P2", "P3", "P4", "P5") else "P1"

    def save_todos(self, items, source_url=""):
        """批量写入待办（status='pending'）。

        items: list[str] 或 list[dict{"content", "priority"}]（尾巴 C：
        priority 可选，P0/P1/P2 之外归一 P1）。
        幂等：同 source_url 且规范化 content 已存在 pending 项 → 跳过。
        返回 (inserted, skipped) 计数。
        """
        conn = sqlite3.connect(self.todos_db)
        cursor = conn.cursor()
        existing = {
            self._normalize_todo(row[0])
            for row in cursor.execute(
                "SELECT content FROM todos WHERE status = 'pending' AND source_url = ?",
                (source_url,))
        }
        inserted = skipped = 0
        for raw in items:
            if isinstance(raw, dict):
                content = str(raw.get("content") or "").strip()
                priority = self._normalize_priority(raw.get("priority"))
            else:
                content = str(raw or "").strip()
                priority = "P1"
            if not content:
                continue
            key = self._normalize_todo(content)
            if key in existing:
                skipped += 1
                continue
            cursor.execute("INSERT INTO todos (content, source_url, priority) VALUES (?, ?, ?)",
                           (content, source_url, priority))
            existing.add(key)
            inserted += 1
        conn.commit()
        conn.close()
        return inserted, skipped

    def get_todos(self, status=None, limit=50):
        """查询待办。status=None 返回全部（id DESC，最新在前）；
        'pending'/'done' 过滤（id ASC，旧号在前便于按序处理）。
        返回 list[dict]：{id, content, source_url, status, priority,
        effective_priority, created_at, done_at, note, pin}——effective_priority
        为 COALESCE(老化列, 原档)（2026-10-07 时间老化/梯队递补，未老化=原档），
        原 priority 列照返（前端"↑已升"标记据此对照）；pin=固定优先级
        （2026-10-30 队长拍板：固定任务不随老化/递补升降）。"""
        conn = sqlite3.connect(self.todos_db)
        cursor = conn.cursor()
        if status in ("pending", "done"):
            order = "ASC" if status == "pending" else "DESC"
            cursor.execute(
                "SELECT id, content, source_url, status, priority, "
                "COALESCE(effective_priority, priority) AS effective_priority, "
                "created_at, done_at, note, pin "
                f"FROM todos WHERE status = ? ORDER BY id {order} LIMIT ?",
                (status, limit))
        else:
            cursor.execute(
                "SELECT id, content, source_url, status, priority, "
                "COALESCE(effective_priority, priority) AS effective_priority, "
                "created_at, done_at, note, pin "
                "FROM todos ORDER BY id DESC LIMIT ?", (limit,))
        rows = [{"id": r[0], "content": r[1], "source_url": r[2], "status": r[3],
                 "priority": r[4], "effective_priority": r[5], "created_at": r[6],
                 "done_at": r[7], "note": r[8] or "", "pin": bool(r[9])}
                for r in cursor.fetchall()]
        conn.close()
        return rows

    def set_todo_pin(self, todo_id, pin):
        """固定优先级开关（2026-10-30 队长拍板）：pin=True 的待办不参与
        时间老化与梯队递补（永远待在当前档）。返回是否真的改了行。"""
        conn = sqlite3.connect(self.todos_db)
        try:
            cur = conn.execute("UPDATE todos SET pin = ? WHERE id = ?",
                               (1 if pin else 0, todo_id))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    def set_effective_priority(self, todo_id, new_priority):
        """时间老化/梯队递补写 effective_priority（2026-10-07 四拍板）。

        只增不回退：新档 P 编号必须**严格小于**现生效档（effective 优先，
        无则取原 priority），同档/降档一律 False——封顶 P0 由"严格小于"
        天然保证；原 priority 列永不改动。仅 pending 行可写。
        """
        new_priority = str(new_priority or "").strip().upper()
        if new_priority not in ("P0", "P1", "P2", "P3", "P4", "P5"):
            return False
        conn = sqlite3.connect(self.todos_db)
        try:
            row = conn.execute(
                "SELECT priority, effective_priority, status FROM todos "
                "WHERE id = ?", (int(todo_id),)).fetchone()
            if not row or row[2] != "pending":
                return False
            cur_eff = row[1] or row[0]
            if int(new_priority[1]) >= int(str(cur_eff)[1]):
                return False   # 只升不降；同档重复写无效（幂等友好）
            conn.execute("UPDATE todos SET effective_priority = ? WHERE id = ?",
                         (new_priority, int(todo_id)))
            conn.commit()
            return True
        finally:
            conn.close()

    def clear_effective_priority(self, todo_id):
        """清除老化痕迹（effective 回 NULL，显示回归原档）——手动改档时
        调用（拍板④：手动覆盖自动），api_todo_priority 同步触发。"""
        conn = sqlite3.connect(self.todos_db)
        try:
            conn.execute("UPDATE todos SET effective_priority = NULL "
                         "WHERE id = ?", (int(todo_id),))
            conn.commit()
        finally:
            conn.close()

    def get_meta(self, key):
        """todos_meta 键值读（老化 last_date 等调度状态；无行返回 None）。
        表在分离库初始化即建；本地库路径按需自建（防御 no such table）。"""
        conn = sqlite3.connect(self.todos_db)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS todos_meta "
                         "(key TEXT PRIMARY KEY, value TEXT)")
            row = conn.execute("SELECT value FROM todos_meta WHERE key = ?",
                               (key,)).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def set_meta(self, key, value):
        """todos_meta 键值写（upsert）。"""
        conn = sqlite3.connect(self.todos_db)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS todos_meta "
                         "(key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO todos_meta (key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                         (key, str(value)))
            conn.commit()
        finally:
            conn.close()

    def set_todo_priority(self, todo_id, priority):
        """设置待办优先级（尾巴 C：前端 P0/P1/P2 pill）。

        priority 经 _normalize_priority 归一（非法值回落 P1，端点侧无需预校验）。
        返回更新后的行 dict；id 不存在 → None。
        """
        conn = sqlite3.connect(self.todos_db)
        cursor = conn.cursor()
        cursor.execute("UPDATE todos SET priority = ? WHERE id = ?",
                       (self._normalize_priority(priority), int(todo_id)))
        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()
        if not updated:
            return None
        return next((t for t in self.get_todos(limit=1000)
                     if t["id"] == int(todo_id)), None)

    def last_extracted_at(self, source_url):
        """该链接最近一次入库时间（unix 秒）；从未入库返回 None。

        尾巴 B：24h 查重的跨进程持久层——内存表进程重启即失，本查询以
        todos.created_at（UTC）为真源，重启后仍能拦住同链接重复提取。
        """
        conn = sqlite3.connect(self.todos_db)
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT MAX(created_at) FROM todos WHERE source_url = ?",
            (source_url,)).fetchone()
        conn.close()
        if not row or not row[0]:
            return None
        import calendar
        return float(calendar.timegm(time.strptime(row[0], "%Y-%m-%d %H:%M:%S")))

    def complete_todo(self, todo_id):
        """标记待办完成（置 status='done'、done_at=当前时刻；仅 pending 行受影响）。

        返回完成后的行 dict；id 不存在或已是 done → None（幂等）。
        """
        conn = sqlite3.connect(self.todos_db)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE todos SET status = 'done', done_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = 'pending'", (int(todo_id),))
        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()
        if not updated:
            return None
        return next((t for t in self.get_todos(status="done", limit=1000)
                     if t["id"] == int(todo_id)), None)

    def reopen_todo(self, todo_id):
        """把已完成待办翻回 pending（清 done_at；仅 done 行受影响）。

        复选框取消钩的存储侧（2026-10-04 尾巴 1，与 complete_todo 对称）。
        返回翻回后的行 dict；id 不存在或已是 pending → None（幂等）。
        """
        conn = sqlite3.connect(self.todos_db)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE todos SET status = 'pending', done_at = NULL "
            "WHERE id = ? AND status = 'done'", (int(todo_id),))
        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()
        if not updated:
            return None
        return next((t for t in self.get_todos(status="pending", limit=1000)
                     if t["id"] == int(todo_id)), None)

    def clear_todos(self):
        """清空 todos 表全部行（pending + done；2026-10-04 /todos clear）。

        返回删除条数。注意：不清 memories 等其他表；24h 提取查重的
        todos.created_at 依赖随之清空 → 清空后同链接可重新提取（预期语义，
        调用方需同步 todo_extractor.clear_recent_urls() 清内存防抖层）。
        """
        conn = sqlite3.connect(self.todos_db)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM todos")
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted

    def delete_todo(self, todo_id):
        """硬删单条待办（2026-10-05 #238：垃圾桶图标；通用单条删，
        后端不限 status，前端仅对已完成项显示入口。不可逆。"""
        conn = sqlite3.connect(self.todos_db)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted > 0

    def set_todo_note(self, todo_id, note):
        """设置待办说明（2026-10-05 #239：折叠 UI 的编辑保存入口）。

        note 存"淡淡说明"文本（多行允许，前端浅色小字展示）；空串 = 清空
        说明。返回更新后的行 dict（经 get_todos 读取，与优先级编辑同款
        返回口径）；id 不存在 → None。
        """
        conn = sqlite3.connect(self.todos_db)
        cursor = conn.cursor()
        cursor.execute("UPDATE todos SET note = ? WHERE id = ?",
                       (str(note or ""), int(todo_id)))
        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()
        if not updated:
            return None
        return next((t for t in self.get_todos(limit=1000)
                     if t["id"] == int(todo_id)), None)

    # ==================== 待办 UI 状态（分区折叠；WebView2 InPrivate 下
    # localStorage 跨启动即焚 → 服务端 JSON 承载，2026-10-04 尾巴 I） ====================

    @property
    def todo_ui_state_file(self):
        """待办 UI 状态文件路径（base_dir 下 todo_ui_state.json）。"""
        return os.path.join(self.base_dir, "todo_ui_state.json")

    def get_todo_collapsed_groups(self):
        """读取折叠分区列表（["P2", "P3"]）；文件缺失/损坏/非数组 → []。"""
        try:
            with open(self.todo_ui_state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []
        groups = data.get("collapsed_groups") if isinstance(data, dict) else None
        if not isinstance(groups, list):
            return []
        return [str(g) for g in groups if isinstance(g, str)]

    def save_todo_collapsed_groups(self, groups):
        """保存折叠分区列表（全量覆盖写；非字符串项跳过）。"""
        clean = [str(g) for g in (groups or []) if isinstance(g, str)]
        data = {"collapsed_groups": clean, "updated_at": time.time()}
        with open(self.todo_ui_state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return clean

    def save_conversation(self, source, messages):
        """把对话历史独立出来，避免污染代码（只保留最近 MAX_MESSAGES 条）"""
        conv_dir = os.path.join(self.base_dir, "conversations")
        os.makedirs(conv_dir, exist_ok=True)
        conv_file = os.path.join(conv_dir, f"{source}_history.json")
        with open(conv_file, "w", encoding="utf-8") as f:
            json.dump(messages[-MAX_MESSAGES:], f, ensure_ascii=False, indent=2)

    # ==================== 用户位置（搜索指代消解，2026-10-02） ====================
    # 隐私口径：位置只存本文件（agent_state/user_location.json，已 gitignore），
    # 不上传 GitHub、不写 .env、不传给云端（仅天气/本地搜索时用于拼 query）。

    @property
    def user_location_file(self):
        """用户位置记录文件路径（base_dir 下 user_location.json）。"""
        return os.path.join(self.base_dir, "user_location.json")

    def save_user_location(self, city, district=None):
        """记录用户默认位置（全量覆盖写；district 可空——主人只说了城市）。

        文件结构：{"city": "长沙", "district": "天心区", "updated_at": 时间戳}。
        """
        data = {"city": str(city or "").strip(),
                "district": str(district or "").strip(),
                "updated_at": time.time()}
        with open(self.user_location_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        shown = data["city"] + (f" {data['district']}" if data["district"] else "")
        print(f"📍 [状态外置层] 已记录用户位置: {shown}（仅本地，不入库）")
        return data

    def get_user_location(self):
        """读取用户位置 {"city", "district"}；未记录 / 文件损坏 / 城市为空
        返回 None（调用方据此走"主动询问"分支）。"""
        try:
            with open(self.user_location_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
        if not isinstance(data, dict) or not str(data.get("city", "")).strip():
            return None
        return {"city": str(data.get("city", "")).strip(),
                "district": str(data.get("district", "")).strip()}

    def clear_user_location(self):
        """清除用户位置记录（删除文件；本就不存在时静默）。"""
        try:
            os.remove(self.user_location_file)
        except OSError:
            pass


# 全局单例，供其他模块直接调用
state_manager = StateManager()


# ==================== 用户位置模块级便捷封装（2026-10-02） ====================
# brain / main 指令族直接调用；测试可用 tmp base_dir 构造独立 StateManager 验证。

def save_user_location(city, district=None):
    """记录用户默认位置（单例便捷封装，见 StateManager.save_user_location）。"""
    return state_manager.save_user_location(city, district)


def get_user_location():
    """读取用户位置（单例便捷封装；无记录返回 None）。"""
    return state_manager.get_user_location()


def clear_user_location():
    """清除用户位置记录（单例便捷封装）。"""
    return state_manager.clear_user_location()


# ── 记忆人称转换（2026-10-27 人格认知 Bug 修复）：主人第一人称落库前转 ──
# 第三人称——防止生命体/模型把主人的喜好念成"我…"（真机实锤：她把
# "我最喜欢玩明日方舟"说成自己的设定）
_P1_PATTERNS = (
    ("我最喜欢", "主人最喜欢"),
    ("我最爱", "主人最爱"),
    ("我最讨厌", "主人最讨厌"),
    ("我喜欢", "主人喜欢"),
    ("我爱", "主人爱"),
    ("我讨厌", "主人讨厌"),
    ("我在玩", "主人在玩"),
    ("我在用", "主人在用"),
    ("我要", "主人要"),
    ("我想", "主人想"),
    ("我的", "主人的"),
    ("我们是", "主人和小橘是"),
)


def to_third_person_memory(text):
    """主人第一人称 → 第三人称（落库前调用）。只替换记忆语义里的"我"
    常见句首/属格形态，避免通篇盲替误伤（引号内台词等仍可能漏——概率
    可接受，替换方向语义安全）。非字符串原样返回。"""
    if not isinstance(text, str) or not text:
        return text
    out = text
    for a, b in _P1_PATTERNS:
        out = out.replace(a, b)
    # 行首/句首残留的独立"我"（"我昨天…"→"主人昨天…"）
    if out.startswith("我"):
        out = "主人" + out[1:]
    out = out.replace("。我", "。主人").replace("，我", "，主人")
    return out
