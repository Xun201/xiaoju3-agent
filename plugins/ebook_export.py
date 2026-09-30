# -*- coding: utf-8 -*-
"""小橘3号 · 电子书导出插件（功能文档 §7："把这段对话导出成电子书"）。

EPUB 3 生成用纯标准库 zipfile（零新依赖，开发日志第十章 EPUB 口径）：
- mimetype 必须是 zip 首条目且不压缩（ZIP_STORED，EPUB 规范硬性要求）；
- META-INF/container.xml 指向 OEBPS/content.opf；
- OEBPS/content.opf（EPUB 3 包描述：元数据 + manifest + spine）；
- OEBPS/nav.xhtml（EPUB 3 导航目录，properties="nav"）；
- 每章一个 XHTML（OEBPS/chapter_NNN.xhtml），中文标题/正文 UTF-8。

对外接口（供 intent_router 意图表以 "plugins.ebook_export:函数名"
延迟字符串引用，S5 接线零成本）：
- export_epub(title, chapters, out_path=None) -> str（返回落盘路径）
- export_from_history(history, title="小橘3号对话导出") -> list[dict]
- export_markdown(title, chapters, out_path=None) -> str（附赠 md 兜底）

chapters 统一为 [{"title": str, "content": str}]，content 为纯文本
（按换行分段）；也兼容直接传字符串章节（标题自动编为"第 N 章"）。
空书名 / 空章节 / 空内容一律 ValueError 拒绝（中文报错）。
out_path 缺省落 agent_state/exports/书名-时间戳.epub，书名中的非法
文件名字符（/ \\ : * ? " < > | 等）自动清洗，防路径注入。
import 零副作用，可独立离线单测（out_path 显式注入 tmp 目录）。
"""
import html
import os
import re
import zipfile
from datetime import datetime, timezone
from uuid import uuid4

from xiaoju3 import AGENT_STATE_DIR

# 导出目录：缺省落 agent_state/exports/（.gitignore 需求已报主控）
EXPORTS_SUBDIR = "exports"

# 对话分章口径：每 10 条消息一章
CHAPTER_SIZE = 10

# Windows 文件名非法字符 + 控制字符
_FILENAME_INVALID = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

# Windows 保留设备名（不区分大小写），作文件名时需加前缀
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _exports_dir():
    """导出目录：agent_state/exports/（独立成函数便于单测注入 tmp）。"""
    return os.path.join(AGENT_STATE_DIR, EXPORTS_SUBDIR)


def sanitize_filename(name, fallback="book"):
    """清洗文件名：非法字符替换为 _，去掉首尾空白与点，防 .. 逃逸与
    Windows 保留名；清洗后为空则回退 fallback。"""
    cleaned = _FILENAME_INVALID.sub("_", str(name))
    cleaned = cleaned.replace("..", "_").strip(" .\t\n")
    if cleaned.upper() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    if not cleaned:
        cleaned = fallback
    return cleaned[:50]  # 控制长度，避免超长文件名


def _stamp():
    """时间戳后缀：20260930-142530 形态。"""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _normalize_chapters(chapters):
    """章节归一与校验：空列表 / 空内容章节一律 ValueError（中文报错）。

    兼容字符串章节（标题自动"第 N 章"）；返回 [{"title", "content"}]。
    """
    if not chapters or not isinstance(chapters, (list, tuple)):
        raise ValueError("没有可导出的章节内容：chapters 不能为空。")
    normalized = []
    for i, ch in enumerate(chapters):
        if isinstance(ch, dict):
            title = str(ch.get("title") or f"第 {i + 1} 章").strip()
            content = str(ch.get("content") or "").strip()
        else:
            title = f"第 {i + 1} 章"
            content = str(ch or "").strip()
        if not content:
            raise ValueError(f"第 {i + 1} 章内容为空：拒绝导出空章节。")
        normalized.append({"title": title or f"第 {i + 1} 章",
                           "content": content})
    return normalized


def _normalize_title(title):
    title = str(title or "").strip()
    if not title:
        raise ValueError("书名不能为空。")
    return title


_XHTML_HEAD = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<!DOCTYPE html>\n'
               '<html xmlns="http://www.w3.org/1999/xhtml" '
               'lang="zh-CN" xml:lang="zh-CN">\n')


def _chapter_xhtml(title, content):
    """单章 XHTML：正文按换行拆段（空行丢弃），HTML 实体转义防注入。"""
    paragraphs = "".join(
        f"  <p>{html.escape(line)}</p>\n"
        for line in content.splitlines() if line.strip()
    )
    esc_title = html.escape(title)
    return (f"{_XHTML_HEAD}"
            f"<head>\n  <meta charset=\"utf-8\"/>\n"
            f"  <title>{esc_title}</title>\n</head>\n"
            f"<body>\n  <h1>{esc_title}</h1>\n{paragraphs}</body>\n</html>\n")


def _write_epub_entries(zf, title, chapters):
    """按 EPUB 3 规范顺序写入各条目（mimetype 必须首条且不压缩）。"""
    # 1) mimetype：首条目 + ZIP_STORED（EPUB 规范：不得压缩、必须最先）
    zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                compress_type=zipfile.ZIP_STORED)

    # 2) META-INF/container.xml：指向包描述文件
    zf.writestr("META-INF/container.xml",
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<container version="1.0" '
                'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                '  <rootfiles>\n'
                '    <rootfile full-path="OEBPS/content.opf" '
                'media-type="application/oebps-package+xml"/>\n'
                '  </rootfiles>\n'
                '</container>\n')

    # 3) 每章一个 XHTML
    chapter_names = []
    for i, ch in enumerate(chapters, 1):
        name = f"OEBPS/chapter_{i:03d}.xhtml"
        chapter_names.append((name, ch["title"]))
        zf.writestr(name, _chapter_xhtml(ch["title"], ch["content"]))

    # 4) OEBPS/nav.xhtml：EPUB 3 导航目录（properties="nav"）
    toc_items = "".join(
        f'      <li><a href="{name.rsplit("/", 1)[-1]}">'
        f'{html.escape(t)}</a></li>\n'
        for name, t in chapter_names)
    zf.writestr("OEBPS/nav.xhtml",
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE html>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml" '
                'xmlns:epub="http://www.idpf.org/2007/ops" '
                'lang="zh-CN" xml:lang="zh-CN">\n'
                '<head>\n  <meta charset="utf-8"/>\n  <title>目录</title>\n'
                '</head>\n<body>\n'
                '  <nav epub:type="toc" id="toc">\n    <h1>目录</h1>\n'
                '    <ol>\n'
                f'{toc_items}'
                '    </ol>\n  </nav>\n</body>\n</html>\n')

    # 5) OEBPS/content.opf：包描述（EPUB 3 元数据 + manifest + spine）
    manifest = "".join(
        f'    <item id="ch{i}" href="chapter_{i:03d}.xhtml" '
        f'media-type="application/xhtml+xml"/>\n'
        for i in range(1, len(chapters) + 1))
    spine = "".join(
        f'    <itemref idref="ch{i}"/>\n'
        for i in range(1, len(chapters) + 1))
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    zf.writestr("OEBPS/content.opf",
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<package xmlns="http://www.idpf.org/2007/opf" '
                'version="3.0" unique-identifier="bookid">\n'
                '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
                f'    <dc:identifier id="bookid">urn:uuid:{uuid4()}</dc:identifier>\n'
                f'    <dc:title>{html.escape(title)}</dc:title>\n'
                '    <dc:language>zh-CN</dc:language>\n'
                f'    <meta property="dcterms:modified">{modified}</meta>\n'
                '  </metadata>\n'
                '  <manifest>\n'
                '    <item id="nav" href="nav.xhtml" '
                'media-type="application/xhtml+xml" properties="nav"/>\n'
                f'{manifest}'
                '  </manifest>\n'
                '  <spine>\n'
                '    <itemref idref="nav"/>\n'
                f'{spine}'
                '  </spine>\n'
                '</package>\n')


def export_epub(title, chapters, out_path=None):
    """生成 EPUB 3 电子书，返回落盘路径（str）。

    - chapters：[{"title", "content"}] 或字符串列表，空列表/空章节拒绝；
    - out_path：缺省落 exports 目录，文件名为清洗后的书名-时间戳.epub；
    - 原子写：先写 .tmp 再 os.replace，失败不留半成品文件。
    """
    title = _normalize_title(title)
    chapters = _normalize_chapters(chapters)
    if out_path is None:
        out_path = os.path.join(
            _exports_dir(),
            f"{sanitize_filename(title)}-{_stamp()}.epub")
    out_path = os.path.abspath(out_path)
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_path = f"{out_path}.tmp"
    try:
        # 其余条目 deflate 压缩；mimetype 单独指定 ZIP_STORED（规范要求）
        with zipfile.ZipFile(tmp_path, "w",
                             compression=zipfile.ZIP_DEFLATED) as zf:
            _write_epub_entries(zf, title, chapters)
        os.replace(tmp_path, out_path)
    finally:
        # 成功 replace 后 tmp 已不存在；失败时清理半成品，不留残骸
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
    return out_path


def export_from_history(history, title="小橘3号对话导出"):
    """把 [{role, content}] 会话历史转为章节列表（不落盘，交给导出函数）。

    分章口径：按每 CHAPTER_SIZE=10 条消息固定切一章。之所以不用"按用户
    消息切章"：会话历史角色分布不均（存在系统消息、连续用户消息、被 50 条
    截断的半轮对话），按用户消息切会产生空章或体量悬殊的超大章；固定 10 条
    切分保证每章体量均匀、章节编号稳定可复现。
    system 消息与空内容消息不进书。
    """
    msgs = []
    for m in history or []:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = str(m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            msgs.append((role, content))
    chapters = []
    for i in range(0, len(msgs), CHAPTER_SIZE):
        chunk = msgs[i:i + CHAPTER_SIZE]
        lines = [f"{'用户' if role == 'user' else '小橘3号'}：{content}"
                 for role, content in chunk]
        chapters.append({"title": f"第 {i // CHAPTER_SIZE + 1} 章",
                         "content": "\n".join(lines)})
    return chapters


def export_markdown(title, chapters, out_path=None):
    """附赠 Markdown 版（EPUB 阅读器不可用时的兜底），返回落盘路径。"""
    title = _normalize_title(title)
    chapters = _normalize_chapters(chapters)
    if out_path is None:
        out_path = os.path.join(
            _exports_dir(),
            f"{sanitize_filename(title)}-{_stamp()}.md")
    out_path = os.path.abspath(out_path)
    parent = os.path.dirname(out_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    parts = [f"# {title}", ""]
    for ch in chapters:
        parts.append(f"## {ch['title']}")
        parts.append("")
        parts.append(ch["content"])
        parts.append("")
    tmp_path = f"{out_path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))
        os.replace(tmp_path, out_path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
    return out_path
