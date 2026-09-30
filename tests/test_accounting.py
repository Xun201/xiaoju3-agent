# -*- coding: utf-8 -*-
"""plugins/accounting 单元测试：记账本增删查汇总与原子落盘。

全部离线可跑：账本路径经 env XIAOJU3_ACCOUNT_BOOK 注入 tmp 目录
（同时验证 env 覆盖口径），网络与外部服务零接触。
覆盖：增删查汇总 roundtrip、非法输入拒绝、原子写不残留半文件、
并发追加不丢数据（threading 小压测）。
"""
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

from plugins import accounting
from plugins.accounting import (ACCOUNT_BOOK_ENV, add_record, delete_record,
                                get_book_path, list_records, summarize)


class AccountingTestBase(unittest.TestCase):
    """公共夹具：账本路径注入 tmp 目录，测试间完全隔离。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_dir = tmp.name
        self.book_path = os.path.join(self.tmp_dir, "account_book.json")
        patcher = mock.patch.dict(os.environ,
                                  {ACCOUNT_BOOK_ENV: self.book_path})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _records_on_disk(self):
        with open(self.book_path, "r", encoding="utf-8") as f:
            return json.load(f)


class AddAndListTest(AccountingTestBase):
    def test_add_then_list_roundtrip(self):
        result = add_record(-28, category="餐饮", note="午饭")
        self.assertIn("✅", result)
        self.assertIn("-28.00", result)
        self.assertIn("支出", result)

        records = self._records_on_disk()
        self.assertEqual(len(records), 1)
        rec = records[0]
        # 落盘结构锁定：date/amount/category/note/ts 五字段
        self.assertEqual(set(rec), {"date", "amount", "category",
                                    "note", "ts"})
        self.assertEqual(rec["amount"], -28.0)
        self.assertEqual(rec["category"], "餐饮")
        self.assertEqual(rec["note"], "午饭")
        self.assertIsInstance(rec["ts"], float)

        listing = list_records()
        self.assertIn("午饭", listing)
        self.assertIn("[餐饮]", listing)
        self.assertIn("共 1 笔", listing)

    def test_string_amount_accepted(self):
        result = add_record("12.5", category="交通")
        self.assertIn("✅", result)
        self.assertEqual(self._records_on_disk()[0]["amount"], 12.5)

    def test_income_positive_sign_kept(self):
        add_record(3000, category="工资", note="月薪")
        rec = self._records_on_disk()[0]
        self.assertEqual(rec["amount"], 3000.0)
        self.assertIn("收入", add_record(1))  # 正数按收入口径播报

    def test_explicit_date_recorded(self):
        add_record(-10, date="2026-08-15")
        self.assertEqual(self._records_on_disk()[0]["date"], "2026-08-15")

    def test_default_date_is_today(self):
        add_record(-10)
        self.assertEqual(self._records_on_disk()[0]["date"][:4], "2026")


class InvalidInputTest(AccountingTestBase):
    def test_invalid_amounts_rejected(self):
        for bad in ("abc", None, "", float("nan"), float("inf"),
                    float("-inf"), True, 0, 0.0, "  ", [1], {"a": 1}):
            with self.subTest(bad=bad):
                result = add_record(bad)
                self.assertTrue(result.startswith("❌"), msg=f"bad={bad!r}")
        # 非法输入不得产生任何落盘
        self.assertFalse(os.path.exists(self.book_path))

    def test_invalid_date_rejected(self):
        result = add_record(-10, date="2026/09/30")
        self.assertTrue(result.startswith("❌"))
        self.assertIn("YYYY-MM-DD", result)
        self.assertFalse(os.path.exists(self.book_path))

    def test_zero_amount_rejected_with_clear_message(self):
        result = add_record(0)
        self.assertTrue(result.startswith("❌"))
        self.assertIn("金额", result)


class SummarizeTest(AccountingTestBase):
    @staticmethod
    def _past_month_date():
        """距今 45 天前的日期：必然不在本月且不是今天（不受跑测日期影响）。"""
        from datetime import datetime, timedelta
        return (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")

    def _seed(self):
        add_record(-28, category="餐饮", note="午饭")
        add_record(-15, category="餐饮", note="晚饭")
        add_record(-10, category="交通", note="地铁")
        add_record(100, category="红包", note="压岁钱",
                   date=self._past_month_date())

    def test_today_summary_has_categories_and_balance(self):
        self._seed()
        text = summarize("today")
        self.assertIn("📊", text)
        # 今天只有三笔：支出 -53，结余 -53
        self.assertIn("支出：-53.00", text)
        self.assertIn("结余：-53.00", text)
        self.assertIn("· 餐饮：-43.00 元", text)
        self.assertIn("· 交通：-10.00 元", text)

    def test_month_excludes_other_months(self):
        self._seed()
        text = summarize("month")
        self.assertIn("· 餐饮：-43.00 元", text)  # 8 月红包不计入本月

    def test_all_includes_everything(self):
        self._seed()
        text = summarize("all")
        self.assertIn("共 4 笔", text)
        self.assertIn("收入：+100.00", text)
        self.assertIn("结余：+47.00", text)

    def test_empty_period(self):
        self.assertIn("暂无", summarize("today"))

    def test_invalid_period_rejected(self):
        result = summarize("yesterday")
        self.assertTrue(result.startswith("❌"))
        self.assertIn("today", result)

    def test_chinese_period_alias(self):
        self._seed()
        self.assertIn("结余", summarize("这个月"))


class DeleteTest(AccountingTestBase):
    def test_delete_by_global_index(self):
        add_record(-1, note="第一笔")
        add_record(-2, note="第二笔")
        add_record(-3, note="第三笔")
        result = delete_record(2)
        self.assertIn("🗑️", result)
        self.assertIn("第二笔", result)
        records = self._records_on_disk()
        self.assertEqual([r["note"] for r in records],
                         ["第一笔", "第三笔"])

    def test_delete_out_of_range(self):
        add_record(-1)
        self.assertTrue(delete_record(5).startswith("❌"))
        self.assertTrue(delete_record(0).startswith("❌"))
        self.assertTrue(delete_record(-1).startswith("❌"))
        self.assertEqual(len(self._records_on_disk()), 1)

    def test_delete_on_empty_book(self):
        self.assertIn("空", delete_record(1))

    def test_delete_invalid_index_type(self):
        self.assertTrue(delete_record("第2笔").startswith("❌"))


class ListLimitTest(AccountingTestBase):
    def test_limit_keeps_latest(self):
        for i in range(25):
            add_record(-(i + 1), note=f"第{i + 1}笔")
        listing = list_records(limit=5)
        self.assertIn("共 25 笔", listing)
        self.assertIn("第25笔", listing)   # 最新在上
        self.assertNotIn("第20笔", listing)

    def test_default_limit_is_20(self):
        for i in range(25):
            add_record(-(i + 1), note=f"第{i + 1}笔")
        listing = list_records()
        self.assertIn("最近 20 笔", listing)
        self.assertNotIn("第5笔", listing)

    def test_empty_book_listing_hint(self):
        listing = list_records()
        self.assertIn("空", listing)
        self.assertIn("记一笔", listing)


class AtomicWriteTest(AccountingTestBase):
    def test_no_tmp_residue_after_success(self):
        add_record(-28, note="午饭")
        leftovers = [n for n in os.listdir(self.tmp_dir)
                     if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])
        self.assertEqual(len(self._records_on_disk()), 1)

    def test_failed_save_keeps_original_and_cleans_tmp(self):
        add_record(-28, note="原有的账")
        original = self._records_on_disk()

        # 注入序列化失败：原文件必须完好，且不残留 .tmp 半成品
        with mock.patch.object(accounting, "_dump_json",
                               side_effect=OSError("磁盘满")):
            result = add_record(-99, note="写不进去的账")
        self.assertTrue(result.startswith("❌"))
        self.assertIn("保存失败", result)
        self.assertEqual(self._records_on_disk(), original)
        leftovers = [n for n in os.listdir(self.tmp_dir)
                     if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_chinese_roundtrip_through_disk(self):
        add_record(-28.5, category="餐饮", note="鱼香肉丝饭")
        reread = accounting._load_records(self.book_path)
        self.assertEqual(reread[0]["note"], "鱼香肉丝饭")
        self.assertEqual(reread[0]["category"], "餐饮")


class ConcurrencyTest(AccountingTestBase):
    def test_concurrent_add_no_data_loss(self):
        """20 线程 × 各 5 笔并发追加：落盘必须一条不少（线程锁口径）。"""
        errors = []

        def worker(worker_id):
            try:
                for i in range(5):
                    # +1 避免 worker 0 首笔算出 -0（0 元本就是非法金额）
                    result = add_record(-(worker_id * 10 + i + 1),
                                        category="并发", note=f"t{worker_id}-{i}")
                    if not result.startswith("✅"):
                        errors.append(result)
            except Exception as e:  # 线程内异常先收集，主线程统一断言
                errors.append(repr(e))

        threads = [threading.Thread(target=worker, args=(k,))
                   for k in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        records = self._records_on_disk()
        self.assertEqual(len(records), 100)
        # 100 笔备注互不相同，证明并发下没有任何一条被覆盖丢失
        notes = {r["note"] for r in records}
        self.assertEqual(len(notes), 100)

    def test_concurrent_delete_and_add_consistent(self):
        add_record(-1, note="基线")
        errors = []

        def adder():
            try:
                for i in range(10):
                    add_record(-(100 + i))
            except Exception as e:
                errors.append(repr(e))

        def deleter():
            try:
                delete_record(1)  # 删除"基线"那笔
            except Exception as e:
                errors.append(repr(e))

        t1 = threading.Thread(target=adder)
        t2 = threading.Thread(target=deleter)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [])
        records = self._records_on_disk()
        self.assertEqual(len(records), 10)
        self.assertNotIn("基线", [r["note"] for r in records])


class EnvOverrideTest(unittest.TestCase):
    def test_env_path_overrides_default(self):
        """env 指向 A 时写入 A，不碰缺省路径。"""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path_a = os.path.join(tmp.name, "book_a.json")
        with mock.patch.dict(os.environ, {ACCOUNT_BOOK_ENV: path_a}):
            self.assertEqual(get_book_path(), path_a)
            add_record(-7, note="A 账本")
        self.assertTrue(os.path.exists(path_a))
        self.assertIn("A 账本", accounting._load_records(path_a)[0]["note"])

    def test_default_path_falls_back_to_state_dir(self):
        """未设 env 时回落 agent_state/account_book.json（缺省口径）。"""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ACCOUNT_BOOK_ENV, None)
            from xiaoju3 import AGENT_STATE_DIR
            self.assertEqual(get_book_path(),
                             os.path.join(AGENT_STATE_DIR,
                                          "account_book.json"))


if __name__ == "__main__":
    unittest.main()
