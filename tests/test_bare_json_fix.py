# -*- coding: utf-8 -*-
"""裸 JSON bug 修复锚（2026-10-14 冒烟实锤：QQ 收到裸
{"ui_tap_element":{...}}）。修①=strip_pollution 补工具名键 JSON 剥除；
修②=解析失败幻觉调用诚实兜底。
"""
import chain_of_thought
import brain


# ①-1 冒烟实锤形态：工具名作键嵌套 JSON → 剥除，前后缀保留
def test_toolkey_json_stripped():
    text = ('好的{"ui_tap_element":{"app":"文件管理器",'
            '"path":"/桌面/测试文件"}}请稍等')
    out = chain_of_thought.strip_pollution(text)
    assert "ui_tap_element" not in out
    assert "好的" in out and "请稍等" in out


# ①-2 假工具名（不在注册表）不剥——留给修②诚实兜底/普通旁路
def test_fake_tool_name_not_stripped():
    text = '{"fake_tool":{"a":1}}'
    assert chain_of_thought.strip_pollution(text) == text


# ①-3 正文讨论普通 JSON（键非工具名）不剥（防误伤）
def test_normal_json_discussion_kept():
    text = 'JSON 长这样：{"name": "张三", "age": 30}，是一种数据格式。'
    assert chain_of_thought.strip_pollution(text) == text.strip()


# ②-1 解析失败 + [行动]+注册工具名 → 诚实兜底
def test_hallucinated_call_honest_fallback():
    raw = ('[思考] 需要删除文件。\n[计划] 点击文件管理器。\n'
           '[行动] {"ui_tap_element":{"app":"文件管理器"}}')
    out = brain._hallucinated_tool_reply(raw)
    assert out == brain.HALLUCINATED_TOOL_BODY


# ②-2 冒烟形态（无 [行动]，工具名键 JSON）→ 也判幻觉
def test_toolkey_json_shape_detected():
    out = brain._hallucinated_tool_reply(
        '{"ui_tap_element":{"app":"文件管理器","path":"/桌面/测试文件"}}')
    assert out == brain.HALLUCINATED_TOOL_BODY


# ②-3 不含工具名 → None（原文直出行为不变）
def test_no_tool_name_returns_none():
    assert brain._hallucinated_tool_reply(
        "好的，我已经帮您把文件删除了。") is None
    assert brain._hallucinated_tool_reply(
        '{"name": "张三", "age": 30}') is None


# ②-4 正文讨论工具名（无 [行动] 无 JSON）不误伤
def test_tool_name_discussion_not_flagged():
    assert brain._hallucinated_tool_reply(
        "ui_tap_element 是手机点击工具，通过 UI 解析找元素。") is None


# ②-5 两调用点接线静态锚（smart_ask+stream 均挂幻觉守卫）
def test_hallucination_guard_wired():
    with open("brain.py", encoding="utf-8") as f:
        src = f.read()
    assert src.count("_hallucinated_tool_reply(raw_reply)") >= 2


# ==================== 修 B v2 扩形态（2026-10-14 晚冒烟实锤） ====================
# 19:27 群聊轮：{"action": "get_file_names"} 工具名在"值"不在键——修①/修②
# 原判据（顶层键=注册工具名）双漏，末靠 #322 全剥兜成沉默。扩形态三键。

# ②-v2-1 检测器：action 键值形态 → 诚实兜底（19:27 实锤原样）
def test_v2_action_keyed_json_honest_fallback():
    assert brain._hallucinated_tool_reply(
        '{"action": "get_file_names"}') == brain.HALLUCINATED_TOOL_BODY


# ②-v2-2 检测器：tool / tool_name 键值形态同判
def test_v2_tool_and_tool_name_keyed_detected():
    assert brain._hallucinated_tool_reply(
        '{"tool": "del_file"}') == brain.HALLUCINATED_TOOL_BODY
    assert brain._hallucinated_tool_reply(
        '{"tool_name": "del"}') == brain.HALLUCINATED_TOOL_BODY


# ②-v2-3 防误伤：普通 JSON/纯文本/非字符串值（嵌套结构）不判幻觉
def test_v2_no_false_positive_on_normal_content():
    assert brain._hallucinated_tool_reply('{"weather": "sunny"}') is None
    assert brain._hallucinated_tool_reply('今天天气不错') is None
    assert brain._hallucinated_tool_reply('{"action": {"nested": 1}}') is None


# ①-v2-1 消毒器：整段裸 action JSON（含 think 卡前缀）→ 剥净
def test_v2_whole_text_action_json_stripped():
    out = chain_of_thought.strip_pollution(
        '<think>[思考] x</think>{"action": "get_file_names"}')
    assert out == ""
    assert chain_of_thought.strip_pollution('{"tool": "x"}') == ""


# ①-v2-2 防误伤：行内嵌在自然语言里的讨论原样保留（只剥纯泄漏形态）
def test_v2_inline_discussion_preserved():
    out = chain_of_thought.strip_pollution('看看 {"tool": "x"} 这个格式')
    assert '{"tool": "x"}' in out
