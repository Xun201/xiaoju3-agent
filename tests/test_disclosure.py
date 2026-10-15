# -*- coding: utf-8 -*-
"""disclosure 过滤层锚（disclosure.py，design_297_phase2_unified §二小批
2.2，2026-10-15）。

消费侧过滤（phase3 §三）：普通行直注现状透传 / mute 丢弃 / boost 豁免
B3 / 7 天频次 / 负面 checkpoint 问句 / autonomous 负面直出 / 纠正落账
降档。全纯函数（注入 state，不碰实库），离线直调。
"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import autonomy
import disclosure


def _row(mid, content="记忆内容"):
    """recall 行形态（state_manager 同构六元组）。"""
    return (mid, "fact", content, 1.0, "neutral", "active")


NOW = datetime(2026, 10, 15, 12, 0, 0)
EP_POS = {"start_ts": "2026-10-14 10:00:00", "tag": "positive"}
EP_NEG = {"start_ts": "2026-10-13 10:00:00", "tag": "negative"}


class DisclosureFilterTests(unittest.TestCase):
    """消费侧过滤层四象限 + 纠正落账。"""

    def test_plain_rows_pass_through_unchanged(self):
        """无段关联普通行 → 直接注入（现状行为，元组逐字节透传）。"""
        rows = [_row(1), _row(2, "另一条")]
        direct, asks = disclosure.filter_memories(rows, associations={},
                                                  d=disclosure.load.__self__ if False else autonomy.default_domain(now=NOW),
                                                  now=NOW)
        self.assertEqual(direct, rows)
        self.assertEqual(asks, [])

    def test_report_phase_episode_becomes_ask(self):
        """report 态：段关联行 → 问句列（不直出）。"""
        d = autonomy.default_domain(now=NOW)
        direct, asks = disclosure.filter_memories(
            [_row(7)], associations={7: EP_POS}, d=d, now=NOW)
        self.assertEqual(direct, [])
        self.assertEqual([r[0] for r in asks], [7])

    def test_mute_drops_everywhere(self):
        """manual mute：任何 phase 都不提（用户说了"这个别提"）。"""
        for phase in ("report", "checkpoint", "autonomous"):
            d = autonomy.set_phase(autonomy.default_domain(now=NOW), phase,
                                   via="manual", now=NOW)
            d = disclosure.note_correction(
                d, EP_POS["start_ts"], disclosure.MUTE, "这个别提", now=NOW)
            direct, asks = disclosure.filter_memories(
                [_row(7)], associations={7: EP_POS}, d=d, now=NOW)
            self.assertEqual((direct, asks), ([], []), phase)

    def test_b3_frequency_drop_and_boost_exempt(self):
        """B3：7 天内提过丢弃；boost 豁免频次。"""
        d = autonomy.set_phase(autonomy.default_domain(now=NOW),
                               "autonomous", via="manual", now=NOW)
        d = disclosure.note_mention(d, EP_POS["start_ts"],
                                    polarity="positive",
                                    now=NOW - timedelta(days=2))
        direct, asks = disclosure.filter_memories(
            [_row(7)], associations={7: EP_POS}, d=d, now=NOW)
        self.assertEqual(direct, [])             # 2 天前提过 → B3 丢
        d = disclosure.note_correction(
            d, EP_POS["start_ts"], disclosure.BOOST, "这个该多提", now=NOW)
        direct, asks = disclosure.filter_memories(
            [_row(7)], associations={7: EP_POS}, d=d, now=NOW)
        self.assertEqual([r[0] for r in direct], [7])   # boost 豁免频次

    def test_negative_checkpoint_ask_autonomous_direct(self):
        """负面段：checkpoint → 问句；autonomous → 直出（只报结果约束在
        2.3 文案侧，此处验 gate 决定）。"""
        d_cp = autonomy.set_phase(autonomy.default_domain(now=NOW),
                                  "checkpoint", via="manual", now=NOW)
        direct, asks = disclosure.filter_memories(
            [_row(8)], associations={8: EP_NEG}, d=d_cp, now=NOW)
        self.assertEqual((direct, asks), ([], [_row(8)]))
        d_au = autonomy.set_phase(autonomy.default_domain(now=NOW),
                                  "autonomous", via="manual", now=NOW)
        direct, asks = disclosure.filter_memories(
            [_row(8)], associations={8: EP_NEG}, d=d_au, now=NOW)
        self.assertEqual([r[0] for r in direct], [8])
        self.assertEqual(asks, [])


class DisclosureCorrectionLedgerTests(unittest.TestCase):
    """纠正落账：overrides+流水+降档；boost 不降档。"""

    def test_mute_correction_writes_override_and_demotes(self):
        d = autonomy.set_phase(autonomy.default_domain(now=NOW),
                               "checkpoint", via="manual", now=NOW)
        d = disclosure.note_correction(
            d, EP_POS["start_ts"], disclosure.MUTE, "这个别提", now=NOW)
        self.assertEqual(
            d["data"]["manual_overrides"][EP_POS["start_ts"]], "mute")
        kinds = [c["kind"] for c in d["corrections"]]
        self.assertIn("mute", kinds)                 # mute 流水在案
        self.assertEqual(kinds[-1], "phase")         # 降档审计流水随后
        self.assertEqual(d["phase"], "report")       # mute 走纠正降档

    def test_boost_records_preference_without_demotion(self):
        d = autonomy.set_phase(autonomy.default_domain(now=NOW),
                               "checkpoint", via="manual", now=NOW)
        d = disclosure.note_correction(
            d, EP_POS["start_ts"], disclosure.BOOST, "这个该多提", now=NOW)
        self.assertEqual(
            d["data"]["manual_overrides"][EP_POS["start_ts"]], "boost")
        self.assertEqual(d["phase"], "checkpoint")   # boost 是偏好非纠正

    def test_mention_updates_frequency_and_graduation(self):
        d = autonomy.default_domain(now=NOW)
        d = disclosure.note_mention(d, EP_POS["start_ts"],
                                    polarity="positive", now=NOW)
        self.assertIn(EP_POS["start_ts"], d["data"]["last_mentioned"])
        self.assertEqual(d["uncorrected_streak"], 1)
        d = disclosure.note_mention(d, EP_NEG["start_ts"],
                                    polarity="negative", now=NOW)
        self.assertEqual(d["uncorrected_streak"], 1)   # 负面不参与毕业


if __name__ == "__main__":
    unittest.main()
