# -*- coding: utf-8 -*-
"""pytest 全局夹具（双哨兵）。

1. XIAOJU3_PLUGIN_AUTOLOAD=0（2026-10-25 #312 插件总线配套）：测试环境禁用
   main 模块级插件自动装载——真机 agent_state/plugins/ 的插件会经 load_all
   污染派生常量（tools.TOOL_WHITELIST 变 17 项），打穿"内置 15 项"类语义
   断言（测试顺序依赖）。插件行为测试在 test_plugin_loader.py 内自管。
   【2026-10-28 事故教训】该哨兵曾被同日新批的 conftest 覆盖写抹掉（新批
   只写了自家开关没读原文件）→ ext_* 泄漏白名单打穿 test_brain——**改全局
   夹具前必先读原内容合并，禁止整文件覆盖**。
2. XIAOJU3_QQ_CLOUD_TAKEOVER=0（2026-10-28 多脑重组配套）：QQ 闲聊云端
   直回分支测试态强制关闭——测试进程经隔离区 .env 拿到真 DEEPSEEK_API_KEY
   会真调 DeepSeek（花钱+断言不确定）；生产无此键=默认开。
"""
import os

os.environ.setdefault("XIAOJU3_PLUGIN_AUTOLOAD", "0")
os.environ["XIAOJU3_QQ_CLOUD_TAKEOVER"] = "0"
