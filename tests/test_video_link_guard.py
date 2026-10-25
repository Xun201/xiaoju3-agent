# -*- coding: utf-8 -*-
"""视频链接路由层硬拦截（#348 三期幻觉防线）测试。

真机实锤：本地模型对含视频平台链接的消息凭预训练知识"脑补"剧情总结——
路由层拦截（main.video_link_guard 三通道共用）+插件 URL 直达意图双层。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import shutil
import tempfile
from unittest.mock import patch

import main
import intent_router
import plugin_loader


class VideoLinkGuardTests(unittest.TestCase):
    """main.video_link_guard 三态（拦截/动作词放行/无链接放行）。"""

    def test_bare_bilibili_link_intercepted(self):
        r = main.video_link_guard("https://www.bilibili.com/video/BV1GJ411x7h7")
        self.assertIsNotNone(r)
        self.assertIn("发现视频链接", r)
        self.assertIn("总结这个视频", r)

    def test_douyin_short_link_intercepted(self):
        """v.douyin.com 短链（子域通配实锤漏网后修）。纯链接=拦截；
        带动作词"看看"（含"看"）→ 放行交插件 URL 直达意图（行为闭环）。"""
        self.assertIsNotNone(main.video_link_guard("https://v.douyin.com/abc123/"))
        self.assertIsNotNone(main.video_link_guard("https://b23.tv/abc123"))

    def test_action_word_passes_to_plugin(self):
        """带动作词 → None 放行（插件意图处理转写）。"""
        self.assertIsNone(main.video_link_guard(
            "总结这个视频 https://www.bilibili.com/video/BV1GJ411x7h7"))
        self.assertIsNone(main.video_link_guard(
            "解析这个视频 https://www.bilibili.com/video/BV1"))

    def test_no_link_passes(self):
        """无链接 → None 放行。"""
        self.assertIsNone(main.video_link_guard("今天天气怎么样"))
        self.assertIsNone(main.video_link_guard("https://example.com/article"))


class VideoIntentWordlistTests(unittest.TestCase):
    """插件意图词表扩容（口语覆盖+URL 直达）。"""

    @classmethod
    def setUpClass(cls):
        import plugin_loader
        plugin_loader._loaded.clear()
        plugin_loader._rejected.clear()
        # video_ingest setup 预检需要 faster_whisper——真 _deps 预注入 sys.path
        #（tmp 外部目录不含 _deps，依赖走 dev 真目录；生产语义由插件自足）
        real_deps = os.path.join(PROJECT_ROOT, "agent_state", "plugins", "_deps")
        if os.path.isdir(real_deps) and real_deps not in sys.path:
            sys.path.insert(0, real_deps)
        cls._tmp = tempfile.mkdtemp(prefix="xj3_vguard_")
        cls._enter = patch.object(plugin_loader, "external_dir",
                                  lambda: cls._tmp)
        cls._enter.start()
        # 三真插件 copy 进 tmp（video_ingest 依赖 dice 无关但保持完整态）
        for name in ("video_ingest.py",):
            shutil.copy2(os.path.join(PROJECT_ROOT, "agent_state", "plugins", name),
                         os.path.join(cls._tmp, name))
        plugin_loader.load_all()

    def tearDown(self):
        self._enter.stop()
        plugin_loader._loaded.clear()
        plugin_loader._rejected.clear()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_colloquial_wordlist(self):
        """口语词表：提取视频内容/解析这个视频/看下这个视频。"""
        for msg in ("提取视频内容", "解析这个视频", "看下这个视频讲了什么"):
            r = intent_router.route(msg)
            self.assertIsNotNone(r, msg)
            self.assertTrue(r.name.startswith("ext_video"), msg)

    def test_url_direct_guard_intent(self):
        """URL 直达意图：纯链接也命中插件（link_guard 引导/转写分流）。"""
        for msg in ("https://www.bilibili.com/video/BV1GJ411x7h7",
                    "帮我看看 https://b23.tv/abc123 是什么"):
            r = intent_router.route(msg)
            self.assertIsNotNone(r, msg)
            self.assertEqual(r.name, "ext_video_link_guard", msg)


if __name__ == "__main__":
    unittest.main()
