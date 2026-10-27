# -*- coding: utf-8 -*-
"""qq_lifemate 切片 b 表现力测试（2026-10-27）——概率契约/降级链/CQ 形态。

全部 mock 网络与合成（真 Edge-TTS/SAPI 不在测试里跑）；概率用注入 rng
钉死。覆盖：
- 概率契约：VOICE_PROB=0.30 / STICKER_PROB=0.25（拍板锚）；
- rng=1.0 全不附加、rng=0.0 全附加；语音失败不影响表情；
- send_voice：合成成功→CQ:record file:/// 形态+发后焚文件；合成失败→False；
- send_sticker：图库空→False；有图→CQ:image file:/// 形态；
- send_cq：owner 未配置→False；
- wake_once 集成：表现力异常不炸文字落账。
"""
import importlib.util
import os
import random
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_SRC = os.path.join(PROJECT_ROOT, "agent_state", "plugins", "qq_lifemate")
if PLUGIN_SRC not in sys.path:
    sys.path.insert(0, PLUGIN_SRC)

import express  # noqa: E402
import waker  # noqa: E402
from datetime import datetime  # noqa: E402
from unittest.mock import patch  # noqa: E402


class ProbContractTests(unittest.TestCase):
    def test_prob_constants(self):
        """M1 拍板锚：语音 30% / 表情 25%（改动须过本用例）。"""
        self.assertEqual(express.VOICE_PROB, 0.30)
        self.assertEqual(express.STICKER_PROB, 0.25)
        self.assertEqual(express.EDGE_VOICE, "zh-CN-XiaoxiaoNeural")


class FakeRng:
    """受控 rng：按脚本依次出值（Random(seed) 序列不可控，弃用）。"""

    def __init__(self, values):
        self._values = list(values)
        self._i = 0

    def random(self):
        v = self._values[min(self._i, len(self._values) - 1)]
        self._i += 1
        return v


class MaybeExpressTests(unittest.TestCase):
    def test_never_express_when_rng_always_one(self):
        """rng 恒 1.0：零附加。"""
        with patch.object(express, "send_voice", return_value=True) as v, \
             patch.object(express, "send_sticker", return_value=True) as s:
            acts = express.maybe_express("嗨", rng=FakeRng([1.0, 1.0]))
        self.assertEqual(acts, "")
        v.assert_not_called()
        s.assert_not_called()

    def test_always_express_when_rng_always_zero(self):
        """rng 恒 0：语音+表情都附加。"""
        with patch.object(express, "send_voice", return_value=True) as v, \
             patch.object(express, "send_sticker", return_value=True) as s:
            acts = express.maybe_express("嗨", rng=FakeRng([0.0, 0.0]))
        self.assertEqual(acts, "voice+sticker")
        v.assert_called_once_with("嗨")
        s.assert_called_once()

    def test_voice_fail_still_sticker(self):
        """语音失败静默：表情照走。"""
        with patch.object(express, "send_voice", return_value=False), \
             patch.object(express, "send_sticker", return_value=True) as s:
            acts = express.maybe_express("嗨", rng=FakeRng([0.0, 0.0]))
        self.assertEqual(acts, "sticker")
        s.assert_called_once()


import shutil  # noqa: E402


class SendVoiceTests(unittest.TestCase):
    def test_cq_record_form_and_file_cleanup(self):
        """CQ:record file:/// 形态+发后焚文件。"""
        fake = os.path.join(tempfile.gettempdir(), "lm_voice_test.mp3")
        with open(fake, "wb") as f:
            f.write(b"x")
        with patch.object(express, "synthesize_speech", return_value=fake), \
             patch.object(express, "send_cq", return_value=True) as cq:
            self.assertTrue(express.send_voice("想你了"))
        msg = cq.call_args[0][0]
        self.assertTrue(msg.startswith("[CQ:record,file=file:///"))
        self.assertFalse(os.path.exists(fake))   # 发后焚

    def test_synth_fail_returns_false(self):
        with patch.object(express, "synthesize_speech", return_value=None):
            self.assertFalse(express.send_voice("嗨"))

    def test_synth_edge_fallback_sapi_shape(self):
        """Edge 失败→SAPI 兜底被调用（降级链形状；pyttsx3 假模块注入——
        本机未装也验证形状）。"""
        import types
        fake_pyttsx3 = types.ModuleType("pyttsx3")
        made = []

        class _FakeEngine:
            def save_to_file(self, text, path):
                made.append(path)
                with open(path, "wb") as f:
                    f.write(b"wav")

            def runAndWait(self):
                pass

        fake_pyttsx3.init = lambda: _FakeEngine()

        import builtins
        real_import = builtins.__import__

        def _fake_import(name, *a, **kw):
            if name == "edge_tts":
                raise RuntimeError("断网（注入）")
            if name == "pyttsx3":
                return fake_pyttsx3
            return real_import(name, *a, **kw)

        with patch("builtins.__import__", side_effect=_fake_import):
            path = express.synthesize_speech("hello")
        self.assertTrue(path and path.endswith(".wav"))
        self.assertEqual(len(made), 1)


class SendStickerTests(unittest.TestCase):
    def test_empty_gallery_false(self):
        tmp = tempfile.mkdtemp(prefix="lm_stk_empty_")
        with patch.object(express, "sticker_root", return_value=tmp):
            self.assertFalse(express.send_sticker("happy"))
        shutil.rmtree(tmp, ignore_errors=True)

    def test_mood_dir_preferred_then_cq_image(self):
        """mood 子目录优先；CQ:image file:/// 形态。"""
        tmp = tempfile.mkdtemp(prefix="lm_stk_")
        happy = os.path.join(tmp, "happy")
        os.makedirs(happy)
        img = os.path.join(happy, "a.png")
        open(img, "wb").write(b"x")
        root_only = os.path.join(tmp, "b.png")
        open(root_only, "wb").write(b"x")
        with patch.object(express, "sticker_root", return_value=tmp), \
             patch.object(express, "send_cq", return_value=True) as cq:
            self.assertTrue(express.send_sticker("happy"))
        self.assertIn("a.png", cq.call_args[0][0])
        self.assertTrue(cq.call_args[0][0].startswith("[CQ:image,file=file:///"))
        shutil.rmtree(tmp, ignore_errors=True)

    def test_fallback_to_root_when_mood_missing(self):
        """mood 目录不存在：回退全库随机。"""
        tmp = tempfile.mkdtemp(prefix="lm_stk_f_")
        img = os.path.join(tmp, "b.png")
        open(img, "wb").write(b"x")
        with patch.object(express, "sticker_root", return_value=tmp), \
             patch.object(express, "send_cq", return_value=True) as cq:
            self.assertTrue(express.send_sticker("angry"))
        self.assertIn("b.png", cq.call_args[0][0])
        shutil.rmtree(tmp, ignore_errors=True)


class SendCqTests(unittest.TestCase):
    def test_no_owner_false(self):
        with patch.dict(os.environ, {"XIAOJU3_OWNER_QQ": "",
                                     "ONEBOT_API_URL": "http://127.0.0.1:3000"}):
            self.assertFalse(express.send_cq("[CQ:image,file=file:///x.png]"))


class WakeExpressIntegrationTests(unittest.TestCase):
    def test_express_crash_not_break_wake(self):
        """表现力异常不炸文字落账（文字是主消息）。"""
        tmp = tempfile.mkdtemp(prefix="lm_wake_x_")
        waker.set_data_dir(tmp)
        try:
            with patch.object(waker, "generate_wake_text", return_value="嗨"), \
                 patch.object(waker, "send_qq", return_value=True), \
                 patch("express.maybe_express", side_effect=RuntimeError("炸")):
                self.assertTrue(waker.wake_once(datetime(2026, 10, 27, 14, 0, 0)))
            db = waker._db()
            n = db.execute("SELECT COUNT(*) FROM chat_log").fetchone()[0]
            db.close()
            self.assertEqual(n, 1)
        finally:
            waker.stop()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
