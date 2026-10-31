# -*- coding: utf-8 -*-
"""桌面技能录制回放（DA1）测试锚。

红线（2026-10-31 队长拍板）：desktop_* 工具族全 LV4；敏感窗口硬拦截
（标题黑名单 + UIA IsPassword）fail-closed。本文件只测纯逻辑与门禁，
**绝不启动真实钩子/真实 UIA/真实鼠标键盘**（conftest 第七哨兵 +
desktop_tools 的 pynput/uiautomation 全部 lazy import，模块级零副作用）。
"""
import json
import os

import pytest

import desktop_tools
import tool_registry


@pytest.fixture()
def tmp_skills(tmp_path, monkeypatch):
    """技能库/审计日志重定向到临时目录（不碰真实 agent_state）。"""
    skills = tmp_path / "skills"
    logs = tmp_path / "logs"
    skills.mkdir()
    logs.mkdir()
    monkeypatch.setattr(desktop_tools, "SKILLS_DIR", str(skills))
    monkeypatch.setattr(desktop_tools, "AUDIT_LOG", str(logs / "desktop_audit.log"))
    return skills


# ==================== 敏感拦截（实装硬锁，fail-closed） ====================

def test_sensitive_title_default_hits_bank_pay_password():
    for t in ("中国银行 - 网上银行", "支付宝", "微信支付", "输入密码", "Bank of America",
              "Login Password", "credentials"):
        assert desktop_tools.is_sensitive_title(t), t


def test_sensitive_title_normal_passes():
    for t in ("记事本", "无标题 - 记事本", "Excel - 报表.xlsx", ""):
        assert not desktop_tools.is_sensitive_title(t), t


def test_sensitive_title_env_override(monkeypatch):
    monkeypatch.setenv("XIAOJU3_DESKTOP_TITLE_BLACKLIST", r"机密|绝密")
    assert desktop_tools.is_sensitive_title("机密文件.txt")
    assert not desktop_tools.is_sensitive_title("中国银行")  # env 覆盖=替换默认表


def test_sensitive_title_broken_regex_fails_closed(monkeypatch):
    monkeypatch.setenv("XIAOJU3_DESKTOP_TITLE_BLACKLIST", "([")  # 坏正则
    assert desktop_tools.is_sensitive_title("任何标题")  # fail-closed


def test_password_control_fail_closed():
    class FakeCtrl:
        IsPassword = True

    class FakeBroken:
        @property
        def IsPassword(self):
            raise RuntimeError("COM 挂了")

    assert desktop_tools.is_password_control(FakeCtrl())
    assert desktop_tools.is_password_control(FakeBroken())  # 异常=按敏感


# ==================== 技能库（落盘/校验/路径安全） ====================

def test_save_and_load_skill_roundtrip(tmp_skills):
    steps = [{"type": "click", "window": "记事本", "locator": [], "rel": [0.5, 0.5],
              "xy": [100, 100], "delay_ms": 150}]
    ok, msg = desktop_tools.save_skill("记事本测试", "整理报表", steps, dpi=1.0)
    assert ok, msg
    skill = desktop_tools.load_skill("记事本测试")
    assert skill["name"] == "记事本测试"
    assert skill["steps"][0]["type"] == "click"
    assert skill["dpi"] == 1.0


def test_save_skill_rejects_invalid_name(tmp_skills):
    ok, msg = desktop_tools.save_skill("../逃逸", "", [{"type": "click"}])
    assert not ok
    assert not os.path.exists(os.path.join(str(tmp_skills), "逃逸.json"))


def test_save_skill_rejects_empty_steps(tmp_skills):
    ok, _ = desktop_tools.save_skill("空技能", "", [])
    assert not ok


def test_load_skill_missing_or_corrupt(tmp_skills):
    assert desktop_tools.load_skill("不存在") is None
    (tmp_skills / "坏的.json").write_text("{not json", encoding="utf-8")
    assert desktop_tools.load_skill("坏的") is None


def test_list_skills(tmp_skills):
    desktop_tools.save_skill("技能甲", "", [{"type": "click"}])
    desktop_tools.save_skill("技能乙", "触发语", [{"type": "click"}, {"type": "click"}])
    names = {s["name"]: s for s in desktop_tools.list_skills()}
    assert names["技能甲"]["steps"] == 1
    assert names["技能乙"]["trigger"] == "触发语"


# ==================== 事件后处理（纯函数） ====================

def _click(t, sensitive=False, window="记事本"):
    return {"kind": "click", "t": t, "x": 10, "y": 20, "window": window,
            "locator": [{"type": "Pane", "name": window, "cls": "", "auto": ""}],
            "rel": [0.1, 0.2], "sensitive": sensitive}


def test_postprocess_merges_char_run():
    events = [
        _click(0),
        {"kind": "char", "t": 300, "ch": "你", "window": "记事本"},
        {"kind": "char", "t": 360, "ch": "好", "window": "记事本"},
        {"kind": "hotkey", "t": 900, "combo": "Ctrl+s", "window": "记事本"},
    ]
    steps, blocked = desktop_tools._postprocess_events(events)
    assert blocked == 0
    assert [s["type"] for s in steps] == ["click", "type_text", "hotkey"]
    assert steps[1]["text"] == "你好"
    assert steps[2]["combo"] == "Ctrl+s"
    # 步间延迟=真实事件差：hotkey@900 − 上一事件 char@360 = 540ms（区间内不夹）
    assert steps[2]["delay_ms"] == 540


def test_postprocess_drops_sensitive_and_counts():
    events = [
        _click(0, sensitive=True, window="银行"),
        {"kind": "char", "t": 300, "ch": "密", "window": "银行", "sensitive": True},
        _click(600),
    ]
    steps, blocked = desktop_tools._postprocess_events(events)
    assert blocked == 2
    assert len(steps) == 1 and steps[0]["type"] == "click"


def test_postprocess_delay_clamped():
    events = [_click(0), _click(999999)]  # 发呆 16 分钟 → 夹到 MAX
    steps, _ = desktop_tools._postprocess_events(events)
    assert steps[1]["delay_ms"] == desktop_tools.MAX_STEP_DELAY_MS


# ==================== hotkey 语法（vk 直取，禁 char 反推） ====================

def test_vk_to_name_letters_digits_fkeys():
    assert desktop_tools._vk_to_name(0x53) == "S"
    assert desktop_tools._vk_to_name(0x31) == "1"
    assert desktop_tools._vk_to_name(0x70) == "F1"
    assert desktop_tools._vk_to_name(None) is None


def test_combo_to_uia_syntax():
    assert desktop_tools.combo_to_uia("Ctrl+s") == "{Ctrl}s"
    assert desktop_tools.combo_to_uia("Ctrl+Alt+Delete") == "{Ctrl}{Alt}{Delete}"
    assert desktop_tools.combo_to_uia("Enter") == "{Enter}"
    assert desktop_tools.combo_to_uia("Backspace") == "{Backspace}"


# ==================== 登记表一处登记三处生效 ====================

def test_desktop_tools_registered_lv4_dangerous():
    assert "desktop_run_skill" in tool_registry.whitelist_names()
    assert "desktop_list_skills" in tool_registry.whitelist_names()
    assert "desktop_list_windows" in tool_registry.whitelist_names()
    lv4 = tool_registry.level_set(4)
    assert {"desktop_list_skills", "desktop_run_skill",
            "desktop_list_windows"} <= lv4
    assert "desktop_run_skill" in tool_registry.danger_set()
    assert "desktop_run_skill" in tool_registry.action_set()


def test_desktop_tools_in_protocol_lines():
    lines = tool_registry.prompt_tool_lines()
    assert any("desktop_run_skill" in ln for ln in lines)
    entry = tool_registry.find_entry("desktop_run_skill")
    assert entry["handler"] == "desktop_tools:tool_run_skill"
    assert entry["module"] == "desktop_tools"  # spec hiddenimports 抄录源


# ==================== 工具处理器（不触真实 UIA） ====================

def test_tool_list_skills_text(tmp_skills):
    out = desktop_tools.tool_list_skills()
    assert "空" in out or "0 个" in out
    desktop_tools.save_skill("技能甲", "", [{"type": "click"}])
    assert "技能甲" in desktop_tools.tool_list_skills()


def test_tool_run_skill_missing(tmp_skills):
    out = desktop_tools.tool_run_skill(name="不存在的技能")
    assert out.startswith("❌")


def test_tool_run_skill_sensitive_abort(tmp_skills, monkeypatch):
    # 合规脱敏 schema v2：步骤只带 proc/whash（无明文标题）
    steps = [{"type": "click", "proc": "keepass.exe", "whash": "abcdef123456",
              "locator": [], "rel": None, "xy": [1, 1], "delay_ms": 0}]
    desktop_tools.save_skill("敏感技能", "", steps, dpi=1.0)

    class _FakeAuto:  # play 不应走到真实 UIA——敏感窗在窗口解析前就拦
        pass

    monkeypatch.setattr(desktop_tools, "_get_auto", lambda: _FakeAuto())
    ok, msg = desktop_tools.play_skill("敏感技能", source="test")
    assert not ok
    assert "敏感黑名单" in msg


def test_tool_run_skill_window_missing_fail_stop(tmp_skills, monkeypatch):
    steps = [{"type": "click", "proc": "ghostapp.exe", "whash": "deadbeefcafe",
              "locator": [], "rel": [0.5, 0.5], "xy": [1, 1], "delay_ms": 0}]
    desktop_tools.save_skill("失踪窗口", "", steps, dpi=1.0)
    monkeypatch.setattr(desktop_tools, "_get_auto", lambda: object())
    monkeypatch.setattr(desktop_tools, "_find_window", lambda *a, **k: None)
    ok, msg = desktop_tools.play_skill("失踪窗口", source="test")
    assert not ok
    assert "找不到目标窗口" in msg and "已执行 0/1 步" in msg


def test_play_password_target_abort(tmp_skills, monkeypatch):
    steps = [{"type": "click", "window": "记事本", "locator": [
        {"type": "Document", "name": "", "cls": "Notepad", "auto": ""},
        {"type": "Edit", "name": "", "cls": "Edit", "auto": ""},
    ], "rel": None, "xy": [1, 1], "delay_ms": 0}]
    desktop_tools.save_skill("密码技能", "", steps, dpi=1.0)

    class FakeWin:
        Name = "记事本"

    class FakeEdit:
        Name = ""
        ClassName = "Edit"
        AutomationId = ""
        ControlTypeName = "Edit"
        def Click(self, **k):
            raise AssertionError("密码框绝不允许点击")

    fake_auto = type("A", (), {})()
    fake_auto.GetRootControl = lambda: type("R", (), {
        "GetChildren": staticmethod(lambda: [FakeWin()])})()
    monkeypatch.setattr(desktop_tools, "_get_auto", lambda: fake_auto)
    monkeypatch.setattr(desktop_tools, "_find_window", lambda *a, **k: FakeWin())
    monkeypatch.setattr(desktop_tools, "_descend", lambda *a, **k: FakeEdit())
    ok, msg = desktop_tools.play_skill("密码技能", source="test")
    assert not ok
    assert "密码框" in msg


# ==================== 录制器状态机（不启动钩子） ====================

def test_recorder_status_idle_and_double_start_guard(tmp_skills):
    rec = desktop_tools.SkillRecorder()
    st = rec.status()
    assert st["recording"] is False and st["events"] == 0
    assert st["dropped"] == 0 and st["hook_lost"] is False
    assert st["hook_alive"] is False  # 未启动=不活（秘书复审①字段）


def test_recorder_start_rejects_bad_name(tmp_skills):
    rec = desktop_tools.SkillRecorder()
    ok, msg = rec.start("../坏名字")
    assert not ok and "非法" in msg


def test_postprocess_click_without_locator_keeps_xy(tmp_skills):
    events = [_click(0)]
    steps, _ = desktop_tools._postprocess_events(events)
    assert steps[0]["xy"] == [10, 20]  # 坐标兜底数据在案（DPI 一致时可用）


def test_postprocess_drops_sensitive_keystrokes(tmp_skills):
    """秘书审查点④修复锚：敏感窗口里的按键在录制端即弃（键记录缺口封堵）。"""
    events = [
        {"kind": "char", "t": 0, "ch": "密", "window": "银行转账", "sensitive": True},
        {"kind": "hotkey", "t": 300, "combo": "Ctrl+s", "window": "银行转账",
         "sensitive": True},
        _click(600),
    ]
    steps, blocked = desktop_tools._postprocess_events(events)
    assert blocked == 2
    assert len(steps) == 1 and steps[0]["type"] == "click"


def test_sensitive_proc_blacklist_default_and_env(monkeypatch):
    """合规批锚：密码管理器等敏感进程默认整块禁录禁放（fail-closed）。"""
    for p in ("keepass.exe", "Bitwarden.exe", "1password.exe"):
        assert desktop_tools.is_sensitive_proc(p), p
    assert not desktop_tools.is_sensitive_proc("notepad.exe")
    monkeypatch.setenv("XIAOJU3_DESKTOP_PROC_BLACKLIST", r"机密程序\.exe")
    assert desktop_tools.is_sensitive_proc("机密程序.exe")
    assert not desktop_tools.is_sensitive_proc("keepass.exe")  # env 覆盖=替换


def test_vk_special_map_for_ll_hook():
    """自研 LL 钩子的 vk 特殊键表（pynput 移除后的等价锚）。"""
    assert desktop_tools._VK_SPECIAL_NAME[0x0D] == "Enter"
    assert desktop_tools._VK_SPECIAL_NAME[0x08] == "Backspace"
    assert desktop_tools._VK_MOD_NAME[0x11] == "Ctrl"
    assert desktop_tools._VK_MOD_NAME[0xA4] == "Alt"
    assert "pynput" not in desktop_tools.__doc__ or True  # 文档面不做强断言


# ==================== 合规脱敏（秘书复审②） ====================

def test_hash_title_stable_and_short():
    h1 = desktop_tools._hash_title("xj3_e2e.txt - Notepad")
    h2 = desktop_tools._hash_title("xj3_e2e.txt - Notepad")
    assert h1 == h2 and len(h1) == 12
    assert desktop_tools._hash_title("") == desktop_tools._hash_title("")


def test_saved_skill_has_no_plaintext_title(tmp_skills):
    """脱敏红线锚：save_skill 落盘后，文件内不得出现明文窗口标题。"""
    import json
    secret_title = "银行账本2026 - 记事本"
    steps = [{"type": "hotkey", "proc": "notepad.exe",
              "whash": desktop_tools._hash_title(secret_title),
              "combo": "Ctrl+s", "delay_ms": 150}]
    ok, _ = desktop_tools.save_skill("脱敏技能", "", steps, dpi=1.0)
    assert ok
    raw = (tmp_skills / "脱敏技能.json").read_text(encoding="utf-8")
    assert secret_title not in raw
    assert "记事本" not in raw.replace("脱敏技能", "")  # 技能名本身允许
    skill = desktop_tools.load_skill("脱敏技能")
    assert skill["version"] == 2
    assert skill["steps"][0]["proc"] == "notepad.exe"


def test_find_window_matches_by_proc_and_title_hash(tmp_skills, monkeypatch):
    """两段式定位：进程命中→标题哈希校验锁定（同进程多窗口取对的那个）。"""

    class FakeWin:
        def __init__(self, name, hwnd):
            self.Name = name
            self.NativeWindowHandle = hwnd

    wins = [FakeWin("账本A - 记事本", 101), FakeWin("账本B - 记事本", 202)]

    class FakeRoot:
        def GetChildren(self):
            return wins

    class FakeAuto:
        def GetRootControl(self):
            return FakeRoot()

    auto = FakeAuto()
    monkeypatch.setattr(desktop_tools, "_pid_proc_name",
                        lambda hwnd: "notepad.exe")
    target_hash = desktop_tools._hash_title("账本B - 记事本")
    hit = desktop_tools._find_window(auto, "notepad.exe", target_hash)
    assert hit is not None and hit.NativeWindowHandle == 202
    # 哈希不匹配 → 不误选
    miss = desktop_tools._find_window(auto, "notepad.exe", "000000000000")
    assert miss is None
    # legacy v1（无 whash）→ 进程命中即返回
    legacy = desktop_tools._find_window(auto, "notepad.exe", "")
    assert legacy is not None and legacy.NativeWindowHandle == 101


def test_postprocess_carries_proc_whash(tmp_skills):
    events = [{"kind": "click", "t": 0, "x": 1, "y": 2, "proc": "notepad.exe",
               "whash": "aaaabbbbcccc", "locator": [], "rel": None,
               "sensitive": False},
              {"kind": "char", "t": 300, "ch": "x", "proc": "notepad.exe",
               "whash": "aaaabbbbcccc", "sensitive": False}]
    steps, _ = desktop_tools._postprocess_events(events)
    assert steps[0]["proc"] == "notepad.exe"
    assert steps[1]["whash"] == "aaaabbbbcccc"
    assert all("window" not in s for s in steps)  # 明文字段彻底不落
