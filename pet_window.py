# -*- coding: utf-8 -*-
"""小橘3号 · 独立桌宠窗口（tkinter 方案，零新依赖）。

2026-10-29 队长拍板（方案 A·tkinter，否 PySide6 200MB 方案）：
- 无边框 + 置顶 + 色键透明（magenta 挖空）
- 拖拽移动 + 位置记忆（ui_pref.json）
- 右键菜单：隐藏 / 退出
- 生命周期：主进程退出 → 窗口跟着关（daemon 线程或独立进程）
- 启停：ui_pref.json desktop_pet_enabled 控制（默认 False）

用法：
    python pet_window.py              # 阻塞运行（桌面进程 spawn）
    python pet_window.py --test       # 内置自检（不开窗口）
"""
import json
import os
import sys

try:
    import tkinter as tk
except ImportError:
    tk = None

#: ui_pref.json 路径（与 desktop_launcher._ui_pref_path 同一文件）
_PREF_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "agent_state", "ui_pref.json")

#: 透明色（magenta 作色键——素材中不会出现的颜色）
_TC = "magenta"
#: 素材路径
_PET_IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "assets", "DSniang1.jpg")
#: 默认窗口大小
_PET_SIZE = 200


def _read_pref():
    try:
        with open(_PREF_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_pref(data):
    try:
        tmp = _PREF_PATH + ".pettmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _PREF_PATH)
    except Exception:
        pass


def _enabled():
    return bool(_read_pref().get("desktop_pet_enabled", False))


def _save_pos(x, y):
    pref = _read_pref()
    pref["desktop_pet_x"] = x
    pref["desktop_pet_y"] = y
    _write_pref(pref)


def _load_pos():
    pref = _read_pref()
    return (pref.get("desktop_pet_x"), pref.get("desktop_pet_y"))


def run():
    """创建并运行桌宠窗口（阻塞——调用方需在独立线程/进程）。"""
    if tk is None:
        print("🐾 [pet] tkinter 不可用，桌宠跳过")
        return
    root = tk.Tk()
    root.overrideredirect(True)       # 无边框
    root.attributes("-topmost", True)  # 置顶
    root.config(bg=_TC)
    root.attributes("-transparentcolor", _TC)  # 色键透明

    size = _PET_SIZE
    root.geometry(f"{size}x{size}")

    # 位置恢复或默认右下角
    pos = _load_pos()
    if pos and pos[0] is not None:
        root.geometry(f"+{pos[0]}+{pos[1]}")
    else:
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"+{sw - size - 20}+{sh - size - 60}")

    # 素材（JPG 或 PNG）
    img_label = tk.Label(root, bg=_TC, cursor="hand2")
    img_label.pack(fill="both", expand=True)
    try:
        from PIL import Image as PILImage, ImageTk
        img = PILImage.open(_PET_IMG)
        ratio = size / max(img.width, img.height)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)))
        photo = ImageTk.PhotoImage(img)
        img_label.config(image=photo, width=size, height=size)
        img_label.image = photo   # 防 GC
    except Exception as e:
        # 素材缺失 → 显示 emoji 兜底
        print(f"🐾 [pet] 素材加载失败（emoji 兜底）: {e}")
        img_label.config(text="🦊", font=("Segoe UI Emoji", 48),
                         fg="orange")

    # ── 拖拽 ──
    drag = {"sx": 0, "sy": 0, "wx": 0, "wy": 0, "on": False}

    def on_press(event):
        drag["on"] = True
        drag["sx"] = event.x_root
        drag["sy"] = event.y_root
        drag["wx"] = root.winfo_x()
        drag["wy"] = root.winfo_y()

    def on_move(event):
        if not drag["on"]:
            return
        dx = event.x_root - drag["sx"]
        dy = event.y_root - drag["sy"]
        root.geometry(f"+{drag['wx'] + dx}+{drag['wy'] + dy}")

    def on_release(event):
        if drag["on"]:
            _save_pos(root.winfo_x(), root.winfo_y())
        drag["on"] = False

    img_label.bind("<ButtonPress-1>", on_press)
    img_label.bind("<B1-Motion>", on_move)
    img_label.bind("<ButtonRelease-1>", on_release)

    # ── 右键菜单 ──
    menu = tk.Menu(root, tearoff=0)

    def _hide():
        root.withdraw()

    def _exit():
        _save_pos(root.winfo_x(), root.winfo_y())
        root.destroy()

    menu.add_command(label="🐾 隐藏桌宠", command=_hide)
    menu.add_separator()
    menu.add_command(label="❌ 退出桌宠", command=_exit)

    def on_right_click(event):
        menu.tk_popup(event.x_root, event.y_root)

    img_label.bind("<Button-3>", on_right_click)

    # 关闭时保存位置
    root.protocol("WM_DELETE_WINDOW", _exit)

    root.mainloop()


def selftest():
    """离线自检（不开窗口）：配置读写+模块导入。"""
    import tempfile
    orig = _PREF_PATH
    try:
        import plugins.summary_facts as _sf  # noqa: F401  确认模块链完整
    except ImportError:
        pass
    # 测试 _read_pref / _write_pref 用临时文件
    with tempfile.TemporaryDirectory() as td:
        pf = os.path.join(td, "ui_pref.json")
        import plugins.summary_facts  # noqa: F401  触发 import 链
        _orig = globals()["_PREF_PATH"]
        globals()["_PREF_PATH"] = pf
        try:
            self_data = {"desktop_pet_enabled": True, "desktop_pet_x": 100}
            import json as _json
            with open(pf, "w", encoding="utf-8") as f:
                _json.dump(self_data, f)
            pref = _read_pref()
            assert pref.get("desktop_pet_enabled") is True
            assert pref.get("desktop_pet_x") == 100
            _save_pos(200, 300)
            pref2 = _read_pref()
            assert pref2.get("desktop_pet_x") == 200
            assert pref2.get("desktop_pet_y") == 300
        finally:
            globals()["_PREF_PATH"] = _orig
    print("PET_WINDOW_SELFTEST_OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
    else:
        run()
