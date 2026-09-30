# -*- coding: utf-8 -*-
"""emoji_manager 离线单测：收藏 / 去重 / 容量截断 / 按标签与随机取用 /
缺失标签时的下载兜底（架构 §10 #6 闭环）。

仓库文件与表情库目录一律注入临时目录，不触碰真实 agent_state 与 workspace；
网络不触碰（download_emoji 的 requests 一律 mock）。patch 全部经
unittest.mock.patch + addCleanup 自动还原，不向 sys.modules 注入伪模块。
"""
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import emoji_manager


class TestSaveEmojiLink(unittest.TestCase):
    """收藏：追加、去重、容量截断与失败口径。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_emoji_")
        self.log_file = os.path.join(self.tmp, "emoji_links.json")
        p = patch("emoji_manager.EMOJI_LOG_FILE", self.log_file)
        p.start()
        self.addCleanup(p.stop)

    def _load(self):
        with open(self.log_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_save_appends_url(self):
        self.assertTrue(emoji_manager.save_emoji_link("https://a/1.jpg"))
        self.assertTrue(emoji_manager.save_emoji_link("https://a/2.jpg"))
        self.assertEqual(self._load(), ["https://a/1.jpg", "https://a/2.jpg"])

    def test_dedupe_same_url(self):
        emoji_manager.save_emoji_link("https://a/1.jpg")
        emoji_manager.save_emoji_link("https://a/1.jpg")
        self.assertEqual(self._load(), ["https://a/1.jpg"])

    def test_capacity_keeps_latest(self):
        with patch("emoji_manager.MAX_EMOJI_LINKS", 3):
            for i in range(5):
                emoji_manager.save_emoji_link(f"https://a/{i}.jpg")
        self.assertEqual(self._load(),
                         ["https://a/2.jpg", "https://a/3.jpg", "https://a/4.jpg"])

    def test_corrupt_store_returns_false(self):
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write("{broken json")
        self.assertFalse(emoji_manager.save_emoji_link("https://a/1.jpg"))

    def test_unwritable_path_returns_false(self):
        blocker = os.path.join(self.tmp, "blocker.txt")
        self.touch(blocker)
        # 以"文件"为父目录，makedirs 必然失败 → 优雅返回 False
        bad = os.path.join(blocker, "sub", "emoji_links.json")
        with patch("emoji_manager.EMOJI_LOG_FILE", bad):
            self.assertFalse(emoji_manager.save_emoji_link("https://a/1.jpg"))

    @staticmethod
    def touch(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("x")
        return path


class TestEmojiFetch(unittest.TestCase):
    """取用：按标签 / 随机取图（供 brain.translate_emoji 延迟导入对接）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_emoji_dir_")
        p = patch("emoji_manager.EMOJI_DIR", self.tmp)
        p.start()
        self.addCleanup(p.stop)
        # 收藏链接库同样注入临时目录：缺省无链接，确保取用路径离线零网络
        log = patch("emoji_manager.EMOJI_LOG_FILE",
                    os.path.join(self.tmp, "emoji_links.json"))
        log.start()
        self.addCleanup(log.stop)

    def _touch(self, name):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as f:
            f.write(b"img")
        return path

    def test_get_emoji_path_by_tag(self):
        path = self._touch("开心 猫猫.png")
        self.assertEqual(emoji_manager.get_emoji_path("开心"), path)

    def test_get_emoji_path_miss(self):
        self._touch("开心 猫猫.png")
        self.assertIsNone(emoji_manager.get_emoji_path("生气"))

    def test_get_emoji_path_missing_dir(self):
        with patch("emoji_manager.EMOJI_DIR", os.path.join(self.tmp, "nope")):
            self.assertIsNone(emoji_manager.get_emoji_path("开心"))

    def test_get_random_emoji(self):
        p1 = self._touch("a.png")
        p2 = self._touch("b.png")
        self.assertIn(emoji_manager.get_random_emoji(), {p1, p2})

    def test_get_random_emoji_empty(self):
        self.assertIsNone(emoji_manager.get_random_emoji())

    def test_brain_translate_emoji_contract(self):
        """brain.translate_emoji 延迟导入 get_emoji_path 的对接契约（签名一致）。"""
        path = self._touch("开心.png")
        from brain import translate_emoji
        reply = translate_emoji("哈哈 [EMOJI:开心]")
        self.assertEqual(reply, f"哈哈 [CQ:image,file=file://{path}]")


class TestEmojiDownloadFallback(unittest.TestCase):
    """下载兜底（架构 §10 #6 闭环）：本地库缺失标签 → 收藏链接下载 → 可用。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_emoji_dl_")
        self.dir = os.path.join(self.tmp, "emoji_library")
        self.log_file = os.path.join(self.tmp, "emoji_links.json")
        for target, value in [("emoji_manager.EMOJI_DIR", self.dir),
                              ("emoji_manager.EMOJI_LOG_FILE", self.log_file)]:
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    def _store_link(self, url):
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump([url], f)

    def test_miss_downloads_from_stored_link_then_hit(self):
        """缺标签 → 取收藏库最新链接下载 → 文件名含标签 → 翻译链路自然可用。"""
        self._store_link("https://gchat.qpic.cn/happy.jpg")
        resp = MagicMock(status_code=200, content=b"imgbytes")
        with patch("emoji_manager.requests.get", return_value=resp) as get_mock:
            path = emoji_manager.get_emoji_path("开心")
        get_mock.assert_called_once()
        self.assertEqual(get_mock.call_args[0][0], "https://gchat.qpic.cn/happy.jpg")
        self.assertIsNotNone(path)
        self.assertTrue(os.path.exists(path))
        self.assertIn("开心", os.path.basename(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"imgbytes")
        # 下载成功后再取同一标签：直接命中本地库，不再发起网络请求
        with patch("emoji_manager.requests.get") as get_mock2:
            self.assertEqual(emoji_manager.get_emoji_path("开心"), path)
        get_mock2.assert_not_called()

    def test_miss_without_stored_links_returns_none(self):
        """收藏库为空：无下载源，优雅返回 None 且零网络。"""
        with patch("emoji_manager.requests.get") as get_mock:
            self.assertIsNone(emoji_manager.get_emoji_path("开心"))
        get_mock.assert_not_called()

    def test_download_non_200_returns_none(self):
        self._store_link("https://gchat.qpic.cn/x.jpg")
        with patch("emoji_manager.requests.get", return_value=MagicMock(status_code=404)):
            self.assertIsNone(emoji_manager.get_emoji_path("开心"))

    def test_download_exception_returns_none(self):
        """网络异常优雅降级：返回 None，不阻断 translate 回复链。"""
        self._store_link("https://gchat.qpic.cn/x.jpg")
        with patch("emoji_manager.requests.get", side_effect=RuntimeError("net down")):
            self.assertIsNone(emoji_manager.get_emoji_path("开心"))

    def test_hit_does_not_download(self):
        os.makedirs(self.dir, exist_ok=True)
        path = os.path.join(self.dir, "开心.png")
        with open(path, "wb") as f:
            f.write(b"img")
        self._store_link("https://gchat.qpic.cn/happy.jpg")
        with patch("emoji_manager.requests.get") as get_mock:
            self.assertEqual(emoji_manager.get_emoji_path("开心"), path)
        get_mock.assert_not_called()

    def test_download_emoji_success_and_failure(self):
        os.makedirs(self.dir, exist_ok=True)
        with patch("emoji_manager.requests.get",
                   return_value=MagicMock(status_code=200, content=b"data")):
            self.assertTrue(emoji_manager.download_emoji("https://a/1.jpg", "生气"))
        files = os.listdir(self.dir)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith("生气"))
        with patch("emoji_manager.requests.get",
                   return_value=MagicMock(status_code=500)):
            self.assertFalse(emoji_manager.download_emoji("https://a/2.jpg", "生气"))


if __name__ == "__main__":
    unittest.main()
