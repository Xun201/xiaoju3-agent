# -*- coding: utf-8 -*-
"""collab_desktop 逻辑自测（bypass webview，零联网）"""
import importlib.util, os, sys, tempfile, time
import unittest
from unittest import mock
import urllib.request

spec = importlib.util.spec_from_file_location(
    "app", r"F:\Orangepi_number3\collab_desktop\app.py")
app = importlib.util.module_from_spec(spec)
sys.modules.setdefault('webview', type(sys)('webview'))
spec.loader.exec_module(app)

tmp = tempfile.mkdtemp(prefix="xj3_dt_")
app.SYNC_PATH = os.path.join(tmp, "SYNC.md")
app.TASK_PATH = os.path.join(tmp, "TASK_BUS.md")
with open(app.SYNC_PATH, "w", encoding="utf-8") as f:
    f.write("# SYNC\n")
with open(app.TASK_PATH, "w", encoding="utf-8") as f:
    f.write("# TASK_BUS\n")
api = app.BossApi()
api.hub.sync_path = app.SYNC_PATH
api.hub.task_path = app.TASK_PATH
print("DEBUG hub.task_path =", api.hub.task_path)
print("DEBUG app.TASK_PATH =", app.TASK_PATH)

# ① send_boss
r = api.send_boss("给协作面板加导出功能")
assert r["code"] == 200, r
print("DEBUG send 后文件头 =", repr(open(app.TASK_PATH, encoding="utf-8").read()[:80]))
assert "[老板拍板]" in open(app.TASK_PATH, encoding="utf-8").read()
assert api.hub.snapshot()[-1]["role"] == "boss"
print("① send_boss PASS")

# ② 无 Key 门
saved_key = app.ENV.get("DEEPSEEK_API_KEY")
app.ENV["DEEPSEEK_API_KEY"] = None
app.ENV.pop("CLOUD_KEY", None)
r2 = api.request_plan("测试需求")
assert r2["code"] == 500, r2
app.ENV["DEEPSEEK_API_KEY"] = saved_key
print("② 无 Key 门 PASS")

# ③ poll
r3 = api.poll()
assert "new" in r3 and "items" in r3
print("③ poll PASS")


# ④ DeepSeek 方案链（mock urlopen）
class FakeResp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def read(self):
        import json as _j
        return _j.dumps({"choices": [{"message": {"content":
            "- 方案要点一\n- 方案要点二\n@options: 同意|先出细节|暂缓"
            "\n@summary: 测试摘要\n@老板 请确认"}}]}).encode()


with mock.patch.object(urllib.request, "urlopen",
                       lambda req, timeout=None: FakeResp()):
    r4 = api.request_plan("给面板加导出")
    assert r4["code"] == 200, r4
    time.sleep(2.0)
    tb = open(app.TASK_PATH, encoding="utf-8").read()
    assert "## [包工头任务]" in tb, "包工头任务节缺失"
    roles = [m["role"] for m in api.hub.snapshot()]
    assert "secretary" in roles and "zcode" in roles, roles
print("④ request_plan 新编排 PASS（方案+派单+zcode 状态）")

# ⑤ 两两交流循环 Mock：reasoning_content 抓取+包工头回执触发审查轮
import collab_hub as _ch
with mock.patch.object(_ch.CollabHub, "start", lambda self: None):
    api2 = app.BossApi()
api2.hub.sync_path = app.SYNC_PATH
api2.hub.task_path = app.TASK_PATH
api2.hub._sync_hash = None

calls = {"n": 0}
class SeqResp:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def __init__(self, content, reasoning): self.c, self.r = content, reasoning
    def read(self):
        import json as _j
        return _j.dumps({"choices": [{"message": {
            "content": self.c, "reasoning_content": self.r}}],
            "usage": {"total_tokens": 100}}).encode()

seq = [("秘书方案正文（第一轮）", "第一轮思维链：拆解老板需求…"),
       ("审查意见：回执合格（第三轮）", "第三轮思维链：核对回执…")]
def fake_urlopen_seq(req, timeout=None):
    c, r = seq[min(calls["n"], len(seq)-1)]
    calls["n"] += 1
    return SeqResp(c, r)

# 预置一条包工头回执在 TASK_BUS（模拟 ZCode 已交回执）
receipt_text = "回执：任务已完成，改动 3 文件测试全绿"
with open(app.TASK_PATH, "a", encoding="utf-8") as f:
    f.write("\n## [包工头回执] 2026-10-30 19:00:00\n\n"
            + receipt_text + "\n\n---\n")

with mock.patch.object(urllib.request, "urlopen", fake_urlopen_seq), \
     mock.patch.object(app.BossApi, "_wait_receipt",
                       lambda self, timeout_s=600: receipt_text):
    r5 = api2.request_plan("整理本周三个 bug 修复摘要")
    assert r5["code"] == 200, r5
    time.sleep(2.5)

hist = api2.hub.snapshot()
roles = [m["role"] for m in hist]
thinks = [m for m in hist if m.get("thinking")]
assert "secretary" in roles, roles
assert len(thinks) >= 2, f"思维链应 ≥2 条: {len(thinks)}"
assert any("第一轮思维链" in m["thinking"] for m in thinks), "方案轮思维链缺失"
assert any("第三轮思维链" in m["thinking"] for m in thinks), "审查轮思维链缺失"
assert "## [包工头任务]" in open(app.TASK_PATH, encoding="utf-8").read()
assert "## [秘书审查]" in open(app.TASK_PATH, encoding="utf-8").read()
print("⑤ 两两交流循环 PASS（思维链 2 条+包工头任务+秘书审查三节全落）")
print("=== 自测 5/5 全过 ===")
