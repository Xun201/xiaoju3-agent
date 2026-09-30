# -*- coding: utf-8 -*-
"""intent_router 单元测试：自然语言意图路由（规则层 + 模型层 + dispatch）。

全部离线可跑：
- 规则层：正则命中/排除词/参数抽取，零网络零模型；
- 模型层：brain 用替身模块经 mock.patch.dict(sys.modules) 注入
  （自动还原，无永久注入），env XIAOJU3_MODEL_ROUTE 控制开关；
- dispatch：真实执行 accounting 离线 handler（账本路径注入 tmp），
  异常路径全走中文报错串。
覆盖功能文档 §7 例句对照表："帮我记一下账"→记账、"把这段对话导出成
电子书"→导出电子书，以及"今天天气不错"→不误路由。
"""
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from intent_router import (CONFIDENCE_MODEL, CONFIDENCE_RULE,
                           INTENT_PATTERNS, IntentResult, MODEL_ROUTE_ENV,
                           dispatch, route)
from plugins import accounting


class FakeBrain:
    """替身 brain 模块：记录 smart_ask 调用，可注入回复/异常。"""

    def __init__(self, reply="", error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    def smart_ask(self, message, history=None):
        self.calls.append({"message": message, "history": history})
        if self.error is not None:
            raise self.error
        return self.reply, "🏠 本地"


class RuleLayerDocExamplesTest(unittest.TestCase):
    """功能文档 §7 例句对照表口径。"""

    def test_jizhang_sentence_routes_to_accounting(self):
        result = route("帮我记一下账")
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "accounting_add")
        self.assertEqual(result.handler, "plugins.accounting:add_record")
        self.assertEqual(result.source, "rule")
        self.assertGreaterEqual(result.confidence, CONFIDENCE_RULE)

    def test_export_ebook_sentence_routes_to_ebook(self):
        result = route("把这段对话导出成电子书")
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "export_ebook")
        self.assertEqual(result.handler,
                         "plugins.ebook_export:export_from_history")

    def test_search_sentence_extracts_query(self):
        result = route("帮我搜一下天气")
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "web_search")
        self.assertEqual(result.args.get("query"), "天气")
        self.assertEqual(result.handler, "search_tools:web_search")

    def test_plain_chat_not_routed(self):
        # 非意图闲聊一律不路由（走正常对话），这是 None 的语义
        for text in ("今天天气不错", "你觉得人生的意义是什么",
                     "给我讲个笑话吧"):
            with self.subTest(text=text):
                self.assertIsNone(route(text))

    def test_home_control_not_routed_to_search(self):
        # 功能文档 §7："把客厅灯关了" 走模型工具协议，路由层不得抢
        self.assertIsNone(route("把客厅灯关了"))

    def test_workspace_query_blocked_by_negative_patterns(self):
        # "查一下"本是搜索触发词，但工作区/文件类请求必须留给工具协议
        self.assertIsNone(route("查一下工作区有哪些文件"))

    def test_url_reading_not_routed(self):
        # 功能文档 §7："读一下 https://…" 由 brain 抓网页总结，不路由
        self.assertIsNone(route("读一下 https://example.com"))


class RuleLayerAccountingTest(unittest.TestCase):
    def test_expense_amount_extraction(self):
        # 金额符号口径（模块 docstring 锁定）：支出动词 → 负数
        result = route("记一笔午饭花了28元")
        self.assertEqual(result.name, "accounting_add")
        self.assertEqual(result.args["amount"], -28.0)
        # 分类推断 + 备注取命中的物项词
        self.assertEqual(result.args["category"], "餐饮")
        self.assertEqual(result.args["note"], "午饭")

    def test_income_amount_extraction(self):
        result = route("记一笔收到红包200元")
        self.assertEqual(result.name, "accounting_add")
        self.assertEqual(result.args["amount"], 200.0)

    def test_amount_without_cue_defaults_to_expense(self):
        result = route("记一笔28元")
        self.assertEqual(result.args["amount"], -28.0)

    def test_add_without_amount_keeps_intent_empty_args(self):
        # "帮我记一下账"无金额：仍命中记账意图，args 留空由执行层追问
        result = route("帮我记一下账")
        self.assertEqual(result.args, {})

    def test_query_period_extraction(self):
        self.assertEqual(route("这个月花了多少").args["period"], "month")
        self.assertEqual(route("今天花了多少").args["period"], "today")
        self.assertEqual(route("帮我把账单汇总一下").args["period"], "all")

    def test_query_beats_search_by_table_order(self):
        # "查一下"同时命中搜索触发词，账表项在前必须先赢
        result = route("帮我查一下这个月花了多少")
        self.assertEqual(result.name, "accounting_query")
        self.assertEqual(result.args["period"], "month")

    def test_list_intent(self):
        result = route("看看记账本")
        self.assertEqual(result.name, "accounting_list")
        self.assertEqual(result.handler, "plugins.accounting:list_records")
        self.assertEqual(result.args, {})

    def test_ebook_title_extraction(self):
        result = route("把这段对话导出成《九月手记》电子书")
        self.assertEqual(result.name, "export_ebook")
        self.assertEqual(result.args.get("title"), "九月手记")


class RuleLayerSearchTest(unittest.TestCase):
    def test_search_variants_extract_query(self):
        cases = {
            "帮我搜一下天气": "天气",
            "搜索一下Python教程": "Python教程",
            "请查一下地铁运营时间": "地铁运营时间",
            "麻烦你联网搜索最新新闻": "最新新闻",
        }
        for text, query in cases.items():
            with self.subTest(text=text):
                result = route(text)
                self.assertEqual(result.name, "web_search")
                self.assertEqual(result.args.get("query"), query)


class IntentTableMetaTest(unittest.TestCase):
    """数据驱动表的结构契约：新增意图只加表项，不改路由逻辑。"""

    def test_table_entries_have_required_fields(self):
        for entry in INTENT_PATTERNS:
            for key in ("name", "patterns", "extractor", "handler_name"):
                self.assertIn(key, entry, msg=entry.get("name"))
            self.assertTrue(callable(entry["extractor"]))
            self.assertGreater(len(entry["patterns"]), 0)
            self.assertIn(":", entry["handler_name"])
            for pattern in entry["patterns"]:
                re.compile(pattern)  # 全部可编译

    def test_intent_names_unique(self):
        names = [entry["name"] for entry in INTENT_PATTERNS]
        self.assertEqual(len(names), len(set(names)))

    def test_rule_handler_references_are_lazy_strings(self):
        # 延迟字符串引用：模块解耦，import intent_router 不应拉起 handler
        handlers = [entry["handler_name"] for entry in INTENT_PATTERNS]
        self.assertIn("plugins.accounting:add_record", handlers)
        self.assertIn("plugins.ebook_export:export_from_history", handlers)
        self.assertIn("search_tools:web_search", handlers)


class ModelLayerTest(unittest.TestCase):
    """模型层：默认关闭；开启后走替身 brain，缺席优雅降级 None。"""

    def _enable(self):
        patcher = mock.patch.dict(os.environ, {MODEL_ROUTE_ENV: "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_disabled_by_default_no_brain_call(self):
        brain = FakeBrain(reply='{"intent": "web_search", "args": {}}')
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(MODEL_ROUTE_ENV, None)
            with mock.patch.dict("sys.modules", {"brain": brain}):
                result = route("帮我挑一件衣服")
        self.assertIsNone(result)
        self.assertEqual(brain.calls, [])  # 开关关闭：模型根本没被问

    def test_brain_absent_returns_none(self):
        self._enable()
        # sys.modules 置 None 可让延迟 `import brain` 稳定抛 ImportError
        with mock.patch.dict("sys.modules", {"brain": None}):
            self.assertIsNone(route("帮我挑一件衣服"))

    def test_model_hit_parses_intent(self):
        self._enable()
        brain = FakeBrain(reply='{"intent": "web_search", '
                                '"args": {"query": "明天天气"}}')
        with mock.patch.dict("sys.modules", {"brain": brain}):
            result = route("帮我挑一件衣服")
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "web_search")
        self.assertEqual(result.args, {"query": "明天天气"})
        self.assertEqual(result.source, "model")
        self.assertEqual(result.confidence, CONFIDENCE_MODEL)
        self.assertEqual(result.handler, "search_tools:web_search")
        # 分类提示词包含全部候选意图名
        self.assertIn("accounting_add", brain.calls[0]["message"])

    def test_model_none_intent_returns_none(self):
        self._enable()
        brain = FakeBrain(reply='{"intent": "none", "args": {}}')
        with mock.patch.dict("sys.modules", {"brain": brain}):
            self.assertIsNone(route("帮我挑一件衣服"))

    def test_model_garbage_reply_returns_none(self):
        self._enable()
        for bad in ("我不太明白你的意思", "", None,
                    '{"intent": "unknown_intent"}', "{broken json"):
            with self.subTest(bad=bad):
                brain = FakeBrain(reply=bad)
                with mock.patch.dict("sys.modules", {"brain": brain}):
                    self.assertIsNone(route("帮我挑一件衣服"))

    def test_model_error_degrades_gracefully(self):
        self._enable()
        brain = FakeBrain(error=RuntimeError("模型服务不可用"))
        with mock.patch.dict("sys.modules", {"brain": brain}):
            self.assertIsNone(route("帮我挑一件衣服"))

    def test_context_history_forwarded_to_model(self):
        self._enable()
        brain = FakeBrain(reply='{"intent": "none"}')
        history = [{"role": "user", "content": "上一句"}]
        with mock.patch.dict("sys.modules", {"brain": brain}):
            route("继续", context={"history": history})
        self.assertEqual(brain.calls[0]["history"], history)


class DispatchTest(unittest.TestCase):
    """dispatch 动态 import：真实调用离线 handler + 异常转中文报错。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.book_path = os.path.join(tmp.name, "account_book.json")
        patcher = mock.patch.dict(
            os.environ, {accounting.ACCOUNT_BOOK_ENV: self.book_path})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_dispatch_intent_result_calls_handler(self):
        intent = IntentResult(name="accounting_add",
                              args={"amount": -28, "category": "餐饮",
                                    "note": "午饭"},
                              confidence=CONFIDENCE_RULE,
                              handler="plugins.accounting:add_record")
        result = dispatch(intent)
        self.assertIn("✅", result)
        with open(self.book_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        self.assertEqual(records[0]["amount"], -28.0)

    def test_dispatch_handler_string_form(self):
        result = dispatch("plugins.accounting:list_records")
        self.assertIn("空", result)  # 离线可验证：tmp 账本为空

    def test_dispatch_bad_format_rejected(self):
        self.assertTrue(dispatch("no_colon_here").startswith("❌"))

    def test_dispatch_missing_module_rejected(self):
        result = dispatch("no_such_module_xyz:run")
        self.assertTrue(result.startswith("❌"))
        self.assertIn("意图执行失败", result)

    def test_dispatch_missing_args_rejected_in_chinese(self):
        intent = IntentResult(name="accounting_add", args={},
                              confidence=1.0,
                              handler="plugins.accounting:add_record")
        result = dispatch(intent)
        self.assertTrue(result.startswith("❌"))
        self.assertIn("参数不全", result)

    def test_dispatch_handler_exception_reported_in_chinese(self):
        # handler 内部抛错（空章节 ValueError）也不向上穿透
        intent = IntentResult(name="export_ebook", args={"title": "空书"},
                              confidence=1.0,
                              handler="plugins.ebook_export:export_epub")
        result = dispatch(intent)
        self.assertTrue(result.startswith("❌"))
        self.assertIn("chapters", result)


if __name__ == "__main__":
    unittest.main()
