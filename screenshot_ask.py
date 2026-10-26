# -*- coding: utf-8 -*-
"""UI 三期 · 截图提问（切片 a）：Alt+A 冻结帧划选截图。

流程（队长拍板 A 案 2026-10-26）：全局热键 Alt+A → （生产接线时主窗隐藏
200ms，本模块留 pre_hide/post_show 钩子）→ PIL.ImageGrab 抓虚拟屏全屏
（冻结帧）→ tkinter 全屏无边框遮罩铺冻结帧（暗化 55% 营造模态感）→
鼠标拖拽红框划选 → 松开裁剪 → PNG 存临时目录 → 返回路径；Esc/右键取消。

DPI 硬口径（切片 a 重点）：进程级 Per-Monitor-V2 感知（shcore
SetProcessDpiAwareness(2)，Win7 回退 user32.SetProcessDPIAware）——声明后
鼠标事件坐标、tkinter 几何、ImageGrab 像素三者同为物理像素，125%/150% 缩放
屏不漂移。声明进程内一次有效，重复调用安全吞掉。

线程模型：RegisterHotKey 需要注册线程自带消息泵——start_hotkey_daemon 起
daemon 线程跑 GetMessageW 循环，WM_HOTKEY 回调在该线程执行 snip()（Tk 主体
临时起在该线程，用完即毁，与 pywebview 自有 GUI 线程互不干扰）。

切片 a 验收：真机 Alt+A 框选 → 保存出一张 PNG（见 _dev/_u3_snip_test.py）。
"""
import ctypes
import ctypes.wintypes as _wt
import os
import threading
import time

# ==================== DPI（切片 a 重点） ====================

_DPI_DONE = False


def _ensure_dpi_awareness():
    """进程级 Per-Monitor-V2 感知（物理像素口径）。进程内一次生效，重复
    调用报错吞掉；Win7 无 shcore 回退 SetProcessDPIAware（系统级缩放口径，
    单屏够用）。"""
    global _DPI_DONE
    if _DPI_DONE:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    _DPI_DONE = True


def _virtual_screen_box():
    """虚拟屏原点+尺寸（物理像素）：SM_XVIRTUALSCREEN=76/77/78/79。"""
    user32 = ctypes.windll.user32
    vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
    vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
    return vx, vy, vw, vh


# ==================== 冻结帧抓屏 ====================

def grab_virtual_screen():
    """抓虚拟屏全屏（多屏 all_screens）→ (PIL.Image, (vx, vy))——vx/vy 为
    虚拟屏原点（主屏左侧有副屏时为负），遮罩鼠标坐标换算要用。"""
    _ensure_dpi_awareness()
    from PIL import ImageGrab
    img = ImageGrab.grab(all_screens=True)
    return img, _virtual_screen_box()[:2]


# ==================== 遮罩划选（Tk 临时主体） ====================

_HIDE_DELAY_MS = 200   # 生产接线：主窗隐藏后等合成器刷净再抓屏（队长拍板）


def snip(save_dir=None, pre_hide=None, post_show=None, dark=0.55):
    """阻塞式划选一次：返回 PNG 路径；取消返回 None。

    pre_hide/post_show：生产接线钩子（主窗隐藏/恢复；hide 后内部等
    _HIDE_DELAY_MS 再抓屏）。dark：冻结帧暗化系数（模态感）。
    """
    _ensure_dpi_awareness()
    if pre_hide:
        try:
            pre_hide()
        except Exception:
            pass
        time.sleep(_HIDE_DELAY_MS / 1000.0)
    try:
        return _snip_tk(save_dir, dark)
    finally:
        if post_show:
            try:
                post_show()
            except Exception:
                pass


def _snip_tk(save_dir, dark):
    import io
    import tempfile
    from PIL import Image, ImageEnhance, ImageTk

    img, (vx, vy) = grab_virtual_screen()
    vw, vh = img.size
    frozen = ImageEnhance.Brightness(img).enhance(dark)
    buf = io.BytesIO()
    frozen.save(buf, "PNG")
    buf.seek(0)

    import tkinter as tk
    result = {"path": None}

    root = tk.Tk()
    root.overriderirect(False)
    root.overrideredirect(True)
    root.geometry(f"{vw}x{vh}+{vx}+{vy}")
    root.attributes("-topmost", True)
    root.config(cursor="crosshair", bg="black")

    canvas = tk.Canvas(root, width=vw, height=vh, highlightthickness=0,
                       cursor="crosshair")
    canvas.pack(fill="both", expand=True)
    photo = ImageTk.PhotoImage(frozen, master=root)
    canvas.create_image(0, 0, image=photo, anchor="nw")

    state = {"x0": 0, "y0": 0, "rect": None}

    def _finish(save):
        if save:
            x1, y1 = min(state["x0"], state["x1"]), min(state["y0"], state["y1"])
            x2, y2 = max(state["x0"], state["x1"]), max(state["y0"], state["y1"])
            if x2 - x1 >= 5 and y2 - y1 >= 5:   # 过小视为误触=取消
                crop = img.crop((vx + x1, vy + y1, vx + x2, vy + y2))
                d = save_dir or os.path.join(tempfile.gettempdir(), "xiaoju3_snip")
                os.makedirs(d, exist_ok=True)
                path = os.path.join(
                    d, time.strftime("snip_%Y%m%d_%H%M%S") + ".png")
                crop.save(path, "PNG")
                result["path"] = path
        root.destroy()

    def _press(e):
        state["x0"], state["y0"] = e.x, e.y
        if state["rect"] is not None:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(
            e.x, e.y, e.x, e.y, outline="#dc2626", width=2)

    def _move(e):
        if state["rect"] is not None:
            canvas.coords(state["rect"], state["x0"], state["y0"], e.x, e.y)
            state["x1"], state["y1"] = e.x, e.y

    def _release(e):
        state["x1"], state["y1"] = e.x, e.y
        _finish(save=True)

    def _cancel(_e=None):
        _finish(save=False)

    canvas.bind("<ButtonPress-1>", _press)
    canvas.bind("<B1-Motion>", _move)
    canvas.bind("<ButtonRelease-1>", _release)
    root.bind("<Escape>", _cancel)
    canvas.bind("<Button-3>", _cancel)   # 右键取消（微信同款）
    root.focus_force()
    root.mainloop()
    return result["path"]


# ==================== Alt+A 全局热键（守护线程+消息泵） ====================

_MOD_ALT = 0x0001
_MOD_SHIFT = 0x0004
_VK_A = 0x41
_VK_S = 0x53
_WM_HOTKEY = 0x0312
_HOTKEY_ID = 1

# 降级链（队长口径 2026-10-26：Alt+A 被微信/QQ 等占用是常态——逐个尝试，
# 全部失败打印提示不崩）
_HOTKEY_CANDIDATES = (
    ("Alt+A", _MOD_ALT, _VK_A),
    ("Alt+S", _MOD_ALT, _VK_S),
    ("Alt+Shift+A", _MOD_ALT | _MOD_SHIFT, _VK_A),
)

_BUSY = threading.Lock()


def start_hotkey_daemon(on_done=None, save_dir=None, pre_hide=None,
                        post_show=None):
    """按降级链注册全局热键（Alt+A→Alt+S→Alt+Shift+A），起 daemon 消息泵
    线程。每次触发执行一次 snip（划选中重复按键忽略——busy 锁）；on_done
    (png_path|None) 在热键线程回调。返回 (stop_event, hotkey_name|None)：
    全部注册失败时 hotkey_name=None、仅打印人话提示不抛不崩（stop set 即
    退出泵并注销热键）。"""
    _ensure_dpi_awareness()
    user32 = ctypes.windll.user32
    registered = None
    for name, mod, vk in _HOTKEY_CANDIDATES:
        if user32.RegisterHotKey(None, _HOTKEY_ID, mod, vk):
            registered = (name, mod, vk)
            break
    stop = threading.Event()
    if registered is None:
        print("⚠️ 热键被占用，请修改设置"
              "（已尝试 Alt+A / Alt+S / Alt+Shift+A 均被占用）", flush=True)
        threading.Thread(target=stop.wait, daemon=True).start()
        return stop, None
    name, mod, vk = registered
    print(f"⌨️ 截图热键已注册：{name}（按下即进入划选）", flush=True)

    def _pump():
        msg = _wt.MSG()
        while not stop.is_set():
            # GetMessageW 阻塞泵本线程消息；WM_HOTKEY=划选触发
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r <= 0 or stop.is_set():
                break
            if msg.message == _WM_HOTKEY:
                if _BUSY.acquire(blocking=False):
                    try:
                        path = snip(save_dir=save_dir, pre_hide=pre_hide,
                                    post_show=post_show)
                        if on_done:
                            on_done(path)
                    finally:
                        _BUSY.release()
        user32.UnregisterHotKey(None, _HOTKEY_ID)

    t = threading.Thread(target=_pump, name="xiaoju3-hotkey", daemon=True)
    t.start()
    return stop, name


if __name__ == "__main__":
    # 自测：python screenshot_ask.py —— 触发一次划选（免热键，直接进遮罩）
    path = snip()
    print("PNG:", path if path else "(已取消)")
