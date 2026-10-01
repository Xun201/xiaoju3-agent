# -*- coding: utf-8 -*-
"""Edge-TTS 语音合成接口（POST/GET /api/tts）单元测试（全部离线）。

覆盖（任务 6 后端口径）：
- GET  /api/tts：音色表结构 {code, data:{default, voices:[{voice, name}]}}；
  默认音色 zh-CN-XiaoxiaoNeural 居首、表内互不重复、3-5 个自然女声；
- POST /api/tts 正常合成：mock edge_tts.Communicate → 假 audio 分片 →
  200 + Content-Type audio/mpeg + 分片拼接正确；Communicate 收到
  (text, voice) 位置参数；未传 voice 走默认音色；
- text 空 / 无 JSON 体 → 400（业务码与 HTTP 状态一致）；
- 服务端未安装 edge-tts（sys.modules 置 None → import 抛 ImportError）
  → 501 + 中文提示 "服务端未安装 edge-tts"；
- 合成异常（Communicate 抛 RuntimeError 模拟断网）→ 500 + 简短中文原因；
- 合成成功但零音频分片 → 500（不给前端空音频）；
- 方法限制：DELETE /api/tts → 405。

mock 注意：全部走 context manager（结束即还原）——edge_tts.Communicate 用
mock.patch 还原；sys.modules 用 mock.patch.dict 还原，绝不污染真实环境。
"""
import contextlib
import io
import sys
import unittest
from unittest import mock

import os as _os
PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import xiaoju3_dashboard as dashboard  # noqa: E402


class _FakeCommunicate:
    """edge_tts.Communicate 桩：记录调用参数，stream() 产出 audio 与
    WordBoundary 混合分片（验证只收集 audio 分片）。"""

    calls = []   # [(text, voice), ...]

    def __init__(self, text, voice=None, **kwargs):
        _FakeCommunicate.calls.append((text, voice))

    async def stream(self):
        yield {"type": "audio", "data": b"fake-mp3-"}
        yield {"type": "WordBoundary", "offset": 0, "duration": 100}
        yield {"type": "audio", "data": b"chunk"}


class _EmptyAudioCommunicate:
    """合成成功但零 audio 分片（在线服务返回空流）的桩。"""

    def __init__(self, text, voice=None, **kwargs):
        pass

    async def stream(self):
        yield {"type": "WordBoundary", "offset": 0, "duration": 100}


@contextlib.contextmanager
def _quiet():
    """吞掉仪表盘的进度 print，保持测试输出干净。"""
    with contextlib.redirect_stdout(io.StringIO()):
        yield


class TtsVoiceTableTests(unittest.TestCase):
    """GET /api/tts：音色表结构与常量口径。"""

    def setUp(self):
        self.client = dashboard.app.test_client()

    def test_voice_table_structure(self):
        """返回 {code:200, data:{default, voices}}，每项含 voice/name。"""
        payload = self.client.get("/api/tts").get_json()
        self.assertEqual(payload["code"], 200)
        self.assertEqual(payload["data"]["default"], dashboard.DEFAULT_TTS_VOICE)
        voices = payload["data"]["voices"]
        self.assertTrue(3 <= len(voices) <= 5)   # 任务口径：3-5 个自然女声
        for item in voices:
            self.assertIn("voice", item)
            self.assertIn("name", item)

    def test_default_voice_is_xiaoxiao_and_first(self):
        """默认音色为晓晓（zh-CN-XiaoxiaoNeural）且居表首。"""
        self.assertEqual(dashboard.DEFAULT_TTS_VOICE, "zh-CN-XiaoxiaoNeural")
        self.assertEqual(dashboard.EDGE_VOICES[0]["voice"],
                         "zh-CN-XiaoxiaoNeural")

    def test_voice_ids_unique_natural_female(self):
        """音色 id 互不重复（任务点名口径），且全部为 zh-CN 女声 Neural。"""
        ids = [item["voice"] for item in dashboard.EDGE_VOICES]
        self.assertEqual(len(ids), len(set(ids)), msg="音色表存在重复")
        for vid in ids:
            self.assertTrue(vid.startswith("zh-CN-"), msg=vid)
            self.assertTrue(vid.endswith("Neural"), msg=vid)

    def test_default_voice_member_of_table(self):
        """默认音色必须收录在音色表中（前后端下拉口径一致）。"""
        ids = {item["voice"] for item in dashboard.EDGE_VOICES}
        self.assertIn(dashboard.DEFAULT_TTS_VOICE, ids)


class TtsSynthesisTests(unittest.TestCase):
    """POST /api/tts：正常合成、默认音色、分片拼接（全部 mock，离线）。"""

    def setUp(self):
        self.client = dashboard.app.test_client()
        _FakeCommunicate.calls = []

    def test_tts_normal_synthesis_returns_mpeg(self):
        """mock Communicate → 假 audio bytes：200 + audio/mpeg + 分片拼接。"""
        with mock.patch("edge_tts.Communicate", _FakeCommunicate):
            resp = self.client.post("/api/tts",
                                    json={"text": "你好",
                                          "voice": "zh-CN-XiaoyiNeural"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("Content-Type"), "audio/mpeg")
        self.assertEqual(resp.get_data(), b"fake-mp3-chunk")   # 只拼 audio 分片
        self.assertEqual(_FakeCommunicate.calls, [("你好", "zh-CN-XiaoyiNeural")])

    def test_tts_default_voice_without_voice_field(self):
        """未传 voice：走默认音色 zh-CN-XiaoxiaoNeural。"""
        with mock.patch("edge_tts.Communicate", _FakeCommunicate):
            resp = self.client.post("/api/tts", json={"text": "在吗"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(_FakeCommunicate.calls,
                         [("在吗", dashboard.DEFAULT_TTS_VOICE)])

    def test_tts_word_boundary_chunks_not_collected(self):
        """WordBoundary 等非 audio 分片不进音频流（只收集 type==audio）。"""
        with mock.patch("edge_tts.Communicate", _FakeCommunicate):
            resp = self.client.post("/api/tts", json={"text": "x"})

        data = resp.get_data()
        self.assertNotIn(b"WordBoundary", data)   # 桩未产出该类型 audio，天然验证
        self.assertEqual(data, b"fake-mp3-chunk")


class TtsValidationErrorTests(unittest.TestCase):
    """POST /api/tts：空文本 / 方法限制。"""

    def setUp(self):
        self.client = dashboard.app.test_client()

    def test_tts_empty_text_rejected_400(self):
        """text 空：HTTP 400 + 业务码 400 + 中文错误。"""
        resp = self.client.post("/api/tts", json={"text": "   "})
        self.assertEqual(resp.status_code, 400)
        payload = resp.get_json()
        self.assertEqual(payload["code"], 400)
        self.assertIn("文本不能为空", payload["error"])

    def test_tts_missing_body_rejected_400(self):
        """无 JSON 体：同样 400，不 500。"""
        resp = self.client.post("/api/tts")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["code"], 400)

    def test_tts_delete_not_allowed(self):
        """/api/tts 仅 GET/POST：DELETE 返回 405。"""
        resp = self.client.delete("/api/tts")
        self.assertEqual(resp.status_code, 405)


class TtsDependencyTests(unittest.TestCase):
    """依赖缺失与异常降级（红线口径：延迟导入 + 清晰中文提示）。"""

    def setUp(self):
        self.client = dashboard.app.test_client()

    def test_tts_module_missing_returns_501(self):
        """sys.modules 置 None → import 抛 ImportError → 501 + 中文提示。"""
        with mock.patch.dict(sys.modules, {"edge_tts": None}):
            resp = self.client.post("/api/tts", json={"text": "你好"})

        self.assertEqual(resp.status_code, 501)
        payload = resp.get_json()
        self.assertEqual(payload["code"], 501)
        self.assertEqual(payload["error"], "服务端未安装 edge-tts")

    def test_tts_module_missing_does_not_touch_other_routes(self):
        """edge-tts 缺失只影响 /api/tts：/api/history 等照常可用。"""
        with mock.patch.dict(sys.modules, {"edge_tts": None}):
            resp = self.client.get("/api/history")
        self.assertEqual(resp.status_code, 200)

    def test_tts_synthesis_exception_returns_500(self):
        """Communicate 抛异常（模拟断网等）：500 + 含原因的中文错误。"""
        boom = mock.Mock(side_effect=RuntimeError("网络连接超时"))
        with mock.patch("edge_tts.Communicate", boom):
            resp = self.client.post("/api/tts", json={"text": "你好"})

        self.assertEqual(resp.status_code, 500)
        payload = resp.get_json()
        self.assertEqual(payload["code"], 500)
        self.assertIn("语音合成失败", payload["error"])
        self.assertIn("网络连接超时", payload["error"])

    def test_tts_empty_audio_stream_returns_500(self):
        """合成成功但零 audio 分片：500（不给前端空音频）。"""
        with mock.patch("edge_tts.Communicate", _EmptyAudioCommunicate):
            resp = self.client.post("/api/tts", json={"text": "你好"})

        self.assertEqual(resp.status_code, 500)
        self.assertIn("未返回音频数据", resp.get_json()["error"])

    def test_tts_static_no_store_not_applied_to_api(self):
        """no-store 只套静态路由：/api/tts 响应不套用（既有 after_request 口径）。"""
        resp = self.client.get("/api/tts")
        self.assertNotEqual(resp.headers.get("Cache-Control"), "no-store")


if __name__ == "__main__":
    unittest.main()
