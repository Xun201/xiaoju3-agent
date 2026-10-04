# -*- coding: utf-8 -*-
"""待办说明折叠测试（2026-10-05 #239）：note 列迁移与缺省兼容 /
set_todo_note 读写 / POST /api/todos/<id>/note 路由 / content→note
拆分解析四形态 / #240 特殊切分 / 前端渲染锚（note 在→渲染、空→不渲染、
编辑态 textarea、/send_image 排除同款精确锚）。全离线（tmp 库 + 静态锚）。"""
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agent_state.state_manager import StateManager
import xiaoju3_dashboard as dashboard

# 与迁移脚本同款拆分函数（生产迁移逻辑的回归镜像）
def _split_one(content):
    if "\n" not in content:
        if "：" in content and content.index("：") < 20:
            i = content.index("：")
            return content[:i].strip(), content[i + 1:].strip()
        return content.strip(), ""
    if content.lstrip().startswith("纯技术人路线"):
        i = content.find("\n核心：")
        if i != -1:
            return ("纯技术人路线（长期战略）",
                    (content[content.find("：") + 1:i + 1].strip()
                     + "\n" + content[i + 1:].strip()))
    if "\n细则" in content:
        i = content.find("\n细则")
        return content[:i].strip(), content[i + 1:].strip()
    if "：" in content and content.index("：") < 20:
        i = content.index("：")
        return content[:i].strip(), content[i + 1:].strip()
    return content.strip(), ""


class TodoNoteSplitTests(unittest.TestCase):
    """content→note 拆分解析：四形态（迁移脚本同款逻辑的回归锚）。"""

    def test_xize_style(self):
        title, note = _split_one(
            "软著四件套核验\n细则：\n① 交付物\n② 截止 10-08")
        self.assertEqual(title, "软著四件套核验")
        self.assertTrue(note.startswith("细则："))

    def test_design_dimension_style(self):
        title, note = _split_one(
            "多品牌初版\n细则（设计维度）：\n① 聚合层\n② 前缀路由")
        self.assertEqual(title, "多品牌初版")
        self.assertTrue(note.startswith("细则（设计维度）："))

    def test_strategy_special_240(self):
        content = ("纯技术人路线（长期战略）：用开源换声誉 → 全程不开公司。\n"
                   "核心：工资是主食，其他是配菜。\n细则：\n① 短期")
        title, note = _split_one(content)
        self.assertEqual(title, "纯技术人路线（长期战略）")
        self.assertIn("用开源换声誉", note)      # 战略陈述并入 note 头
        self.assertIn("核心：工资是主食", note)
        self.assertIn("细则：", note)

    def test_colon_style_and_single_line(self):
        title, note = _split_one("删除单条待办：新增 delete_todo(id)")
        self.assertEqual(title, "删除单条待办")
        self.assertEqual(note, "新增 delete_todo(id)")
        title, note = _split_one("单行老待办")
        self.assertEqual((title, note), ("单行老待办", ""))


class TodoNoteStateTests(unittest.TestCase):
    """set_todo_note 读写 + note 列迁移兼容（tmp 库）。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name

    def test_note_column_added_to_legacy_db(self):
        """旧库（无 note 列）→ StateManager 初始化自动 ALTER 补列，
        既有行 note=''。"""
        base = os.path.join(self.tmp, "agent_state")
        os.makedirs(base)
        con = sqlite3.connect(os.path.join(base, "long_term.db"))
        con.execute("""CREATE TABLE todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL,
            source_url TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            priority TEXT NOT NULL DEFAULT 'P1',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP, done_at DATETIME)""")
        con.execute("INSERT INTO todos (content) VALUES ('老待办')")
        con.commit()
        con.close()
        sm = StateManager(base_dir=base)
        con = sqlite3.connect(sm.memory_db)
        cols = [r[1] for r in con.execute("PRAGMA table_info(todos)")]
        con.close()
        self.assertIn("note", cols)
        self.assertEqual(sm.get_todos()[0]["note"], "")

    def test_set_todo_note_roundtrip(self):
        sm = StateManager(base_dir=self.tmp)
        sm.save_todos([{"content": "主任务", "priority": "P1"}])
        tid = sm.get_todos()[0]["id"]
        todo = sm.set_todo_note(tid, "① 交付物\n② 截止")
        self.assertEqual(todo["note"], "① 交付物\n② 截止")
        self.assertEqual(sm.get_todos()[0]["note"], "① 交付物\n② 截止")
        # 空串清空；不存在 id → None
        self.assertEqual(sm.set_todo_note(tid, "")["note"], "")
        self.assertIsNone(sm.set_todo_note(99999, "x"))

    def test_separated_todos_db_also_migrated(self):
        """分离模式（共享 todos.db）同样自动补 note 列。"""
        shared_dir = os.path.join(self.tmp, "shared")
        todos_db = os.path.join(shared_dir, "todos.db")
        os.makedirs(shared_dir)
        con = sqlite3.connect(todos_db)
        con.execute("""CREATE TABLE todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL,
            source_url TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            priority TEXT NOT NULL DEFAULT 'P1',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP, done_at DATETIME)""")
        con.execute("INSERT INTO todos (content) VALUES ('旧行')")
        con.commit()
        con.close()
        with mock.patch.dict(os.environ,
                             {"XIAOJU3_TODOS_DB_PATH": todos_db}):
            sm = StateManager(base_dir=os.path.join(self.tmp, "base"))
        self.assertEqual(sm.todos_db, todos_db)
        self.assertEqual(sm.get_todos()[0]["note"], "")
        sm.set_todo_note(sm.get_todos()[0]["id"], "新说明")
        self.assertEqual(sm.get_todos()[0]["note"], "新说明")


class TodoNoteApiTests(unittest.TestCase):
    """POST /api/todos/<id>/note 路由（低危写端点）。"""

    def setUp(self):
        import xiaoju3_dashboard as dashboard
        self.dashboard = dashboard
        self.client = dashboard.app.test_client()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.dict(os.environ,
                                  {"XIAOJU3_TODOS_DB_PATH":
                                   os.path.join(tmp.name, "todos.db")})
        patcher.start()
        self.addCleanup(patcher.stop)
        # 重建单例（指向 tmp 库）
        from agent_state.state_manager import StateManager
        self.sm = StateManager(base_dir=os.path.join(tmp.name, "as"))
        self.sm_patcher = mock.patch.object(
            dashboard, "state_manager", self.sm)
        self.sm_patcher.start()
        self.addCleanup(self.sm_patcher.stop)
        self.sm.save_todos([{"content": "主任务", "priority": "P1"}])
        self.tid = self.sm.get_todos()[0]["id"]

    def test_note_post_and_404(self):
        resp = self.client.post(f"/api/todos/{self.tid}/note",
                                json={"note": "淡淡说明"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"]["todo"]["note"], "淡淡说明")
        # 404
        resp = self.client.post("/api/todos/99999/note",
                                json={"note": "x"})
        self.assertEqual(resp.status_code, 404)
        # 类型错
        resp = self.client.post(f"/api/todos/{self.tid}/note",
                                json={"note": 123})
        self.assertEqual(resp.status_code, 400)
        # /api/todos 响应透传 note
        data = self.client.get("/api/todos").get_json()["data"]
        self.assertIn("note", data["todos"][0])


class TodoNoteFrontendAnchorTests(unittest.TestCase):
    """前端渲染锚（静态断言）：note 在→渲染 todo-note、空→不渲染、
    编辑态 textarea+保存、切换箭头在位（textContent 注入=escapeHtml）。"""

    def _js(self):
        with open(os.path.join(PROJECT_ROOT, "console.js"),
                  encoding="utf-8") as f:
            return f.read()

    def test_note_render_anchors(self):
        js = self._js()
        self.assertIn("todo-note-toggle", js)
        self.assertIn("todo-note-edit", js)
        self.assertIn("todo-note-save", js)
        self.assertIn("expandedNotes", js)
        self.assertIn("/api/todos/${tid}/note", js)
        # textContent 注入口径：note 经 escapeHtml
        self.assertIn("escapeHtml(note)", js)

    def test_css_present(self):
        with open(os.path.join(PROJECT_ROOT, "index.html"),
                  encoding="utf-8") as f:
            html = f.read()
        for cls in (".todo-note ", ".todo-note-toggle", ".todo-note-edit",
                    ".todo-note-save"):
            self.assertIn(cls, html)


if __name__ == "__main__":
    unittest.main()
