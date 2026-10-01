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

缩放换算可见化（2026-10-01 用户指令）：换算数学保持不变（real =
模型坐标 × 实际屏幕/截图比，与既有"除以 scale_ratio"等价），但两个
此前"静默按缺省值执行"的薄弱环节改为显式 ⚠️ 警告——_png_size 解析
失败（设备吐 JPEG 或非 PNG 头）按 1:1 换算时、get_screen_size 走
缺省 1080x2400 兜底时；旧 🎯 行替换为单行全量日志（📏 [视觉缩放]：
模型原始坐标 / 截图分辨率 / 手机实际分辨率 / 换算后坐标四要素，
截图分辨率解析失败时显示"未知(按1:1)"）。换算仍发生在 adb_tap 之前。

提示词末尾强化（2026-10-01 用户指令，用户原文）：提示词最末尾追加
"请只输出 JSON 格式，不要包含 markdown 代码块（如 ```json），不要
包含任何解释性文字，示例：{"x": 100, "y": 200}。"——与规则 7/8
语义重叠属刻意强化（实测仍偶发代码块输出导致解析失败）。

严格匹配强化与顶部坐标警告（2026-10-01 用户指令）：qwen3-vl-flash
实测找屏幕中下方的"WLAN"文字时误点顶部搜索框——(1) 提示词在"忽略
状态栏"规则后新增一条：请严格匹配屏幕上的【中文字符】，定位到目标
文字本身所在位置、不要定位图标或搜索框（附"WLAN"正例），找不到
务必返回全 -1 坐标、不要瞎猜；(2) 换算出 real_y 落在屏幕顶部 15%
区域（real_y < 0.15 × screen_height，通常是状态栏/搜索框位置）时，
adb_tap 前打印一行 ⚠️ 警告"视觉坐标可能定位到搜索框或状态栏"——
用户找的常是屏幕中下方元素，顶部命中大概率是误定位；仅警告不阻断，
点击行为保持不变（可观测、不擅改）。

ADB 点击间隔与指令容错（2026-10-01 用户指令，组 D1）：实测"📏 换算
正确、指令已发送但手机未响应"——(1) 📏 日志后、adb_tap 前固定
sleep 0.5 秒（截图与点击间隔，避免屏幕未就绪）；(2) adb_tap 返回串含
失败语义（❌ 开头或含"失败"字样，与 adb_tools 实际返回形态对齐）时
打印 ⚠️ 警告"ADB 点击指令发送失败，请确认手机已开启 USB 调试（模拟
点击）权限"并把警告语义并入返回串；(3) 二次确认点击：模块级开关
VISION_CONFIRM_RETAP（默认开，env 同名置 0/false/off/no 可关）——
首次点击返回成功串后 sleep 1 秒对相同坐标再点一次"确认点击"（用户
场景"点击已发送但手机没动"无法直接检测跳转，两次都执行最务实），
返回串注明"已执行二次确认点击"；首次已明确失败则不重复。

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

观察-描述前置提示（2026-10-01 用户指令，任务 2）：提示词最末尾强势
追加"请先仔细观察屏幕，先描述你看到了什么，再给出坐标。如果找不到
目标文字，请直接返回 -1 坐标，不要瞎猜。"——允许模型在 JSON 前先输出
描述文本（_extract_click_point 对 prose 包裹已容错，JSON 提取不受
描述影响），同时保留"JSON 本体只含坐标"口径：原末尾强化句的"不要
包含任何解释性文字"与描述前置直接冲突，改为约束"JSON 本体只含
x/y 坐标"。

顶部疑似区分级警告与偏移策略修正（2026-10-01 用户指令修正）：此前
"15%~40% 一律强推 5% 屏高下移"好心办坏事——用户找设置列表里的
"蓝牙"（y=847/2712=31.2%，正常元素位置）被强推到 y=982，点击漂移
到"我的设备"。修正为三级矩阵：<15% 屏高（真状态栏/搜索框区）→
"搜索框/状态栏"提示 + 强警告"目标位于屏幕上部，极易误点到账号或
搜索框" + 向下偏移 2% 屏高（屏高 2712 时约 54 像素）；15%~40% →
仅打印"⚠️ 目标位于屏幕上部，请确认"，不偏移、保留模型原始坐标执行；
≥40% → 零警告零偏移。常量：VISION_TOP_STRONG_RATIO=0.15（偏移+
强警告线）/ VISION_TOP_ZONE_RATIO=0.40（警告上限）/
VISION_TOP_OFFSET_RATIO=0.02；开关 VISION_TOP_OFFSET 语义不变
（默认开、env 置 0/false/off/no 可关，关=连 15% 内也不偏移）。

点击前后变化检测（2026-10-01 用户指令，任务 3 后半）：首次点击前把
截图（SCREENSHOT_PATH）复制到临时文件留底（adb_screenshot 每次覆盖
同名文件，必须先留底），二次确认点击完成后重新截图，与留底比对 MD5
（android_ui_tools.file_md5，stdlib hashlib）——一致打印"⚠️ 页面未
发生变化，目标可能未点中，尝试滑动屏幕或重新寻找"（返回串处理口径
升级见下段）；不一致打印"✅ 页面已变化，
点击已生效"（可观测对照）。整段检测 try/except 兜底（重新截图失败/
文件缺失/MD5 失败一律静默跳过），不影响点击结果返回；
VISION_CONFIRM_RETAP=0（无二次点击）时跳过变化检测（只点一次无从
比对）。

顶部误识别降级告知进返回串 + 页面未变化明确失败（2026-10-01 用户
指令，F3）：(1) 换算后坐标落在顶部两级疑似区（<15% 或 15%~40% 屏高，
沿用既有分级判定）时，控制台既有警告之外，返回串末尾追加一行
"⚠️ 视觉模型可能识别到了顶部区域（如账号/搜索框），建议手动确认。"
——此前该提示只进控制台、聊天框看不到（背景：视觉模型把"蓝牙"误
识别为"账号"区域 (163, 847)，两次点击都点到了账号）；≥40% 正常坐标
不追加。(2) 变化检测 MD5 一致（点击两次页面纹丝不动）时，返回串
整体替换为明确失败口径"❌ 视觉模型未点中目标，请尝试手动点击或换
个清晰的图标"（替换原"（⚠️ 页面未发生变化，已尝试点击 2 次）"含糊
附加段；❌ 前缀同时切断 brain 工具调用重试），控制台保留一行简短
原因说明；检测本就在两次点击全部完成后进行，不做任何额外重试点击。

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
import tempfile
import time

from adb_tools import adb_screenshot, adb_tap, SCREENSHOT_PATH
from android_ui_tools import file_md5
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


def _env_flag(name):
    """环境变量布尔开关：未设置或空串默认 True；置 0/false/off/no
    （不分大小写）为 False。"""
    value = os.environ.get(name)
    if value is None or not value.strip():
        return True
    return value.strip().lower() not in ("0", "false", "off", "no")


# 二次确认点击开关（2026-10-01 用户指令，组 D1）：默认开——首次 adb_tap
# 返回成功串后等 1 秒对相同坐标再点一次"确认点击"（用户场景"点击已发送
# 但手机没动"无法直接检测跳转，两次都执行最务实可靠）；env
# VISION_CONFIRM_RETAP 置 0/false/off/no 可关（测试与低速场景）。
VISION_CONFIRM_RETAP = _env_flag("VISION_CONFIRM_RETAP")

# 顶部疑似区分级阈值（屏高比例，2026-10-01 偏移策略修正）：
# - VISION_TOP_STRONG_RATIO=0.15：偏移+强警告线——real_y < 15% 屏高
#   （真状态栏/搜索框区域）才自动向下偏移并打强警告；
# - VISION_TOP_ZONE_RATIO=0.40：警告上限——15%~40% 只打印"请确认"
#   警告、不偏移（设置列表正常元素如"蓝牙"31.2% 也落在该区间，此前
#   40% 区 5% 强推下移导致"蓝牙"漂移到"我的设备"，好心办坏事）；
# - ≥40% 零警告零偏移。
VISION_TOP_STRONG_RATIO = 0.15
VISION_TOP_ZONE_RATIO = 0.40
# 15% 线内向下偏移量（2% 屏高，屏高 2712 时 int(0.02×2712)=54 像素）：
# env VISION_TOP_OFFSET 置 0/false/off/no 可关（默认开），关闭后连
# 15% 内也仅警告不偏移
VISION_TOP_OFFSET_RATIO = 0.02
VISION_TOP_OFFSET = _env_flag("VISION_TOP_OFFSET")

# 顶部疑似区误识别降级告知（2026-10-01 用户指令，F3-1）：换算后坐标
# 落在顶部两级疑似区（<15% 或 15%~40% 屏高）时，控制台既有警告之外
# 把该文案追加进返回串（聊天框可见）；≥40% 正常坐标不追加
VISION_TOP_ZONE_NOTE = ("⚠️ 视觉模型可能识别到了顶部区域"
                        "（如账号/搜索框），建议手动确认。")
# 页面未变化明确失败口径（2026-10-01 用户指令，F3-2）：变化检测 MD5
# 一致（点击两次页面纹丝不动）时返回串整体替换为该文案——不再含糊地
# 附加"（⚠️ 页面未发生变化，已尝试点击 2 次）"；控制台保留一行简短
# 原因说明；❌ 前缀可切断 brain 工具调用重试
VISION_PAGE_UNCHANGED_FAIL = ("❌ 视觉模型未点中目标，"
                              "请尝试手动点击或换个清晰的图标")


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
    """获取手机屏幕的物理分辨率

    兜底可见化（2026-10-01 用户指令）：adb 输出无法解析或命令异常时，
    此前静默回退缺省 1080x2400（缩放比算错导致点击偏差却无从排查），
    现打印一行 ⚠️ 警告，让"静默错误"变成"可见错误"。"""
    try:
        result = subprocess.run("adb shell wm size", shell=True, capture_output=True, text=True)
        match = re.search(r'(\d+)x(\d+)', result.stdout)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    print("⚠️ [视觉缩放] 手机分辨率获取失败（adb shell wm size），"
          "按缺省 1080x2400 处理（点击若偏差请检查 ADB 连接）")
    return 1080, 2400


def _tap_failed(result):
    """adb_tap 返回串是否含失败语义（2026-10-01 用户指令，组 D1）：❌
    开头或含"失败"字样——与 adb_tools.adb_tap 实际返回形态对齐（成功
    "✅ 已模拟点击坐标: (x, y)" / 失败 "❌ ADB 点击失败: {异常}"，两种
    判定任一命中即视为发送失败）；非 str（测试替身）不含失败语义、
    不判失败，不崩溃。"""
    return isinstance(result, str) and (result.startswith("❌") or "失败" in result)


def _discard_snapshot(path):
    """删除临时快照文件（静默容错：清理失败不影响点击主流程）。"""
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _copy_screenshot_snapshot():
    """点击前截图留底（2026-10-01 用户指令，任务 3 后半变化检测基线）：
    adb_screenshot 每次覆盖同名文件，必须先把 SCREENSHOT_PATH 复制到
    临时文件再点击，否则点击后重新截图会把"点击前"的证据覆盖掉。
    文件缺失/复制失败返回 None——变化检测整体降级跳过，不影响点击
    主流程。"""
    snapshot_path = None
    try:
        if not os.path.exists(SCREENSHOT_PATH):
            return None
        fd, snapshot_path = tempfile.mkstemp(
            prefix="xiaoju3_vision_before_", suffix=".png")
        os.close(fd)
        with open(SCREENSHOT_PATH, "rb") as src, \
                open(snapshot_path, "wb") as dst:
            dst.write(src.read())
        return snapshot_path
    except Exception:
        _discard_snapshot(snapshot_path)
        return None


def _page_change_outcome(before_snapshot):
    """点击前后变化检测（2026-10-01 用户指令，任务 3 后半；返回口径
    升级 2026-10-01 F3-2）：重新截图与点击前留底比对 MD5——一致 →
    控制台打印一行简短原因"⚠️ 页面未发生变化，目标可能未点中，尝试
    滑动屏幕或重新寻找"，返回串整体替换为明确失败口径
    VISION_PAGE_UNCHANGED_FAIL（不再含糊地附加"页面未发生变化"段）；
    不一致 → 打印"✅ 页面已变化，点击已生效"（可观测对照），返回空串
    （调用方维持成功串）。任何环节失败（重新截图失败/文件缺失/MD5
    计算失败）返回空串，不影响点击结果返回。before_snapshot 为空
    （留底失败/未启用二次点击）直接跳过。检测在两次点击全部完成后
    进行，本函数不做任何额外重试点击。"""
    if not before_snapshot:
        return ""
    try:
        reshot = adb_screenshot()
        if not isinstance(reshot, str) or "失败" in reshot:
            return ""
        if not os.path.exists(SCREENSHOT_PATH):
            return ""
        before_md5 = file_md5(before_snapshot)
        after_md5 = file_md5(SCREENSHOT_PATH)
        if not before_md5 or not after_md5:
            return ""
        if before_md5 != after_md5:
            print("✅ 页面已变化，点击已生效")
            return ""
        print("⚠️ 页面未发生变化，目标可能未点中，尝试滑动屏幕或重新寻找")
        return VISION_PAGE_UNCHANGED_FAIL
    except Exception:
        return ""
    finally:
        _discard_snapshot(before_snapshot)


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

    # 2. 获取屏幕真实分辨率，换算缩放比（无裁剪，cropped_top=0）。
    #    换算数学保持参考实现结构（center / scale_ratio，与"坐标 ×
    #    实际屏幕/截图比"等价）；_png_size 解析失败（设备吐 JPEG 或
    #    非 PNG 头）时此前静默按 1:1 执行，现打印明确警告（2026-10-01
    #    用户指令：让"静默错误"变成"可见错误"）
    screen_width, screen_height = get_screen_size()
    png_size = _png_size(SCREENSHOT_PATH)
    if png_size:
        screenshot_label = f"{png_size[0]}x{png_size[1]}"
        scale_ratio = png_size[0] / screen_width
    else:
        print("⚠️ [视觉缩放] 截图分辨率解析失败，按 1:1 换算"
              "（点击若偏差请检查截图格式）")
        screenshot_label = "未知(按1:1)"
        scale_ratio = 1.0
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
        # 严格匹配强化（2026-10-01 用户指令，用户口径）：qwen3-vl-flash
        # 实测找屏幕中下方的"WLAN"文字时误点顶部搜索框，故紧跟"忽略状态
        # 栏"规则强调——定位到目标文字本身，绝不落在图标或搜索框上；
        # 找不到时如实返回全 -1 坐标，禁止瞎猜
        "3. 请严格匹配屏幕上的【中文字符】。例如寻找“WLAN”，应该定位到"
        "文字“WLAN”所在位置，不要定位图标或搜索框。如果找不到，请务必"
        "返回全 -1 坐标，不要瞎猜；\n"
        "4. 目标可能藏在应用列表或文件夹中，请逐屏仔细排查每一个图标；\n"
        "5. 请务必只输出 JSON 格式："
        '{"x": 数字, "y": 数字}，'
        "表示要点击的屏幕绝对坐标（JSON 本体只含坐标，描述文字放在 "
        "JSON 之前）；\n"
        '6. 找不到时，只输出：{"x": -1, "y": -1}，不要编造坐标；\n'
        "7. 直接输出 JSON 本体，不要用 ```json 等代码块包裹；\n"
        '8. "x" 与 "y" 每个值都必须带键名，数字不要加引号'
        '（例：{"x": 246, "y": 531}）。\n'
        # 末尾强化句（2026-10-01 用户指令）：与规则 7/8 语义重叠属刻意
        # 强化；其中"不要包含任何解释性文字"按任务 2 口径让位——允许
        # 模型在 JSON 前先描述所见内容，改为约束"JSON 本体只含 x/y 坐标"
        "请只输出一行 JSON 格式，JSON 本体只含 x/y 坐标，"
        "不要包含 markdown 代码块（如 ```json），"
        '示例：{"x": 100, "y": 200}。'
        # 观察-描述前置（2026-10-01 用户指令，任务 2，用户原文）：先描述
        # 再给坐标，逼模型真正"看图"而非凭印象乱点（背景：把"账号"看成
        # "蓝牙"）；找不到如实返回 -1，解析端 _extract_click_point 对
        # prose 包裹已容错，JSON 提取不受描述影响
        "请先仔细观察屏幕，先描述你看到了什么，再给出坐标。"
        "如果找不到目标文字，请直接返回 -1 坐标，不要瞎猜。"
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
    #    cropped_top=0）。换算发生在 adb_tap 之前
    real_x = int(click_x / scale_ratio)
    real_y = int(click_y / scale_ratio) + cropped_top

    # 单行全量日志（2026-10-01 用户指令）：模型原始坐标 / 截图分辨率 /
    # 手机实际分辨率 / 换算后坐标四要素一行可查，缩放换算错误一眼可见；
    # 截图分辨率解析失败时显示"未知(按1:1)"（另有 ⚠️ 警告）
    print(f"📏 [视觉缩放] 模型原始坐标: ({click_x:g}, {click_y:g}) | "
          f"截图分辨率: {screenshot_label} | "
          f"手机实际分辨率: {screen_width}x{screen_height} | "
          f"换算后坐标: ({real_x}, {real_y})")

    # 顶部区域合理性检查（2026-10-01 用户指令）：用户要找的目标常在屏幕
    # 中下方（如设置页里的"WLAN"），换算后点击点却落在屏幕顶部 15% 区域
    # （通常是状态栏/搜索框的位置）时，大概率是视觉模型把搜索框/状态栏
    # 当成了目标文字——打印一行 ⚠️ 警告提醒核对目标文字位置。
    # top_zone_hit（F3-1）：两级疑似区（<15% 或 15%~40%）任一命中即置
    # True，供返回串追加聊天框可见的降级告知；判定用换算后原始坐标
    # （偏移前），≥40% 保持 False 不追加
    top_zone_hit = False
    if real_y < VISION_TOP_STRONG_RATIO * screen_height:
        top_zone_hit = True
        print("⚠️ 视觉坐标可能定位到搜索框或状态栏，请检查目标文字位置")
        # 强警告 + 2% 屏高向下偏移（2026-10-01 偏移策略修正）：偏移只在
        # 15% 线内（真状态栏/搜索框区）生效；VISION_TOP_OFFSET 关时仅
        # 警告不偏移；偏移后打印实际执行坐标
        print("⚠️ 目标位于屏幕上部，极易误点到账号或搜索框")
        if VISION_TOP_OFFSET:
            real_y += int(VISION_TOP_OFFSET_RATIO * screen_height)
            print(f"📍 [视觉防误点] 已向下偏移 2% 屏高，实际执行坐标: "
                  f"({real_x}, {real_y})")
    elif real_y < VISION_TOP_ZONE_RATIO * screen_height:
        # 15%~40% 只提醒不偏移（2026-10-01 偏移策略修正，关键修复）：
        # 设置列表正常元素（如"蓝牙"y=847/2712=31.2%）也落在该区间，
        # 保留模型原始坐标执行，杜绝"蓝牙→我的设备"式漂移
        top_zone_hit = True
        print("⚠️ 目标位于屏幕上部，请确认")
    # ≥40%：零警告零偏移

    # 8. 点击前固定间隔（2026-10-01 用户指令，组 D1）：截图/识别完成到
    #    点击之间留 0.5 秒——实测换算正确、指令已发送但手机未响应，怀疑
    #    是截图后立即点击时屏幕尚未就绪
    time.sleep(0.5)

    # 9. 点击前截图留底（任务 3 后半变化检测基线）：adb_screenshot 每次
    #    覆盖同名文件，必须先复制到临时文件再点击；复制失败仅跳过检测、
    #    不影响点击
    before_snapshot = _copy_screenshot_snapshot()

    # 10. 执行点击 + 指令结果检查：返回串含失败语义（❌ 开头或含"失败"，
    #     见 _tap_failed）时打印 ⚠️ 警告并把警告语义并入返回串——此前
    #     adb 指令发送失败会被静默吞掉，用户只看到"手机没动"无从排查
    result = adb_tap(real_x, real_y)
    if _tap_failed(result):
        _discard_snapshot(before_snapshot)
        print("⚠️ ADB 点击指令发送失败，请确认手机已开启 USB 调试（模拟点击）权限")
        return f"{result}（⚠️ 请确认手机已开启 USB 调试/模拟点击权限）"

    # 顶部疑似区降级告知（F3-1）：坐标落在顶部两级疑似区时返回串末尾
    # 追加聊天框可见提示（前导空格，与既有"未找到"串附加风格一致）；
    # 点击指令发送失败分支不追加——点击未执行，USB 调试排查优先
    top_note = f" {VISION_TOP_ZONE_NOTE}" if top_zone_hit else ""

    # 11. 二次确认点击（VISION_CONFIRM_RETAP，默认开）：用户场景"点击
    #     已发送但手机没动"无法直接检测跳转，最务实口径——首次返回
    #     成功串后等 1 秒对相同坐标再点一次"确认点击"，两次都执行；
    #     首次已明确失败（上方分支）则不重复。env VISION_CONFIRM_RETAP=0
    #     可关（测试与低速场景）
    if VISION_CONFIRM_RETAP:
        time.sleep(1)
        confirm_result = adb_tap(real_x, real_y)
        if _tap_failed(confirm_result):
            _discard_snapshot(before_snapshot)
            print("⚠️ ADB 点击指令发送失败，请确认手机已开启 USB 调试（模拟点击）权限")
            return (f"{result}（二次确认点击发送失败，"
                    f"⚠️ 请确认手机已开启 USB 调试/模拟点击权限）")
        # 变化检测（任务 3 后半；F3-2 口径升级）：二次确认点击完成后
        # 重新截图与点击前留底比对 MD5；VISION_CONFIRM_RETAP=0（无二次
        # 点击）时跳过——只点一次无从比对。页面未变化 → 返回串整体
        # 替换为明确失败口径（❌ 未点中）；已变化 → 成功串 + 顶部降级
        # 告知（如有）。检测不做任何额外重试点击
        change_outcome = _page_change_outcome(before_snapshot)
        if change_outcome:
            return change_outcome
        return f"{result}（已执行二次确认点击）{top_note}"
    _discard_snapshot(before_snapshot)   # 无二次点击：跳过变化检测
    return f"{result}{top_note}"
