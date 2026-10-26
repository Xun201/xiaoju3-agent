# -*- coding: utf-8 -*-
"""知识库文档管理器 + 附件阅后即焚闭环测试（2026-10-26，全部离线）。

覆盖：
- _doc_attach_replace 替换语义（Bug②核心）：stash 空不动作（旧批保留——
  全失败上传时前端芯片还显示着旧批，清了反而制造幽灵态）；非空清旧批+
  清就绪截图+存新批；
- POST /api/knowledge/doc/remount 行为级：原文件在（走 _extract_text 同链，
  source=file）/ 原文件不在（chunks 按 chunk_index 拼回，source=chunks）/
  不在库里 404 / 空路径 400 / 挂载即替换旧批+清截图；
- POST /api/knowledge/doc/delete 行为级：真删（切片+embedding 同行同删）/
  删后库空 / 不在库里 404 / 空路径 400；
- GET /api/plugins 清单增强：docs[] 含 size / ingested_at 键；
- 静态锚：send-btn 初始 disabled+置灰 CSS、console.js init 幽灵态清空两
  fetch、同步置灰桥、管理器浮层 data-act、upload 走 _doc_attach_replace、
  doc_ingest ingested_at 列。

mock 注意：知识库一律临时目录（patch xiaoju3.AGENT_STATE_DIR），全局
_DOC_ATTACH/_SHOT_ATTACH 每用例复位，不污染真实 agent_state。
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import xiaoju3_dashboard as dashboard  # noqa: E402
import xiaoju3 as _x3  # noqa: E402

_DASH_SRC = open(os.path.join(os.path.dirname(__file__), "..",
                              "xiaoju3_dashboard.py"),
                 encoding="utf-8").read()
_JS_SRC = open(os.path.join(os.path.dirname(__file__), "..",
                            "console.js"), encoding="utf-8").read()
_HTML_SRC = open(os.path.join(os.path.dirname(__file__), "..",
                              "index.html"), encoding="utf-8").read()
_PLUGIN_SRC = open(os.path.join(os.path.dirname(__file__), "..",
                                "agent_state", "plugins", "doc_ingest.py"),
                   encoding="utf-8").read()


def _reset_attach_state():
    with dashboard._DOC_ATTACH_LOCK:
        dashboard._DOC_ATTACH["items"] = []
    with dashboard._SHOT_LOCK:
        dashboard._SHOT_ATTACH["path"] = None


class ReplaceSemanticsTests(unittest.TestCase):
    """_doc_attach_replace：替换语义三态（Bug②闭环核心）。"""

    def tearDown(self):
        _reset_attach_state()

    def test_empty_stash_keeps_old(self):
        """stash 空=不动作：旧批与就绪截图都保留（防幽灵态反转）。"""
        _reset_attach_state()
        dashboard._DOC_ATTACH["items"] = [{"name": "旧.txt", "text": "旧内容"}]
        dashboard._SHOT_ATTACH["path"] = r"F:\shot.png"
        stored = dashboard._doc_attach_replace([])
        self.assertEqual(stored, [])
        self.assertEqual(dashboard._DOC_ATTACH["items"],
                         [{"name": "旧.txt", "text": "旧内容"}])
        self.assertEqual(dashboard._SHOT_ATTACH["path"], r"F:\shot.png")

    def test_nonempty_stash_replaces_all(self):
        """非空=清旧批+清截图+存新批（后到为准，与截图互斥同构）。"""
        _reset_attach_state()
        dashboard._DOC_ATTACH["items"] = [{"name": "旧.txt", "text": "旧内容"}]
        dashboard._SHOT_ATTACH["path"] = r"F:\shot.png"
        stored = dashboard._doc_attach_replace([("新.txt", "新内容")])
        self.assertEqual(stored, ["新.txt"])
        self.assertEqual(dashboard._DOC_ATTACH["items"],
                         [{"name": "新.txt", "text": "新内容"}])
        self.assertIsNone(dashboard._SHOT_ATTACH["path"])

    def test_store_truncates_over_total(self):
        """超总量截断：先上传先占坑，第三个文件达到总量上限被丢弃。"""
        _reset_attach_state()
        stored = dashboard._doc_attach_replace(
            [("a.txt", "x" * 2500), ("b.txt", "y" * 2500),
             ("c.txt", "z" * 2500)])
        self.assertEqual(stored, ["a.txt", "b.txt"])
        self.assertEqual(len(dashboard._DOC_ATTACH["items"][0]["text"]), 2500)


class KnowledgeDocApiTests(unittest.TestCase):
    """remount / delete 行为级：临时知识库，不碰真实 agent_state。"""

    def setUp(self):
        _reset_attach_state()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        plugin_dir = os.path.join(self.tmp.name, "plugins", "doc_ingest")
        os.makedirs(plugin_dir)
        self.dbp = os.path.join(plugin_dir, "knowledge.db")
        db = sqlite3.connect(self.dbp)
        db.execute("""CREATE TABLE chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_title TEXT, doc_path TEXT, chunk_index INTEGER,
            text TEXT, embedding BLOB, ingested_at TEXT)""")
        db.commit()
        db.close()
        self.doc_path = os.path.join(self.tmp.name, "书.txt")
        with open(self.doc_path, "w", encoding="utf-8") as f:
            f.write("全文字符" * 100)
        patcher = mock.patch.object(_x3, "AGENT_STATE_DIR", self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = dashboard.app.test_client()

    def _seed(self, path, chunks=("甲段内容", "乙段内容")):
        db = sqlite3.connect(self.dbp)
        db.executemany(
            "INSERT INTO chunks (doc_title, doc_path, chunk_index, text, "
            "ingested_at) VALUES (?,?,?,?,?)",
            [("书.txt", path, i, t, "2026-10-26 21:00")
             for i, t in enumerate(chunks)])
        db.commit()
        db.close()

    def test_remount_from_file(self):
        """原文件在：走 _extract_text 同链，source=file，旧批+截图被替换。"""
        self._seed(self.doc_path)
        dashboard._DOC_ATTACH["items"] = [{"name": "旧.txt", "text": "旧"}]
        dashboard._SHOT_ATTACH["path"] = r"F:\shot.png"
        fake_mod = mock.Mock()
        fake_mod._extract_text = mock.Mock(return_value="  原文件全文  ")
        with mock.patch("plugin_loader.loaded_plugins",
                        return_value={"doc_ingest": {"module": fake_mod}}):
            resp = self.client.post("/api/knowledge/doc/remount",
                                    json={"path": self.doc_path})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["source"], "file")
        self.assertEqual(data["name"], "书.txt")
        items = dashboard._DOC_ATTACH["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "原文件全文")   # strip 后挂载
        self.assertEqual(data["chars"], len("原文件全文"))
        self.assertIsNone(dashboard._SHOT_ATTACH["path"])  # 截图让位

    def test_remount_from_chunks_when_file_gone(self):
        """原文件不在：chunks 按 chunk_index 拼回，source=chunks。"""
        gone = os.path.join(self.tmp.name, "丢了.txt")
        self._seed(gone, chunks=("第一片。", "第二片。", "第三片。"))
        resp = self.client.post("/api/knowledge/doc/remount",
                                json={"path": gone})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(data["source"], "chunks")
        self.assertEqual(dashboard._DOC_ATTACH["items"][0]["text"],
                         "第一片。\n第二片。\n第三片。")

    def test_remount_unknown_path_404(self):
        """不在库里：404 人话。"""
        resp = self.client.post("/api/knowledge/doc/remount",
                                json={"path": r"F:\没有.txt"})
        self.assertEqual(resp.status_code, 404)

    def test_remount_empty_path_400(self):
        resp = self.client.post("/api/knowledge/doc/remount", json={})
        self.assertEqual(resp.status_code, 400)

    def test_delete_removes_chunks_and_vectors(self):
        """删除：切片与 embedding BLOB 同行同删，删后该 path 零残留。"""
        self._seed(self.doc_path)
        db = sqlite3.connect(self.dbp)
        db.execute("UPDATE chunks SET embedding=X'0003' WHERE doc_path=?",
                   (self.doc_path,))
        db.commit()
        db.close()
        resp = self.client.post("/api/knowledge/doc/delete",
                                json={"path": self.doc_path})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"]["chunks"], 2)
        db = sqlite3.connect(self.dbp)
        n = db.execute("SELECT COUNT(*) FROM chunks WHERE doc_path=?",
                       (self.doc_path,)).fetchone()[0]
        db.close()
        self.assertEqual(n, 0)

    def test_delete_unknown_path_404(self):
        resp = self.client.post("/api/knowledge/doc/delete",
                                json={"path": r"F:\没有.txt"})
        self.assertEqual(resp.status_code, 404)

    def test_delete_empty_path_400(self):
        resp = self.client.post("/api/knowledge/doc/delete", json={})
        self.assertEqual(resp.status_code, 400)

    def test_plugins_docs_have_size_and_time_keys(self):
        """清单增强：docs[] 每项含 size / ingested_at 键（缺列库容错）。"""
        self._seed(self.doc_path)
        with mock.patch.dict(os.environ, {}):
            resp = self.client.get("/api/plugins")
        self.assertEqual(resp.status_code, 200)
        ctx = resp.get_json()["data"]["context"]
        docs = ctx.get("docs") or []
        self.assertTrue(docs)
        for d in docs:
            self.assertIn("size", d)
            self.assertIn("ingested_at", d)
            self.assertIn("chunks", d)

    def test_plugins_self_heals_legacy_db_without_time_column(self):
        """schema 自愈：旧库（无 ingested_at 列）清单照常返回，列被补上。"""
        legacy = os.path.join(self.tmp.name, "plugins", "doc_ingest",
                              "legacy.db")
        db = sqlite3.connect(legacy)
        db.execute("""CREATE TABLE chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_title TEXT, doc_path TEXT, chunk_index INTEGER,
            text TEXT, embedding BLOB)""")
        db.execute("INSERT INTO chunks (doc_title, doc_path, chunk_index, "
                   "text) VALUES ('旧书.txt', 'F:\\\\旧书.txt', 0, '旧内容')")
        db.commit()
        db.close()
        # 把清单指向 legacy.db：临时库 knowledge.db 让位（删掉后清单读 legacy）
        os.rename(self.dbp, self.dbp + ".hidden")
        os.rename(legacy, self.dbp)
        self.addCleanup(lambda: os.path.exists(self.dbp)
                        and os.remove(self.dbp))
        resp = self.client.get("/api/plugins")
        self.assertEqual(resp.status_code, 200)
        ctx = resp.get_json()["data"]["context"]
        self.assertEqual(ctx.get("doc_count"), 1)
        self.assertEqual(ctx["docs"][0]["title"], "旧书.txt")
        self.assertEqual(ctx["docs"][0]["ingested_at"], "")   # 旧数据如实空
        db = sqlite3.connect(self.dbp)
        cols = {r[1] for r in db.execute("PRAGMA table_info(chunks)")}
        db.close()
        self.assertIn("ingested_at", cols)   # 自愈补列实锤


class StaticAnchorTests(unittest.TestCase):
    """静态锚：前端置灰联动+幽灵态清空+管理器接线+插件时间列。"""

    def test_sendbtn_initial_disabled_and_css(self):
        self.assertIn('<button id="send-btn" class="send-btn"', _HTML_SRC)
        self.assertIn('.send-btn:disabled', _HTML_SRC)
        self.assertIn('.send-btn:hover:not(:disabled)', _HTML_SRC)

    def test_consolejs_sync_sendbtn_bridge(self):
        self.assertIn('window.__xj3SyncSendBtn = syncSendBtn', _JS_SRC)
        self.assertIn("chatInput.addEventListener('input', syncSendBtn)",
                      _JS_SRC)
        self.assertIn('if (window.__xj3SyncSendBtn) '
                      'window.__xj3SyncSendBtn();', _JS_SRC)

    def test_consolejs_init_clears_ghost_attach(self):
        """页面加载即清后端滞留附件/截图（幽灵态封死——Bug②）。"""
        self.assertIn("fetch('/api/doc_attach/clear', "
                      "{ method: 'POST' }).catch(function () {});", _JS_SRC)
        self.assertIn("fetch('/api/screenshot/clear', "
                      "{ method: 'POST' }).catch(function () {});", _JS_SRC)

    def test_consolejs_manager_wiring(self):
        self.assertIn('data-act="remount"', _JS_SRC)
        self.assertIn('data-act="del-doc"', _JS_SRC)
        self.assertIn("'/api/knowledge/doc/remount'", _JS_SRC)
        self.assertIn("'/api/knowledge/doc/delete'", _JS_SRC)
        self.assertIn("docsCache", _JS_SRC)

    def test_dashboard_upload_uses_replace(self):
        """upload 走替换语义助手（旧批滞留=同书传两次双份的真机雷）。"""
        self.assertIn("def _doc_attach_replace", _DASH_SRC)
        self.assertIn("stored = _doc_attach_replace(stash)", _DASH_SRC)
        self.assertIn('"/api/knowledge/doc/remount"', _DASH_SRC)
        self.assertIn('"/api/knowledge/doc/delete"', _DASH_SRC)
        self.assertIn("MIN(ingested_at)", _DASH_SRC)

    def test_doc_ingest_ingested_at_column(self):
        self.assertIn("def _ensure_ingested_at_col", _PLUGIN_SRC)
        self.assertIn("_ensure_ingested_at_col(db)", _PLUGIN_SRC)
        self.assertIn("doc_title, doc_path, chunk_index, text, ingested_at",
                      _PLUGIN_SRC)


if __name__ == "__main__":
    unittest.main()
