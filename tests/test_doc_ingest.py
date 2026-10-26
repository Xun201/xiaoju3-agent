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


if __name__ == "__main__":
    unittest.main()
