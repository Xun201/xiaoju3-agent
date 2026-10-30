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
    time.sleep(1.5)
    roles = [m["role"] for m in api.hub.snapshot()]
    assert "secretary" in roles, roles
    last = api.hub.snapshot()[-1]
    assert last.get("options") == ["同意", "先出细节", "暂缓"], last
    assert last.get("summary") == "测试摘要"
    assert "@options" not in last["text"]
    assert "[秘书回复]" in open(app.TASK_PATH, encoding="utf-8").read()
print("④ DeepSeek 方案链 PASS")

print("=== 自测 4/4 全过 ===")
