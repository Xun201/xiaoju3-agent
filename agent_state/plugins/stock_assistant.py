# -*- coding: utf-8 -*-
"""agent_state/plugins/stock_assistant · 炒股辅助插件（一期：数据源验证）。

队长三层选股逻辑（2026-10-28 晚更新，取代早期 ratio 筛选方案）：
- 第一层 行业筛选：行业盈利排名（净利润/ROE top10）
- 第二层 政策匹配：非结构化，交 LLM 搜索/RAG（一期只输出行业名）
- 第三层 个股过滤：国企/集体（实控人属性）+ 现价 5-20 元

数据源结论（2026-10-28 晚实测，_dev/stock_data_test.py 全链验证）：
- 行业盈利排名：巨潮 stock_industry_pe_ratio_cninfo（净利润-静态，120 行业）
- 行业成分+现价：新浪 stock_sector_spot/detail（new_jdhy 家电 37 只带价）
- 实际控制人：巨潮 stock_hold_control_cninfo 全表 → 名称启发式
  （⚠️"国资"二字在"国有资产"中不连续，词表必须含"国有资产/国资委/国有"）
- 备选现价：腾讯 stock_zh_a_spot_tx（zxj 列）；东财 push2 对本 IP 频控
  封锁（反复重试疑似重置计时）——二期严禁实时拉东财
- 本模块早期 ratio 筛选（研发/营业利润）已按新三层逻辑暂停，screen() 留作
  数据层参考；二期按三层逻辑重构+注册 ext_stock_screen 工具（_deps 模式）
"""
import json
import os
import sys
import time

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "stock_assistant_cache.json")

POLITE_SLEEP = 2.5          # 请求间隔（东财 WAF 频控实测，宁慢勿封）
CACHE_TTL = 6 * 3600        # 财务数据当日级够用（缓存 6h）


def PLUGIN():
    """一期骨架：零工具注册（队长拍板：先验数据源，不接 LLM/路由）。"""
    return {
        "name": "stock_assistant",
        "version": "0.1.0",
        "desc": "炒股辅助（一期）：行业硬逻辑筛选器骨架，tools=[] 不注册工具",
        "author": "xun",
        "level": 3,
        "tools": [],
    }


def setup(*args, **kwargs):     # loader 兼容：无初始化需求
    return None


# ── 数据层（惰性 import akshare：生产装载零开销，frozen 未打包也能 import 本模块） ──

def _cache_load():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _cache_save(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def _cached(key, fetch_fn, ttl=CACHE_TTL):
    """带 TTL 的请求级缓存（WAF 频控防线的一半，另一半是限速）。"""
    cache = _cache_load()
    ent = cache.get(key)
    if ent and time.time() - ent.get("ts", 0) < ttl:
        return ent["data"]
    data = fetch_fn()
    cache[key] = {"ts": time.time(), "data": data}
    _cache_save(cache)
    return data


def industry_constituents(industry="家电行业"):
    """行业成分股（东财，含市值）：返回 [{code, name, mktcap}]。"""
    import akshare as ak
    df = ak.stock_board_industry_cons_em(symbol=industry)
    df = df.sort_values("总市值", ascending=False)
    return [{"code": str(r["代码"]), "name": str(r["名称"]),
             "mktcap": float(r["总市值"])}
            for _, r in df.iterrows()]


def financial_income(symbol):
    """新浪利润表（需交易所前缀：6→sh / 0,3→sz / 4,8→bj）。
    返回最新报告期一行的 {研发费用, 营业利润, 报告日}。"""
    import akshare as ak
    code = str(symbol)
    if code.startswith(("sh", "sz", "bj")):
        full = code
    elif code[0] == "6":
        full = "sh" + code
    elif code[0] in "03":
        full = "sz" + code
    elif code[0] in "48":
        full = "bj" + code
    else:
        full = "sz" + code
    df = ak.stock_financial_report_sina(stock=full, symbol="利润表")
    time.sleep(POLITE_SLEEP)    # 频控防线：每请求后强制间隔
    row = df.sort_values("报告日", ascending=False).iloc[0]
    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return {"报告日": str(row.get("报告日", "")),
            "研发费用": _f(row.get("研发费用")),
            "营业利润": _f(row.get("营业利润"))}


def screen(industry="家电行业", top=8, lo=0.10, hi=0.20, log=print,
           cons_list=None):
    """硬逻辑筛选：行业市值 top N → 研发费用/营业利润 ∈ [lo, hi] 且盈利。

    口径：研发费用占**营业利润**比（队长命题）；两者取同一最新报告期。
    cons_list：注入成分股列表（[{code,name,mktcap}]）——东财被频控时用
    （二期单测依赖隔离口）。返回 (hits, allrows)。"""
    tops = cons_list if cons_list is not None else \
        _cached(f"cons:{industry}", lambda: industry_constituents(industry))
    tops = tops[:top]
    hits, allrows = [], []
    for ent in tops:
        code, name = ent["code"], ent["name"]
        try:
            fin = _cached(f"inc:{code}", lambda c=code: financial_income(c))
        except Exception as e:
            log(f"  ⚠️ {name}({code}) 财务拉取失败: {type(e).__name__}")
            continue
        op, rd = fin.get("营业利润"), fin.get("研发费用")
        if not op or not rd or op <= 0:
            log(f"  · {name}({code}) 数据缺失或亏损（op={op}, rd={rd}）")
            continue
        ratio = rd / op
        row = (code, name, rd, op, ratio)
        allrows.append(row)
        tag = "✔" if lo <= ratio <= hi else " "
        if tag == "✔":
            hits.append(row)
        log(f"  {tag} {name}({code}) [{fin.get('报告日')}] "
            f"研发 {rd / 1e8:.2f}亿 / 营业利润 {op / 1e8:.2f}亿"
            f" = {ratio:.1%}")
    return hits, allrows


def main(argv=None):
    log = print
    log("== stock_assistant 一期筛选器（家电行业 市值top8 研发/营业利润 10%-20% 且盈利）==")
    hits, allrows = screen(log=log)
    log(f"\n== 命中 {len(hits)}/{len(allrows)} ==")
    for code, name, rd, op, ratio in hits:
        log(f"  ★ {name}({code}) 占比 {ratio:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
