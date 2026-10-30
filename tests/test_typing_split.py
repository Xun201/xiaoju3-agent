# -*- coding: utf-8 -*-
"""打字机分段发送锚（方案 B：分段不逐字，2026-10-14）。

切段纯函数+发送出口契约（顺序/延迟/开关缺省关=单发逐字节一致）。
"""
import pytest

import main


LONG_TEXT = (
    "今天天气不错，适合出门散步。不过我记得你昨天说想在家休息，"
    "所以也没约你，一个人在客厅趴着晒太阳来着。要不要我帮你查查周末的天气？"
    "如果好的话，咱们可以计划一次短途出行，去郊外走走。"
    "顺便说一句，你上次念叨的那家面馆我记着呢，就在老街拐角，"
    "周六人应该不多，去晚了可要排队。尾巴再来一小段凑长度。"
)


# 1 长回复切段：2-3 段、每段 ≥min、非末段以句末标点收尾
def test_long_reply_splits_at_sentence_ends():
    segs = main.split_reply_for_typing(LONG_TEXT)
    assert 2 <= len(segs) <= main.TYPING_MAX_SEGMENTS
    for s in segs:
        assert len(s) >= main.TYPING_MIN_SEGMENT
    for s in segs[:-1]:
        assert s[-1] in main._SENTENCE_END_CHARS
    assert "".join(segs) == LONG_TEXT   # 切段无损（strip 后拼回）


# 2 短回复不切：≤阈值原样单段
def test_short_reply_single_segment():
    segs = main.split_reply_for_typing("在呢，有啥事？")
    assert segs == ["在呢，有啥事？"]


# 3 无自然断点的超长文本：强切不崩，拼回无损
def test_no_punctuation_hard_cut():
    text = "啊" * 250
    segs = main.split_reply_for_typing(text)
    assert 2 <= len(segs) <= main.TYPING_MAX_SEGMENTS
    assert "".join(segs) == text


# 4 尾段碎片并入前段（<min_len 不单独成段）
def test_tiny_tail_merged():
    text = "第一句话在这里结束。第二句话也结束。" + "补充" * 45 + "。尾"
    segs = main.split_reply_for_typing(text)
    assert all(len(s) >= main.TYPING_MIN_SEGMENT for s in segs)


# 5 发送出口：开关开+长回复 → 顺序多段+段间延迟 1-2s（注入 post/sleep）
def test_send_segments_order_and_delays(monkeypatch):
    monkeypatch.setenv("XIAOJU3_CHAT_TYPING", "1")
    posts, sleeps = [], []
    main._send_reply_segments(
        12345, None, LONG_TEXT,
        post=lambda ep, p: posts.append((ep, p)),
        sleep_fn=lambda s: sleeps.append(s))
    assert len(posts) == len(sleeps) + 1          # N 段=N 发、N-1 次延迟
    assert all(ep == "send_private_msg" for ep, _ in posts)
    assert [p["message"] for _, p in posts] == main.split_reply_for_typing(LONG_TEXT)
    assert all(p["user_id"] == 12345 for _, p in posts)
    assert all(1.0 <= s <= 2.0 for s in sleeps)


# 6 开关缺省关：长回复也单发原文、零延迟（行为逐字节一致）
def test_switch_default_off_single_send(monkeypatch):
    monkeypatch.delenv("XIAOJU3_CHAT_TYPING", raising=False)
    posts, sleeps = [], []
    main._send_reply_segments(
        12345, "group-1", LONG_TEXT,
        post=lambda ep, p: posts.append((ep, p)),
        sleep_fn=lambda s: sleeps.append(s))
    assert len(posts) == 1 and sleeps == []
    assert posts[0][0] == "send_group_msg"
    assert posts[0][1] == {"group_id": "group-1", "message": LONG_TEXT}


# 7 群/私端点选择：私聊 user_id payload
def test_private_payload_shape(monkeypatch):
    monkeypatch.setenv("XIAOJU3_CHAT_TYPING", "1")
    posts = []
    main._send_reply_segments(
        12345, None, "第一句。第二句。第三句。第四句。第五句。第六句。" * 3,
        post=lambda ep, p: posts.append((ep, p)), sleep_fn=lambda s: None)
    assert all(p == {"user_id": 12345, "message": p["message"]}
               for _, p in posts)


# 7 回执校验（2026-10-30 #259 老雷根治）：retcode 非 0 → 显式失败日志，
# 不再静默假成功；失败不抛（下条消息不受影响）
def test_send_receipt_failure_logged(monkeypatch, capsys):
    class _BadResp:
        status_code = 200
        def json(self):
            return {"status": "failed", "retcode": 120, "wording": "风控拦截",
                    "data": None}
    main._send_reply_segments(
        12345, None, "短回复",
        post=lambda ep, p: _BadResp(), sleep_fn=lambda s: None)
    out = capsys.readouterr().out
    assert "回执异常" in out and "120" in out and "风控拦截" in out


# 8 回执成功（retcode 0 + message_id）→ 零失败日志
def test_send_receipt_ok_silent(monkeypatch, capsys):
    class _OkResp:
        status_code = 200
        def json(self):
            return {"status": "ok", "retcode": 0,
                    "data": {"message_id": 123}}
    main._send_reply_segments(
        12345, None, "短回复",
        post=lambda ep, p: _OkResp(), sleep_fn=lambda s: None)
    assert "回执异常" not in capsys.readouterr().out
