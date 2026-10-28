# -*- coding: utf-8 -*-
"""炒股辅助二期测试（2026-10-28）：全量流水线假数据注入+意图路由+契约。

零网络零 akshare：scan_pipeline 的数据函数全部 mock；意图路由测正则表；
装载契约测 PLUGIN() 清单。合规声明强制出现在最终输出。
"""
import importlib.util
import os
import sys
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

PLUGIN_SRC = os.path.join(PROJECT_ROOT, "agent_state", "plugins")
if PLUGIN_SRC not in sys.path:
    sys.path.insert(0, PLUGIN_SRC)

import stock_assistant as sa  # noqa: E402
import intent_router  # noqa: E402


class SoeHeuristicTests(unittest.TestCase):
    """国企启发式（一期校准回归锁死：国有资产不连续教训）。"""

    def test_soe_hits(self):
        for name in ("绵阳市国有资产监督管理委员会",
                     "国务院国资委", "国务院",
                     "青岛市财政局", "中国兵器工业集团",
                     "黄山市供销合作社联合社"):
            self.assertTrue(sa._is_soe(name)[0], name)

    def test_non_soe(self):
        for name in ("无", "梁昭贤;梁惠强", "李东生", "徐新建", "", None):
            self.assertFalse(sa._is_soe(name)[0], name)


class SectorMatchTests(unittest.TestCase):
    """映射层：覆盖表优先+模糊兜底+诚实 None。"""

    def test_overrides_first(self):
        smap = {"new_dqhy": "电器行业", "new_dzxx": "电子信息"}
        self.assertEqual(sa.match_sector(
            "电气机械和器材制造业", smap), "new_dqhy")
        self.assertEqual(sa.match_sector(
            "计算机、通信和其他电子设备制造业", smap), "new_dzxx")

    def test_fuzzy_prefix(self):
        smap = {"new_dlhy": "电力行业"}
        self.assertEqual(sa.match_sector(
            "电力、热力生产和供应业", smap), "new_dlhy")

    def test_no_match_none(self):
        self.assertIsNone(sa.match_sector("不认识的行业XYZ",
                                          {"new_dlhy": "电力行业"}))


class PipelineTests(unittest.TestCase):
    """全量流水线（假数据注入）：cap3/无标注/Markdown/JSON/合规。"""

    def _fake_scan(self):
        cons = {"new_dlhy": [
            {"code": "600001", "name": "甲电力", "price": 8.8,
             "mktcap": 500},
            {"code": "600002", "name": "乙电力", "price": 12.0,
             "mktcap": 400},
            {"code": "600003", "name": "丙电力", "price": 6.5,
             "mktcap": 300},
            {"code": "600004", "name": "丁电力", "price": 9.9,
             "mktcap": 200},   # cap3 应被挤掉
            {"code": "600005", "name": "戊民营", "price": 7.0,
             "mktcap": 150},   # 非国企应被滤
        ]}
        ctrl = {"600001": "某市国有资产监督管理委员会",
                "600002": "国务院国资委", "600003": "某县财政局",
                "600004": "某省国有资本运营集团", "600005": "张三"}
        with mock.patch.object(sa, "_cached", side_effect=lambda k, f, **kw: (
                cons[k.split(":", 1)[1]] if k.startswith("cons:")
                else ctrl if k == "controllers"
                else [("C01", "电力A", 100.0)] if k == "top_industries"
                else {"new_dlhy": "电力行业"})):
            return sa.scan_pipeline(top_n=1, per_cap=3, log=lambda m: None)

    def test_cap3_and_soe_filter(self):
        results = self._fake_scan()
        rows = results[0]["rows"]
        self.assertEqual(len(rows), 3)
        codes = {r["代码"] for r in rows}
        self.assertEqual(codes, {"600001", "600002", "600003"})  # 市值大者
        self.assertNotIn("600005", codes)                        # 民营滤除

    def test_markdown_and_json(self):
        results = self._fake_scan()
        md = sa.build_markdown(results)
        self.assertIn("| 电力A（100亿） | 甲电力 | 600001 | 8.8 |", md)
        self.assertIn("国有资产监督管理委员会", md)
        js = sa.build_json(results)
        self.assertIn("甲电力", js)

    def test_zero_hit_industry_notes_none(self):
        with mock.patch.object(sa, "_cached", side_effect=lambda k, f, **kw: (
                [] if k.startswith("cons:")
                else {} if k == "controllers"
                else [("C02", "保险B", 90.0)] if k == "top_industries"
                else {"new_jrhy": "金融行业"})):
            results = sa.scan_pipeline(top_n=1, log=lambda m: None)
        self.assertIn("无", results[0]["note"])
        md = sa.build_markdown(results)
        self.assertIn("无（", md)


class ReplyEntryTests(unittest.TestCase):
    """stock_screen_reply：政策面前置+合规声明强制+失败诚实。"""

    def test_compliance_always_present(self):
        fake = [{"行业": "电力A", "净利润亿": 100, "板块": "电力行业",
                 "rows": [], "note": "无"}]
        with mock.patch.object(sa, "_cached", return_value=fake), \
                mock.patch.object(sa, "policy_summary",
                                  return_value="电力：绿电政策利好。"):
            out = sa.stock_screen_reply("帮我选股")
        self.assertIn(sa.COMPLIANCE, out)
        self.assertIn("【政策面】", out)
        self.assertTrue(out.rstrip().endswith(sa.COMPLIANCE))

    def test_failure_returns_honest_error(self):
        # 友好兜底（队长拍板）：刺眼 RuntimeError 换自然语言，堆栈进日志
        with mock.patch.object(sa, "_cached",
                               side_effect=RuntimeError("网络炸了")):
            out = sa.stock_screen_reply("选股")
        self.assertIn("拉取数据失败", out, out)
        self.assertIn("稍后再试", out, out)
        self.assertNotIn("RuntimeError", out)   # 异常类名不漏给用户

    def test_policy_failure_placeholder(self):
        self.assertIn("失败", sa.policy_summary(
            ["电力A"], chat_fn=lambda m: (_ for _ in ()).throw(
                RuntimeError("云端挂"))))


class IntentAndContractTests(unittest.TestCase):
    """意图路由+插件契约。"""

    def test_intent_triggers(self):
        for msg in ("帮我选股一下", "查一下国企股名单", "电力行业景气度如何"):
            r = intent_router.route(msg)
            self.assertIsNotNone(r, msg)
            self.assertEqual(r.name, "stock_screen", msg)
            self.assertIn("agent_state_plugins_stock_assistant",
                          r.handler)

    def test_intent_passthrough(self):
        for msg in ("帮我搜一下天气", "记一下账", "今天心情怎么样"):
            r = intent_router.route(msg)
            if r is not None:
                self.assertNotEqual(r.name, "stock_screen", msg)

    def test_plugin_manifest_contract(self):
        mf = sa.PLUGIN()
        self.assertEqual(mf["name"], "stock_assistant")
        self.assertEqual(mf["version"], "0.2.0")
        tools = mf["tools"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "ext_stock_screen")
        self.assertTrue(tools[0]["handler"].startswith(
            "agent_state_plugins_stock_assistant:"))


if __name__ == "__main__":
    unittest.main()
