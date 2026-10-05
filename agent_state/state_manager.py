# -*- coding: utf-8 -*-
"""小橘3号 · 状态外置层：SQLite 长期记忆 + 会话落盘。

按《架构设计文档》§4：long_term.db 长期记忆（memories 表）与
save_conversation 会话 JSON 落盘（只保留最近 MAX_MESSAGES 条）。
当前为脚手架，不接入对话主链路，但模块本身完整可用。
路径基于统一配置 xiaoju3.AGENT_STATE_DIR，也支持显式传参以便测试。
"""
import os
import json
import sqlite3
import time

from xiaoju3 import AGENT_STATE_DIR, MAX_MESSAGES


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

    def save_memory(self, category, content):
        """保存一条长期记忆"""
        conn = sqlite3.connect(self.memory_db)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO memories (category, content) VALUES (?, ?)", (category, content))
        conn.commit()
        conn.close()
        print(f"💾 [状态外置层] 已保存记忆: {category}")

    def get_recent_memories(self, limit=5):
        """获取最近几条记忆，用于注入 Prompt"""
        conn = sqlite3.connect(self.memory_db)
        cursor = conn.cursor()
        cursor.execute("SELECT category, content FROM memories ORDER BY timestamp DESC LIMIT ?", (limit,))
        results = cursor.fetchall()
        conn.close()
        return results

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
        created_at, done_at}。"""
        conn = sqlite3.connect(self.todos_db)
        cursor = conn.cursor()
        if status in ("pending", "done"):
            order = "ASC" if status == "pending" else "DESC"
            cursor.execute(
                "SELECT id, content, source_url, status, priority, created_at, done_at, note "
                f"FROM todos WHERE status = ? ORDER BY id {order} LIMIT ?",
                (status, limit))
        else:
            cursor.execute(
                "SELECT id, content, source_url, status, priority, created_at, done_at, note "
                "FROM todos ORDER BY id DESC LIMIT ?", (limit,))
        rows = [{"id": r[0], "content": r[1], "source_url": r[2], "status": r[3],
                 "priority": r[4], "created_at": r[5], "done_at": r[6],
                 "note": r[7] or ""}
                for r in cursor.fetchall()]
        conn.close()
        return rows

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
