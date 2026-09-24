import json
import os

CORE_FILE = "/mnt/agent/memory/core_memory.json"
CORE_PASSWORD = "XUNandorangepi"  # 你的专属密码，可以改成你喜欢的

def load_core_memory():
    if os.path.exists(CORE_FILE):
        try:
            with open(CORE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_core_memory(data):
    try:
        os.makedirs(os.path.dirname(CORE_FILE), exist_ok=True)
        with open(CORE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
