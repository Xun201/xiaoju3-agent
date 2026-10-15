# -*- coding: utf-8 -*-
"""演化放权统一件锚（autonomy.py，design_297_phase2_unified §一，2026-10-15）。

状态机语义（拍板 E3）：promote N=5 连续未纠正升一档（累计 10 到
autonomous）；纠正 1 次退档+streak 清零；连续 2 次纠正直退 report；
manual 钉档；gate 三相矩阵。全纯函数，离线直调。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import autonomy


def _fresh():
    return autonomy.default_domain(now="2026-10-15 10:00:00")


class AutonomyLadderTests(unittest.TestCase):
    """三态阶梯状态机：升/降/清零/钉档/闸矩阵。"""

    def test_initial_state_is_report(self):
        d = _fresh()
        self.assertEqual(d["phase"], "report")
        self.assertEqual(d["uncorrected_streak"], 0)
        self.assertEqual(autonomy.gate(d["phase"], "positive"), "ask")

    def test_promote_report_to_checkpoint_at_5(self):
        d = _fresh()
        for _ in range(4):
            d = autonomy.record_use(d)
        self.assertEqual(d["phase"], "report")       # 4 次不动
        d = autonomy.record_use(d)
        self.assertEqual(d["phase"], "checkpoint")   # 第 5 次升档

    def test_promote_to_autonomous_at_cumulative_10(self):
        d = _fresh()
        for _ in range(10):
            d = autonomy.record_use(d)
        self.assertEqual(d["phase"], "autonomous")   # 累计 10
        for _ in range(5):                           # 封顶不再升
            d = autonomy.record_use(d)
        self.assertEqual(d["phase"], "autonomous")

    def test_correction_demotes_one_and_resets_streak(self):
        d = _fresh()
        for _ in range(5):
            d = autonomy.record_use(d)
        self.assertEqual(d["phase"], "checkpoint")
        d = autonomy.record_correction(d)
        self.assertEqual(d["phase"], "report")       # 退一档
        self.assertEqual(d["uncorrected_streak"], 0)  # 清零重攒
        # 重攒 5 次才再升（不是 0 次直升）
        d = autonomy.record_use(d)
        self.assertEqual(d["phase"], "report")

    def test_two_consecutive_corrections_drop_to_report(self):
        d = _fresh()
        for _ in range(10):
            d = autonomy.record_use(d)
        self.assertEqual(d["phase"], "autonomous")
        d = autonomy.record_correction(d)
        self.assertEqual(d["phase"], "checkpoint")   # 退一档
        d = autonomy.record_correction(d)
        self.assertEqual(d["phase"], "report")       # 连续 2 次直退 report

    def test_negative_use_does_not_count_toward_graduation(self):
        """负面段不参与自主毕业（phase3 §二收紧）。"""
        d = _fresh()
        for _ in range(8):
            d = autonomy.record_use(d, polarity="negative")
        self.assertEqual(d["phase"], "report")       # 8 次负面零毕业
        self.assertEqual(d["uncorrected_streak"], 0)

    def test_manual_pin_overrides_automation(self):
        """手动钉档：压过自动升降，钉后从新档位继续。"""
        d = _fresh()
        d = autonomy.set_phase(d, "autonomous", via="manual")
        self.assertEqual(d["phase"], "autonomous")
        self.assertTrue(any(c["via"] == "manual"
                            for c in d["corrections"]))   # 审计流水
        d = autonomy.set_phase(d, "report", via="manual")
        d = autonomy.record_use(d)
        self.assertEqual(d["phase"], "report")   # 钉 report 后 1 次使用不跳档
        self.assertEqual(d["set_phase" if False else "phase"], "report")

    def test_gate_matrix(self):
        """闸矩阵：report 全 ask / checkpoint 正直负问 / autonomous 全直。"""
        for polarity in ("positive", "negative"):
            self.assertEqual(autonomy.gate("report", polarity), "ask")
        self.assertEqual(autonomy.gate("checkpoint", "positive"), "direct")
        self.assertEqual(autonomy.gate("checkpoint", "negative"), "ask")
        for polarity in ("positive", "negative"):
            self.assertEqual(autonomy.gate("autonomous", polarity), "direct")

    def test_record_use_resets_consecutive_corrections(self):
        d = _fresh()
        d = autonomy.record_correction(d)
        self.assertEqual(d["consecutive_corrections"], 1)
        d = autonomy.record_use(d)
        self.assertEqual(d["consecutive_corrections"], 0)   # 未纠正使用清零连纠计数


if __name__ == "__main__":
    unittest.main()
