# -*- coding: utf-8 -*-
"""黄金样本采集与比对（#227 批 1 验收门）。

用法：
- 固化基线：python -m pytest tests/test_golden_samples.py -q --golden-capture
- 批后比对：python -m pytest tests/test_golden_samples.py -q（自动比对）
- 基线文件：tests/data/handle_message_golden_output.json（2026-10-14 起正档=tests/data）
"""
import json
import os
import unittest
from unittest import mock

import main

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "data")   # D6 拍板：正档=tests/data（2026-10-14 统一，_dev/golden_samples 留作历史）
GOLDEN_INPUT = os.path.join(GOLDEN_DIR, "handle_message_golden.json")
GOLDEN_OUTPUT = os.path.join(GOLDEN_DIR, "handle_message_golden_output.json")

CAPTURE = os.environ.get("GOLDEN_CAPTURE") == "1"


def _load_samples():
    with open(GOLDEN_INPUT, encoding="utf-8") as f:
        return json.load(f)["samples"]


class GoldenSampleRunner(unittest.TestCase):
    """逐条跑黄金样本，捕获或比对 handle_message 输出。"""

    def setUp(self):
        self.samples = _load_samples()
        self.sleeps = []

    def _run_one(self, sample):
        """跑单条样本，返回 (status_json, handle_reply, posts)。"""
        replies = []
        posts = []
        # mock 外部依赖
        with mock.patch.object(main, "brain") as mbrain, \
                mock.patch.object(main.requests, "post",
                                  side_effect=lambda *a, **k:
                                  posts.append((a, k))), \
                mock.patch.object(main, "save_memory") as sm, \
                mock.patch.object(main, "_compress_and_save"), \
                mock.patch.object(main, "state_manager") as msm, \
                mock.patch.object(main, "_strip_llm_pollution",
                                  side_effect=lambda r: r), \
                mock.patch.object(main, "_chat_rhythm_enabled",
                                  return_value=False), \
                mock.patch.object(main.time, "sleep",
                                  side_effect=self.sleeps.append), \
                mock.patch.dict(main.__dict__, {
                    "messages_web": [main.SYSTEM_PROMPT],
                    "messages_qq": [main.SYSTEM_PROMPT],
                }):
            mbrain.smart_ask.return_value = "（模拟脑回复）"
            msm.save_memory.return_value = None
            msm.get_recent_memories.return_value = []
            msm.save_conversation.return_value = None
            # 位置等待窗关
            mbrain._waiting_location_active.return_value = False
            mbrain._find_city_district.return_value = ("", "")

            resp = main.onebot_event({
                "post_type": "message",
                "message_type": "private" if not sample.get("group_id") else "group",
                "self_id": "10000",
                "sender": {"user_id": sample.get("user_id", 10001)},
                "raw_message": sample["raw_message"],
                "group_id": sample.get("group_id"),
            })

            # 从 posts 提取实际发送文本（如有）
            sent = None
            for a, k in posts:
                if "json" in k and "message" in k["json"]:
                    sent = k["json"]["message"]
            return resp, sent

    def test_golden_samples(self):
        results = {}
        for s in self.samples:
            with self.subTest(desc=s["desc"]):
                resp, sent = self._run_one(s)
                results[s["desc"]] = {
                    "resp_status": resp.get("status"),
                    "sent_reply": sent,
                }
                if CAPTURE:
                    continue
                # 比对模式
                expected = s.get("expected", {})
                if not expected:
                    continue
                self.assertEqual(resp.get("status"),
                                 expected.get("resp_status"),
                                 f"{s['desc']}: status mismatch")
                if expected.get("sent_reply") is not None:
                    self.assertEqual(sent, expected["sent_reply"],
                                     f"{s['desc']}: reply mismatch")

        if CAPTURE:
            os.makedirs(GOLDEN_DIR, exist_ok=True)
            with open(GOLDEN_OUTPUT, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n[黄金基线] {len(results)} 条已固化 → {GOLDEN_OUTPUT}")


if __name__ == "__main__":
    unittest.main()
