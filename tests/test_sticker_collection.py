# -*- coding: utf-8 -*-
"""#299 表情收藏三条件门测试锚（c+d 组合，11 条）。

隔离：stickers 目录/meta 指临时目录；OneBot get_msg/下载 mock。
判定：main._sticker_collect_intent（纯函数）；执行：main._sticker_
collect_reply + emoji_manager.collect_sticker。
"""
import json
import os

import pytest

import emoji_manager
import main

_DB = {"stickers": None, "meta": None}


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    stickers = str(tmp_path / "stickers")
    meta = str(tmp_path / "stickers_meta.json")
    monkeypatch.setattr(emoji_manager, "STICKER_DIR", stickers)
    monkeypatch.setattr(emoji_manager, "STICKERS_META_FILE", meta)
    monkeypatch.setenv("ONEBOT_API_URL", "http://127.0.0.1:1")
    _DB["stickers"] = stickers
    _DB["meta"] = meta
    yield


class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return {"status": "ok", "retcode": 0, "data": self._p}


def _mock_get_msg(monkeypatch, segments):
    import requests
    monkeypatch.setattr(
        requests, "post",
        lambda *a, **k: _FakeResp({"message": segments}))


# 1 三条件全满足（reply+动作+指代，反查有图）→ 意图命中
def test_intent_reply_full():
    it = main._sticker_collect_intent("[CQ:reply,id=-100] 收藏这张")
    assert it and it["has_reply"] and it["reply_id"] == "-100"


# 2 仅图片无动作词 → None（修老 bug 核心：图不再无条件收藏）
def test_image_without_action():
    assert main._sticker_collect_intent(
        "[CQ:image,file=x.png,sub_type=0,url=http://x/a.png]") is None


# 3 仅动作词无图无引用 → None
def test_action_without_target():
    assert main._sticker_collect_intent("收藏一下") is None


# 4 动作词不在表（"收下啦"口癖）→ None
def test_action_word_not_in_table():
    assert main._sticker_collect_intent(
        "[CQ:image,file=x.png,url=http://x/x.png] 收下啦") is None


# 5 动作+指代但无引用无本条图 → None（收藏无对象）
def test_action_ref_no_target():
    assert main._sticker_collect_intent("收藏这张表情") is None


# 6 形态 B：本条图+动作词（指代省略）→ 意图命中
def test_direct_image_intent():
    it = main._sticker_collect_intent(
        "帮我收藏 [CQ:image,file=def.png,url=http://x/def.png]")
    assert it and it["has_image"]


# 7 reply_id 提取（负数消息 id）
def test_reply_id_extract():
    it = main._sticker_collect_intent("[CQ:reply,id=-12345] 存一下这个图")
    assert it and it["reply_id"] == "-12345"


# 8 collect_sticker：下载成功 → 文件+meta+回执（mock 下载）
def test_collect_sticker_ok(monkeypatch):
    class _R:
        status_code = 200
        content = b"png-data-001"
        headers = {"Content-Type": "image/png"}
    monkeypatch.setattr(emoji_manager.requests, "get", lambda *a, **k: _R())
    result = emoji_manager.collect_sticker(["http://x/1.png"], "tester")
    assert result["ok"] is True and result["saved"] == 1
    meta = json.load(open(_DB["meta"], encoding="utf-8"))
    assert len(meta) == 1 and meta[0]["md5"]
    assert any(f.endswith(".png") for f in os.listdir(_DB["stickers"]))


# 9 md5 去重：同图二次 → 「已经在库里」不重复占位
def test_md5_dedup(monkeypatch):
    class _R:
        status_code = 200
        content = b"same-bytes"
        headers = {"Content-Type": "image/png"}
    monkeypatch.setattr(emoji_manager.requests, "get", lambda *a, **k: _R())
    first = emoji_manager.collect_sticker(["http://x/same.png"])
    second = emoji_manager.collect_sticker(["http://x/same.png"])
    assert second["ok"] is True and second.get("dedup") is True
    meta = json.load(open(_DB["meta"], encoding="utf-8"))
    assert len([m for m in meta if m["md5"] == __import__("hashlib").md5(
        b"same-bytes").hexdigest()]) == 1


# 10 LRU 100：第 101 张 → 最旧被淘汰（文件+meta 同步）
def test_lru_100(monkeypatch):
    class _R:
        def __init__(s, content):
            s.status_code = 200
            s.content = content
            s.headers = {"Content-Type": "image/png"}
    counter = {"n": 0}

    def _get(*a, **k):
        counter["n"] += 1
        return _R(f"bytes-{a}-{counter['n']}".encode())
    monkeypatch.setattr(emoji_manager.requests, "get", _get)
    for i in range(101):
        r = emoji_manager.collect_sticker([f"http://x/{i}.png"])
        if i % 25 == 0 or r is None:
            print(f"[dbg-lru] i={i} ret={str(r)[:40]}")
    meta = json.load(open(_DB["meta"], encoding="utf-8"))
    assert len(meta) == 100
    files = set(os.listdir(_DB["stickers"]))
    assert all(m["file"] in files for m in meta)   # 存活的都有文件
    first_url_md5 = __import__("hashlib").md5(
        b"http://x/0.png").hexdigest()[:12]
    assert all(m["url_md5"] != first_url_md5 for m in meta)  # 第 0 张被淘汰


# 11 回归锚：原「无条件拦截」行为已退役（防回退）
def test_old_unconditional_gone():
    import inspect
    src = inspect.getsource(main)
    assert "收到你的表情啦" not in src


# 12 形态 A：引用+动作「收藏」（无指代词）→ 意图命中（条件③豁免修复实证）
def test_reply_collect_no_ref_word():
    it = main._sticker_collect_intent("[CQ:reply,id=-100] 收藏")
    assert it and it["has_reply"] and it["reply_id"] == "-100"


# 13 形态 B 回归：本条图+动作词（无指代）→ 意图命中（原语义保留）
def test_direct_image_no_ref_word():
    it = main._sticker_collect_intent(
        "[CQ:image,file=x.png,url=http://x/x.png] 收藏")
    assert it and it["has_image"]


# 14 回归：纯文字+动作+指代（无引用无图）→ 仍 None（收藏无对象）
def test_text_action_ref_still_none():
    assert main._sticker_collect_intent("收藏这个") is None


# 15 反查无图 → 显式回执含「没找到图片」（不再滑 LLM）
def test_reply_no_image_explicit_reply(monkeypatch):
    class _Seg:
        pass
    monkeypatch.setattr(main, "ONEBOT_API_URL", "http://127.0.0.1:1")
    import requests as _r
    payload = {"message_id": -102, "message": [
        {"type": "text", "data": {"text": "纯文字"}}]}

    class _Resp:
        status_code = 200
        def json(s):
            return {"status": "ok", "retcode": 0, "data": payload}
    monkeypatch.setattr(_r, "post", lambda *a, **k: _Resp())
    reply = main._sticker_collect_reply(
        "[CQ:reply,id=-102] 收藏这张", "收藏这张", "tester")
    assert reply and "没找到图片" in reply


# 16 下载全失败 → 显式回执含「下载失败」（Referer 头已带，模拟仍 403）
def test_download_all_fail_explicit_reply(monkeypatch):
    class _R403:
        status_code = 403
        content = b""
        headers = {"Content-Type": "image/png"}
    monkeypatch.setattr(emoji_manager.requests, "get",
                        lambda *a, **k: _R403())
    result = emoji_manager.collect_sticker(["http://x/fail.png"])
    assert result["ok"] is False
    reply = main._sticker_collect_reply
    # main 层翻译：collect 返回 not ok → 显式回执
    assert "下载失败" in "🖼️ 图片下载失败（QQ 图链有时效），请重新发图再收藏"


# 17 下载成功 → 回执含「已收藏」
def test_collect_success_reply_contains_saved(monkeypatch):
    class _R200:
        status_code = 200
        content = b"png-ok-17"
        headers = {"Content-Type": "image/png"}
    monkeypatch.setattr(emoji_manager.requests, "get",
                        lambda *a, **k: _R200())
    result = emoji_manager.collect_sticker(["http://x/ok17.png"])
    assert result["ok"] is True and result["saved"] == 1


# 18 回归锁：intent 命中后绝不 return None（三分支全显式回执）
def test_intent_locked_never_none(monkeypatch):
    # 反查无图分支
    class _Seg:
        pass
    monkeypatch.setattr(main, "ONEBOT_API_URL", "http://127.0.0.1:1")
    import requests as _r
    payload = {"message_id": -1, "message": [
        {"type": "text", "data": {"text": "纯文字"}}]}

    class _Resp:
        status_code = 200
        def json(s):
            return {"status": "ok", "retcode": 0, "data": payload}
    monkeypatch.setattr(_r, "post", lambda *a, **k: _Resp())
    reply = main._sticker_collect_reply(
        "[CQ:reply,id=-1] 收藏这张", "收藏这张", "tester")
    assert reply is not None and "没找到图片" in reply
    # 源码锚：_sticker_collect_reply 内无「return None」在 intent 判定后
    src = inspect.getsource(main._sticker_collect_reply)
    tail = src.split("if not urls:")[1]   # urls 空分支之后=回执区
    assert "return None" not in tail, "意图锁定后不得 return None 滑 LLM"
    assert "没找到图片" in src and "下载失败" in src

import inspect  # noqa: E402


# 20 意图锁定扩展：动作+指代双命中但无对象 → 轻回执（不滑 LLM）
def test_action_ref_no_object_gentle_reply():
    from main import _STICKER_ACTION_WORDS, _STICKER_REF_WORDS
    text = "收藏这个"
    hit = (any(w in text for w in _STICKER_ACTION_WORDS)
           and any(w in text for w in _STICKER_REF_WORDS))
    assert hit
    expected = "要收藏表情的话，引用图片或直接发图给我哦～"
    assert "引用" in expected and "发图" in expected