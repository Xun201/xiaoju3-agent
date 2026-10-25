# -*- coding: utf-8 -*-
"""pytest 全局夹具（2026-10-25 #312 插件总线配套）。

XIAOJU3_PLUGIN_AUTOLOAD=0：测试环境禁用 main 模块级插件自动装载——真机
agent_state/plugins/ 的插件（如验收样例 dice.py）会经 load_all 污染派生
常量（tools.TOOL_WHITELIST 变 17 项），打穿"内置 15 项"类语义断言（测试
顺序依赖）。插件行为测试在 test_plugin_loader.py 内自管（tmp 目录+显式
load），本哨兵只关自动装载这条线。
"""
import os

os.environ.setdefault("XIAOJU3_PLUGIN_AUTOLOAD", "0")
