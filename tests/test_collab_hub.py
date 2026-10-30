# -*- coding: utf-8 -*-
"""AI 协作总线测试（2026-10-30 Multi-Agent UI 批）。

覆盖（临时目录零联网）：
- CollabHub 增量解析：SYNC 变化→zcode 消息；TASK_BUS [秘书回复]/[老板拍板]
  新节→secretary/boss 消息；签名去重（同节不重放）；
- HITL：@老板 → hitl=True；
- emit_boss：写 TASK_BUS [老板拍板] 节 + 入 history；
- snapshot 截断与顺序；
- 联网门：XIAOJU3_BUS_ENABLED≠1 → _auto_secretary 零调用（黑名单/日帽同源
  ai_bus_daemon 已验，此处只锚门）。
"""
import importlib.util
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location(
    "collab_hub", os.path.join(ROOT, "collab_hub.py"))
collab_hub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collab_hub)


def _hub(tmp):
    return collab_hub.CollabHub(
        sync_path=os.path.join(tmp, "SYNC.md"),
        task_path=os.path.join(tmp, "TASK_BUS.md"),
        env={"XIAOJU3_BUS_ENABLED": "0"})


class CollabHubTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xj3_collab_")
        self.hub = _hub(self.tmp)

    def _w(self, name, text):
        with open(os.path.join(self.tmp, name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_sync_change_emits_zcode(self):
        self._w("SYNC.md", "# SYNC 头部导航\n")
        self.hub.poll_once()   # 首轮入基线
        self._w("SYNC.md", "# SYNC 头部导航\n\n## 最新状态\n修复了发送回执校验" * 3)
        n = self.hub.poll_once()
        self.assertGreaterEqual(n, 1)
        roles = [m["role"] for m in self.hub.snapshot()]
        self.assertIn("zcode", roles)

    def test_task_bus_new_sections_parsed_once(self):
        self._w("TASK_BUS.md", "# TASK_BUS\n")
        self.hub.poll_once()
        self._w("TASK_BUS.md",
                "# TASK_BUS\n\n## [秘书回复] 2026-10-30 11:00\n\n- 结论甲\n\n---\n"
                "\n## [老板拍板] 2026-10-30 11:05\n\n同意方案 A\n\n---\n")
        self.hub.poll_once()
        roles = sorted(m["role"] for m in self.hub.snapshot())
        self.assertIn("secretary", roles)
        self.assertIn("boss", roles)
        # 同节重放：再 poll 不产生新消息（签名去重）
        before = len(self.hub.snapshot())
        self.hub.poll_once()
        self.assertEqual(len(self.hub.snapshot()), before)

    def test_hitl_flag_on_at_boss(self):
        self.hub._emit("secretary", "方案 A 已就绪，@老板 请确认方案 A")
        last = self.hub.snapshot()[-1]
        self.assertTrue(last["hitl"])
        self.hub._emit("secretary", "普通结论无确认诉求")
        self.assertFalse(self.hub.snapshot()[-1]["hitl"])

    def test_emit_boss_writes_task_bus_and_history(self):
        path = os.path.join(self.tmp, "TASK_BUS.md")
        r = self.hub.emit_boss("拍板：采用方案 A")
        self.assertEqual(r["code"], 200)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn(collab_hub.BOSS_TAG, content)
        self.assertIn("拍板：采用方案 A", content)
        self.assertEqual(self.hub.snapshot()[-1]["role"], "boss")

    def test_emit_boss_empty_400(self):
        self.assertEqual(self.hub.emit_boss("  ")["code"], 400)

    def test_snapshot_limit(self):
        for i in range(30):
            self.hub._emit("zcode", f"msg-{i}")
        snap = self.hub.snapshot(10)
        self.assertEqual(len(snap), 10)
        self.assertEqual(snap[-1]["text"], "msg-29")   # 新在后

    def test_auto_secretary_gate_off(self):
        """联网门：开关≠1 → 零调用（不写秘书节）。"""
        self._w("TASK_BUS.md", "# TASK_BUS\n")   # 预建（门关时不写文件）
        self._w("SYNC.md", "初始")
        self.hub.poll_once()
        self._w("SYNC.md", "初始\n\n## 最新状态\n" + "较长的新战报内容，" * 20)
        self.hub.poll_once()
        zcode_msgs = [m for m in self.hub.snapshot() if m["role"] == "zcode"]
        self.assertGreaterEqual(len(zcode_msgs), 1)   # zcode 消息照常
        with open(os.path.join(self.tmp, "TASK_BUS.md"), encoding="utf-8") as f:
            self.assertNotIn(collab_hub.SECRET_TAG, f.read())   # 联网门关=零秘书节


class HitlOptionsTests(unittest.TestCase):
    """HITL 升级锚（2026-10-30 队长拍板）：options/@summary 解析+剥离。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xj3_hitl_")
        self.hub = _hub(self.tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_options_line_parsed_and_stripped(self):
        self.hub._emit(
            "secretary",
            "两个方向请定夺\n@options: 启动M2多端联动|优先修APK|暂缓"
            "\n@summary: 当前有两条路线，请老板指示\n@老板 请拍板")
        last = self.hub.snapshot()[-1]
        self.assertTrue(last["hitl"])
        self.assertEqual(last["options"],
                         ["启动M2多端联动", "优先修APK", "暂缓"])
        self.assertEqual(last["summary"], "当前有两条路线，请老板指示")
        self.assertNotIn("@options", last["text"])   # 协议行从正文剥离
        self.assertNotIn("@summary", last["text"])

    def test_no_options_line_no_field(self):
        self.hub._emit("secretary", "普通消息 @老板 看一眼")
        last = self.hub.snapshot()[-1]
        self.assertTrue(last["hitl"])
        self.assertIsNone(last.get("options"))
        self.assertIsNone(last.get("summary"))

    def test_options_capped_at_six(self):
        self.hub._emit("secretary",
                       "@老板 选一个\n@options: a|b|c|d|e|f|g|h")
        self.assertEqual(len(self.hub.snapshot()[-1]["options"]), 6)
        self.assertEqual(len(self.hub.snapshot()[-1]["options"]), 6)


class ProtocolEdgeTests(unittest.TestCase):
    """秘书回执①：协议行边界收严——围栏免疫/正文中段不解析/整行锚定/
    列表前缀与加粗不认/选项截断。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xj3_proto_")
        self.hub = _hub(self.tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_code_fence_immunity(self):
        fence = "```"
        text = ("正文说明\n" + fence + "\n@options: 假选项A|假选项B\n"
                "@summary: 假摘要\n" + fence + "\n@老板 请看上面的示例代码")
        clean, opts, summ, hitl = collab_hub.parse_protocol_lines(text)
        self.assertTrue(hitl)
        self.assertIsNone(opts)      # 围栏内协议样文本零误伤
        self.assertIsNone(summ)
        self.assertIn("@options", clean)   # 围栏内容原样保留

    def test_mid_body_not_parsed(self):
        # 协议行放 index 3（7 行文本的中段：3 <= idx < 4 之外皆合法区）
        lines = ["开头行", "中间说明一", "中间说明二",
                 "@options: 中段伪协议", "中间说明三", "中间说明四",
                 "@老板 结尾"]
        text = "\n".join(lines)
        clean, opts, summ, hitl = collab_hub.parse_protocol_lines(text)
        self.assertTrue(hitl)
        self.assertIsNone(opts)      # 正文中段（>3 行）永不解析
        self.assertIn("@options: 中段伪协议", clean)

    def test_head_and_tail_parsed(self):
        lines = ["@summary: 头部摘要", "@老板 开头确认", "正文中间随便写",
                 "再一行", "@options: 选项甲|选项乙", "@老板 尾部确认"]
        clean, opts, summ, hitl = collab_hub.parse_protocol_lines("\n".join(lines))
        self.assertEqual(opts, ["选项甲", "选项乙"])
        self.assertEqual(summ, "头部摘要")

    def test_list_prefix_and_bold_not_matched(self):
        lines = ["- @options: 列表前缀伪协议", "**@options:** 加粗伪协议",
                 "@老板 正文"]
        clean, opts, summ, hitl = collab_hub.parse_protocol_lines("\n".join(lines))
        self.assertTrue(hitl)
        self.assertIsNone(opts)      # 列表前缀/加粗形态不认
        self.assertIn("- @options:", clean)
        self.assertIn("**@options:**", clean)

    def test_option_truncated_at_30(self):
        long_opt = "超长选项" * 10
        text = "@老板 请选\n@options: " + long_opt + "|短项"
        clean, opts, summ, hitl = collab_hub.parse_protocol_lines(text)
        self.assertEqual(len(opts[0]), 30)
        self.assertEqual(opts[1], "短项")

    def test_fullwidth_colon_accepted(self):
        text = "@老板 请拍板\n@options：全角冒号选项"
        clean, opts, summ, hitl = collab_hub.parse_protocol_lines(text)
        self.assertEqual(opts, ["全角冒号选项"])


if __name__ == "__main__":
    unittest.main()


class DeepSeekReviewAdoptionTests(unittest.TestCase):
    """MCP 实战演练（2026-10-30）：DeepSeek 审查 parse_protocol_lines 的
    5 项采纳修复回归——①uuid 占位防伪造 ②短文本窗口显式判定 ③首尾空行
    裁剪 ④hitl 围栏免疫 ⑤多协议行取首个+正文原样（无全局空行压缩）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xj3_rev_")
        self.hub = _hub(self.tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_short_text_protocol_still_parsed(self):
        """DeepSeek 意见②：n≤6 短文本旧 lo/hi 区间恒空=全漏判——v2 显式判定修复。"""
        clean, opts, summ, hitl = collab_hub.parse_protocol_lines(
            "@summary: 短消息摘要\n@老板 请确认")
        self.assertEqual(summ, "短消息摘要")
        self.assertTrue(hitl)

    def test_trailing_blank_lines_do_not_evict_protocol(self):
        """DeepSeek 意见③：尾部空行不再把协议行挤出窗口。"""
        text = "@老板 请确认\n@options: 甲|乙\n\n\n\n"
        clean, opts, summ, hitl = collab_hub.parse_protocol_lines(text)
        self.assertEqual(opts, ["甲", "乙"])

    def test_fence_placeholder_unforgeable(self):
        """DeepSeek 意见①：uuid 随机占位——正文伪造旧占位串不再错乱。"""
        evil = "正文含伪造占位 \x00FENCE0\x00 结束\n@老板 看看"
        clean, opts, summ, hitl = collab_hub.parse_protocol_lines(evil)
        self.assertIn("\x00FENCE0\x00", clean)   # 伪造串原样保留（未被还原成围栏）
        self.assertTrue(hitl)

    def test_hitl_ignores_boss_in_fence(self):
        """DeepSeek 意见⑤：围栏内 @老板 不触发 HITL。"""
        text = "```py\nprint('@老板 请确认')\n```\n普通正文无协议"
        clean, opts, summ, hitl = collab_hub.parse_protocol_lines(text)
        self.assertFalse(hitl)

    def test_multiple_protocol_lines_first_wins_body_kept(self):
        """DeepSeek 意见⑥⑦：多协议行取首个；正文无全局空行压缩。"""
        text = "@summary: 摘要甲\n\n\n\n@summary: 摘要乙\n@老板 正文\n\n\n保留空行"
        clean, opts, summ, hitl = collab_hub.parse_protocol_lines(text)
        self.assertEqual(summ, "摘要甲")
        self.assertIn("\n\n\n", clean)   # 正文连续空行原样
