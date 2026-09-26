import os
import subprocess
import sys
sys.path.append('/home/orangepi/xiaoju3_data')
from config import WORKSPACE

def execute_tool(tool_name, args):
    try:
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
        return "未知工具"
    except Exception as e:
        return f"工具执行失败: {e}"
