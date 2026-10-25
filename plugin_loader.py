# -*- coding: utf-8 -*-
"""plugin_loader · 外部插件总线（#312 一期，2026-10-25 五点拍板落地）。

设计正档 _dev/design_plugin_arch.md。核心哲学：不发明新机制，把既有三张
手工表（tool_registry.TOOL_MANIFEST / intent_router.INTENT_PATTERNS /
spec hiddenimports）的"插件贡献部分"改为插件自声明 + 总线自动汇聚。

契约（插件 = agent_state/plugins/ 下一个 .py 文件或目录包，零注册动作）：
    PLUGIN = {
        "name": "dice", "version": "1.0.0", "desc": "…",        # 必填元数据
        "level": 2,                     # 权限等级（外部插件上限 Lv.3，D1）
        "tools": [ {…manifest 同款条目, "handler": "模块:函数"} ],  # 可选
        "intents": [ {…INTENT_PATTERNS 同款条目} ],                 # 可选
        "setup": fn(ctx) / "teardown": fn(),                        # 可选钩子
    }

拍板口径：R1-a 派生消费口动态化（tools.refresh_derived + prompts reload +
main.refresh_system_messages，from-import 快照退役）/ D1 外部插件锁 Lv.3 /
D2 工具名强制 ext_ 前缀 / D3 启动自动加载 + /plugin_reload 手动 / D5 内置
插件双轨并存（本模块不扫内置 plugins/）。

隔离三层：加载期单插件失败跳过+审计（不阻断其他）；setup 超时回滚；
执行期异常隔离由 tool_registry.dispatch_plugin_tool 既有双层 try/except
承担（本模块不重复）。安全立场：外部插件目录=主人设备物理控制，一期
不做代码审计（诚实声明），执行门禁靠既有权限体系兜底。
"""
import importlib
import importlib.util
import os
import re
import sys
import threading
import traceback

_SETUP_TIMEOUT = 30     # setup 钩子超时（秒）——重依赖插件（faster-whisper 链）冷 import 可超 5s（pytest 实锤），30s 覆盖
_TEARDOWN_TIMEOUT = 3   # teardown 钩子超时（秒），异常吞掉照走
_MAX_LEVEL = 3          # D1：外部插件权限上限（Lv.4 主人级能力保留内置）
_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# 已载插件登记：name -> {"plugin": PLUGIN dict, "module": module,
# "source": 文件路径, "origin": "file"|"package"}
_loaded = {}
# 拒载详情（#348 三期诊断）：[{name, source, reason}]，plugin_debug 消费
_rejected = []


def external_dir():
    """外部插件目录：AGENT_STATE_DIR/plugins（frozen 路径铁律——一律经
    xiaoju3.AGENT_STATE_DIR，禁 __file__ fallback）。"""
    import xiaoju3
    return os.path.join(xiaoju3.AGENT_STATE_DIR, "plugins")


def rejected_plugins():
    """拒载详情只读视图（plugin_debug 消费）。"""
    return list(_rejected)


def loaded_plugins():
    """已载插件登记的只读视图（/plugin_list 消费）。"""
    return dict(_loaded)


def _audit(msg):
    """总线审计行（[插件] 前缀，运维一眼可辨；flush=True——frozen 车的
    stdout 全缓冲曾吞审计行致排障盲区，2026-10-25 实锤）。"""
    print(f"[插件] {msg}", flush=True)


def scan():
    """扫描外部插件目录：返回 [(name, 路径, origin)]，sorted 稳定序。

    单文件 *.py 与目录包（含 __init__.py）均算；下划线开头（_草稿）与
    无 PLUGIN 声明的文件跳过。目录不存在=空列表（零插件零成本）。"""
    root = external_dir()
    if not os.path.isdir(root):
        return []
    found = []
    for entry in sorted(os.listdir(root)):
        if entry.startswith("_"):
            continue
        path = os.path.join(root, entry)
        if entry.endswith(".py") and os.path.isfile(path):
            found.append((entry[:-3], path, "file"))
        elif os.path.isdir(path) and os.path.isfile(os.path.join(path, "__init__.py")):
            found.append((entry, path, "package"))
    return found


def _validate(plugin, source, seen_names):
    """契约校验（D1/D2 落地点）。返回错误文案列表（空=通过）。

    校验项：必填元数据 / level 数值且 ≤3（越权直接压回上限，不拒载——
    保守策略：声明 Lv.4 的外部插件按 Lv.3 收录并审计警告）/ tools[].name
    强制 ext_ 前缀 + 全局唯一 + 不与内置冲突 / handler 形态合法。"""
    errs = []
    if not isinstance(plugin, dict):
        return ["PLUGIN 声明必须是 dict"]
    for key in ("name", "version", "level"):
        if not plugin.get(key):
            errs.append(f"缺少必填元数据 {key}")
    if errs:
        return errs
    name = str(plugin["name"])
    if not _TOOL_NAME_RE.match(name):
        errs.append(f"插件名 {name!r} 非法（须 [a-z][a-z0-9_]*）")
    if name in seen_names:
        errs.append(f"插件名 {name!r} 与已载插件冲突")
    if plugin["level"] > _MAX_LEVEL:
        _audit(f"{name} 声明 Lv.{plugin['level']} 超外部插件上限，已压回 Lv.{_MAX_LEVEL}")
        plugin["level"] = _MAX_LEVEL
    builtin_names = {t["name"] for t in importlib.import_module("tool_registry").TOOL_MANIFEST}
    for t in plugin.get("tools") or []:
        tname = t.get("name", "")
        if not tname.startswith("ext_"):
            errs.append(f"工具 {tname!r} 违反 ext_ 前缀强制（D2）")
        if tname in builtin_names:
            errs.append(f"工具 {tname!r} 与内置工具冲突")
        if tname in seen_names or any(tname in (p.get("tools") or []) for
                                      p in [pl["plugin"] for pl in _loaded.values()]):
            errs.append(f"工具 {tname!r} 重名")
        if "handler" not in t or ":" not in str(t.get("handler", "")):
            errs.append(f"工具 {tname!r} 缺合法 handler（'模块:函数'）")
    for it in plugin.get("intents") or []:
        if not it.get("extractor"):
            errs.append(f"意图 {it.get('name', '?')!r} 缺 extractor（路由契约必填）")
        if ":" not in str(it.get("handler_name", "")):
            errs.append(f"意图 {it.get('name', '?')!r} 缺合法 handler_name")
    seen_names.add(name)
    return errs


def _import_plugin(name, path, origin):
    """按路径导入插件模块（绕开 PYZ 静态盲区的关键——数据目录文件不经
    PyInstaller 打包，spec_from_file_location 直接从源加载）。"""
    mod_name = f"agent_state_plugins_{name}"   # sys.modules 顶层隔离命名
    if origin == "file":
        spec = importlib.util.spec_from_file_location(mod_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
    else:
        init_py = os.path.join(path, "__init__.py")
        spec = importlib.util.spec_from_file_location(
            mod_name, init_py, submodule_search_locations=[path])
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
    return module


def _run_hook(fn, args, timeout, label):
    """钩子超时执行（setup/teardown 共用）：线程+join(timeout)，超时/异常
    返回 False（调用方决定回滚或继续）。"""
    result = {"ok": True}

    def _run():
        try:
            fn(*args)
        except Exception as e:
            result["ok"] = False
            _audit(f"{label} 钩子异常: {e}")
    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        _audit(f"{label} 钩子超时（>{timeout}s）")
        return False
    return result["ok"]


def load_all():
    """扫描 → 校验 → 导入 → setup → 汇聚 → 派生刷新（六步生命周期）。

    单插件任何一步失败：跳过+审计，不影响其他插件与主程序（隔离①）。
    返回 (loaded_count, skipped_count)。"""
    unload_all()
    seen = set()
    ok = fail = 0
    tools_acc, intents_acc = [], []
    for name, path, origin in scan():
        try:
            module = _import_plugin(name, path, origin)
        except Exception as e:
            import traceback
            _rejected.append({"name": name, "source": path,
                              "reason": f"导入失败: {e}",
                              "tb": traceback.format_exc()[-600:]})
            _audit(f"{name} 导入失败，跳过: {e}")
            fail += 1
            continue
        raw = getattr(module, "PLUGIN", None)
        # 契约 v1.1（2026-10-25）：PLUGIN 支持工厂函数 def PLUGIN(): return {...}
        # ——常量 dict 引用模块内后定义的函数会在 import 期 NameError（dice/
        # video_ingest 三次踩同坑），工厂延迟求值结构性根治；dict 形态兼容。
        if callable(raw) and not isinstance(raw, dict):
            try:
                plugin = raw()
            except Exception as e:
                _audit(f"{name} PLUGIN() 求值失败，跳过: {e}")
                fail += 1
                continue
        else:
            plugin = raw
        if plugin is None:
            _rejected.append({"name": name, "source": path,
                              "reason": "无 PLUGIN 声明"})
            _audit(f"{name} 无 PLUGIN 声明，跳过")
            fail += 1
            continue
        errs = _validate(plugin, path, seen)
        if errs:
            _rejected.append({"name": name, "source": path,
                              "reason": "契约校验: " + "; ".join(errs)})
            _audit(f"{name} 契约校验未过，跳过: {'; '.join(errs)}")
            fail += 1
            continue
        setup = (plugin or {}).get("setup")
        if callable(setup):
            ctx = {"data_dir": os.path.join(external_dir(), name), "log": _audit}
            if not _run_hook(setup, (ctx,), _SETUP_TIMEOUT, f"{name}.setup"):
                import traceback as _tb
                _rejected.append({"name": name, "source": path,
                                  "reason": "setup 失败/超时",
                                  "tb": _tb.format_exc()[-600:]})
                _audit(f"{name} setup 失败/超时，跳过")
                fail += 1
                continue
        _loaded[plugin["name"]] = {"plugin": plugin, "module": module,
                                   "source": path, "origin": origin}
        tools_acc.extend(plugin.get("tools") or [])
        intents_acc.extend(plugin.get("intents") or [])
        ok += 1
        _audit(f"{name} v{plugin['version']} 已载入"
               f"（工具 {len(plugin.get('tools') or [])}，意图 {len(plugin.get('intents') or [])}）")
    _apply(tools_acc, intents_acc)
    _audit(f"装载完成：{ok} 成功 / {fail} 跳过"
           + (f"（拒载: {[r['name'] for r in _rejected]}）" if _rejected else ""))
    return ok, fail


def _apply(tools_acc, intents_acc):
    """汇聚落账：tool_registry 外部容器写入 + intent_router 注册 + 派生刷新
    （tools.refresh_derived + prompts reload + main.refresh_system_messages，
    R1-a 消费口动态化三件套）。"""
    import tool_registry
    tool_registry.external_tools[:] = tools_acc
    import tools
    tools.refresh_derived()
    try:
        import intent_router
        intent_router.register_external_intents(intents_acc)
    except Exception as e:
        _audit(f"意图汇聚失败（工具已生效）: {e}")
    try:
        import prompts
        importlib.reload(prompts)   # 纯常量模块：reload 即重建 SYSTEM_PROMPT
    except Exception as e:
        _audit(f"prompts reload 失败: {e}")
    try:
        import main
        main.refresh_system_messages()
    except Exception as e:
        _audit(f"会话容器头部刷新失败: {e}")


def unload_all():
    """逐个 teardown（超时吞错）→ sys.modules 摘除 → 清空登记与汇聚容器 →
    派生刷新。reload 的前置半程；无插件时零成本直过。"""
    if not _loaded:
        return
    for name, rec in list(_loaded.items()):
        teardown = rec["plugin"].get("teardown")
        if callable(teardown):
            _run_hook(teardown, (), _TEARDOWN_TIMEOUT, f"{name}.teardown")
        mod_name = rec["module"].__name__
        sys.modules.pop(mod_name, None)
        _audit(f"{name} 已卸载")
    _loaded.clear()
    _apply([], [])


def reload_all():
    """原子整体换装（D3）：unload_all + load_all，主程序不重启。"""
    load_all()   # load_all 首行即 unload_all——幂等


def list_reply():
    """/plugin_list 面向用户的清单文案（权限门禁在指令层）。"""
    if not _loaded:
        return "📦 当前没有已载入的外部插件。"
    lines = ["📦 已载入外部插件："]
    for name, rec in _loaded.items():
        p = rec["plugin"]
        lines.append(f"· {name} v{p.get('version')} —— {p.get('desc', '')}"
                     f"（工具 {len(p.get('tools') or [])}，Lv.{p.get('level')}）")
    return "\n".join(lines)
