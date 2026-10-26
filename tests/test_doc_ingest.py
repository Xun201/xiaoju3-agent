# -*- coding: utf-8 -*-
"""doc_ingest 知识库插件异常用例测试（验收纪律 2：边界+异常覆盖）。

隔离策略：真插件源码 copy 进 tmp 外部目录（external_dir patch）+装载，
零碰真实 agent_state/plugins；PDF 相关 mock pypdf（不构造真 PDF 二进制）。
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import plugin_loader

SAMPLE = ("小橘3号知识手册\n\n第一章 能力架构\n小橘3号采用双脑架构：本地小模型"
          "负责快速响应，云端大模型负责复杂推理。\n\n第二章 记忆系统\n记忆分为"
          "情绪记忆、关系记忆与核心记忆三层，情绪记忆采用 PAD 三维模型。")


class DocIngestExceptionTests(unittest.TestCase):
    """异常用例（纪律 2）：加密 PDF/损坏 PDF/超大文件/坏编码/空文本/不存在。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="xj3_docing_")
        self._enter = patch.object(plugin_loader, "external_dir",
                                   lambda: self._tmp)
        self._enter.start()
        # 真插件源码 copy 进 tmp（load_all 前置条件）+清 rejected/装载态
        plugin_loader._loaded.clear()
        plugin_loader._rejected.clear()
        shutil.copy2(os.path.join(PROJECT_ROOT, "agent_state", "plugins",
                                  "doc_ingest.py"),
                     os.path.join(self._tmp, "doc_ingest.py"))
        plugin_loader.load_all()
        self.plugin = plugin_loader.loaded_plugins()["doc_ingest"]
        self.mod = self.plugin["module"]

    def tearDown(self):
        self._enter.stop()
        plugin_loader._loaded.clear()
        plugin_loader._rejected.clear()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write(self, name, content, encoding="utf-8"):
        path = os.path.join(self._tmp, name)
        mode = "wb" if isinstance(content, bytes) else "w"
        with open(path, mode, **({} if mode == "wb" else {"encoding": encoding})) as f:
            f.write(content)
        return path

    def test_txt_ingest_and_search_roundtrip(self):
        """正向闭环：TXT 摄取→检索命中原文片段（正常路径基线）。"""
        p = self._write("手册.txt", SAMPLE)
        out = self.mod.ingest_document(p)
        self.assertIn("已入库", out)
        hit = self.mod.search_knowledge("记忆系统有几层")
        self.assertIn("PAD", hit)          # 原文真实片段命中
        self.assertIn("手册", hit)          # 文档名标注

    def test_missing_file(self):
        """不存在路径 → ❌ 不抛。"""
        out = self.mod.ingest_document(os.path.join(self._tmp, "不存在.txt"))
        self.assertTrue(out.startswith("❌"))

    def test_unsupported_format(self):
        """不支持的扩展名 → ❌ 人话提示（.docx/.xlsx 自 2026-10-26 起支持，
        反例换 .rtf）。"""
        p = self._write("文档.rtf", "内容")
        out = self.mod.ingest_document(p)
        self.assertIn("不支持的格式", out)

    def test_gbk_encoding_fallback(self):
        """GBK 编码 TXT 自动降级读取（utf-8 失败后）。"""
        p = self._write("gbk手册.txt", "这是 GBK 编码的中文内容", encoding="gbk")
        out = self.mod.ingest_document(p)
        self.assertIn("已入库", out)

    def test_undecodable_file(self):
        """双重编码都无法解码 → ❌ 不抛。"""
        p = os.path.join(self._tmp, "乱码.txt")
        with open(p, "wb") as f:
            f.write(b"\xff\xfe\x81\x82 Bad bytes \x99")
        out = self.mod.ingest_document(p)
        self.assertTrue(out.startswith("❌"))

    def test_oversized_file_rejected(self):
        """超过 20MB 上限 → ❌ 人话提示（同步阻塞防护）。"""
        p = self._write("巨大.txt", "x" * 100)   # 真实 20MB 太慢——mock getsize
        with patch("os.path.getsize", return_value=21 * 1024 * 1024):
            out = self.mod.ingest_document(p)
        self.assertIn("20MB 上限", out)

    def test_encrypted_pdf_friendly_error(self):
        """加密 PDF → ❌ 人话提示（is_encrypted 检测，不抛原始异常）。"""
        fake = MagicMock()
        fake.is_encrypted = True
        fake_mod = MagicMock(PdfReader=MagicMock(return_value=fake))
        with patch.dict("sys.modules", {"pypdf": fake_mod}):
            p = self._write("加密.pdf", b"%PDF-1.4 fake")
            out = self.mod.ingest_document(p)
        self.assertIn("已加密", out)

    def test_corrupted_pdf_friendly_error(self):
        """损坏 PDF（PdfReader 构造抛错）→ ❌ 人话提示。"""
        bad = MagicMock(PdfReader=MagicMock(side_effect=Exception("EOF not found")))
        with patch.dict("sys.modules", {"pypdf": bad}):
            p = self._write("坏.pdf", b"not a pdf")
            out = self.mod.ingest_document(p)
        self.assertIn("损坏或格式异常", out)

    def test_image_only_pdf_friendly_error(self):
        """图片扫描件 PDF（extract_text 全空）→ ❌ 提示扫描件（不静默入库空块）。"""
        fake_reader = MagicMock()
        fake_reader.is_encrypted = False
        fake_reader.pages = [MagicMock(extract_text=MagicMock(return_value=""))]
        bad = MagicMock(PdfReader=MagicMock(return_value=fake_reader))
        with patch.dict("sys.modules", {"pypdf": bad}):
            p = self._write("扫描件.pdf", b"%PDF-1.4 fake")
            out = self.mod.ingest_document(p)
        self.assertIn("没有可用文本", out)

    def test_search_empty_db_and_short_query(self):
        """检索边界：空库引导/超短查询提示（不抛）。"""
        self.assertIn("空的", self.mod.search_knowledge("记忆"))
        p = self._write("手册.txt", SAMPLE)
        self.mod.ingest_document(p)
        self.assertIn("太短", self.mod.search_knowledge("记"))     # 1 字

    def test_factory_and_contract(self):
        """契约 v1.1 哨兵：工厂求值+元数据完整（D1 锁级/D2 前缀）。"""
        plugin = self.plugin["plugin"]
        self.assertEqual(plugin["name"], "doc_ingest")
        self.assertLessEqual(plugin["level"], 3)          # D1 外部锁 Lv.3
        for t in plugin["tools"]:
            self.assertTrue(t["name"].startswith("ext_"))  # D2 前缀强制


class DocxXlsxExtractTests(unittest.TestCase):
    """UI 三期新格式（2026-10-26 队长纠偏）：docx/xlsx 纯 stdlib 解析
    （zip+XML 零新依赖——python-docx 带 lxml 体积代价否决）。构造最小
    OOXML 直接验 _extract_text 路由与文本还原。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="xj3_docing_")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "doc_ingest_direct",
            os.path.join(PROJECT_ROOT, "agent_state", "plugins", "doc_ingest.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _make_docx(self, xml_body):
        import zipfile
        path = os.path.join(self._tmp, "t.docx")
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("word/document.xml",
                       '<?xml version="1.0"?><w:document xmlns:w="w">'
                       + xml_body + "</w:document>")
        return path

    def test_docx_paragraphs_and_table(self):
        path = self._make_docx(
            "<w:p><w:r><w:t>第一段：大肥鱼</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>第二段</w:t></w:r></w:p>"
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>记忆持久化</w:t></w:r></w:p>"
            "</w:tc><w:tc><w:p><w:r><w:t>鲜活度</w:t></w:r></w:p></w:tc>"
            "</w:tr></w:tbl>")
        text = self._mod()._extract_text(path)
        self.assertIn("第一段：大肥鱼", text)
        self.assertIn("第二段", text)
        self.assertIn("记忆持久化", text)   # 单元格文本还原（段/制表混排）
        self.assertIn("鲜活度", text)

    def test_docx_entity_unescape(self):
        path = self._make_docx(
            "<w:p><w:r><w:t>A &amp; B &lt;C&gt;</w:t></w:r></w:p>")
        text = self._mod()._extract_text(path)
        self.assertIn("A & B <C>", text)

    def _make_xlsx(self):
        import zipfile
        path = os.path.join(self._tmp, "t.xlsx")
        NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        shared = ('<?xml version="1.0"?><sst xmlns="%s">'
                  '<si><t>名称</t></si><si><t>大肥鱼</t></si></sst>' % NS)
        sheet = ('<?xml version="1.0"?><worksheet xmlns="%s"><sheetData>'
                 '<row r="1"><c r="A1" t="s"><v>0</v></c>'
                 '<c r="B1" t="s"><v>1</v></c></row>'
                 '<row r="2"><c r="A2"><v>42</v></c>'
                 '<c r="B2" t="inlineStr"><is><t>备注</t></is></c></row>'
                 "</sheetData></worksheet>" % NS)
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("xl/sharedStrings.xml", shared)
            z.writestr("xl/worksheets/sheet1.xml", sheet)
        return path

    def test_xlsx_rows_and_shared_strings(self):
        text = self._mod()._extract_text(self._make_xlsx())
        self.assertIn("名称\t大肥鱼", text)      # 共享字符串还原
        self.assertIn("42\t备注", text)          # 数值+内联字符串
        self.assertIn("sheet1.xml", text)        # 表名头

    def test_docx_corrupted_friendly_error(self):
        path = os.path.join(self._tmp, "bad.docx")
        with open(path, "wb") as f:
            f.write(b"not a zip")
        with self.assertRaises(RuntimeError) as cm:
            self._mod()._extract_text(path)
        self.assertIn("损坏", str(cm.exception))


class EmbedPipelineTests(unittest.TestCase):
    """切片 a 嵌入管线（2026-10-26）：embedding 列幂等+BLOB 存取+补嵌消费+
    Ollama 不可用人话降级（mock requests 零真网）。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="xj3_embed_")
        self.mod = self._load_mod()
        import sqlite3
        self.dbp = os.path.join(self._tmp, "knowledge.db")
        self.conn = sqlite3.connect(self.dbp)
        self.conn.execute("""CREATE TABLE chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_title TEXT, doc_path TEXT, chunk_index INTEGER,
            text TEXT, embedding BLOB)""")
        self.conn.execute("INSERT INTO chunks (doc_title, doc_path, "
                          "chunk_index, text) VALUES ('t', 'p', 0, '块0')")
        self.conn.commit()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _load_mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "doc_ingest_embed_test",
            os.path.join(PROJECT_ROOT, "agent_state", "plugins",
                         "doc_ingest.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_ensure_col_idempotent(self):
        self.mod._ensure_embedding_col(self.conn)
        self.mod._ensure_embedding_col(self.conn)   # 二次不炸
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(chunks)")}
        self.assertIn("embedding", cols)

    def test_pack_unpack_roundtrip(self):
        vec = [0.1, -0.25, 3.5]
        blob = self.mod._pack_vec(vec)
        self.assertIsInstance(blob, bytes)
        back = self.mod._unpack_vec(blob)
        for a, b in zip(vec, back):
            self.assertAlmostEqual(a, b, places=5)

    def test_backfill_fills_null_rows(self):
        """3 行 NULL → 补嵌后全落 BLOB（mock _ollama_embed_batch）。"""
        mod = self.mod
        import sqlite3 as sq
        db = sq.connect(self.dbp)
        for i in range(3):
            db.execute("INSERT INTO chunks (doc_title, doc_path, "
                       "chunk_index, text) VALUES ('t', 'p', ?, ?)", (i, f"块{i}"))
        db.commit()
        db.commit()
        db.close()
        with patch.object(mod, "_ollama_embed_batch",
                          lambda texts: [mod._pack_vec([0.5] * 8)
                                         for _ in texts]):
            done, left = mod._embed_backfill_once(self.dbp)
        self.assertEqual(done, 4)   # setUp 1 行 + 本用例 3 行（NULL 全消费）
        db2 = sq.connect(self.dbp)   # 管线内已 close 自身连接——重开查询
        rows = db2.execute("SELECT embedding FROM chunks").fetchall()
        db2.close()
        self.assertTrue(all(r[0] for r in rows))

    def test_ollama_unavailable_friendly_error(self):
        """Ollama 不可用 → 人话 RuntimeError（管线不炸，下次摄取重试）。"""
        mod_ = self._load_mod()
        # _ollama_embed_batch 抛裸异常属设计；人话包装在管线入口
        # _embed_backfill_once——此处验证入口的人话降级
        with patch("requests.post",
                   side_effect=ConnectionError("refused")):
            with self.assertRaises(RuntimeError) as cm:
                mod_._embed_backfill_once(self.dbp)
        self.assertIn("嵌入失败", str(cm.exception))




class HybridSearchTests(unittest.TestCase):
    """切片 b 混合检索（2026-10-26）：向量语义 Top3 + LIKE Top3 去重合并；
    向量链不可用自动降级纯 LIKE（永不比一期差）。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="xj3_hybrid_")
        self.mod = self._load_mod()
        import sqlite3
        self.dbp = os.path.join(self._tmp, "knowledge.db")
        self.conn = sqlite3.connect(self.dbp)
        self.conn.execute("""CREATE TABLE chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_title TEXT, doc_path TEXT, chunk_index INTEGER,
            text TEXT, embedding BLOB)""")
        # 三块语料：A=部署教程（含"部署"）、B=安装手册（含"安装"）、C=天气
        self.vecs = {"A": [1.0, 0.0], "B": [0.9, 0.1], "C": [0.0, 1.0]}
        self.texts = {
            "A": ("部署教程", "生产环境部署需要配置域名与证书，然后重启服务"),
            "B": ("安装手册", "安装前先下载安装包，安装完成后运行安装程序"),
            "C": ("天气记录", "今天天气多云转晴，适合出行")}
        for k, (t, x) in self.texts.items():
            self.conn.execute(
                "INSERT INTO chunks (doc_title, doc_path, chunk_index, text,"
                " embedding) VALUES (?,?,?,?,?)",
                (t, k, 0, x, self.mod._pack_vec(self.vecs[k])))
        self.conn.commit()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _load_mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "doc_ingest_hybrid_test",
            os.path.join(PROJECT_ROOT, "agent_state", "plugins",
                         "doc_ingest.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _set_query_vec(self, vec):
        """patch 查询向量（与 _embed_query 同位——测试注入不出网）。"""
        import struct
        blob = self.mod._pack_vec(vec)
        return patch.object(self.mod, "_embed_query",
                            lambda q: self.mod._unpack_vec(blob))

    def test_vector_ranking_semantic(self):
        """查询向量靠近 A → 语义命中 A 排首位（非字面命中）。"""
        mod = self.mod
        with self._set_query_vec([0.95, 0.05]),                 patch.object(mod, "_DATA", self._tmp):
            hits = mod._vector_top("部署", 3)
        self.assertEqual(hits[0][2], "部署教程")   # 语义最近者第一
        self.assertEqual(hits[1][2], "安装手册")

    def test_fusion_dedup_and_order(self):
        """向量+LIKE 双路命中同一行 → 去重单条、语义优先排前。"""
        mod = self.mod
        with self._set_query_vec([0.95, 0.05]),                 patch.object(mod, "_DATA", self._tmp):
            out = mod.search_knowledge("部署")
        self.assertIn("📚 知识库相关片段", out)
        self.assertIn("部署教程", out)
        self.assertIn("语义", out)

    def test_vector_chain_downgrades_to_like(self):
        """向量链炸（Ollama 挂）→ 自动降级纯 LIKE，输出不空。"""
        mod = self.mod
        def boom(texts):
            raise RuntimeError("Ollama down")
        with patch.object(mod, "_embed_query", side_effect=boom),                 patch.object(mod, "_DATA", self._tmp):
            out = mod.search_knowledge("安装")
        self.assertIn("📚 知识库相关片段", out)
        self.assertIn("安装", out)


if __name__ == "__main__":
    unittest.main()

if __name__ == "__main__":
    unittest.main()
