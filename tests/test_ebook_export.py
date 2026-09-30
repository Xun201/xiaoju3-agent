# -*- coding: utf-8 -*-
"""plugins/ebook_export 单元测试：EPUB 3 生成与会话转章节。

全部离线可跑（纯 stdlib zipfile，无网络无浏览器）：用 zipfile 读回
校验 EPUB 结构（mimetype 首条且未压缩、container/opf/nav 齐备）、
用 xml.etree 解析断言章节 XHTML 良构、中文内容 roundtrip、空章节
拒绝、文件名清洗（防路径注入）。导出目录经 patch _exports_dir
注入 tmp 目录。
"""
import os
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from unittest import mock

from plugins import ebook_export
from plugins.ebook_export import (export_epub, export_from_history,
                                  export_markdown, sanitize_filename)

DC = "http://purl.org/dc/elements/1.1/"
OPF = "http://www.idpf.org/2007/opf"
CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
XHTML = "http://www.w3.org/1999/xhtml"

CHAPTERS = [
    {"title": "第一章 初次见面", "content": "XUN：你好呀。\n小橘3号：主人好！"},
    {"title": "第二章 记账日常", "content": "XUN：帮我记一下账。\n"
                                            "小橘3号：好的，花了多少？"},
]


def make_history(n_messages):
    """构造 n 条 user/assistant 交替的会话历史。"""
    history = []
    for i in range(n_messages):
        role = "user" if i % 2 == 0 else "assistant"
        history.append({"role": role, "content": f"消息{i}"})
    return history


class ExportTestBase(unittest.TestCase):
    """公共夹具：导出目录注入 tmp。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_dir = tmp.name
        patcher = mock.patch.object(ebook_export, "_exports_dir",
                                    return_value=self.tmp_dir)
        patcher.start()
        self.addCleanup(patcher.stop)


class EpubStructureTest(ExportTestBase):
    def setUp(self):
        super().setUp()
        self.path = export_epub("小橘3号对话实录", CHAPTERS)
        self.zf = zipfile.ZipFile(self.path)
        self.addCleanup(self.zf.close)

    def test_output_is_epub_in_exports_dir(self):
        self.assertEqual(os.path.dirname(self.path), self.tmp_dir)
        self.assertTrue(self.path.endswith(".epub"))
        self.assertTrue(os.path.exists(self.path))

    def test_mimetype_is_first_entry_and_uncompressed(self):
        infos = self.zf.infolist()
        self.assertEqual(infos[0].filename, "mimetype")
        self.assertEqual(infos[0].compress_type, zipfile.ZIP_STORED)
        self.assertEqual(self.zf.read("mimetype").decode("utf-8"),
                         "application/epub+zip")

    def test_other_entries_are_compressed(self):
        for info in self.zf.infolist()[1:]:
            self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED,
                             msg=info.filename)

    def test_container_xml_points_to_opf(self):
        root = ET.fromstring(self.zf.read("META-INF/container.xml"))
        rootfile = root.find(f"{{{CONTAINER}}}rootfiles/"
                             f"{{{CONTAINER}}}rootfile")
        self.assertIsNotNone(rootfile)
        self.assertEqual(rootfile.get("full-path"), "OEBPS/content.opf")

    def test_opf_metadata_manifest_spine(self):
        root = ET.fromstring(self.zf.read("OEBPS/content.opf"))
        self.assertEqual(root.tag, f"{{{OPF}}}package")
        self.assertEqual(root.get("version"), "3.0")
        # 元数据：中文书名、语言、修改时间
        self.assertEqual(root.findtext(f".//{{{DC}}}title"), "小橘3号对话实录")
        self.assertEqual(root.findtext(f".//{{{DC}}}language"), "zh-CN")
        self.assertTrue(root.find(f".//{{{OPF}}}meta[@property="
                                  f"'dcterms:modified']") is not None)
        # manifest：nav（properties="nav"）+ 每章一项
        manifest = root.find(f"{{{OPF}}}manifest")
        items = manifest.findall(f"{{{OPF}}}item")
        nav = next(it for it in items if it.get("properties") == "nav")
        self.assertEqual(nav.get("href"), "nav.xhtml")
        self.assertEqual(len(items), 1 + len(CHAPTERS))
        # spine：每章都在阅读顺序里
        spine_ids = {ref.get("idref")
                     for ref in root.findall(f"{{{OPF}}}spine/"
                                             f"{{{OPF}}}itemref")}
        self.assertTrue({"nav"} <= spine_ids)
        self.assertEqual(len(spine_ids), 1 + len(CHAPTERS))

    def test_nav_xhtml_lists_all_chapters(self):
        root = ET.fromstring(self.zf.read("OEBPS/nav.xhtml"))
        hrefs = [a.get("href") for a in root.iter(f"{{{XHTML}}}a")]
        self.assertEqual(hrefs, [f"chapter_{i:03d}.xhtml"
                                 for i in range(1, len(CHAPTERS) + 1)])
        texts = [a.text for a in root.iter(f"{{{XHTML}}}a")]
        self.assertIn("第一章 初次见面", texts)

    def test_each_chapter_is_one_xhtml(self):
        names = [n for n in self.zf.namelist()
                 if n.startswith("OEBPS/chapter_") and n.endswith(".xhtml")]
        self.assertEqual(len(names), len(CHAPTERS))
        for name in names:
            root = ET.fromstring(self.zf.read(name))  # 良构性：解析即断言
            self.assertEqual(root.tag, f"{{{XHTML}}}html")


class ContentRoundtripTest(ExportTestBase):
    def test_chinese_content_survives_escaping(self):
        """中文正文与 XML 特殊字符（< > & 引号）经转义后读回原样。"""
        tricky = "价格<28元> & 记一笔\"午饭\"、'晚饭'"
        path = export_epub("转义《测试》书", [
            {"title": "特殊字符&章节", "content": tricky}])
        with zipfile.ZipFile(path) as zf:
            raw = zf.read("OEBPS/chapter_001.xhtml").decode("utf-8")
            root = ET.fromstring(raw.encode("utf-8"))
        # 原文必须被转义而非裸注入
        self.assertIn("&lt;28元&gt;", raw)
        self.assertIn("&amp;", raw)
        # 解析后的段落文本与原文一致（roundtrip）
        paragraphs = [p.text for p in root.iter(f"{{{XHTML}}}p")]
        self.assertEqual(paragraphs, [tricky])
        # 书名含书名号也能进 OPF
        with zipfile.ZipFile(path) as zf:
            root = ET.fromstring(zf.read("OEBPS/content.opf"))
        self.assertEqual(root.findtext(f".//{{{DC}}}title"), "转义《测试》书")

    def test_multiline_content_becomes_paragraphs(self):
        path = export_epub("分段书", [
            {"title": "章", "content": "第一段\n\n第二段\n第三段"}])
        with zipfile.ZipFile(path) as zf:
            root = ET.fromstring(zf.read("OEBPS/chapter_001.xhtml"))
        paragraphs = [p.text for p in root.iter(f"{{{XHTML}}}p")]
        self.assertEqual(paragraphs, ["第一段", "第二段", "第三段"])

    def test_string_chapters_get_auto_titles(self):
        path = export_epub("字符串章节", ["第一段正文", "第二段正文"])
        with zipfile.ZipFile(path) as zf:
            root = ET.fromstring(zf.read("OEBPS/nav.xhtml"))
        texts = [a.text for a in root.iter(f"{{{XHTML}}}a")]
        self.assertEqual(texts, ["第 1 章", "第 2 章"])


class EmptyRejectTest(ExportTestBase):
    def test_empty_chapter_list_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            export_epub("空书", [])
        self.assertIn("chapters", str(ctx.exception))
        with self.assertRaises(ValueError):
            export_epub("空书", None)

    def test_empty_content_chapter_rejected(self):
        for bad in ({"title": "空章", "content": ""},
                    {"title": "空白章", "content": "  \n "},
                    "   "):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError) as ctx:
                    export_epub("坏书", [CHAPTERS[0], bad])
                self.assertIn("空章节", str(ctx.exception))

    def test_empty_title_rejected(self):
        for bad_title in ("", "   ", None):
            with self.subTest(bad_title=bad_title):
                with self.assertRaises(ValueError) as ctx:
                    export_epub(bad_title, CHAPTERS)
                self.assertIn("书名", str(ctx.exception))


class FilenameSanitizeTest(ExportTestBase):
    def test_illegal_characters_cleaned_in_default_path(self):
        nasty_title = '坏/名字\\:第*一?章"引号<大于>|竖线'
        path = export_epub(nasty_title, CHAPTERS)
        basename = os.path.basename(path)
        # 落盘位置仍在注入的导出目录内，未被标题带偏
        self.assertEqual(os.path.dirname(path), self.tmp_dir)
        for ch in '\\/:*?"<>|':
            self.assertNotIn(ch, basename)
        self.assertTrue(os.path.exists(path))

    def test_dot_traversal_and_punct_name_cleaned(self):
        for title in ("../../etc/passwd", "..\\..\\windows", "。．."):
            with self.subTest(title=title):
                path = export_epub(title, CHAPTERS)
                basename = os.path.basename(path)
                self.assertNotIn("..", basename)
                self.assertTrue(os.path.exists(path))

    def test_windows_reserved_name_prefixed(self):
        path = export_epub("CON", CHAPTERS)
        self.assertTrue(os.path.basename(path).startswith("_CON"))

    def test_explicit_out_path_respected(self):
        target = os.path.join(self.tmp_dir, "自定义.epub")
        path = export_epub("任意书名", CHAPTERS, out_path=target)
        self.assertEqual(path, os.path.abspath(target))
        self.assertTrue(os.path.exists(target))

    def test_no_tmp_residue_after_write(self):
        export_epub("干净落盘", CHAPTERS)
        leftovers = [n for n in os.listdir(self.tmp_dir)
                     if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])


class FromHistoryTest(ExportTestBase):
    def test_split_every_ten_messages(self):
        chapters = export_from_history(make_history(23))
        self.assertEqual([len(c["content"].splitlines())
                          for c in chapters], [10, 10, 3])
        self.assertEqual([c["title"] for c in chapters],
                         ["第 1 章", "第 2 章", "第 3 章"])

    def test_system_and_empty_messages_excluded(self):
        history = [{"role": "system", "content": "系统提示词"},
                   {"role": "user", "content": "你好"},
                   {"role": "assistant", "content": "   "},
                   {"role": "user", "content": "在吗"},
                   "不是字典的消息",
                   {"role": "tool", "content": "工具消息"}]
        chapters = export_from_history(history)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]["content"].splitlines(),
                         ["XUN：你好", "XUN：在吗"])

    def test_roles_rendered_as_names(self):
        chapters = export_from_history([
            {"role": "user", "content": "谁在说话"},
            {"role": "assistant", "content": "我是小橘3号"}])
        self.assertEqual(chapters[0]["content"],
                         "XUN：谁在说话\n小橘3号：我是小橘3号")

    def test_empty_history_gives_no_chapters(self):
        self.assertEqual(export_from_history([]), [])
        self.assertEqual(export_from_history(None), [])

    def test_history_to_epub_end_to_end(self):
        """会话 → 章节 → EPUB → zip 读回，中文标题正文完整。"""
        history = make_history(25)
        chapters = export_from_history(history, title="九月对话")
        path = export_epub("九月对话", chapters)
        with zipfile.ZipFile(path) as zf:
            root = ET.fromstring(zf.read("OEBPS/content.opf"))
            chapter_root = ET.fromstring(zf.read("OEBPS/chapter_001.xhtml"))
        self.assertEqual(root.findtext(f".//{{{DC}}}title"), "九月对话")
        body_text = "".join(p.text or ""
                            for p in chapter_root.iter(f"{{{XHTML}}}p"))
        self.assertIn("消息0", body_text)
        self.assertIn("消息9", body_text)
        self.assertNotIn("消息10", body_text)  # 第 10 条起归第二章


class MarkdownExportTest(ExportTestBase):
    def test_markdown_roundtrip(self):
        path = export_markdown("小橘3号周记", CHAPTERS)
        self.assertTrue(path.endswith(".md"))
        self.assertEqual(os.path.dirname(path), self.tmp_dir)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("# 小橘3号周记", content)
        self.assertIn("## 第一章 初次见面", content)
        self.assertIn("XUN：你好呀。", content)

    def test_markdown_rejects_empty_chapters(self):
        with self.assertRaises(ValueError):
            export_markdown("空书", [])

    def test_markdown_filename_sanitized(self):
        path = export_markdown('坏/名\\:字', CHAPTERS)
        basename = os.path.basename(path)
        for ch in '\\/:*?"<>|':
            self.assertNotIn(ch, basename)
        self.assertTrue(os.path.exists(path))


class ModuleHygieneTest(unittest.TestCase):
    def test_sanitize_filename_fallback_and_lexical_clean(self):
        # 纯非法字符被逐字替换（不触发 fallback），锁定真实口径
        self.assertEqual(sanitize_filename("///"), "___")
        # 清洗后为空（如全空白）才回退 fallback
        self.assertEqual(sanitize_filename("   ", fallback="book"), "book")
        self.assertTrue(sanitize_filename("正常书名").startswith("正常书名"))

    def test_chapter_size_constant_documented(self):
        # 分章口径锁定：每 10 条消息一章（与 docstring 说明一致）
        self.assertEqual(ebook_export.CHAPTER_SIZE, 10)


if __name__ == "__main__":
    unittest.main()
