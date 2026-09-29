#!/usr/bin/env python3
import os
import random
import subprocess
import sys
import datetime

def main():
    # 1. 生成 6 位动态验证码
    secret_code = str(random.randint(100000, 999999))
    
    print("=" * 45)
    print("      🔐 小橘3号 - 一键重算哈希锁 (动态密码验证)")
    print("=" * 45)
    print(f"⚠️  您的动态验证码是: \033[1;31m{secret_code}\033[0m")
    print("     (输入错误将立即终止操作)")
    user_input = input("👉 请输入验证码以确认重算: ").strip()

    # 2. 验证动态密码
    if user_input != secret_code:
        print("\n❌ 验证码错误，已阻止本次操作！")
        sys.exit(1)

    print("\n✅ 验证通过，正在重新生成哈希指纹...")
    
    # 3. 执行重算和重启
    try:
        # 重新计算哈希
        os.chdir("/home/orangepi/xiaoju3-agent")
        subprocess.run("sha256sum $(cat manifest.txt) > checksums.sha256", shell=True, check=True)
        
        # 记录安全日志
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("/home/orangepi/xiaoju3-agent/logs/security.log", "a") as f:
            f.write(f"[{now}] 用户 orangepi 通过了动态验证，重写了哈希锁。\n")
        print("✅ 哈希更新成功！")

        # 重启服务
        print("🚀 正在重启小橘3号...")
        subprocess.run("sudo systemctl restart xiaoju3", shell=True, check=True)
        print("✅ 服务重启成功！小橘3号已满血复活。")
        
    except Exception as e:
        print(f"❌ 执行失败: {e}")

if __name__ == "__main__":
    main()
