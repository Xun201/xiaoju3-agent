# -*- coding: utf-8 -*-
"""小橘3号 · 云端视觉模型点击。

按《架构设计文档》§5 安卓接管三件套之三：ADB 截图 → 发视觉模型
（OpenAI 兼容 chat/completions 格式）识别元素 Bounding Box 像素坐标 →
换算真实屏幕坐标 → adb_tap 点击。模型名与密钥来自 xiaoju3 配置
（VISION_MODEL / VISION_KEY，.env → 环境变量优先），未配置时返回清晰
中文提示串，不崩溃。

调用方式：阿里云官方推荐的 OpenAI 兼容 SDK（openai 库，base_url 指向
业务空间域名）。新版 sk-ws- 密钥对手工构造的 requests.post 请求会直接
重置连接（ConnectionResetError 10054），SDK 的请求头/签名机制才能通过。
配置统一从 xiaoju3 读取（VISION_API_URL / VISION_KEY / VISION_MODEL），
旧环境变量 VISION_URL 向后兼容覆盖。

健壮性：请求超时 5 秒（网络异常时快速失败，避免长时间卡顿）；网络类
错误（连接被重置/超时等）默认不重试——网络层被重置时重试大概率仍失败
（VISION_MAX_RETRIES=0，重试循环骨架保留，恢复重试只需调大该常量）。

404 容错（2026-09-30 用户指令）：VISION_MODEL 报 404（模型不存在，如
qwen-vl-max-latest 下线/更名）时，按 VISION_FALLBACK_MODELS 备用列表
自动切换重试（去重保序，每个模型独立受网络重试约束）；403 等鉴权/域名
错误换模型无用，不回退、立即诊断；全部候选耗尽才报终态 404（返回串
括号内附已尝试模型列表，控制台诊断块同）。

模型名预检（2026-10-01 用户指令）：vision_tap_element 在构造请求前
检查配置的 VISION_MODEL 名是否含 "vl"（大小写不敏感），不含时打印
一行 ⚠️ 警告（推荐 qwen-vl-max-latest 或 qwen-vl-plus）——只警告不
阻断：用户也可能填了其他厂商带视觉能力但名字不含 vl 的模型。背景：
纯文本模型（如 qwen3.5-122b-a10b）被误填进 VISION_MODEL 时，模型看
不懂截图会一直返回"未找到"。

提示词（2026-10-01 用户指令）：中文屏幕识别友好的结构化指令——中文名
优先匹配、忽略状态栏与桌面小组件、应用列表/文件夹逐屏排查、强制只输出
点击点 JSON {"x": 数字, "y": 数字}（屏幕绝对坐标）；找不到时按约定输出
{"x": -1, "y": -1}，解析端返回明确"未找到"失败文案，而非编造坐标。
输出格式段另加两条硬约束：直接输出 JSON 本体、不要用 ```json 等代码
块包裹；"x" 与 "y" 每个值都必须带键名、数字不加引号（附正例）。

坐标解析容错（2026-10-01 用户指令）：视觉模型实测存在多种输出格式
（用户实测 {"x1": [69, 514, 312, 547]} 值为数组导致旧解析报"未能识别
出坐标"），统一由纯函数 _extract_click_point 按优先级解析为点击点
（标准框 / bounds 数组 / x1 值为数组 / 直接 x+y，数值 int/float/数字
字符串均可），畸形输入返回 None 不崩溃，详见函数 docstring。
解析前统一经 _clean_json_candidates 清洗（markdown ```json 围栏剥离
→ 提取 {} 候选 → 纯数字引号串剥引号 → 缺 "y" 键时给末尾裸数字补键，
针对用户实测 ```json 包裹的 {"x": 246, "531"}）；清洗函数为解析与
失败诊断共用。解析失败时控制台打印两行 ⚠️ 诊断（原始返回内容 /
清洗后的 JSON 候选，均截断 300，只进控制台），聊天框返回串不变。

返回口径（2026-09-30 用户指令，聊天框一律极简、不带任何排查指引）：
- 网络类失败返回 `❌ 视觉模型网络连接失败，操作已中止。`，控制台仅打印
  一行简短提示（❌ 视觉模型网络连接失败: 简短原因）；
- 403 等 HTTP 状态错误返回 `❌ 视觉模型调用失败: HTTP {status}，操作
  已中止。`；404 在备用模型耗尽后返回 `❌ 视觉模型调用失败: HTTP 404，
  操作已中止。（已尝试模型: a/b/c）`；中文诊断块（完整请求 URL、HTTP
  状态码、错误摘要截断 + 密钥脱敏与 .env 三项配置排查指引）只进控制台、
  不进聊天框——那是配置问题，用户需要诊断信息，但聊天框不堆指引。
- 未找到例外（2026-10-01 用户指令）：模型按约定输出全 -1（屏幕上没有
  目标）时，"❌ 视觉模型在屏幕上未找到【…】。"后附加一句兜底排查引导
  （亮屏/停留目标页面 + VISION_MODEL 须为真正的视觉模型）——这是用户
  明确要求的"模型说没找到"场景引导，与"网络失败文案瘦身"口径不冲突
  （瘦的是网络失败路径）。

与参考实现的差异：依赖白名单无 Pillow，跳过"裁剪状态栏 + 压缩缩放"
优化，直接发送截图 PNG base64；缩放比经 PNG 头解析实际宽度换算
（screencap 原图与屏幕等分辨率时恒为 1），坐标换算公式保持参考实现
结构（center / scale_ratio + cropped_top，此处无裁剪 cropped_top=0）。
"""
import base64
import json
import os
import re
import subprocess
import time

from adb_tools import adb_screenshot, adb_tap, SCREENSHOT_PATH
from xiaoju3 import VISION_MODEL, VISION_KEY, VISION_API_URL

# 官方 SDK：延迟可用性检查——未安装时模块仍可导入，调用时给清晰中文提示
try:
    from openai import OpenAI as _OpenAIClient
    import openai as _openai
except ImportError:  # pragma: no cover - 依赖缺失场景
    _OpenAIClient = None
    _openai = None

# 排查指引：只进控制台诊断日志，不随错误串返回聊天框（2026-09-30 用户指令）
_GUIDANCE_FULL = (
    "请检查 .env 中 VISION_API_URL（新版百炼业务空间专属域名）、"
    "VISION_KEY（sk-ws- 开头的新版 Key 需配专属域名）"
    "与 VISION_MODEL（如 qwen-vl-max-latest）三项配置"
)

VISION_TIMEOUT = 5.0    # 单次请求超时（秒）：网络异常时快速失败，避免长时间卡顿
# 网络类错误自动重试次数（指数退避 1s/2s）。当前置 0 = 不重试：网络层被
# 重置时重试大概率仍失败，只会叠加等待拖慢响应。重试循环骨架保留，
# 未来想恢复重试只需把该值调回 1 或 2，无需改代码。
VISION_MAX_RETRIES = 0

# 备用视觉模型列表（阿里云百炼通用可用模型，顺序即回退顺序）：当前配置
# 的 VISION_MODEL 报 404（模型不存在）时按序自动切换重试；403 等鉴权/
# 域名问题换模型无用，不回退。全部候选耗尽才报终态 404。
VISION_FALLBACK_MODELS = ("qwen-vl-plus", "qwen-vl-max", "qwen-vl-max-latest")


def _mask_key(key):
    """密钥脱敏：仅显示前 6 位 + 掩码，防止 Key 泄漏到控制台。"""
    if not key:
        return "(空)"
    return key[:6] + "****"


def _vision_endpoint():
    """解析视觉请求端点 URL（诊断展示与旧变量兼容，选定顺序）：

    1. 旧环境变量 VISION_URL（完整端点 URL）→ 原样使用。它是老用户的显式
       覆盖入口，必须保持"设了即生效"；新配置 xiaoju3.VISION_API_URL 恒有
       缺省值，若让它无条件压过旧名，旧变量将永不生效，故旧名优先。
    2. 否则新配置 base（VISION_API_URL，已含 /compatible-mode/v1）→
       rstrip('/') 后拼 /chat/completions：防双段路径/丢段；base 若已被误
       填成完整端点则原样返回，不重复追加。
    """
    legacy = os.environ.get("VISION_URL")
    if legacy:
        print(f"⚠️ 检测到旧环境变量 VISION_URL，已覆盖视觉端点: {legacy}")
        return legacy
    base = VISION_API_URL.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _client_base_url():
    """SDK 客户端的 base_url：OpenAI 客户端会自动追加 /chat/completions，
    因此必须剥掉端点尾段（旧 VISION_URL 若为完整端点同样剥除）。"""
    endpoint = _vision_endpoint()
    suffix = "/chat/completions"
    if endpoint.endswith(suffix):
        return endpoint[: -len(suffix)]
    return endpoint


def _print_request_failure(endpoint, status, body_summary, note=None):
    """请求失败时打印中文诊断块（错误摘要截断 + 密钥脱敏，防泄漏）。
    note：附加诊断行（如 404 备用模型耗尽时的已尝试模型列表）。"""
    lines = [
        "❌ 视觉模型请求失败",
        f"  请求 URL: {endpoint}",
        f"  HTTP 状态码: {status}",
        f"  响应体摘要: {body_summary}",
    ]
    if note:
        lines.append(f"  {note}")
    lines += [
        f"  密钥(脱敏): {_mask_key(VISION_KEY)}",
        f"  排查指引: {_GUIDANCE_FULL}",
    ]
    print("\n".join(lines))


def _is_network_error(e):
    """是否网络类错误（可重试）：连接被重置/超时等。ConnectionResetError
    （10054）是 ConnectionError 子类，天然覆盖。"""
    if _openai is not None and isinstance(
            e, (_openai.APIConnectionError, _openai.APITimeoutError)):
        return True
    return isinstance(e, (ConnectionError, TimeoutError))


def _http_status_of(e):
    """从异常中提取 HTTP 状态码；非 HTTP 层错误返回 None。"""
    if _openai is not None and isinstance(e, _openai.APIStatusError):
        return getattr(e, "status_code", None) or "未知"
    return None


def _error_body_of(e):
    """从异常中提取服务端错误摘要（截断 + 密钥脱敏）。"""
    body = str(getattr(e, "body", None) or getattr(e, "message", "") or e)
    body = " ".join(body.split())[:200]
    if VISION_KEY and VISION_KEY in body:
        body = body.replace(VISION_KEY, _mask_key(VISION_KEY))
    return body


def _short_reason(e):
    """网络类错误的简短原因（折叠空白 + 截断，供单行提示使用）。"""
    reason = " ".join(str(e).split())
    return reason[:120] or type(e).__name__


def _model_candidates():
    """模型尝试序列：配置模型优先，其后按 VISION_FALLBACK_MODELS 顺序
    补充未出现过的备用模型（去重保序），供 404 自动回退。"""
    return [VISION_MODEL] + [
        m for m in VISION_FALLBACK_MODELS if m != VISION_MODEL]


def _create_with_network_retry(client, model, messages):
    """单模型调用 + 网络类重试骨架（VISION_MAX_RETRIES，当前 0 = 不重试）。

    返回 (response, error)：成功时 error 为 None；失败时 response 为 None，
    网络类错误按 VISION_MAX_RETRIES 指数退避重试后仍失败则原样交还调用方
    统一分类处理（404 换模型 / 403 诊断 / 网络简短文案）。"""
    attempt = 0
    while True:
        try:
            return client.chat.completions.create(
                model=model, messages=messages, temperature=0.1), None
        except Exception as e:
            if _is_network_error(e) and attempt < VISION_MAX_RETRIES:
                delay = 2 ** attempt  # 指数退避：1s、2s
                attempt += 1
                print(f"⚠️ 视觉模型网络类错误（{e}），{delay} 秒后重试"
                      f"（第 {attempt}/{VISION_MAX_RETRIES} 次）...")
                time.sleep(delay)
                continue
            return None, e


def _png_size(path):
    """读取 PNG 头部 IHDR 的宽高（stdlib 实现，替代 Pillow）。失败返回 None。"""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if len(head) >= 24 and head[:8] == b"\x89PNG\r\n\x1a\n":
            width = int.from_bytes(head[16:20], "big")
            height = int.from_bytes(head[20:24], "big")
            if width > 0 and height > 0:
                return width, height
    except Exception:
        pass
    return None


# markdown 代码围栏（```json / ```）：视觉模型实测会把 JSON 本体包进
# 代码块返回，解析前统一剥离（2026-10-01 用户指令，行内首尾均可）
_CODE_FENCE_RE = re.compile(r"```[a-zA-Z0-9_-]*")
# 纯数字引号串（"531" / "-12.5"）：剥引号还原为裸数字；含其他字符的
# 字符串一律不碰
_QUOTED_NUMBER_RE = re.compile(r'"(-?\d+(?:\.\d+)?)"')
# 末尾", 裸数字}"：对象缺 "y" 键的实测畸形（{"x": 246, 531}）
_TRAILING_NUMBER_RE = re.compile(r",\s*(-?\d+(?:\.\d+)?)\s*\}")


def _repair_json_fragment(span):
    """单个候选 JSON 片段修复（2026-10-01 用户指令）：已是合法 JSON 原样
    返回；否则依次尝试——纯数字引号串剥引号（"531" → 531）、对象无 "y"
    键且末尾为", 裸数字}"时补 "y": 键（{"x": 246, 531} →
    {"x": 246, "y": 531}；引号形态 "531" 先经剥引号转裸数字再补键）。
    每步修复结果必须能整体解析才算成功；全部失败返回原片段（保持原貌
    供诊断），全程不抛异常。"""
    try:
        json.loads(span)
        return span
    except Exception:
        pass
    unquoted = _QUOTED_NUMBER_RE.sub(r"\1", span)
    if unquoted != span:
        try:
            json.loads(unquoted)
            return unquoted
        except Exception:
            pass
    if not re.search(r'"y"\s*:', unquoted):
        repaired = _TRAILING_NUMBER_RE.sub(r', "y": \1}', unquoted)
        if repaired != unquoted:
            try:
                json.loads(repaired)
                return repaired
            except Exception:
                pass
    return span


def _clean_json_candidates(content):
    """清洗视觉模型回复为候选 JSON 片段列表（纯函数无副作用，解析与
    失败诊断共用，2026-10-01 用户指令）：

    1. 剥离 markdown 代码围栏（```json / ```，行内首尾均可）；
    2. 提取 {} 候选片段：贪婪整段优先（防嵌套花括号截断），失败再逐个
       尝试非贪婪片段（防回复夹带 prose / 多段 JSON），与既有口径一致；
    3. 各片段经 _repair_json_fragment 修复（引号数字 / 缺 "y" 键）；
       修复后去重保序（贪婪与非贪婪片段常为同一串，诊断不重复刷屏）。
    非 str / 空输入或不含花括号的内容返回空列表。
    """
    if not isinstance(content, str) or not content:
        return []
    text = _CODE_FENCE_RE.sub("", content)
    spans = []
    greedy = re.search(r"\{.*\}", text, re.DOTALL)
    if greedy:
        spans.append(greedy.group(0))
    spans.extend(m.group(0)
                 for m in re.finditer(r"\{.*?\}", text, re.DOTALL))
    candidates = []
    for span in spans:
        repaired = _repair_json_fragment(span)
        if repaired not in candidates:
            candidates.append(repaired)
    return candidates


def _extract_click_point(content):
    """从视觉模型回复中提取点击坐标 (x, y)，无法解析时返回 None。

    纯函数（2026-10-01 用户指令）：候选片段先经 _clean_json_candidates
    清洗（剥离 ```json 等 markdown 围栏 → 引号数字剥引号 → 缺 "y" 键
    补键），再 json.loads 后按键探测而非死盯单一正则，按优先级——
    1. {"bounds": [x, y, x2, y2]}          → 取外接框中心点；
    2. {"x1": [x, y, x2, y2]}（值为数组）   → 按用户口径取数组前两个
       元素作为 x 和 y（实测格式）；
    3. {"x": 数字, "y": 数字}               → 直接作为点击点；
    4. {"x1": 数字, "y1": 数字, "x2": 数字, "y2": 数字}（标准框）→ 中心点
       （既有行为保持）。
    数值容错：int / float / 数字字符串均可；数组元素不足 2 个或非数字
    一律返回 None；json.loads 与取键全程 try/except 兜底，畸形输入
    不崩溃。模型按约定输出全 -1（未找到信号）时，各格式解析结果均为
    (-1, -1)，由调用方统一识别，本函数不做特殊处理。
    """
    if not isinstance(content, str) or not content:
        return None

    def _num(value):
        """数值容错：int / float / 数字字符串 → float；其余（含布尔与
        None）一律非法。"""
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return None
        return None

    def _center(p1, p2):
        """两点中点：任一数值非法 → None（保持既有 (x1+x2)/2 口径）。"""
        a, b = _num(p1), _num(p2)
        if a is None or b is None:
            return None
        return (a + b) / 2

    def _point_from_dict(data):
        # 优先级 1：{"bounds": [x, y, x2, y2]} → 外接框中心点
        bounds = data.get("bounds")
        if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
            cx = _center(bounds[0], bounds[2])
            cy = _center(bounds[1], bounds[3])
            if cx is not None and cy is not None:
                return cx, cy
        # 优先级 2：{"x1": [x, y, ...]}（实测数组值格式）→ 取前两个元素；
        # 元素不足 2 个或非法 → 按用户口径直接判解析失败
        x1_value = data.get("x1")
        if isinstance(x1_value, (list, tuple)):
            if len(x1_value) >= 2:
                x, y = _num(x1_value[0]), _num(x1_value[1])
                if x is not None and y is not None:
                    return x, y
            return None
        # 优先级 3：{"x": 数字, "y": 数字} → 直接作为点击坐标
        x, y = _num(data.get("x")), _num(data.get("y"))
        if x is not None and y is not None:
            return x, y
        # 优先级 4：标准框 → 中心点（既有行为保持）
        if all(key in data for key in ("x1", "y1", "x2", "y2")):
            cx = _center(data["x1"], data["x2"])
            cy = _center(data["y1"], data["y2"])
            if cx is not None and cy is not None:
                return cx, cy
        return None

    # 候选 JSON 片段：先经 _clean_json_candidates 清洗（markdown 围栏
    # 剥离 + 引号数字剥引号 + 缺 "y" 键补键），再逐个解析；畸形片段
    # 修复无效时保持原貌，解析仍失败则跳过，不崩溃
    for span in _clean_json_candidates(content):
        try:
            parsed = json.loads(span)
        except Exception:
            continue    # 畸形 JSON 片段：跳过，不崩溃
        if not isinstance(parsed, dict):
            continue
        point = _point_from_dict(parsed)
        if point is not None:
            return point
    return None


def _print_parse_failure_diagnostics(content):
    """坐标解析失败诊断（2026-10-01 用户指令）：控制台打印两行 ⚠️——
    原始返回内容与清洗后的 JSON 候选（清洗复用 _clean_json_candidates，
    与解析同一份逻辑），均截断 300 防超长刷屏；诊断只进控制台，聊天框
    返回串保持既有口径不变。"""
    raw = content if isinstance(content, str) else str(content)
    print(f"⚠️ [视觉坐标解析失败] 原始返回内容: {raw[:300]}")
    candidates = _clean_json_candidates(content)
    joined = " | ".join(candidates) if candidates else "（无 JSON 候选）"
    print(f"⚠️ [视觉坐标解析失败] 清洗后的 JSON 候选: {joined[:300]}")


def get_screen_size():
    """获取手机屏幕的物理分辨率"""
    try:
        result = subprocess.run("adb shell wm size", shell=True, capture_output=True, text=True)
        match = re.search(r'(\d+)x(\d+)', result.stdout)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    return 1080, 2400


def vision_tap_element(element_name):
    """AI 看图 -> 识别元素像素坐标 -> 换算真实坐标 -> 自动点击"""
    if _OpenAIClient is None:
        return "❌ 未安装 openai SDK（pip install openai），无法使用视觉点击功能。"
    if not VISION_KEY:
        return "❌ 未配置视觉 API Key，无法使用视觉点击功能。"
    if not VISION_MODEL:
        return "❌ 未配置视觉模型 VISION_MODEL，无法使用视觉点击功能。"

    # 模型名预检（2026-10-01 用户指令）：名字里不含 vl 的模型大概率不是
    # 视觉模型（如纯文本模型被误填进 VISION_MODEL，会一直报"未找到"），
    # 请求前打印一行警告；只警告不阻断——用户也可能填了其他厂商带视觉
    # 能力但名字不含 vl 的模型
    if "vl" not in VISION_MODEL.lower():
        print("⚠️ 警告：当前模型可能不支持视觉，"
              "推荐使用 qwen-vl-max-latest 或 qwen-vl-plus")

    # 1. 截图
    screenshot_result = adb_screenshot()
    if "失败" in screenshot_result:
        return screenshot_result
    if not os.path.exists(SCREENSHOT_PATH):
        return "❌ 截图文件不存在，请检查 ADB 连接。"

    # 2. 获取屏幕真实分辨率，换算缩放比（无裁剪，cropped_top=0）
    screen_width, _screen_height = get_screen_size()
    png_size = _png_size(SCREENSHOT_PATH)
    scale_ratio = (png_size[0] / screen_width) if png_size else 1.0
    cropped_top = 0

    # 3. 截图转 base64（PNG 原样发送，不经 Pillow 压缩）
    try:
        with open(SCREENSHOT_PATH, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return f"❌ 图片处理失败: {e}"

    # 4. 构造视觉模型请求（中文屏幕识别友好的结构化提示词 + 强制点击点
    #    JSON 输出约定：找到给 {"x": 数字, "y": 数字} 屏幕绝对坐标，
    #    找不到给 {"x": -1, "y": -1}，杜绝编造坐标；输出格式段另加两条
    #    硬约束——禁代码块包裹、x/y 必须带键名且数字不加引号，
    #    2026-10-01 用户指令）
    prompt = (
        "这是一张 Android 手机的屏幕截图。请在这张截图中仔细查找目标元素"
        f"【{element_name}】（应用图标或按钮），并严格遵循以下规则：\n"
        "1. 屏幕上的应用图标与按钮多为中文名称（如“设置”“微信”“相册”"
        "“浏览器”），请优先按中文名匹配目标；\n"
        "2. 忽略顶部状态栏（时间/电量/信号）与桌面小组件（天气/时钟/日历），"
        "它们不是要找的目标；\n"
        "3. 目标可能藏在应用列表或文件夹中，请逐屏仔细排查每一个图标；\n"
        "4. 请务必只输出 JSON 格式："
        '{"x": 数字, "y": 数字}，'
        "表示要点击的屏幕绝对坐标，不要输出其他任何内容；\n"
        '5. 找不到时，只输出：{"x": -1, "y": -1}，不要编造坐标；\n'
        "6. 直接输出 JSON 本体，不要用 ```json 等代码块包裹；\n"
        '7. "x" 与 "y" 每个值都必须带键名，数字不要加引号'
        '（例：{"x": 246, "y": 531}）。'
    )

    messages = [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}},
    ]}]

    endpoint = _vision_endpoint()

    # 5. 官方 SDK 调用（base_url 自动追加 /chat/completions）+ 404 模型
    #    自动回退：尝试序列 = 配置模型 + 备用模型（去重保序），当前模型
    #    报 404（不存在）时切换下一个备用模型重试；403 等鉴权/域名问题
    #    换模型无用，不回退、立即诊断。网络类重试在单模型内部进行（受
    #    VISION_MAX_RETRIES 约束，当前为 0 = 每个模型只尝试一次）。
    client = _OpenAIClient(api_key=VISION_KEY, base_url=_client_base_url(),
                           timeout=VISION_TIMEOUT)
    candidates = _model_candidates()
    response = None
    last_error = None
    for index, model in enumerate(candidates):
        response, last_error = _create_with_network_retry(
            client, model, messages)
        if last_error is None:
            break
        if _http_status_of(last_error) != 404 or index + 1 >= len(candidates):
            break   # 非 404 或备用模型已耗尽 → 交由下方统一错误出口处理
        # 404 = 模型不存在：提示切换，继续尝试下一个备用模型
        print(f"⚠️ 模型 {model} 不存在（404），自动切换备用模型: "
              f"{candidates[index + 1]}")
        response = None

    if last_error is not None:
        status = _http_status_of(last_error)
        if status == 404:
            # 全部候选模型均 404：诊断块列出已尝试的全部模型名（只进控制台）
            tried = "/".join(candidates)
            _print_request_failure(endpoint, status, _error_body_of(last_error),
                                   note=f"已尝试模型: {tried}")
            # 返回串保持极简口径，括号内附已尝试模型
            return (f"❌ 视觉模型调用失败: HTTP 404，操作已中止。"
                    f"（已尝试模型: {tried}）")
        if status is not None:
            # 403（Key/域名不匹配）等 HTTP 层失败，鉴权与模型错误不重试，
            # 立即诊断（诊断块只进控制台）
            _print_request_failure(endpoint, status, _error_body_of(last_error))
            # 返回串极简：不带指引，指引在控制台诊断块里
            return f"❌ 视觉模型调用失败: HTTP {status}，操作已中止。"
        if _is_network_error(last_error):
            # 网络类失败（连接被重置/超时等）：这是网络问题而非配置问题，
            # 控制台只留一行简短提示、返回一句简短文案，不输出大段诊断块
            print(f"❌ 视觉模型网络连接失败: {_short_reason(last_error)}")
            return "❌ 视觉模型网络连接失败，操作已中止。"
        return f"❌ 视觉模型调用失败: {last_error}"

    # 6. 提取模型回复中的点击坐标（多格式容错解析，见 _extract_click_point：
    #    标准框 / bounds 数组 / 实测的 x1 数组值格式 / 直接 x+y 均可）
    choices = getattr(response, "choices", None)
    if not choices:
        return f"❌ 视觉模型返回异常: 缺少 choices 字段"
    content = getattr(choices[0].message, "content", None)
    if not content:
        return "❌ 视觉模型返回异常: 回复内容为空"

    click_point = _extract_click_point(content)
    if click_point is None:
        # 解析失败诊断（2026-10-01 用户指令）：原始回复与清洗后的 JSON
        # 候选一并打出，只进控制台，便于定位模型输出格式问题；返回串
        # 保持既有口径不变
        _print_parse_failure_diagnostics(content)
        return f"❌ 视觉模型未能识别出坐标。回复内容：{content}"

    # 明确的"未找到"信号：模型按提示词约定输出全 -1（各兼容格式的解析
    # 结果均为 (-1, -1)）→ 返回明确失败文案，不换算、不点击，避免编造
    # 坐标误触屏幕
    click_x, click_y = click_point
    if click_x == -1 and click_y == -1:
        # 未找到（2026-10-01 用户指令）：失败串后附加一句兜底排查引导。
        # 与"网络失败文案瘦身"口径不冲突——瘦的是网络失败路径，这里是
        # "模型说没找到"的场景（亮屏/页面 + 模型配置两手排查）
        return (f"❌ 视觉模型在屏幕上未找到【{element_name}】。 "
                "⚠️ 请确认手机屏幕已亮屏且停留在目标页面，同时确认 "
                ".env 中的 VISION_MODEL 是真正的视觉模型"
                "（如 qwen-vl-max-latest）")

    # 7. 换算成手机真实像素坐标（截图可能被缩放，除以缩放比；无裁剪
    #    cropped_top=0）
    real_x = int(click_x / scale_ratio)
    real_y = int(click_y / scale_ratio) + cropped_top

    print(f"🎯 视觉模型解析：模型识别点击点({click_x:g},{click_y:g}) -> "
          f"实际屏幕坐标({real_x}, {real_y})")

    # 8. 执行点击
    return adb_tap(real_x, real_y)
