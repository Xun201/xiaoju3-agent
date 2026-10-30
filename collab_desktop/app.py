# -*- coding: utf-8 -*-
"""专属 AI 协作工作台（2026-10-30 队长拍板：停止折腾第三方，用自己的底层能力封装）。

架构：pywebview 独立窗（ui/index.html 三区界面）+ js_api 桥 + CollabHub 内核复用
（SYNC/TASK_BUS 监听 → 三色气泡消息流）+ 老板需求 → DeepSeek 方案 → 写 TASK_BUS
（[老板拍板]+[秘书回复]）→ 包工头经 AGENTS「老板拍板感知」纪律领命。

零配置：DeepSeek Key/路径全部自动读生产环境（.env + 项目根），队长双击即用。
"""
import os
import re
import sys
import threading
import time
import webview   # pywebview

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))   # 仓库根（collab_hub 所在）
_ROOT = os.path.dirname(_HERE)

# 路径（本机工具，env 可覆盖；默认=生产/仓库约定位置）
ENV_PATH = os.environ.get("XIAOJU3_COLLAB_ENV",
                          r"F:\Xunandxiaoju3\xiaoju3_data\.env")
SYNC_PATH = os.environ.get("XIAOJU3_COLLAB_SYNC",
                           r"F:\Orangepi_number3\_dev\SYNC_DEEPSEEK.md")
TASK_PATH = os.environ.get("XIAOJU3_COLLAB_TASK",
                           r"F:\Orangepi_number3\_dev\TASK_BUS.md")


def _load_env():
    env = dict(os.environ)
    try:
        with open(ENV_PATH, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip())
    except Exception:
        pass
    return env


ENV = _load_env()


class BossApi:
    """js_api 桥：前端 window.pywebview.api.* 直接调用。"""

    def __init__(self):
        from collab_hub import CollabHub
        self.hub = CollabHub(sync_path=SYNC_PATH, task_path=TASK_PATH,
                             env=ENV)
        self._deepseek_lock = threading.Lock()

    # ---------- 消息流 ----------
    def history(self):
        return self.hub.snapshot(100)

    def poll(self):
        """前端定时调：驱动一轮文件监听（返回本轮新消息）。"""
        n = self.hub.poll_once()
        return {"new": n, "items": self.hub.snapshot(30)}

    # ---------- 老板发言 ----------
    def send_boss(self, text):
        """老板发言：写 TASK_BUS [老板拍板] 节 + 推流。"""
        r = self.hub.emit_boss(text)
        return r

    # ---------- DeepSeek 方案生成（后台线程，前端轮询取结果） ----------
    def request_plan(self, text):
        """老板需求 → DeepSeek 出方案 → 写 TASK_BUS [秘书回复] 节。
        后台线程跑（云端 10-30s），前端轮询 history 收 secretary 气泡。"""
        text = str(text or "").strip()
        if not text:
            return {"code": 400, "error": "空需求"}
        if not ENV.get("XIAOJU3_BUS_ENABLED") == "1" and \
                ENV.get("DEEPSEEK_API_KEY") is None and \
                ENV.get("CLOUD_KEY") is None:
            return {"code": 500, "error": "未找到 DeepSeek Key"}
        threading.Thread(target=self._plan_worker, args=(text,),
                         daemon=True, name="deepseek-plan").start()
        return {"code": 200, "data": {"queued": True}}

    def _deepseek(self, messages, max_tokens=900):
        """DeepSeek 单轮调用（reasoner 默认=带思维链）。返回
        (content, thinking)；失败抛异常。"""
        import urllib.request
        key = ENV.get("DEEPSEEK_API_KEY") or ENV.get("CLOUD_KEY") or ""
        url = ENV.get("CLOUD_URL") or \
            "https://api.deepseek.com/chat/completions"
        model = ENV.get("CLOUD_MODEL") or "deepseek-reasoner"
        if not key:
            raise RuntimeError("未配置 DeepSeek Key")
        payload = {"model": model, "messages": messages,
                   "stream": False, "temperature": 0.3,
                   "max_tokens": max_tokens}
        req = urllib.request.Request(
            url, data=json_dumps(payload),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json_loads(r.read().decode())
        msg = (body.get("choices") or [{}])[0].get("message", {})
        content = str(msg.get("content") or "").strip()
        thinking = str(msg.get("reasoning_content") or "").strip()
        tk = body.get("usage", {}).get("total_tokens", "?")
        return content, thinking, tk

    def _write_task_section(self, tag, body):
        with open(TASK_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n## [{tag}] {_now_iso()}\n\n{body[:1500]}\n\n---\n")

    def _plan_worker(self, text):
        """两两交流循环（2026-10-30 队长：融合两两互相交流，用户可看见
        工作思维链）：老板需求 → 秘书出方案（思维链抓取）→ 方案落
        TASK_BUS [包工头任务] 节（包工头领命）→ [包工头回执] 出现后秘书
        审查回执（第二轮）→ @老板 总结。全程消息带 thinking 上屏。"""
        with self._deepseek_lock:
            # 第一轮：秘书出方案（reasoner 带思维链）
            try:
                content, thinking, tk = self._deepseek([
                    {"role": "system", "content":
                     "你是小橘3号项目的技术秘书。老板提出了一个需求，请给出"
                     "可直接执行的技术方案：最多 5 条要点，每条一行以「- 」"
                     "开头，简体中文；最后一行写「已派发给包工头，请其领命"
                     "执行并回执」。不确定的明确说不确定，禁止编造。"},
                    {"role": "user", "content": f"【老板原话】{text}"}])
            except Exception as e:
                self.hub._emit("secretary", f"方案生成失败（请重试）: {e}")
                return
            m = {"role": "secretary", "text": content[:1500],
                 "ts": _now_iso(), "hitl": False,
                 "thinking": thinking[:2000], "round": "方案"}
            self.hub._emit("secretary", m["text"], thinking=m["thinking"],
                           round_tag=m["round"])
            # 方案落 TASK_BUS [包工头任务] 节（包工头领命依据）
            self._write_task_section(
                "包工头任务", f"（秘书方案，请包工头领命执行）\n{content[:1200]}"
                f"\n\n【老板原话】{text[:200]}")
            # 第二轮：等包工头回执（轮询 TASK_BUS，最多等 10 分钟）
            self.hub._emit("zcode", "（已收到任务，包工头执行中——回执写入后"
                                    "秘书将自动审查）", round_tag="执行")
            receipt = self._wait_receipt(timeout_s=600)
            if not receipt:
                self.hub._emit("secretary",
                               "包工头暂未回执（超时 10 分钟），任务保持"
                               "在 TASK_BUS，回执到达后我会自动审查。")
                return
            # 第三轮：秘书审查回执（思维链抓取）+ @老板 总结
            try:
                review, r_thinking, r_tk = self._deepseek([
                    {"role": "system", "content":
                     "你是小橘3号项目的技术秘书。包工头对刚才的任务提交了"
                     "回执，请审查：完成质量/遗漏/风险，最多 3 条要点，"
                     "最后给一行「@老板」总结（一句话结论）。简体中文。"},
                    {"role": "user",
                     "content": f"【原任务】{content[:800]}\n"
                                f"【包工头回执】{receipt[:800]}"}],
                    max_tokens=500)
                self._write_task_section("秘书审查", review[:1200])
                self.hub._emit("secretary", review[:1200],
                               thinking=r_thinking[:2000], round_tag="审查")
                self.hub._emit("boss", f"（自动总结）{review.splitlines()[0][:120]}"
                               if review.splitlines() else "（审查完成）")
            except Exception as e:
                self.hub._emit("secretary", f"审查轮失败: {e}")

    def _wait_receipt(self, timeout_s=600):
        """轮询 TASK_BUS 等 [包工头回执] 新节（Signal：ZCode 写回执即触发）。"""
        import re as _re
        deadline = time.time() + timeout_s
        baseline = self._read_receipts()
        while time.time() < deadline:
            time.sleep(5)
            cur = self._read_receipts()
            new = [r for r in cur if r not in baseline]
            if new:
                return new[-1]
        return None

    def _read_receipts(self):
        try:
            with open(TASK_PATH, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception:
            return []
        out = []
        for m in re.finditer(
                r"## \[包工头回执\][^\n]*\n(.*?)(?=\n## |\Z)", text, re.S):
            out.append(m.group(1).strip())
        return out


def json_dumps(obj):
    import json
    return json.dumps(obj).encode("utf-8")


def json_loads(text):
    import json
    return json.loads(text)


def _now_iso():
    return datetime_now()


def datetime_now():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ==================== pywebview 启动 ====================

def _ui_path():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "ui", "index.html")


def main():
    try:
        api = BossApi()
        hub = api.hub
        hub.start()   # 文件监听线程（CollabHub 复用）
        webview.create_window(
            "小橘协作工作台", _ui_path(),
            js_api=api, width=1080, height=760, min_size=(860, 560),
            background_color="#0f172a")
        webview.start(debug=False)
    except Exception:
        import traceback
        err = traceback.format_exc()
        try:
            base = os.path.dirname(sys.executable if getattr(
                sys, "frozen", False) else os.path.abspath(__file__))
            with open(os.path.join(base, "startup_error.log"), "w",
                      encoding="utf-8") as f:
                f.write(err)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
