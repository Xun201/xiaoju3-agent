# -*- coding: utf-8 -*-
"""game_mode.py · 智能算力调度（两档模式，2026-10-27 队长拍板）。

日常模式：Ollama keep_alive=-1 常驻，本地 r1 可用。
游戏模式：Ollama keep_alive=0 卸载显存，所有请求直发云端。
游戏退出防抖 3 分钟：防切出回消息导致频繁卸载/重载。
安全绳：/mode game / /mode auto QQ 指令手动覆盖。
"""
import json
import os
import threading
import time

SCAN_INTERVAL_SEC = 5
GAME_EXIT_DEBOUNCE_SEC = 180

_lock = threading.Lock()
_game_mode = False
_force_mode = None            # "game" / "auto" / None
_stop = threading.Event()
_THREAD = None
_DATA_DIR = "."


def set_data_dir(d):
    global _DATA_DIR
    _DATA_DIR = os.path.abspath(d or ".")


def is_game_mode():
    with _lock:
        if _force_mode == "game":
            return True
        if _force_mode == "auto":
            return False
        return _game_mode


def get_force_mode():
    with _lock:
        return _force_mode


def set_force_mode(mode):
    with _lock:
        _force_mode = mode


def game_list_path():
    return os.path.join(_DATA_DIR, "game_list.json")


def load_game_list():
    try:
        with open(game_list_path(), "r", encoding="utf-8") as f:
            return [p.lower() for p in json.load(f).get("processes", [])]
    except Exception:
        return []


def save_game_list(processes):
    with open(game_list_path(), "w", encoding="utf-8") as f:
        json.dump({"processes": processes}, f, ensure_ascii=False, indent=2)


def _check_game_processes():
    import psutil
    whitelist = load_game_list()
    if not whitelist:
        return []
    hits = []
    for proc in psutil.process_iter(["name"]):
        try:
            name = (proc.info["name"] or "").lower()
            for w in whitelist:
                if w in name:
                    hits.append(name)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return hits


def _ollama_unload():
    try:
        import requests
        requests.post(
            _env("LOCAL_URL") or "http://127.0.0.1:11434/api/chat",
            json={"model": _env("LOCAL_MODEL") or "deepseek-r1:1.5b",
                  "keep_alive": 0, "messages": []}, timeout=5)
        print("🎮 [game_mode] Ollama 模型已卸载（显存释放）")
    except Exception as e:
        print(f"🎮 [game_mode] Ollama 卸载失败（不影响）: {e}")


def _env(key, default=""):
    return (os.environ.get(key, "") or "").strip()


def _monitor_loop():
    global _game_mode
    game_gone_since = None
    print("🎮 [game_mode] 监控启动（5s 扫描，防抖 3min）")
    while not _STOP.wait(SCAN_INTERVAL_SEC):
        try:
            hits = _check_game_processes()
            now = time.time()
            with _lock:
                if hits and not _game_mode:
                    _game_mode = True
                    game_gone_since = None
                    print(f"🎮 [game_mode] 游戏启动 {hits} → 切游戏模式")
                    _ollama_unload()
                elif not hits and _game_mode:
                    if game_gone_since is None:
                        game_gone_since = now
                    elif now - game_gone_since >= GAME_EXIT_DEBOUNCE_SEC:
                        _game_mode = False
                        game_gone_since = None
                        print("🎮 [game_mode] 防抖 3min 通过 → 切回日常")
                elif hits and _game_mode:
                    game_gone_since = None
        except Exception as e:
            print(f"🎮 [game_mode] 异常: {e}")


def start():
    global _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        return
    _STOP.clear()
    _THREAD = threading.Thread(target=_monitor_loop, daemon=True,
                               name="game_mode_monitor")
    _THREAD.start()


def stop():
    _STOP.set()
