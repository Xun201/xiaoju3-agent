# -*- coding: utf-8 -*-
"""persona console 修复锚（冒烟实锤驱动：dashboard 两端点不传 user_id
→ mode_suffix uid 空串 → 控制台人格永不生效）。

修法：api_chat / api_chat_stream 调 smart_ask(_stream) 传 user_id="owner"
（控制台=owner 本机语境，与 relationship.tone_prefix 同源兜底）。
"""
import brain


# 1 静态接线：两端点调用行均带 user_id="owner"
def test_dashboard_endpoints_pass_owner_uid():
    with open("xiaoju3_dashboard.py", encoding="utf-8") as f:
        src = f.read()
    assert 'smart_ask(user_msg, history, user_id="owner")' in src
    assert "user_id=\"owner\")   # 控制台=owner 语境" in src


# 2 行为链：user_id="owner" 时 persona 段真注入 system 消息；
#   user_id=None（修复前 console 形态）不含——缺陷对照。
#   表现闸 50 条事件需先种（与生产判定层同门槛）。
def test_console_uid_reaches_persona_segment(tmp_path, monkeypatch):
    db = str(tmp_path / "rel.db")
    monkeypatch.setenv("XIAOJU3_RELATIONSHIP_DB_PATH", db)
    monkeypatch.setenv("XIAOJU3_PERSONA_ENABLED", "1")
    import relationship
    import personality
    conn = relationship._connect()
    with conn:
        for i in range(50):
            conn.execute(
                "INSERT INTO rel_event_log (ts, user_id, event, delta,"
                " affinity_after, note) VALUES (?, 'owner', 'interaction',"
                " 0, 0, 'console-fix-test')",
                (f"2026-10-14 10:{i:02d}:00",))
    conn.close()
    assert personality.set_mode_manual("owner", "banter")
    assert personality._is_expression_ready("owner")

    msgs = brain._build_messages("在干嘛呢", [], user_id="owner")
    assert "【关系模式参数】" in msgs[0]["content"]
    assert "斗嘴型" in msgs[0]["content"]

    msgs_none = brain._build_messages("在干嘛呢", [], user_id=None)
    assert "【关系模式参数】" not in msgs_none[0]["content"]
