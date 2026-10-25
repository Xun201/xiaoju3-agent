# -*- coding: utf-8 -*-
"""agent_state/plugins/dice · 插件总线一期验收样例（#312）。

掷骰子：意图路由（"掷骰子"）+ 模型工具（ext_roll_dice）双通道演示。
故意保留 boom 工具作异常隔离演示（模型误调/主动测试时返回 ❌ 串，主链不受影响）。
"""
import random

def extract_noargs(_message=None, _match=None):
    """意图参数抽取（本意图无参数，恒空 dict——契约要求条目必带 extractor）。"""
    return {}


PLUGIN = {
    "name": "dice",
    "version": "1.0.0",
    "desc": "掷骰子（插件总线一期验收样例）",
    "author": "xun",
    "level": 2,
    "tools": [
        {"name": "ext_roll_dice", "desc": "掷一个骰子并报点数",
         "params": "sides (可选，骰子面数，默认 6)",
         "handler": "agent_state_plugins_dice:roll"},
        {"name": "ext_boom", "desc": "异常隔离演示工具（调用必失败）",
         "params": "无",
         "handler": "agent_state_plugins_dice:boom"},
    ],
    "intents": [
        {"name": "ext_dice_roll", "desc": "掷骰子",
         "patterns": [r"掷骰子", r"掷一个骰子", r"骰子"],
         "extractor": extract_noargs,   # 函数对象直引（内置表同款；handler_name 才是延迟字符串）
         "handler_name": "agent_state_plugins_dice:roll_reply"},
    ],
}

_SETUP_STATE = {"started": False}


def setup(ctx):
    """生命周期钩子演示：记录数据目录（插件私有数据规范位）。"""
    _SETUP_STATE["started"] = True
    _SETUP_STATE["data_dir"] = ctx.get("data_dir", "")


def teardown():
    """卸载钩子演示：落状态标记（真实插件在这里停线程/关资源）。"""
    _SETUP_STATE["started"] = False


def roll(sides=6):
    """模型工具：掷骰子，返回面向用户的中文文本。"""
    sides = int(sides or 6)
    if sides < 2 or sides > 1000:
        return "❌ 骰子面数须在 2-1000 之间。"
    return f"🎲 掷出了 {random.randint(1, sides)} 点（{sides} 面骰）"


def boom():
    """异常隔离演示：必抛异常——dispatch_plugin_tool 兜底为 ❌ 串，主链照常。"""
    raise RuntimeError("这是插件异常隔离演示（dice.boom）")


def roll_reply(**_):
    """意图路由处理器：不走模型直接回（规则层零 token）。"""
    return roll(6)
