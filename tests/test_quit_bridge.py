# -*- coding: utf-8 -*-
"""#264 B2d④ 退出桥单测（desktop_launcher.QuitBridge / ui_pref / NapCat 全杀）。

覆盖：
- ui_pref.json 读写：缺省 ask / 合法值回读 / 损坏文件兜底 ask；
- set_exit_pref：非法 mode 拒绝、合法值落盘；
- quit_app：full_exit=destroy+NapCat 全杀被调+remember 落盘；
  backend_only=NapCat 杀手不被调；非法 mode 拒绝；
- _kill_napcat_all 分类：NapCat*/QQ.exe/cmd(launcher-user) 命中，
  无关进程（explorer/其他 cmd）不误杀。
"""
import json
import os
import tempfile
import unittest
from unittest import mock

import desktop_launcher as dl


class _FakeWindow:
    def __init__(self):
        self.destroyed = False

    def destroy(self):
        self.destroyed = True


class _FakeProc:
    def __init__(self, name, cmdline=None):
        self.info = {"name": name, "cmdline": cmdline or []}
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True


class _FakePsutil:
    def __init__(self, procs):
        self.procs = procs

    def process_iter(self, attrs=None):
        return list(self.procs)

    def wait_procs(self, procs, timeout=None):
        return (procs, [])


class UiPrefTests(unittest.TestCase):
    """ui_pref.json 读写（记住选择持久化——localStorage 关窗即焚禁用）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_uipref_")
        self.path = os.path.join(self.tmp, "ui_pref.json")

    def test_default_ask_when_missing_or_corrupt(self):
        self.assertEqual(dl._load_ui_pref(self.path), {"exit": "ask"})
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("not json {{{")
        self.assertEqual(dl._load_ui_pref(self.path), {"exit": "ask"})

    def test_save_load_roundtrip(self):
        dl._save_ui_pref({"exit": "full_exit"}, self.path)
        self.assertEqual(dl._load_ui_pref(self.path), {"exit": "full_exit"})
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"exit": "full_exit"})


class QuitBridgeTests(unittest.TestCase):
    """QuitBridge：set_exit_pref / quit_app 双方法。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_bridge_")
        self.path = os.path.join(self.tmp, "ui_pref.json")
        self.win = _FakeWindow()
        self.state = {"quitting": None}
        self.killer_calls = []
        self.bridge = dl.QuitBridge(
            lambda: self.win, self.state, out=lambda m: None,
            pref_path=self.path,
            napcat_killer=lambda out=None: self.killer_calls.append(1))

    def test_set_exit_pref_validates_and_persists(self):
        r = self.bridge.set_exit_pref("bogus")
        self.assertFalse(r["ok"])
        r = self.bridge.set_exit_pref("backend_only")
        self.assertTrue(r["ok"])
        self.assertEqual(dl._load_ui_pref(self.path), {"exit": "backend_only"})
        self.assertEqual(self.bridge.get_exit_pref(), "backend_only")

    def test_quit_app_full_exit_destroys_and_remembers(self):
        # NapCat 全杀发生在 main() finally（destroy→start 返回→按 mode 清理），
        # 不在 quit_app 内——接线由 test_finally_dispatch_source_anchor 锁
        r = self.bridge.quit_app("full_exit", remember=True)
        self.assertTrue(r["ok"])
        self.assertTrue(self.win.destroyed)
        self.assertEqual(self.state["quitting"], "full_exit")
        self.assertEqual(dl._load_ui_pref(self.path), {"exit": "full_exit"})

    def test_finally_dispatch_source_anchor(self):
        """main() finally 按 mode 分派：full_exit→_kill_napcat_all；
        backend_only→跳过后端终止；两模式均停监督线程+释放互斥体。"""
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "desktop_launcher.py"),
            encoding="utf-8").read()
        self.assertIn('if mode == "backend_only":', src)
        self.assertIn("ℹ️ 仅退窗口：后端与 NapCat 按你的选择保持运行", src)
        self.assertIn('if mode == "full_exit":', src)
        self.assertIn("_kill_napcat_all(_print)", src)
        self.assertIn("window.events.closing += _on_closing", src)
        self.assertIn("js_api=bridge", src)

    def test_closing_return_semantics_source_anchor(self):
        """#264 B2d④ 修复锚（坑库 #18）：closing 返回值语义——pywebview
        winforms 实锤 should_cancel=closing.set()（任一 handler 返回
        False→取消关闭）。拦截路径必须 return False、放行路径必须
        return True（曾写反致 X 直接关窗、弹窗永不出现）。"""
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "desktop_launcher.py"),
            encoding="utf-8").read()
        self.assertIn("return False   # 取消本次默认关闭", src)
        self.assertIn("return True   # quit_app/legacy 已受理", src)
        self.assertIn("handler 返回 False=取消关闭", src)   # 语义注释在位
        self.assertIn("except Exception:\n            return True", src)   # 异常放行不卡关窗

    def test_quit_app_backend_only_keeps_napcat(self):
        r = self.bridge.quit_app("backend_only")
        self.assertTrue(r["ok"])
        self.assertTrue(self.win.destroyed)
        self.assertEqual(self.state["quitting"], "backend_only")
        self.assertEqual(self.killer_calls, [])   # NapCat 杀手不被调

    def test_quit_app_rejects_invalid_mode(self):
        r = self.bridge.quit_app("bogus")
        self.assertFalse(r["ok"])
        self.assertFalse(self.win.destroyed)
        self.assertIsNone(self.state["quitting"])


class DevAuditTests(unittest.TestCase):
    """#264 B2c a：连点审计（QuitBridge.dev_audit → settings_log）。"""

    def test_dev_audit_writes_and_swallows_errors(self):
        tmp = tempfile.mkdtemp(prefix="xiaoju3_devaudit_")
        import settings_api
        calls = []
        bridge = dl.QuitBridge(lambda: None, {}, out=lambda m: None,
                               pref_path=os.path.join(tmp, "ui_pref.json"),
                               napcat_killer=lambda out=None: None)
        with mock.patch.object(settings_api, "_audit",
                               side_effect=lambda e: calls.append(e)):
            r = bridge.dev_audit("tap7 level=4")
        self.assertTrue(r["ok"])
        self.assertEqual(calls[0]["action"], "dev_mode")
        # 失败静默：_audit 抛错不外溢
        with mock.patch.object(settings_api, "_audit",
                               side_effect=RuntimeError("db gone")):
            r = bridge.dev_audit("tap7")
        self.assertFalse(r["ok"])


class KillNapCatAllTests(unittest.TestCase):
    """_kill_napcat_all 分类锚：NapCat*/QQ.exe/cmd(launcher-user) 命中，
    无关进程不误杀（与 #305 F2「只杀副本」的语义区分点）。"""

    def test_classification_and_no_collar_damage(self):
        napcat = _FakeProc("NapCatWinBootMain.exe")
        qq = _FakeProc("QQ.exe")
        cmd_ghost = _FakeProc("cmd.exe", ["cmd", "/c", "launcher-user.bat"])
        explorer = _FakeProc("explorer.exe")
        other_cmd = _FakeProc("cmd.exe", ["cmd", "/C", "dir"])
        fake = _FakePsutil([napcat, qq, cmd_ghost, explorer, other_cmd])
        killed = dl._kill_napcat_all(psutil_mod=fake)
        self.assertEqual(killed, 3)
        self.assertTrue(napcat.terminated and qq.terminated
                        and cmd_ghost.terminated)
        self.assertFalse(explorer.terminated)
        self.assertFalse(other_cmd.terminated)


if __name__ == "__main__":
    unittest.main()
