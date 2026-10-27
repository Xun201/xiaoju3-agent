# -*- coding: utf-8 -*-
"""qq_lifemate 表现力测试（切片 b/b+/三轨质检门）——概率契约/降级链/CQ 形态。

全部 mock 网络与合成（真 Edge-TTS/SAPI/GLM-4V 不在测试里跑）；概率用注入
rng 钉死。覆盖：
- 概率契约：VOICE_PROB=0.30 / STICKER_PROB=0.25 / 晓伊音色（拍板锚）；
- 三轨图库：base/user 优先于 cache；mood 子目录优先→轨根随机；全空不发；
- 视觉质检门：≥7 分发送+入 cache；<7 重搜后降级本地；解析失败默认 5；
  视觉链异常=0 分；
- send_voice：CQ:record file:/// 形态+发后焚文件；Edge 挂→SAPI 兜底形状；
- send_cq：owner 未配置→False；
- wake_once 集成：表现力异常不炸文字落账。
"""
import importlib.util
import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_SRC = os.path.join(PROJECT_ROOT, "agent_state", "plugins", "qq_lifemate")
if PLUGIN_SRC not in sys.path:
    sys.path.insert(0, PLUGIN_SRC)

import express  # noqa: E402
import waker  # noqa: E402
import shutil  # noqa: E402
from datetime import datetime  # noqa: E402
from unittest.mock import patch  # noqa: E402


class ProbContractTests(unittest.TestCase):
    def test_prob_constants(self):
        """M1 拍板锚：语音 30% / 表情 25% / 晓伊音色。"""
        self.assertEqual(express.VOICE_PROB, 0.30)
        self.assertEqual(express.STICKER_PROB, 0.25)
        self.assertEqual(express.EDGE_VOICE, "zh-CN-XiaoyiNeural")   # 晓伊（2026-10-27 换档）

    def test_three_tier_contract(self):
        """三轨制锚（2026-10-27 队长拍板）：轨序 base→user→cache+质检及格线 7。"""
        self.assertEqual(express.STICKER_TIERS, ("base", "user", "cache"))
        self.assertEqual(express.QA_THRESHOLD, 7)
        self.assertTrue(express.STICKER_API_ENABLED)


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
        """Edge 失败→SAPI 兜底被调用（降级链形状；pyttsx3 假模块注入）。"""
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
    """三轨图库（base/user/cache）。"""

    def test_empty_gallery_false(self):
        tmp = tempfile.mkdtemp(prefix="lm_stk_empty_")
        with patch.object(express, "sticker_root", return_value=tmp):
            self.assertFalse(express.send_sticker("happy"))
        shutil.rmtree(tmp, ignore_errors=True)

    def test_mood_dir_preferred_then_cq_image(self):
        """cache/happy/ mood 子目录优先；CQ:image file:/// 形态。"""
        tmp = tempfile.mkdtemp(prefix="lm_stk_")
        happy = os.path.join(tmp, "cache", "happy")
        os.makedirs(happy)
        img = os.path.join(happy, "a.png")
        open(img, "wb").write(b"x")
        base_dir = os.path.join(tmp, "base")
        os.makedirs(base_dir)
        base_img = os.path.join(base_dir, "b.png")
        open(base_img, "wb").write(b"x")
        with patch.object(express, "sticker_root", return_value=tmp), \
             patch.object(express, "send_cq", return_value=True) as cq:
            self.assertTrue(express.send_sticker("happy"))
        # base 轨优先于 cache 轨
        self.assertIn("b.png", cq.call_args[0][0])
        self.assertTrue(cq.call_args[0][0].startswith("[CQ:image,file=file:///"))
        shutil.rmtree(tmp, ignore_errors=True)

    def test_cache_used_when_base_user_empty(self):
        """base/user 空：cache 轨可用。"""
        tmp = tempfile.mkdtemp(prefix="lm_stk_c_")
        cache_dir = os.path.join(tmp, "cache")
        os.makedirs(cache_dir)
        img = os.path.join(cache_dir, "c.png")
        open(img, "wb").write(b"x")
        with patch.object(express, "sticker_root", return_value=tmp), \
             patch.object(express, "send_cq", return_value=True) as cq:
            self.assertTrue(express.send_sticker("happy"))
        self.assertIn("c.png", cq.call_args[0][0])
        shutil.rmtree(tmp, ignore_errors=True)

    def test_unsorted_not_in_random_pool(self):
        """unsorted/ 不进发送池（待分类暂存）。"""
        tmp = tempfile.mkdtemp(prefix="lm_stk_u_")
        unsorted_dir = os.path.join(tmp, "unsorted")
        os.makedirs(unsorted_dir)
        open(os.path.join(unsorted_dir, "x.png"), "wb").write(b"x")
        with patch.object(express, "sticker_root", return_value=tmp), \
             patch.object(express, "send_cq", return_value=True) as cq:
            self.assertFalse(express.send_sticker("happy"))
        cq.assert_not_called()
        shutil.rmtree(tmp, ignore_errors=True)

    def test_fallback_to_tier_root_when_mood_missing(self):
        """mood 目录不存在：回退轨根随机。"""
        tmp = tempfile.mkdtemp(prefix="lm_stk_f_")
        user_dir = os.path.join(tmp, "user")
        os.makedirs(user_dir)
        img = os.path.join(user_dir, "b.png")
        open(img, "wb").write(b"x")
        with patch.object(express, "sticker_root", return_value=tmp), \
             patch.object(express, "send_cq", return_value=True) as cq:
            self.assertTrue(express.send_sticker("angry"))
        self.assertIn("b.png", cq.call_args[0][0])
        shutil.rmtree(tmp, ignore_errors=True)


class SearchStickerTests(unittest.TestCase):
    """表情搜索：双源降级。"""

    def _fake_resp(self, data):
        import types
        r = types.SimpleNamespace()
        r.json = lambda: {"code": 0, "data": data}
        return r

    def _fake_resp_muming(self, data):
        import types
        r = types.SimpleNamespace()
        r.json = lambda: {"code": 200, "data": data}
        return r

    def test_primary_source_hit(self):
        with patch("requests.get", return_value=self._fake_resp(
                [{"sticker_url": "https://biaoqing.gtimg.com/a.jpg"}])):
            url = express.search_sticker("开心", page=1)
        self.assertEqual(url, "https://biaoqing.gtimg.com/a.jpg")

    def test_fallback_to_muming(self):
        """主源异常→备选慕名 img_url。"""
        def _get(url, **kw):
            if "xcvts" in url:
                raise RuntimeError("主源挂")
            return self._fake_resp_muming([{"img_url": "https://gtimg.com/b.jpg"}])
        with patch("requests.get", side_effect=_get):
            url = express.search_sticker("开心")
        self.assertEqual(url, "https://gtimg.com/b.jpg")

    def test_both_down_none(self):
        with patch("requests.get", side_effect=RuntimeError("全挂")):
            self.assertIsNone(express.search_sticker("开心"))

    def test_empty_keyword_none(self):
        self.assertIsNone(express.search_sticker("  "))


class QaGateTests(unittest.TestCase):
    """视觉质检门（1-10 打分制，≥7 发送+入 cache）。"""

    def test_qa_score_parses_and_defaults(self):
        """qa_score：解析分数；解析失败默认 5（<7 拒）；视觉链异常=0。"""
        with patch("vision_tools.vision_ask_image", return_value="8 画风可爱清晰"):
            self.assertEqual(express.qa_score("x.img"), (8, "8 画风可爱清晰"))
        with patch("vision_tools.vision_ask_image", return_value="看不懂"):
            score, _ = express.qa_score("x.img")
            self.assertEqual(score, 5)
        with patch("vision_tools.vision_ask_image",
                   side_effect=RuntimeError("断网")):
            score, reason = express.qa_score("x.img")
            self.assertEqual(score, 0)
            self.assertIn("异常", reason)

    def test_send_api_sticker_qa_pass_sends_and_stashes(self):
        """质检 ≥7：URL 直发 CQ:image+沉淀 cache 轨。"""
        with patch.object(express, "search_sticker",
                          return_value="https://gtimg.com/x.jpg"), \
             patch.object(express, "_download_temp", return_value="t.img"), \
             patch.object(express, "qa_score", return_value=(8, "可爱清晰")), \
             patch.object(express, "send_cq", return_value=True) as cq, \
             patch.object(express, "stash_sticker") as st:
            self.assertTrue(express.send_api_sticker("开心", "happy"))
        msg = cq.call_args[0][0]
        self.assertEqual(msg, "[CQ:image,file=https://gtimg.com/x.jpg]")
        st.assert_called_once_with("https://gtimg.com/x.jpg", "happy",
                                   tier="cache")

    def test_send_api_sticker_qa_fail_retries_then_local(self):
        """质检不过：重搜 QA_FAIL_RETRY 次仍不过→降级本地图库，绝不发送。"""
        with patch.object(express, "search_sticker",
                          return_value="https://gtimg.com/bad.jpg") as se, \
             patch.object(express, "_download_temp", return_value="t.img"), \
             patch.object(express, "qa_score", return_value=(3, "古早包浆")), \
             patch.object(express, "send_cq", return_value=True) as cq, \
             patch.object(express, "send_sticker", return_value=True) as ls:
            self.assertTrue(express.send_api_sticker("开心", "happy"))
        self.assertEqual(se.call_count, express.QA_FAIL_RETRY + 1)
        cq.assert_not_called()   # 低分图绝不发送
        ls.assert_called_once_with("happy")

    def test_api_disabled_goes_local(self):
        """总开关关：直接走本地图库。"""
        with patch.object(express, "STICKER_API_ENABLED", False), \
             patch.object(express, "search_sticker") as se, \
             patch.object(express, "send_sticker", return_value=True) as ls:
            self.assertTrue(express.send_api_sticker("开心", "happy"))
        se.assert_not_called()
        ls.assert_called_once_with("happy")

    def test_stash_downloads_and_dedups(self):
        """沉淀：下载写 cache/<mood>/ + URL md5 去重。"""
        import hashlib
        import time
        tmp = tempfile.mkdtemp(prefix="lm_stash_")
        with patch.object(express, "sticker_root", return_value=tmp), \
             patch("requests.get") as g:
            g.return_value = type("R", (), {
                "status_code": 200, "content": b"imgbytes",
                "headers": {"content-type": "image/jpeg"}})()
            url = "https://gtimg.com/dup.jpg"
            express.stash_sticker(url, "happy", tier="cache")
            d = os.path.join(tmp, "cache", "happy")
            for _ in range(30):
                if os.path.isdir(d) and os.listdir(d):
                    break
                time.sleep(0.1)
            files = os.listdir(d)
            self.assertEqual(len(files), 1)
            expect = hashlib.md5(url.encode()).hexdigest()[:12] + ".jpg"
            self.assertEqual(files[0], expect)
            express.stash_sticker(url, "happy", tier="cache")
            time.sleep(0.4)
            self.assertEqual(len(os.listdir(d)), 1)   # 去重
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
            with patch.object(waker, "generate_wake_text",
                              return_value=("嗨", None)), \
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
