# -*- coding: utf-8 -*-
"""global_task_reviewer.py · 全局任务审查员骨架 v0（2026-10-28 午休施工）。

**独立模块，主链路未接入**（设计稿：_dev/design_global_task_reviewer.md；
理论锚：_dev/thinking_notes.md「多步推理误差累积」——每步 95%、十步 60%）。

职责：多步工具执行时在关键节点做「执行链 vs 原始请求」的整体校验，
防"局部靠谱、全局崩溃"。三则触发（T1 链长/T2 跳族+语义距离/T3 败后续），
高副作用半径工具强制审查；其余零开销直通。

队长增量（本版落实）：T2 不依赖死板族分类——叠加**语义距离**（字符
2-gram Jaccard，纯标准库零依赖）与**高副作用半径**判定（写/控/删类词根）。

扳手原则：零句子硬编码；族表/副作用词根/阈值全部可配置。
"""

import re
from dataclasses import dataclass, field

# ── 可配置默认值（扳手原则：全部可注入覆盖） ──

#: T1：同一请求内第 N 次工具调用前触发审查（0.95^3≈0.86，衰减开始可见）
CHAIN_LEN_TRIGGER = 3

#: T2：语义距离阈值（字符 2-gram Jaccard 低于此值判"偏离"）
SEMANTIC_DISTANCE_TRIGGER = 0.2

#: 高副作用半径词根（工具名匹配，命中即强制审查——写/控/删/系统类）
SIDE_EFFECT_ROOTS = (
    "control", "write", "delete", "remove", "restart", "install",
    "uninstall", "adb_tap", "adb_swipe", "adb_", "ui_tap",
    "vision_tap", "send_", "system_", "set_", "toggle", "create",
)

#: 工具族粗分类（T2 初筛用；语义距离是第二道兜底，不依赖此表完备）
FAMILY_KEYWORDS = {
    "ha": ("light", "climate", "switch", "cover", "sensor", "input_boolean",
           "ha_", "home"),
    "media": ("play", "music", "media", "volume"),
    "todo": ("todo",),
    "web": ("search", "web", "fetch", "news"),
    "file": ("file", "list_files", "read_file", "write_file"),
    "device": ("adb", "ui_tap", "vision", "screen", "app"),
}

#: 批量链保护：原始请求含列举/多目标信号 → 同族重复放行（防误杀"开三个灯"）
_BATCH_SIGNAL_RE = re.compile(
    r"所有|全部|每|各个|和|跟|一起|顺便|然后|再来|还有|列表|们")


def _bigrams(text):
    """字符 2-gram 集合（语义距离的近似载体，纯标准库）。"""
    t = re.sub(r"\s+", "", str(text or ""))
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) > 1 else {t}


_PUNCT_SUB = re.compile(r"[，。！？、；：\s,.!?;:()]+")


def _sentences(text):
    """粗切句（质量层复读检测与链摘要共用）。"""
    return [p for p in re.split(r"(?<=[。！？!?；;])", str(text or ""))
            if p and p.strip()]


def semantic_distance(a, b):
    """字符 2-gram **containment** 距离：0=几乎同题（一方是另一方子集），
    1=完全无关。用 containment 而非 Jaccard——短中文句的 Jaccard 天然偏低
    会误报偏离；containment 对"子串语义"场景校准得多。纯标准库。"""
    ba, bb = _bigrams(a), _bigrams(b)
    if not ba or not bb:
        return 1.0
    inter = len(ba & bb)
    smaller = min(len(ba), len(bb))
    return 1.0 - inter / smaller


def tool_family(tool_name, args=None):
    """工具族粗分类：先看工具名，再看 entity_id/args 线索；未命中='unknown'。"""
    text = str(tool_name or "") + " " + str(args or "")
    low = text.lower()
    for fam, kws in FAMILY_KEYWORDS.items():
        if any(k in low for k in kws):
            return fam
    return "unknown"


def is_high_side_effect(tool_name):
    """高副作用半径判定：工具名词根匹配（写/控/删/系统/屏幕类）。"""
    low = str(tool_name or "").lower()
    return any(root in low for root in SIDE_EFFECT_ROOTS)


@dataclass
class ChainEntry:
    """执行链上的一条记录。"""
    tool: str
    args: str = ""
    ok: bool = True
    family: str = "unknown"


@dataclass
class TaskState:
    """单会话任务状态（纯内存，进程亡即清——审查员无记忆惩罚权）。"""
    orig_request: str = ""
    chain: list = field(default_factory=list)
    falsify: str = ""   # 证伪条件（云审 CONTINUE 时收集；工具失败=疑似命中）


class TaskLedger:
    """会话账本：记录每个会话的原始请求与工具执行链，供触发三则判定。

    纯内存 dict；max_sessions 上限 FIFO 驱逐防膨胀（2026-10-28 影子模式
    上车：链跨轮按会话累积——单轮单工具架构下逐消息清链永远攒不出数据）。
    """

    def __init__(self, chain_len_trigger=CHAIN_LEN_TRIGGER,
                 semantic_trigger=SEMANTIC_DISTANCE_TRIGGER,
                 side_effect_roots=SIDE_EFFECT_ROOTS,
                 family_keywords=None, max_sessions=256):
        self.chain_len_trigger = chain_len_trigger
        self.semantic_trigger = semantic_trigger
        self.side_effect_roots = tuple(side_effect_roots)
        self.family_keywords = family_keywords or FAMILY_KEYWORDS
        self.max_sessions = max(1, int(max_sessions))
        self._tasks = {}

    # ── 记账 ──

    def start_task(self, session_key, orig_request):
        """新一轮用户请求：覆盖式登记原始请求并清空旧链。"""
        if (len(self._tasks) >= self.max_sessions
                and session_key not in self._tasks):
            oldest = next(iter(self._tasks))   # dict 有序：逐出最早会话
            self._tasks.pop(oldest, None)
        self._tasks[session_key] = TaskState(orig_request=str(orig_request or ""))

    def touch(self, session_key, orig_request):
        """更新原始请求但**不清链**（影子模式跨轮累积口径）：会话已有账本
        时只刷新 orig_request（批量保护/云端 verdict 用最新请求语义）；
        无账本则等价 start_task。"""
        st = self._tasks.get(session_key)
        if st is None:
            self.start_task(session_key, orig_request)
        else:
            st.orig_request = str(orig_request or "")

    def set_falsify(self, session_key, condition):
        """登记当前任务的证伪条件（云审 CONTINUE 时收集）。"""
        st = self._tasks.get(session_key)
        if st is not None:
            st.falsify = str(condition or "")

    def get_falsify(self, session_key):
        st = self._tasks.get(session_key)
        return st.falsify if st else ""

    def chain_summary(self, session_key, limit=8):
        """执行链紧凑摘要（影子日志/云端 verdict 输入）：`tool(ok)/tool(FAIL)`。"""
        st = self._tasks.get(session_key)
        if not st:
            return ""
        tail = st.chain[-limit:]
        return "/".join(f"{e.tool}({'FAIL' if not e.ok else 'ok'})"
                        for e in tail)

    def orig_request_of(self, session_key):
        st = self._tasks.get(session_key)
        return st.orig_request if st else ""

    def record(self, session_key, tool, args="", ok=True):
        """工具执行后记一笔（调用方在执行点顺手调，零额外成本）。"""
        st = self._tasks.get(session_key)
        if st is None:
            st = self._tasks[session_key] = TaskState()
        fam = tool_family(tool, args, )
        st.chain.append(ChainEntry(tool=str(tool), args=str(args or ""),
                                   ok=bool(ok), family=fam))

    def evict(self, session_key):
        self._tasks.pop(session_key, None)

    # ── 触发三则 ──

    def should_review(self, session_key, next_tool, next_args=""):
        """执行下一个工具前判定是否需要审查。

        返回 (need_review: bool, reason: str)。不命中=零开销直通。
        """
        st = self._tasks.get(session_key)
        if st is None:
            return False, ""
        chain = st.chain
        # 批量链保护最先（设计稿 §3.4）：请求含列举/多目标信号且 next 与
        # 链内任一同族 → 合法批量操作直通（副作用语境已被链确立，不重复审）
        if chain and self._is_batch_chain(st, next_tool):
            return False, ""
        # T3 败后续：上一工具失败后还想调下一个（挣扎形态，最易漂移）
        if chain and not chain[-1].ok:
            return True, "T3:败后续"
        # T2 跳族/机械循环：链非空且
        #  a) 下一工具与链尾族不同（初筛）
        #  b) 链尾近 3 条工具+参数指纹全同（机械循环——跨语言稳定；
        #     不与中文原始请求比 n-gram：中文请求 vs 英文工具名 containment
        #     恒低，会全量误报——2026-10-28 单测实锤）。
        #     机械循环是强漂移信号，排在 T1 链长之前。
        if chain:
            prev = chain[-1]
            fam = tool_family(next_tool, next_args)
            if fam != "unknown" and prev.family != "unknown" and fam != prev.family:
                return True, f"T2:跳族{prev.family}->{fam}"
            if len(chain) >= 3:
                fp = [(e.tool, e.args) for e in chain[-3:]]
                if len(set(fp)) == 1:
                    return True, "T2:机械循环"
        # T1 链长：即将进行的这次是第 chain_len_trigger 次
        if len(chain) + 1 >= self.chain_len_trigger:
            return True, f"T1:链长{len(chain) + 1}"
        # 高副作用半径：链上尚无同族副作用先例 → 强制过目（首次写/控/删类
        # 值得看一眼；批量语境已在上方 batch 保护放行）
        if self._is_side_effect(next_tool) and not any(
                self._is_side_effect(e.tool) for e in chain):
            return True, "T-SIDE:首次高副作用"
        return False, ""

    # ── 内部 ──

    def _is_side_effect(self, tool_name):
        low = str(tool_name or "").lower()
        return any(root in low for root in self.side_effect_roots)

    def _is_batch_chain(self, st, next_tool):
        """批量链保护（设计稿 §3.4）：原始请求含多目标信号 + next 工具与
        链内已执行工具同族 → 合法批量操作，放行。"""
        if not _BATCH_SIGNAL_RE.search(st.orig_request):
            return False
        fam = tool_family(next_tool)
        return any(e.family == fam and fam != "unknown" for e in st.chain)


# ── 审查执行骨架（verdict 注入式：云端/规则二选一由接入方决定） ──

DEFAULT_RULE_VERDICT = (
    "你是任务审查员。给出：①用户的原始请求 ②已执行的工具链 ③拟执行的下一步。"
    "判断下一步是否仍在完成原始请求：偏离→输出 ABORT。"
    "仍在正轨→第一行输出 CONTINUE，第二行输出\"证伪条件：\"开头的一句话——"
    "回答：出现什么结果，就说明我们当前的计划完全错了？（证伪思维：先说清"
    "被推翻的标准，再继续走）。只输出这两行，不要解释。")


def rule_verdict_ex(orig_request, chain_summary, next_tool, cloud_chat_fn=None,
                    sys_prompt=None):
    """rule_verdict 的证伪扩展版：返回 (verdict, falsify_condition)。
    CONTINUE 时解析第二行"证伪条件："（云端没给=空串，不影响主流程）。
    失败/超时 → ("CONTINUE", "")（宁放行不空谈，兜底同 rule_verdict）。
    自持云调用：rule_verdict 会 upper 全文只回 CONTINUE/ABORT，证伪行被
    丢弃无法复用。"""
    if cloud_chat_fn is None:
        return "CONTINUE", ""
    prompt = (f"原始请求：{orig_request}\n已执行链：{chain_summary}\n"
              f"拟执行：{next_tool}")
    try:
        out = str(cloud_chat_fn(
            [{"role": "system",
              "content": sys_prompt or DEFAULT_RULE_VERDICT},
             {"role": "user", "content": prompt}]) or "").strip()
    except Exception:
        return "CONTINUE", ""
    if out.upper().startswith("ABORT"):
        return "ABORT", ""
    m = re.search(r"证伪条件[:：]\s*(.+)", out)
    falsify = m.group(1).strip()[:120] if m else ""
    return "CONTINUE", falsify


def rule_verdict(orig_request, chain_summary, next_tool, cloud_chat_fn=None,
                 sys_prompt=DEFAULT_RULE_VERDICT):
    """审查动作骨架：默认调用注入的云端函数（如 brain.ask_cloud 同款签名
    messages→content），失败/超时由调用方兜底（设计稿 §3.3：审查员自身
    故障绝不放大成主链故障）。骨架期不绑定任何具体云端实现。"""
    if cloud_chat_fn is None:
        return "CONTINUE"   # 无审查通道=放行（宁漏勿误，兜底交给既有防线）
    prompt = (f"原始请求：{orig_request}\n已执行链：{chain_summary}\n"
              f"拟执行：{next_tool}")
    try:
        out = str(cloud_chat_fn(
            [{"role": "system", "content": sys_prompt},
             {"role": "user", "content": prompt}]) or "").strip().upper()
    except Exception:
        return "CONTINUE"   # 云端故障放行（规则兜底由接入方叠加）
    return "ABORT" if out.startswith("ABORT") else "CONTINUE"


# ── 结果质量审查层（2026-10-28 午休追加：借鉴 Nutlope/hallmark 的
# "规则化审查"思想——57 道 slop-test 门+发射前自审。把"结果很烂但任务
# 算完成"的主观感受，转成可执行、可审计的硬规则。MIT 思想借鉴+自实现，
# pattern 级零句子硬编码，扳手合规。） ──

@dataclass
class QualityRule:
    """一条结果质量规则：name+正则 pattern+严重级。"""
    name: str
    pattern: "re.Pattern"
    severity: str = "warn"          # warn | abort


#: 内置通用规则（对 1.5B/云端产物文本的 AI 味/废话检测，pattern 可扩充）
DEFAULT_QUALITY_RULES = (
    QualityRule("套话收尾", re.compile(
        r"如果还有其他问题[^。！？]*|随时告诉我|希望这能帮到你|祝您生活愉快"
        r"|希望能帮到你|很高兴为您")),
    QualityRule("评测腔", re.compile(
        r"体会到[^。！？]*重要性|深刻体会|培养了[^。！？]*(?:精神|能力)")),
    QualityRule("空洞承诺", re.compile(
        r"我会尽力|我将竭诚|我会努力为你")),
    QualityRule("AI 味总结", re.compile(
        r"综上(?:所述)?|总而言之|值得一提的是|总的来说[，,]")),
    QualityRule("复读开场", re.compile(
        r"^(?:你好[，,])?+(?:建议您?|您(?:可以|好)[，,]?(?:建议|可以))")),
)


class QualityGuard:
    """结果质量审查门：audit(text, user_msg="") → [(rule_name, severity,
    match 片段)]。与 TaskLedger 正交——审查员在 verdict=CONTINUE 后仍可
    跑质量层（"任务完成了但结果很烂"的第二道门）。"""

    def __init__(self, rules=None):
        self.rules = list(rules) if rules is not None else list(DEFAULT_QUALITY_RULES)

    def add_rule(self, name, pattern, severity="warn"):
        self.rules.append(QualityRule(name, re.compile(pattern), severity))

    def audit(self, text, user_msg=""):
        """跑全部规则，返回违规列表 [(rule_name, severity, match_text)]。"""
        s = str(text or "")
        violations = []
        for rule in self.rules:
            for m in rule.pattern.finditer(s):
                violations.append((rule.name, rule.severity, m.group(0)[:30]))
                break   # 每规则记一处即可（审计定位用，不刷屏）
        # 复读原话检测（与硬护栏 R1 同判据：去标点首句重合率 ≥0.8）
        if user_msg:
            first = _sentences(s)[0] if _sentences(s) else ""
            u = _PUNCT_SUB.sub("", user_msg)
            f = _PUNCT_SUB.sub("", first)
            if u and f:
                overlap = sum(1 for ch in f if ch in u) / max(len(f), 1)
                if overlap >= 0.8:
                    violations.append(("复读原话", "abort", first[:30]))
        return violations
