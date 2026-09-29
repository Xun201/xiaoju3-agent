import os
import subprocess
import sys
sys.path.append('/home/orangepi/xiaoju3_data')
from config import WORKSPACE
from home_tools import get_ha_states, control_ha_device
from adb_tools import adb_screenshot, adb_tap, adb_swipe
from vision_tools import vision_tap_element
from android_ui_tools import ui_tap_element
from permission import permission_manager

def execute_tool(tool_name, args):
    try:
        DANGER_TOOLS = ["adb_tap", "adb_swipe", "write_file", "control_ha_device"]
        if tool_name in DANGER_TOOLS and not permission_manager.has_permission("write_file"):
            return "❌ 安全拒绝：当前权限不足，无法执行此物理控制操作！"

        if tool_name == "list_files":
            result = subprocess.run(["ls", "-la", WORKSPACE], capture_output=True, text=True)
            return result.stdout if result.stdout else "（工作区为空）"
        
        elif tool_name == "read_file":
            filepath = os.path.join(WORKSPACE, args["filename"])
            if not os.path.realpath(filepath).startswith(os.path.realpath(WORKSPACE)):
                return "❌ 安全拒绝：不允许访问工作区以外的文件！"
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    return f.read()[:1000]
            return f"文件 {args['filename']} 不存在。"
        
        elif tool_name == "write_file":
            filepath = os.path.join(WORKSPACE, args["filename"])
            if not os.path.realpath(filepath).startswith(os.path.realpath(WORKSPACE)):
                return "❌ 安全拒绝：不允许访问工作区以外的文件！"
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(args["content"])
            return f"✅ 文件 {args['filename']} 写入成功！"
        
        # === 🆕 新增：智能家居工具 ===
        elif tool_name == "get_ha_devices":
            return get_ha_states()
            
        elif tool_name == "control_ha_device":
            entity_id = args.get("entity_id")
            action = args.get("action")
            if not entity_id or not action:
                return "❌ 缺少参数：需要提供 entity_id 和 action"
            return control_ha_device(entity_id, action)
        # ============================
        
        # === 🆕 新增：ADB 手机接管工具 ===
        elif tool_name == "adb_screenshot":
            return adb_screenshot()
        elif tool_name == "adb_tap":
            x = args.get("x")
            y = args.get("y")
            if x is None or y is None:
                return "❌ 缺少参数：需要提供 x 和 y 坐标"
            return adb_tap(int(x), int(y))
        elif tool_name == "adb_swipe":
            return adb_swipe(int(args.get("x1")), int(args.get("y1")), int(args.get("x2")), int(args.get("y2")))

        # === 🆕 新增：视觉元素点击 ===
        elif tool_name == "vision_tap_element":
            element_name = args.get("element_name")
            if not element_name:
                return "❌ 缺少参数：需要提供 element_name (要点击的文字/图标名称)"
            return vision_tap_element(element_name)

         # === 🆕 新增：UI 层级精准点击 ===
        elif tool_name == "ui_tap_element":
            element_name = args.get("element_name")
            if not element_name:
                return "❌ 缺少参数：需要提供 element_name (要点击的按钮或图标名称)"
            return ui_tap_element(element_name)

        return "未知工具"
    except Exception as e:
        return f"工具执行失败: {e}"