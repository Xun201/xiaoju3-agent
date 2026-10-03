# -*- coding: utf-8 -*-
"""小橘3号 · 首装引导探针模块（安装器方案步 A3，docs/INSTALLER_STEP_A_DESIGN.md §3.2）。

四探针全部**复用既有实现**，不重写检测逻辑：
- ollama：brain.probe_local()（1 秒超时返回 bool）；
- napcat：xiaoju3_launcher._napcat_running（ensure_napcat 的 running_fn 缺省
  实现，进程名扫描→6099 端口回退；**只检测不拉起**，拉起仍是 ensure_napcat）；
- home_assistant：home_tools._headers()（Bearer 组装单源）+ GET {HA_URL}/api/；
- deepseek：validate_deepseek_key（本地格式校验，sk- 前缀 + 长度，不联网）。

约束：探针**只读**——不写盘、不拉任何服务、不改任何配置；四探针并发执行
（ThreadPoolExecutor），总耗时 = 最慢者（首装 UI 即时显示口径）。
本模块被 dashboard 路由延迟导入（/api/first_run/*），不影响既有依赖面。
"""
import concurrent.futures
import os
import re

import requests

import brain
import home_tools
import xiaoju3_launcher as _xl
from xiaoju3 import CLOUD_KEY, ENV_FILE  # CLOUD_KEY 即 env 键 DEEPSEEK_API_KEY

# 跳过标记（方案 C：后端文件承载，彻底弃用 localStorage——容器差异免疫）：
# 与 ENV_FILE 同根（数据根 xiaoju3_data/），.env 落盘时由 complete 顺手清除
SKIP_FLAG_FILE = os.path.join(os.path.dirname(ENV_FILE), ".first_run_skipped")

# 安装器意向报告（步 B3a 产出：iss DeinitializeSetup 每次安装会话覆写，
# 内容=时间戳 + 硬件自检建议 + ollama/napcat/ha 三意向；与跳过标记同根=数据根，
# frozen 下即安装器写入的 {app}\xiaoju3_data\installer_report.txt，路径逐字节对齐）
INSTALLER_REPORT_FILE = os.path.join(os.path.dirname(ENV_FILE), "installer_report.txt")

_PROBE_TIMEOUT = 5          # HA /api/ 探测超时（秒）；Ollama 探针自带 1s
_DEEPSEEK_KEY_MIN_LEN = 30  # DeepSeek key 形态：sk- 前缀 + 充分长度


def is_first_run():
    """首装判定（单一事实源在文件）：.env 不存在 且 无跳过标记文件。"""
    if os.path.exists(ENV_FILE):
        return False
    return not os.path.exists(SKIP_FLAG_FILE)


def mark_skipped():
    """写跳过标记（空文件）。失败抛 OSError（调用方提示用户重试）。"""
    os.makedirs(os.path.dirname(SKIP_FLAG_FILE), exist_ok=True)
    with open(SKIP_FLAG_FILE, "w", encoding="utf-8") as f:
        f.write("")


def clear_skipped():
    """清除跳过标记（complete 成功落盘时调用）；文件不存在则静默跳过。"""
    try:
        os.remove(SKIP_FLAG_FILE)
    except OSError:
        pass


def validate_deepseek_key(key):
    """DeepSeek key 本地格式校验：sk- 前缀 + 长度 ≥ 30。不做网络验证
    （可选"测试连接"属调用方）。"""
    k = str(key or "").strip()
    return k.startswith("sk-") and len(k) >= _DEEPSEEK_KEY_MIN_LEN


def _probe_ollama():
    """本地大脑探针：复用 brain.probe_local（1s 超时）。"""
    try:
        ok = bool(brain.probe_local())
    except Exception:
        ok = False
    detail = ("本地大脑在线，完整版本地优先可用" if ok
              else "未检测到本地 Ollama（可选项，可稍后安装，不影响云端使用）")
    return {"ok": ok, "detail": detail}


def _probe_napcat():
    """NapCat/QQ 探针：复用 _napcat_running（只检测，绝不拉起）。"""
    try:
        ok = bool(_xl._napcat_running())
    except Exception:
        ok = False
    detail = ("NapCat/QQ 侧已就绪" if ok
              else "未检测到 NapCat 运行（可稍后安装，setup_napcat.bat 一键装配）")
    return {"ok": ok, "detail": detail}


def _probe_ha():
    """Home Assistant 探针：复用 home_tools._headers（Bearer 单源）。
    HA_URL 未配置属可选项，灰显跳过而非失败。"""
    url = str(getattr(home_tools, "HA_URL", "") or "").strip()
    if not url:
        return {"ok": False,
                "detail": "未配置（可选项：填 HA_URL/HA_TOKEN 后启用主动服务心跳）"}
    try:
        r = requests.get(url.rstrip("/") + "/api/",
                         headers=home_tools._headers(), timeout=_PROBE_TIMEOUT)
        ok = r.status_code == 200
    except Exception:
        ok = False
    detail = ("Home Assistant 连通正常，主动服务心跳可用" if ok
              else "Home Assistant 暂不可达（可选项，检查 HA_URL/HA_TOKEN 或稍后再试）")
    return {"ok": ok, "detail": detail}


def _probe_deepseek():
    """DeepSeek 探针：当前进程内 key 的格式校验（写完 .env 需重启生效，
    见方案 §3.4——本探针如实报告当前进程态）。"""
    ok = validate_deepseek_key(CLOUD_KEY)
    detail = ("云端大脑已配置（sk- key 格式校验通过）" if ok
              else "未配置 DeepSeek key（云端对话必需：按引导注册并填写）")
    return {"ok": ok, "detail": detail}


def run_probes():
    """四探针并发执行，固定顺序聚合（UI 展示顺序稳定）。"""
    probes = [
        ("ollama", _probe_ollama),
        ("napcat", _probe_napcat),
        ("home_assistant", _probe_ha),
        ("deepseek", _probe_deepseek),
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(probes)) as ex:
        futures = [ex.submit(fn) for _, fn in probes]
        results = [{"name": name, **fut.result()}
                   for (name, fn), fut in zip(probes, futures)]
    return results


# 安装器意向报告解析（步 B3 消费端，docs/INSTALLER_STEP_B3_CONSUMER_DESIGN.md §2.1）
_TIER_HINT_PREFIX = "硬件自检建议: "
_INTENT_KEYS = ("ollama", "napcat", "ha")
_INTENT_LINE_RE = re.compile(r"^(ollama|napcat|ha)=(1|0)$")


def parse_installer_report(text):
    """解析安装器意向报告文本（纯函数）→
    {"installed_at": str|None, "tier_hint": str|None,
     "intents": {"ollama": True|False|None, "napcat": …, "ha": …}}

    行规则：文案/布尔行先归类（"硬件自检建议: " 前缀行 → tier_hint；
    ^(ollama|napcat|ha)=(1|0)$ 严格取布尔，其余值不匹配 → None 未知）；
    首个无法归类的非空行 = installed_at（安装器 5 行格式恒为行 1 时间戳；
    缺时间戳行时布尔/文案行仍各归其位，不误吞）；其余行忽略。
    解析全程异常不外抛，逐项降级为 None。"""
    result = {"installed_at": None, "tier_hint": None,
              "intents": {key: None for key in _INTENT_KEYS}}
    try:
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(_TIER_HINT_PREFIX):
                result["tier_hint"] = line[len(_TIER_HINT_PREFIX):].strip() or None
                continue
            matched = _INTENT_LINE_RE.match(line)
            if matched:
                result["intents"][matched.group(1)] = matched.group(2) == "1"
                continue
            if result["installed_at"] is None:
                result["installed_at"] = line
    except Exception:
        pass
    return result


def read_installer_report():
    """读取安装器意向报告（只读，绝不外抛）→ {"available": bool, ...}。

    文件缺失/读盘失败/解析异常一律 {"available": False}（便携 exe /
    python 直跑 / 升级后无报告=非安装形态，前端 hints 块保持隐藏）。
    编码回退 utf-8 → gbk：Inno 6 SaveStringToFile 的 S 参是 AnsiString，
    中文按系统 ANSI 代码页落盘（中文 Windows=GBK），utf-8 严格读会炸。"""
    try:
        with open(INSTALLER_REPORT_FILE, "rb") as f:
            raw = f.read()
    except OSError:
        return {"available": False}
    text = None
    for encoding in ("utf-8", "gbk"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            text = None
    if text is None:
        # utf-8 读 GBK 字节可能无声误读为乱码（非异常），但报告仅作展示，
        # 三布尔行纯 ASCII 不受影响，故 errors="replace" 兜底可接受。
        text = raw.decode("utf-8", errors="replace")
    try:
        parsed = parse_installer_report(text)
    except Exception:
        return {"available": False}
    return {"available": True, **parsed}
