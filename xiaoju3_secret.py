#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import subprocess

# 新的目标路径：指向隔离区的环境变量文件
ENV_FILE = "/home/orangepi/xiaoju3_data/.env"

def update_env_variable(key_name, new_value):
    """安全替换 .env 文件中的变量"""
    if not os.path.exists(ENV_FILE):
        print(f"❌ 找不到环境变量文件: {ENV_FILE}")
        return False

    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    found = False
    with open(ENV_FILE, 'w', encoding='utf-8') as f:
        for line in lines:
            if line.startswith(f"{key_name}="):
                f.write(f"{key_name}={new_value}\n")
                found = True
            else:
                f.write(line)

    if not found:
        with open(ENV_FILE, 'a', encoding='utf-8') as f:
            f.write(f"\n{key_name}={new_value}\n")
    return True

def restart_service():
    print("🚀 正在重启小橘3号...")
    try:
        subprocess.run("sudo systemctl restart xiaoju3", shell=True, check=True)
        print("✅ 服务重启成功！")
    except Exception as e:
        print(f"❌ 服务重启失败: {e}")

def main():
    while True:
        os.system('clear')
        print("=" * 40)
        print("        🍊 小橘3号密钥管理控制台 (安全版)")
        print("=" * 40)
        print("1. 修改 DeepSeek API Key")
        print("2. 修改 NapCat Token")
        print("3. 退出")
        print("=" * 40)
        
        choice = input("请选择要执行的操作 [1-3]: ").strip()
        
        if choice == '1':
            key = input("请输入新的 DeepSeek API Key: ").strip()
            if not key:
                print("❌ 输入为空，取消操作")
                input("按回车键继续...")
                continue
            if update_env_variable("DEEPSEEK_API_KEY", key):
                print("✅ API Key 修改成功！已写入隔离区 .env")
                restart_service()
            input("按回车键继续...")
            
        elif choice == '2':
            token = input("请输入新的 NapCat Token: ").strip()
            if not token:
                print("❌ 输入为空，取消操作")
                input("按回车键继续...")
                continue
            if update_env_variable("NAPCAT_TOKEN", token):
                print("✅ NapCat Token 修改成功！")
                restart_service()
            input("按回车键继续...")
            
        elif choice == '3':
            print("再见！")
            break
        else:
            print("❌ 无效选择，请重新输入")
            input("按回车键继续...")

if __name__ == "__main__":
    main()