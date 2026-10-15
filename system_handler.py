# -*- coding: utf-8 -*-
"""系统领域 handler（#227 批 0：location/creator/child/help，2026-10-13）。

v2 领域拆分版（design_227b_boundary_v2.md）。轻分派+本体聚合本文件；
**批 C.1（2026-10-15）：creator 本体（署名卡+creator.json 读取）已从
main 迁入**——cb 注入退役改内聚直调（G2 彻底改指拍板）。

【数据域审计地图（#319 灵魂物流判据落地，design_227c_batch_c §一）】
- creator：身份署名（creator.json）——**灵魂核 core，不可镜像**（跟人走）；
- location：user_location.json（.env 为注释误报，实文零 .env 写）——**灵魂核 core，不可镜像（C.2 已迁入 2026-10-16）**；
- child：儿童锁裁决——运行时安全态，非灵魂核（本体暂留 main，全局状态
  网强耦合单列待办，2026-10-15 评估）；
- 镜像只发生在数据层文件，代码层不存在第二份数据（依赖方向纪律）。

分派顺序纪律：main 中 location → creator → child → help 的先后即既有
管线序，迁出后调用点保持同序（行为等价由黄金样本守护）。

接口纪律：每 handler ≤3 参数；本模块零 import main。
"""
import json
import os

import paths  # 双根路径锚（creator.json 等用户数据锚定数据根）


def handle_location(command_text):
    """位置指令分派（批 C.2：本体 location_command 迁入本模块，内聚直调）。"""
    return location_command(command_text)


def get_creator_name(base_dir=None):
    """创作者署名（xiaoju3_data/creator.json 存在即激活；缺省返回 ""）。

    只表现署名，不授予任何权限（权限由 LV4 决定）。公开版（无隔离区
    文件）返回空串，所有署名位置自动隐藏。base_dir 仅供测试注入临时
    目录（缺省 = 数据根下 xiaoju3_data）。
    """
    base = base_dir or os.path.join(paths.DATA_ROOT,
                                    "xiaoju3_data")
    path = os.path.join(base, "creator.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str((data or {}).get("name") or "").strip()
    except Exception:
        return ""


def creator_command():
    """/creator 命令本体：返回创作者署名卡（QQ 与网页控制台共用）。

    creator.json 存在 → 署名卡；缺失 → 开源项目链接。不要求任何权限
    （LV1 也可查）。
    """
    name = get_creator_name()
    if name:
        return f"🦊 小橘3号 · 由 {name} 创造与维护"
    return "🦊 小橘3号 · 开源项目（https://github.com/Xun201/xiaoju3-agent）"


def location_command(message):
    """位置指令本体（2026-10-02 隐私口径；批 C.2 自 main 迁入）：QQ 与网页共用。

    - /set_location <城市> [区县] → 写入本地位置记忆
      （agent_state/user_location.json，gitignore 不入库）；
    - /clear_location → 清除位置记录；
    - 命中返回回复文本；未命中返回 None（调用方继续走正常对话链路）。
    位置不上传 GitHub、不写 .env、不传云端（仅天气/本地搜索时用于拼 query）。
    清除静默期：brain 内存标记（5 分钟内视为位置未知，不落盘）。
    """
    text = (message or "").strip()
    if text.startswith("/set_location"):
        arg = text[len("/set_location"):].strip()
        parts = arg.split()
        if not parts:
            return ("📍 用法：/set_location <城市> [区县]，"
                    "例如：/set_location 长沙 天心区")
        city = parts[0]
        district = parts[1] if len(parts) > 1 else None
        try:
            from agent_state.state_manager import save_user_location
            save_user_location(city, district)
        except Exception as e:
            return f"❌ 位置记录失败: {e}"
        shown = city + (f" {district}" if district else "")
        return (f"✅ 位置已记录：{shown}（仅存本地 agent_state/user_location.json，"
                "可用 /clear_location 清除）")
    if text.startswith("/clear_location"):
        try:
            from agent_state.state_manager import clear_user_location
            clear_user_location()
        except Exception as e:
            return f"❌ 位置记录清除失败: {e}"
        # 🚿 清除静默期（2026-10-02 用户口径）：历史消息里的位置仍会把小
        # 模型带偏（从历史推断位置继续用）——清除后 5 分钟内强制视为位置
        # 未知，确保 AI 重新询问（brain 内存标记，不落盘）
        try:
            import brain
            brain.mark_location_cleared()
            brain.clear_waiting_location()   # 遗留的等待回答窗口一并关闭
        except Exception as mark_err:
            print(f"⚠️ 位置静默期标记失败（不影响清除）: {mark_err}")
        return "✅ 位置记录已清除（本地 agent_state/user_location.json）"
    return None


def handle_creator(command_text):
    """创作者署名分派（/creator 精确匹配——去 CQ 码后 raw_message 形态）。"""
    if command_text == "/creator":
        return creator_command()
    return None


def handle_child(command_text, user_key, child_cb):
    """儿童锁裁决转发（/approve /deny，无锁时 cb 自回拒绝文案）。"""
    return child_cb(command_text, user_key)


def handle_help(command_text, level_str_cb):
    """指令菜单（裸 help/大小写不敏感——#264 B2c 后补口径）。

    菜单本体 get_help_menu 在 plugins/help_menu（非 main 域，局部 import
    直接用——plugins 包引用合法）。"""
    if command_text.lower() in ["/help", "help", "菜单", "帮助", "指令"]:
        from plugins.help_menu import get_help_menu
        return get_help_menu(level_str_cb())
    return None
