# -*- coding: utf-8 -*-
"""agent_state/plugins/doc_ingest · 知识库摄取插件（#352，Book-to-Skill 一期）。

队长 2026-10-25 视频灵感：扔一本 PDF/文档给小橘 → 切片入库 → 对话检索引用
（RAG 轻量应用，本地优先）。

一期极简口径（克制原则）：
- 解析：pypdf（PDF，主项目既有依赖）+ TXT/MD 直读；
- 存储：SQLite 单文件库（插件数据目录 knowledge.db），**LIKE 扫描检索**
  （一期块数百级毫秒级；FTS5 trigram 对 2 字中文词失效实测，向量库二期）；
- 切块：500 字滑窗（50 字重叠）；
- 检索：ext_search_knowledge(query) → top3 片段（模型可调，对话自动引用）；
- 总结提炼：二期（检索即用已满足"问书内内容"闭环）。

契约 v1.1：PLUGIN 为工厂函数（延迟求值——引用模块内后方函数结构性安全）。
依赖：pypdf（frozen 已收录或 _deps 兜底，ImportError 诚实降级）。
隔离：全部操作 try/except 落 ❌ 串；检索只读；入库幂等（同文档重摄=替换）。
"""
import os  # noqa: E402
import threading  # noqa: E402
import sqlite3  # noqa: E402

_DATA = None      # setup 注入：插件数据目录（knowledge.db 落盘位）
_DB = "knowledge.db"
_CHUNK = 500      # 滑窗块大小（字符）
_OVERLAP = 50     # 重叠（上下文连续性）


def _extract_path(message, _match=None):
    """意图参数抽取：从消息抽第一个本地路径（盘符开头直到空白/中文标点）。"""
    import re
    m = re.search(r"[A-Za-z]:\\[^\s，。！？》】\"\']+", str(message or ""))
    return {"path": m.group(0).rstrip('.')} if m else {}


def _extract_query(message, _match=None):
    """意图参数抽取：检索词=去掉引导词后的整句（模型侧再精炼）。"""
    text = str(message or "").strip()
    for lead in ("帮我查知识库", "查知识库", "检索知识库", "知识库里",
                 "文档里", "书里", "这本书里"):
        if lead in text:
            text = text.split(lead, 1)[1].strip()
            break
    return {"query": text.strip("？?。！，, ")}


def setup(ctx):
    """生命周期钩子：数据目录就位。"""
    global _DATA
    _DATA = os.path.abspath(ctx.get("data_dir") or ".")
    os.makedirs(_DATA, exist_ok=True)
    ctx.get("log")(f"doc_ingest setup：data={_DATA}")


def PLUGIN():
    return {
        "name": "doc_ingest",
        "version": "0.1.0",
        "desc": "知识库摄取（PDF/TXT 切片入库，对话检索引用，Book-to-Skill 一期）",
        "author": "xun",
        "level": 3,
        "tools": [
            {"name": "ext_ingest_document",
             "desc": "把一个本地文档（PDF/TXT/MD）切片存入知识库，之后可以问我"
                     "文档里的内容",
             "params": "path (文档的完整路径，支持 .pdf/.txt/.md)",
             "note": "当主人发来文档路径并说「学一下/摄取/存进知识库」时使用",
             "handler": "agent_state_plugins_doc_ingest:ingest_document"},
            {"name": "ext_search_knowledge",
             "desc": "在已摄取的知识库里检索与问题相关的片段（top3）",
             "params": "query (要查的问题或关键词)",
             "note": "当主人问「我之前存的文档里/知识库里」某内容时使用",
             "handler": "agent_state_plugins_doc_ingest:search_knowledge"},
        ],
        "intents": [
            {"name": "ext_doc_ingest", "desc": "摄取文档进知识库",
             "patterns": [r"(摄取|学一下|学进|存进|收录).{0,45}(知识库|文档|这?本?书|pdf)",   # 45 字窗：路径常夹在动词与宾语之间（真机实测 10 字窗漏）
                          r"(这?本?书|pdf|文档).{0,8}(学|摄取|入库)"],
             "extractor": _extract_path,
             "handler_name": "agent_state_plugins_doc_ingest:ingest_reply"},
            {"name": "ext_doc_search", "desc": "检索知识库",
             "patterns": [r"(知识库|文档|这?本?书).{0,8}(里|中).{0,10}(说|讲|写|提|提到|有没有)",
                          r"(帮我?查|检索).{0,6}(知识库)"],
             "extractor": _extract_query,
             "handler_name": "agent_state_plugins_doc_ingest:search_reply"},
        ],
        "setup": setup,
    }


def _db():
    """知识库连接（幂等建表）。"""
    db = sqlite3.connect(os.path.join(_DATA, _DB))
    db.execute("""CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_title TEXT, doc_path TEXT, chunk_index INTEGER, text TEXT)""")
    db.execute("""CREATE INDEX IF NOT EXISTS idx_doc ON chunks(doc_path)""")
    return db


_MAX_DOC_BYTES = 20 * 1024 * 1024   # 20MB 上限：超大文档同步提取阻塞请求线程（二期异步化前先挡）


def _extract_text(path):
    """按扩展名提取文本（PDF=pypdf 逐页；TXT/MD 直读+编码降级）。

    异常口径（验收纪律 2 补漏 2026-10-25）：加密 PDF/损坏 PDF/图片扫描件/
    超大文件——全部转 RuntimeError 带人话原因，由 ingest_document 统一兜
    ❌ 串，绝不卡死主链。"""
    if os.path.getsize(path) > _MAX_DOC_BYTES:
        raise RuntimeError(
            f"文档过大（{os.path.getsize(path) // 1024 // 1024}MB > 20MB 上限）——"
            "超大文档二期异步化前暂不支持")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        try:
            import pypdf
        except ImportError:
            raise RuntimeError("PDF 解析依赖 pypdf 未安装（运行环境 pip install pypdf）")
        try:
            reader = pypdf.PdfReader(path)
        except Exception as e:
            raise RuntimeError(f"PDF 文件损坏或格式异常：{e}")
        if reader.is_encrypted:
            raise RuntimeError("PDF 已加密（带密码文档暂不支持，请先另存为未加密版本）")
        try:
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:
            raise RuntimeError(f"PDF 页面解析失败：{e}")
    if ext in (".txt", ".md"):
        for enc in ("utf-8", "gbk"):
            try:
                with open(path, encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        raise RuntimeError("文本编码无法识别（试过 UTF-8/GBK）")
    if ext == ".docx":
        return _extract_docx(path)
    if ext == ".xlsx":
        return _extract_xlsx(path)
    raise RuntimeError(
        f"不支持的格式 {ext}（支持 .pdf/.txt/.md/.docx/.xlsx 及代码文本）")


def _extract_docx(path):
    """docx 正文提取（纯 stdlib：docx=zip+XML，零新依赖——python-docx 带
    lxml 体积代价不值）。w:p=段落换行、w:tc=单元格制表，标签全剥、实体还原。"""
    import io
    import re
    import zipfile
    import html as _html
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except zipfile.BadZipFile as e:
        raise RuntimeError(f"docx 文件损坏或格式异常：{e}")
    xml = xml.replace("</w:tc>", "\t").replace("</w:p>", "\n")
    text = _html.unescape(re.sub(r"<[^>]+>", "", xml))
    return text.strip()


def _extract_xlsx(path):
    """xlsx 表格提取（纯 stdlib 同上）：sharedStrings+前 3 个工作表，
    每行单元格制表拼接。容忍内联字符串/空单元格；日期按原始数值吐出。"""
    import zipfile
    from xml.etree import ElementTree as ET
    NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    try:
        with zipfile.ZipFile(path) as z:
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                sroot = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in sroot.findall(f"{NS}si"):
                    shared.append("".join(
                        t.text or "" for t in si.iter(f"{NS}t")))
            out = []
            sheets = sorted(n for n in z.namelist()
                            if n.startswith("xl/worksheets/sheet")
                            and n.endswith(".xml"))[:3]
            for name in sheets:
                out.append(f"【{os.path.basename(name)}】")
                root = ET.fromstring(z.read(name))
                for row in root.iter(f"{NS}row"):
                    cells = []
                    for c in row.findall(f"{NS}c"):
                        v = c.find(f"{NS}v")
                        if c.get("t") == "s" and v is not None:
                            cells.append(shared[int(v.text or "0")])
                        elif v is not None:
                            cells.append(v.text or "")
                        else:
                            is_el = c.find(f"{NS}is")
                            cells.append("".join(
                                t.text or "" for t in is_el.iter(f"{NS}t"))
                                if is_el is not None else "")
                    out.append("\t".join(cells))
            return "\n".join(out).strip()
    except zipfile.BadZipFile as e:
        raise RuntimeError(f"xlsx 文件损坏或格式异常：{e}")


def _chunks(text):
    """滑窗切块：500 字/块、50 字重叠。空块跳过。"""
    text = text.strip()
    out = []
    i = 0
    while i < len(text):
        piece = text[i:i + _CHUNK].strip()
        if piece:
            out.append(piece)
        i += _CHUNK - _OVERLAP
    return out


def ingest_document(path=""):
    """模型工具：文档切片入库（同路径重摄=替换旧块，幂等）。"""
    path = str(path or "").strip().strip('"').strip("'")
    if not path or not os.path.isfile(path):
        return "❌ 文件不存在：请提供完整路径（如 F:\\docs\\报告.pdf）。"
    try:
        text = _extract_text(path)
        pieces = _chunks(text)
        if not pieces:
            return "❌ 文档提取后没有可用文本（可能是扫描件图片 PDF）。"
        db = _db()
        title = os.path.basename(path)
        db.execute("DELETE FROM chunks WHERE doc_path=?", (path,))
        db.executemany(
            "INSERT INTO chunks (doc_title, doc_path, chunk_index, text) VALUES (?,?,?,?)",
            [(title, path, i, p) for i, p in enumerate(pieces)])
        db.commit()
        total = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        db.close()
        _kick_embed_backfill()   # 切片 a：后台补嵌向量（Ollama 不可用=静默下次再试）
        return (f"📚 《{title}》已入库：{len(pieces)} 个知识块"
                f"（库内共 {total} 块）。现在可以直接问它里面的内容了。")
    except Exception as e:
        return f"❌ 摄取失败：{e}"


def search_knowledge(query=""):
    """模型工具：LIKE 检索 top3 片段（模型拿到片段后自行组织回答）。"""
    query = str(query or "").strip()
    if len(query) < 2:
        return "❌ 检索词太短（至少 2 个字）。"
    db = _db()
    rows = db.execute("SELECT doc_title, text FROM chunks").fetchall()
    db.close()
    if not rows:
        return "📭 知识库还是空的。先发文档路径说「摄取」即可入库。"
    terms = [query[i:i + 2] for i in range(0, min(len(query), 12) - 1)]
    scored = []
    for title, text in rows:
        score = sum(1 for t in terms if t in text) + (2 if query in text else 0)
        if score > 0:
            scored.append((score, title, text))
    if not scored:
        return "📭 知识库里没有找到相关内容。"
    scored.sort(reverse=True)
    lines = ["📚 知识库相关片段："]
    for i, (score, title, text) in enumerate(scored[:3], 1):
        lines.append(f"{i}. 【{title}】{text[:200]}{'…' if len(text) > 200 else ''}")
    return "\n".join(lines)


def ingest_reply(path="", **_):
    """意图路由处理器：无路径给用法示例。"""
    if not path:
        return ("⚠️ 想让我学哪个文档？把完整路径发给我，"
                "例如：摄取 F:\\docs\\报告.pdf")
    return ingest_document(path)


def search_reply(query="", **_):
    """意图路由处理器：检索。"""
    return search_knowledge(query)


def teardown():
    """卸载钩子：无后台资源，占位（契约完整）。"""


# ==================== 向量嵌入管线（#352 二期切片 a，2026-10-26） ====================
# Embedding = 本地 Ollama nomic-embed-text（768 维，全本地零 API 费）；向量以
# float32 BLOB 存 chunks.embedding；检索层（切片 b）消费。降级纪律：Ollama/
# 模型不可用 → 后台任务静默退出打日志，下次摄取自动重试——绝不阻塞摄取主链。
_OLLAMA_URL = os.environ.get("XIAOJU3_OLLAMA_URL", "http://localhost:11434")
_EMBED_MODEL = os.environ.get("XIAOJU3_EMBED_MODEL", "nomic-embed-text")
_EMBED_BATCH = 16
_EMBED_ROUND_CAP = 400   # 单轮补嵌上限（防首库大批量长跑；重摄自动续）
_embed_job = {"running": False, "done": 0, "total": 0, "error": ""}


def _ensure_embedding_col(db):
    """chunks 表补 embedding BLOB 列（幂等——已存在则跳过）。"""
    cols = {r[1] for r in db.execute("PRAGMA table_info(chunks)")}
    if "embedding" not in cols:
        db.execute("ALTER TABLE chunks ADD COLUMN embedding BLOB")
        db.commit()


def _pack_vec(vec):
    """float 列表 → float32 BLOB。"""
    import struct
    return struct.pack(f"{len(vec)}f", *[float(x) for x in vec])


def _unpack_vec(blob):
    import struct
    return struct.unpack(f"{len(blob) // 4}f", blob)


def _ollama_embed_batch(texts):
    """批量调 Ollama /api/embed → float32 BLOB 列表。非 200/长度不符皆抛异常。"""
    import requests
    resp = requests.post(
        _OLLAMA_URL.rstrip("/") + "/api/embed",
        json={"model": _EMBED_MODEL, "input": list(texts)}, timeout=300)
    resp.raise_for_status()
    embs = resp.json().get("embeddings") or []
    if len(embs) != len(texts):
        raise RuntimeError(
            f"Ollama 返回 {len(embs)} 条向量，期望 {len(texts)} 条")
    return [_pack_vec(e) for e in embs]


def _embed_backfill_once(db_path=None):
    """同步补嵌一轮（≤_EMBED_ROUND_CAP 块）。返回 (done, left)。
    db_path 可注入（测试隔离）；缺省走 _db() 生产库。"""
    import sqlite3
    db = sqlite3.connect(db_path or _db())
    _ensure_embedding_col(db)
    rows = db.execute(
        "SELECT rowid, text FROM chunks WHERE embedding IS NULL "
        "LIMIT ?", (_EMBED_ROUND_CAP,)).fetchall()
    done = 0
    for rowid, text in rows:
        try:
            blob = _ollama_embed_batch([text])[0]
            db.execute("UPDATE chunks SET embedding=? WHERE rowid=?",
                       (blob, rowid))
            db.commit()
            done += 1
        except Exception as e:
            db.close()
            raise RuntimeError(f"嵌入失败（rowid={rowid}）：{e}") from e
    left = db.execute(
        "SELECT COUNT(*) FROM chunks WHERE embedding IS NULL").fetchone()[0]
    db.close()
    return done, left


def _embed_backfill_thread():
    global _embed_job
    import sqlite3
    _embed_job = {"running": True, "done": 0, "total": 0, "error": ""}
    db = sqlite3.connect(_db())
    _ensure_embedding_col(db)
    _embed_job["total"] = db.execute(
        "SELECT COUNT(*) FROM chunks WHERE embedding IS NULL").fetchone()[0]
    db.close()
    while True:
        try:
            done, left = _embed_backfill_once()
            _embed_job["done"] += done
            _embed_job["total"] = _embed_job["done"] + left
            if left == 0:
                _embed_job["running"] = False
                break
        except Exception as e:
            _embed_job["running"] = False
            _embed_job["error"] = str(e)[:160]
            print(f"[doc_embed] 补嵌中断（下次摄取自动重试）：{e}", flush=True)
            break


def _kick_embed_backfill():
    """非阻塞启动补嵌线程（已在跑则跳过）。"""
    global _embed_job
    if _embed_job.get("running"):
        return
    threading.Thread(target=_embed_backfill_thread, daemon=True).start()
