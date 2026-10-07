# -*- coding: utf-8 -*-
"""plugins/todo_aging · 待办时间老化 + 梯队递补（2026-10-07 四拍板）。

拍板口径：N=3 天（创建满 3 天才允许 AI 建议升档）/ 每次最多升一档 /
只升不降 / 封顶 P0 / P0 参与递补 / 只增不回退（effective_priority 载体，
原 priority 列永不改动）。挂心跳每天 1 次（todos_meta.aging_last_date
幂等闸，同天重入返回 None）；判级复用提炼链 PRIORITY_CRITERIA 同源防漂移，
走云端同通道（本地小模型工具遵循不可靠）。AI 只建议、代码真升。

已知边界：HA 未配置（离线降级）时心跳循环不启动，老化随之停摆——
正式版 HA 凭证常年在位（2026-10-06 补齐），可接受。
"""
import datetime

from agent_state.state_manager import state_manager
from plugins.batch_logger import ask_cloud
from plugins.todo_extractor import build_aging_prompt, parse_aging_json
from xiaoju3 import CLOUD_KEY, CLOUD_URL

TIER_ORDER = ("P0", "P1", "P2", "P3", "P4", "P5")
AGING_MIN_AGE_DAYS = 3        # 拍板①：创建满 3 天才允许升档
AGING_META_KEY = "aging_last_date"


def _tier_num(p):
    """'P2' → 2（非法输入由调用侧白名单保证）。"""
    return int(str(p)[1])


def _age_in_days(created_at, today):
    """created_at（'YYYY-MM-DD HH:MM:SS'/ISO）→ 距 today 的整天数（解析失败=0，
    即视为不满 N 天不升——防御式默认）。"""
    try:
        d = datetime.datetime.fromisoformat(
            str(created_at).replace("T", " ")[:19]).date()
    except (ValueError, TypeError):
        return 0
    return (today - d).days


def run_daily_aging(sm=None, cloud_fn=None, api_key=None, cloud_url=None,
                    today=None, min_age_days=None):
    """每天一次的老化+递补编排（同天二次调用返回 None，心跳每 60s 重入安全）。

    流程：幂等闸 → 取 pending → 云端建议（build_aging_prompt/parse_aging_json）
    → 代码兜底（满 N 天/只升不降/最多升一档/封顶 P0）写 effective_priority
    → 梯队递补（run_backfill）。返回摘要 dict（promoted/backfilled）供日志与锚。
    全程可注入（sm/cloud_fn/today/min_age_days），测试离线。
    """
    sm = sm or state_manager
    cloud_fn = cloud_fn or ask_cloud
    api_key = CLOUD_KEY if api_key is None else api_key
    cloud_url = CLOUD_URL if cloud_url is None else cloud_url
    today = today or datetime.date.today()
    min_age_days = AGING_MIN_AGE_DAYS if min_age_days is None else min_age_days
    if sm.get_meta(AGING_META_KEY) == str(today):
        return None   # 同天已跑（幂等闸）
    sm.set_meta(AGING_META_KEY, str(today))
    todos = [t for t in (sm.get_todos(limit=500) or [])
             if t.get("status") == "pending"]
    promoted = []
    if todos:
        try:
            reply = cloud_fn(build_aging_prompt(todos), api_key, cloud_url)
        except Exception as e:
            print(f"⚠️ [老化] 云端建议调用失败（本日跳过建议，递补照跑）: {e}")
            reply = None
        by_id = {t["id"]: t for t in todos}
        for sug in parse_aging_json(reply):
            t = by_id.get(sug["id"])
            if not t:
                continue
            cur_eff = t.get("effective_priority") or t.get("priority") or "P1"
            if _age_in_days(t.get("created_at"), today) < min_age_days:
                continue   # 拍板①：创建满 N 天才真升
            if _tier_num(sug["suggest"]) >= _tier_num(cur_eff):
                continue   # 拍板③：只升不降（同档/降档建议一律忽略）
            new_tier = TIER_ORDER[max(0, _tier_num(cur_eff) - 1)]   # 拍板②：最多升一档，封顶 P0
            if sm.set_effective_priority(t["id"], new_tier):
                promoted.append({"id": t["id"], "from": cur_eff, "to": new_tier})
    backfilled = run_backfill(sm)
    return {"promoted": promoted, "backfilled": backfilled}


def run_backfill(sm=None):
    """梯队递补（拍板④/⑤/⑥）：某档按生效档分桶 pending 全空 → 紧邻下一
    非空档整体升一档，级联直到无"空档且其下有货"；只增不回退（写
    effective，原列不动，新项入自己档永不触发回退）；P0 参与递补。
    返回 [{"from", "to", "ids"}] 列表。"""
    sm = sm or state_manager
    moved = []
    while True:
        buckets = {p: [] for p in TIER_ORDER}
        for t in (sm.get_todos(limit=500) or []):
            if t.get("status") != "pending":
                continue
            eff = t.get("effective_priority") or t.get("priority") or "P1"
            if eff in buckets:
                buckets[eff].append(t)   # 非法档防御：不进六档桶=不参与递补
        first_empty = next((i for i, p in enumerate(TIER_ORDER)
                            if not buckets[p]), None)
        if first_empty is None:
            break   # 六档全有货：无需递补
        src = next((j for j in range(first_empty + 1, len(TIER_ORDER))
                    if buckets[TIER_ORDER[j]]), None)
        if src is None:
            break   # 空档之下再无货：递补收敛
        to_tier = TIER_ORDER[src - 1]
        ids = [t["id"] for t in buckets[TIER_ORDER[src]]]
        changed = 0
        for tid in ids:
            if sm.set_effective_priority(tid, to_tier):
                changed += 1
        if changed == 0:
            break   # 并发防线：整桶写失败不再重试（防自旋）
        moved.append({"from": TIER_ORDER[src], "to": to_tier, "ids": ids})
    return moved
