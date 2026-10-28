# -*- coding: utf-8 -*-
"""agent_state/plugins/stock_assistant · 炒股辅助插件（二期：全量流水线）。

队长三层选股逻辑（纯代码硬算，LLM 只做政策面解读）：
- 第一层 行业筛选：巨潮行业 PE 表按净利润-静态排名 top10
- 第二层 政策匹配：行业名交云端大模型（DeepSeek）总结近期利好政策
  （1-2 句/行业，无政策如实说）；**不用本地小脑**
- 第三层 个股过滤：国企/集体（巨潮实控人名称启发式）+ 现价 5-20 元，
  每行业至多 3 只代表性股票（按总市值取大）

数据源（2026-10-28 实测，零东财依赖——东财 push2 对本 IP 频控）：
- 行业盈利排名：巨潮 stock_industry_pe_ratio_cninfo（净利润-静态）
- 行业成分+现价：新浪 stock_sector_spot/detail（一张表带价）
- 实际控制人：巨潮 stock_hold_control_cninfo 全表 → 名称启发式
  （⚠️'国资'在'国有资产'中不连续，词表含 国有资产/国资委/国有）

依赖与打包：akshare 走 agent_state/plugins/_deps/（video_ingest 同款
pip --target 模式，setup 钩子 sys.path 注入，frozen exe 零包体增量）；
akshare 缺席时工具返回诚实提示，插件本体照常装载（意图路由不瘫）。

合规：输出末尾强制硬编码合规声明（不构成投资建议）。
耗时：冷启动约 15-25s（13 次网络请求），结果缓存 6h——工具描述里如实
告知模型"首次较慢"。
"""
import json
import os
import re
import sys
import time

# repo 根入 path（独立脚本形态跑时 brain 可导；frozen/装载形态本就可达）
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

CACHE_TTL = 6 * 3600
COMPLIANCE = "⚠️ 以上仅为基于公开数据的自动化筛选结果，不构成任何投资建议。"

#: 国企/集体启发式（一期校准版——"国资"在"国有资产"中不连续，勿改回 bigram）
SOE_PATTERNS = (
    re.compile(r"国有资产"),        # XX市国有资产监督管理委员会（最常见）
    re.compile(r"国资委"),          # 国务院国资委 等简称
    re.compile(r"国有"),            # 国有资本运营/国有企业
    re.compile(r"人民政府"),
    re.compile(r"财政局"),
    re.compile(r"国务院"),
    re.compile(r"^中国.{2,8}(集团|公司|总公司)"),   # 央企系（中国XX集团）
    re.compile(r"(集体|供销)"),
)

#: 巨潮二级行业名 → 新浪板块 label（确定性覆盖；未命中走模糊，再未命中="无"）
SECTOR_OVERRIDES = {
    "货币金融服务": "new_jrhy",
    "资本市场服务": "new_jrhy",
    "保险业": "new_jrhy",
    "计算机、通信和其他电子设备制造业": "new_dzxx",
    "电气机械和器材制造业": "new_dqhy",
    "电力、热力生产和供应业": "new_dlhy",
    "石油和天然气开采业": "new_syhy",
    "酒、饮料和精制茶制造业": "new_ljhy",
    "化学原料和化学制品制造业": "new_hghy",
    "土木工程建筑业": "new_jzjc",
}

_DEPS = ""
_DATA = ""
_CACHE_FILE = ""


def PLUGIN():
    return {
        "name": "stock_assistant",
        "version": "0.2.0",
        "desc": "炒股辅助（二期）：盈利行业 top10 + 国企 5-20 元筛选 + 政策面解读",
        "author": "xun",
        "level": 3,
        "tools": [
            {"name": "ext_stock_screen",
             "desc": "三层选股扫描：净利润 top10 行业 → 每行业筛国企/集体且现价"
                     "5-20 元的股票（至多 3 只）→ 云端总结各行业政策面。首次运行"
                     "约 20 秒（数据源限速），当天再问走缓存秒回。",
             "params": "无（固定口径；行业范围=全市场二级行业）",
             "note": "当主人想选股/查国企股/看行业景气度与政策面时使用。回复必须"
                     "保留工具输出末尾的合规声明。",
             "handler": "agent_state_plugins_stock_assistant:stock_screen_reply"},
        ],
    }


def setup(ctx):
    """生命周期钩子：_deps 注入（akshare 依赖自足）+ 数据目录就位。"""
    global _DEPS, _DATA, _CACHE_FILE
    _DEPS = os.path.abspath(os.path.join(ctx.get("data_dir") or "",
                                         os.pardir, "_deps"))
    _DATA = ctx.get("data_dir") or os.path.dirname(os.path.abspath(__file__))
    os.makedirs(_DATA, exist_ok=True)
    _CACHE_FILE = os.path.join(_DATA, "stock_assistant_cache.json")
    if os.path.isdir(_DEPS) and _DEPS not in sys.path:
        sys.path.insert(0, _DEPS)
    try:
        import akshare  # noqa: F401
        ctx.get("log")("akshare 预检通过")
    except Exception as e:
        ctx.get("log")(f"akshare 缺席（工具将返回依赖提示）: {e}")


# ── 缓存 ──

def _cache_file():
    global _CACHE_FILE
    if not _CACHE_FILE:
        _CACHE_FILE = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "stock_assistant_cache.json")
    return _CACHE_FILE


def _cached(key, fetch_fn, ttl=CACHE_TTL):
    try:
        with open(_cache_file(), encoding="utf-8") as f:
            ent = json.load(f).get(key)
        if ent and time.time() - ent.get("ts", 0) < ttl:
            return ent["data"]
    except Exception:
        pass
    data = fetch_fn()
    try:
        cache = {}
        try:
            with open(_cache_file(), encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass
        cache[key] = {"ts": time.time(), "data": data}
        with open(_cache_file(), "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass
    return data


# ── 数据层（akshare 全部惰性导入；请求间礼貌间隔） ──

_POLITE = 2.0


def _is_soe(controller_name):
    """实控人名称 → (是否国企/集体, 命中依据)。空/无/自然人 → False。"""
    name = str(controller_name or "").strip()
    if not name or name in ("无", "None", "nan"):
        return False, ""
    for pat in SOE_PATTERNS:
        m = pat.search(name)
        if m:
            return True, m.group(0)
    return False, ""


def top_industries(n=10):
    """第一层：巨潮行业 PE 表按净利润-静态排名（二级行业）。

    当日数据可能未出（实测 20261028 空表）→ 自动回退找最近有数的交易日
    （最多回退 7 天），宁用昨日真数不用空表。"""
    import akshare as ak
    import datetime
    df = None
    for back in range(7):
        day = (datetime.date.today() - datetime.timedelta(days=back)
               ).strftime("%Y%m%d")
        try:
            df = ak.stock_industry_pe_ratio_cninfo(
                symbol="证监会行业分类", date=day)
        except Exception:
            df = None
        if df is not None and len(df) > 0:
            if back:
                print(f"🦊 [stock] 巨潮当日数据未出，回退至 {back} 天前")
            break
        time.sleep(1)
    if df is None or len(df) == 0:
        raise RuntimeError("巨潮行业 PE 表近 7 天均无数据")
    d = df[df["净利润-静态"].notna()].copy()
    d["净利润-静态"] = d["净利润-静态"].astype(float)
    d = d[d["行业层级"] == 2.0]
    d = d.sort_values("净利润-静态", ascending=False).head(n)
    time.sleep(_POLITE)
    return [(str(r["行业编码"]), str(r["行业名称"]), float(r["净利润-静态"]))
            for _, r in d.iterrows()]


def sina_sector_map():
    """新浪板块名录 {label: 板块名}（映射层的匹配目标）。"""
    import akshare as ak
    df = ak.stock_sector_spot(indicator="新浪行业")
    time.sleep(_POLITE)
    return {str(r["label"]): str(r["板块"]) for _, r in df.iterrows()}


def match_sector(cninfo_name, sector_map):
    """巨潮行业名 → 新浪 label：先查确定性覆盖表，再 2 字前缀模糊，
    都不中返回 None（该行业记"无"）。"""
    if cninfo_name in SECTOR_OVERRIDES:
        lab = SECTOR_OVERRIDES[cninfo_name]
        return lab if lab in sector_map else None
    prefix = cninfo_name[:2]
    for lab, sname in sector_map.items():
        if prefix and prefix in sname:
            return lab
    return None


def sector_constituents(label):
    """新浪板块成分（一张表带现价与市值）→ [{code,name,price,mktcap}]。"""
    import akshare as ak
    df = ak.stock_sector_detail(sector=label)
    time.sleep(_POLITE)
    out = []
    for _, r in df.iterrows():
        try:
            out.append({"code": str(r["code"]), "name": str(r["name"]),
                        "price": float(r["trade"]),
                        "mktcap": float(r["mktcap"])})
        except (TypeError, ValueError):
            continue
    return out


def controller_latest():
    """巨潮实控人全表 → 每公司最新一条 {code: 实控人名称}。"""
    import akshare as ak
    df = ak.stock_hold_control_cninfo(symbol="全部")
    time.sleep(_POLITE)
    latest = df.sort_values("变动日期").groupby("证券代码").tail(1)
    return {str(r["证券代码"]): str(r["实际控制人名称"])
            for _, r in latest.iterrows()}


# ── 流水线（纯硬逻辑） ──

def scan_pipeline(top_n=10, per_cap=3, price_lo=5.0, price_hi=20.0,
                  log=lambda m: None):
    """全量扫描：返回 (行业结果列表, markdown 表)。行业映射缺失/零命中→"无"。"""
    tops = _cached("top_industries", lambda: top_industries(top_n))
    smap = _cached("sector_map", sina_sector_map)
    ctrl = _cached("controllers", controller_latest, ttl=7 * 24 * 3600)
    results = []
    for code, name, profit in tops:
        label = match_sector(name, smap)
        if not label:
            results.append({"行业": name, "净利润亿": round(profit),
                            "板块": None, "rows": [], "note": "无（行业映射缺失）"})
            log(f"  · {name} 无新浪板块映射，记'无'")
            continue
        sname = smap[label]
        try:
            cons = _cached(f"cons:{label}", lambda l=label: sector_constituents(l))
        except Exception as e:
            results.append({"行业": name, "净利润亿": round(profit),
                            "板块": sname, "rows": [],
                            "note": f"无（成分拉取失败: {type(e).__name__}）"})
            continue
        picked = []
        for c in sorted(cons, key=lambda x: -x["mktcap"]):
            if len(picked) >= per_cap:
                break
            cname = c["name"]
            if not (price_lo <= c["price"] <= price_hi):
                continue
            soe, hit = _is_soe(ctrl.get(c["code"], ""))
            if not soe:
                continue
            picked.append({"行业": name, "公司": cname, "代码": c["code"],
                           "现价": c["price"], "实控人": ctrl.get(c["code"], ""),
                           "命中依据": hit})
        note = f"无（{sname} 内无国企/集体 5-20 元标的）" if not picked else ""
        results.append({"行业": name, "净利润亿": round(profit),
                        "板块": sname, "rows": picked, "note": note})
        log(f"  · {name}({sname}) 命中 {len(picked)}")
    return results


def build_markdown(results):
    """结果 → Markdown 表（无命中行业带"无"标注行）。"""
    lines = ["| 行业（净利润亿） | 公司 | 代码 | 现价 | 实控人 |",
             "|---|---|---|---|---|"]
    for r in results:
        head = f"{r['行业']}（{r['净利润亿']}亿）"
        if r["rows"]:
            for row in r["rows"]:
                lines.append(f"| {head} | {row['公司']} | {row['代码']} "
                             f"| {row['现价']} | {row['实控人']} |")
        else:
            lines.append(f"| {head} | {r.get('note') or '无'} | — | — | — |")
    return "\n".join(lines)


def build_json(results):
    return json.dumps(results, ensure_ascii=False, indent=1)


# ── 第二层：政策匹配（云端大模型，不用本地小脑） ──

_POLICY_PROMPT = (
    "你是政策研究员。下面是 A 股净利润排名前 10 的行业列表。请逐个行业总结"
    "国家近期对该行业的利好政策（如没有明确的近期政策，请如实说明\"近期无"
    "明确政策\"），每个行业 1-2 句话，格式严格为：行业名：总结。不要输出"
    "其他内容。\n\n行业列表：\n{list}")


def policy_summary(industry_names, chat_fn=None):
    """云端大模型政策解读；失败返回诚实占位（绝不阻塞主流程）。"""
    try:
        if chat_fn is None:
            from brain import ask_cloud as chat_fn
        out = str(chat_fn([
            {"role": "system", "content": "你是政策研究员，只按要求输出行业总结。"},
            {"role": "user",
             "content": _POLICY_PROMPT.format(list="\n".join(industry_names))},
        ]) or "").strip()
        return out or "（政策面：云端返回为空）"
    except Exception as e:
        return f"（政策面获取失败：{type(e).__name__}，可稍后重试）"


# ── 入口（工具/意图共用） ──

def build_text(results):
    """QQ 纯文本形态（QQ 不渲染 Markdown 表格——竖线出戏）。"""
    lines = []
    for r in results:
        head = f"【{r['行业']}】净利润约 {r['净利润亿']} 亿"
        if r["rows"]:
            lines.append(head)
            for row in r["rows"]:
                lines.append(f"  · {row['公司']}（{row['代码']}）"
                             f"现价 {row['现价']} 元｜实控人：{row['实控人']}")
        else:
            lines.append(head + f"：{r.get('note') or '无符合条件标的'}")
    return "\n".join(lines)


def stock_screen_text(message="", **kwargs):
    """QQ 通道入口（强拦截用）：同 stock_screen_reply 但输出纯文本形态。"""
    try:
        results = _cached("pipeline_full", lambda: scan_pipeline(log=_dbg),
                          ttl=CACHE_TTL)
    except Exception as e:
        return (f"❌ 选股扫描失败：{type(e).__name__}（数据源暂不可用，"
                "请稍后再试）")
    try:
        policy = policy_summary([r["行业"] for r in results])
    except Exception:
        policy = "（政策面获取失败，可稍后重试）"
    text = build_text(results)
    return (f"📊 净利润 top10 行业 × 国企 5-20 元筛选\n\n【政策面】\n{policy}"
            f"\n\n【筛选结果】\n{text}\n\n{COMPLIANCE}")


def stock_screen_reply(message="", **kwargs):
    """ext_stock_screen / 意图路由共用入口：全量扫描+政策面+合规声明。"""
    try:
        results = _cached("pipeline_full", lambda: scan_pipeline(log=_dbg),
                          ttl=CACHE_TTL)
    except Exception as e:
        return (f"❌ 选股扫描失败：{type(e).__name__}（数据源暂不可用，"
                "请稍后再试）")
    try:
        policy = policy_summary([r["行业"] for r in results])
    except Exception:
        policy = "（政策面获取失败，可稍后重试）"
    md = build_markdown(results)
    return (f"📊 净利润 top10 行业 × 国企 5-20 元筛选\n\n【政策面】\n{policy}"
            f"\n\n【筛选结果】\n{md}\n\n{COMPLIANCE}")


def _dbg(m):
    print(f"🦊 [stock] {m}")


def selftest():
    """离线自检：假数据注入（零网络零 akshare），锁死契约行为。"""
    fake_results = [
        {"行业": "电力A", "净利润亿": 100, "板块": "电力行业",
         "rows": [{"行业": "电力A", "公司": "甲电力", "代码": "600001",
                   "现价": 8.8, "实控人": "某市国有资产监督管理委员会",
                   "命中依据": "国有资产"}],
         "note": ""},
        {"行业": "保险B", "净利润亿": 90, "板块": "金融行业", "rows": [],
         "note": "无（金融行业 内无国企/集体 5-20 元标的）"},
    ]
    md = build_markdown(fake_results)
    assert "| 电力A（100亿） | 甲电力 | 600001 | 8.8 |" in md
    assert "无（金融行业" in md
    js = build_json(fake_results)
    assert "甲电力" in js
    # 合规声明强制（QQ 纯文本/Markdown 双形态输出在 test_stock_assistant 覆盖）
    assert COMPLIANCE.startswith("⚠️")
    # SOE 启发式（一期校准回归）
    assert _is_soe("绵阳市国有资产监督管理委员会")[0]
    assert _is_soe("国务院国资委")[0]
    assert not _is_soe("梁昭贤;梁惠强")[0]
    assert not _is_soe("无")[0]
    # 映射表：模糊+覆盖双路径
    smap = {"new_dlhy": "电力行业", "new_jrhy": "金融行业", "new_dqhy": "电器行业"}
    assert match_sector("电力、热力生产和供应业", smap) == "new_dlhy"
    assert match_sector("货币金融服务", smap) == "new_jrhy"
    assert match_sector("电气机械和器材制造业", smap) == "new_dqhy"
    assert match_sector("不认识的行业XYZ", smap) is None
    print("STOCK_ASSISTANT_SELFTEST_OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        _dbg("全量扫描开始（冷启动约 20s）")
        results = scan_pipeline(log=_dbg)
        policy = policy_summary([r["行业"] for r in results])
        print("\n【政策面】\n" + policy)
        print("\n【筛选结果】\n" + build_markdown(results))
        print("\n" + COMPLIANCE)
