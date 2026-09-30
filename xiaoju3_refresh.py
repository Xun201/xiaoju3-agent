#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小橘3号 · 一键重算哈希锁（动态 6 位确认码验证，架构设计文档 §8）。

流程：动态 6 位确认码校验通过后 → 重算 sha256（按 manifest.txt 清单）
      → 追加安全日志 → systemctl 重启服务。

核心逻辑（确认码生成/校验、sha256 重算、命令组装）为纯函数，
systemctl/subprocess 调用封装在可注入 runner 的函数中，全部可离线单测。
"""
import datetime
import hashlib
import os
import random
import subprocess
import sys

# 部署目录：默认脚本所在目录（不硬编码机器路径），可用环境变量 XIAOJU3_PROJECT_DIR 覆盖
PROJECT_DIR = os.environ.get("XIAOJU3_PROJECT_DIR") or os.path.dirname(os.path.abspath(__file__))
SERVICE_NAME = os.environ.get("XIAOJU3_SERVICE", "xiaoju3")
MANIFEST_FILE = "manifest.txt"
CHECKSUM_FILE = "checksums.sha256"
LOG_DIR = "logs"


def generate_code():
    """生成 6 位动态验证码（参考实现口径：100000-999999 随机数）。"""
    return str(random.randint(100000, 999999))


def verify_code(expected, actual):
    """校验输入是否与 6 位动态码一致；非 6 位纯数字输入一律拒绝。"""
    if not isinstance(actual, str):
        return False
    if len(actual) != 6 or not actual.isdigit():
        return False
    return actual == expected


def recompute_checksums(project_dir):
    """按 manifest.txt 清单重算 sha256，写入 checksums.sha256（sha256sum 兼容格式）。

    返回 [(相对路径, 哈希)] 列表；清单缺失或为空时抛异常。
    """
    manifest_path = os.path.join(project_dir, MANIFEST_FILE)
    if not os.path.isfile(manifest_path):
        raise FileNotFoundError(f"缺少清单文件: {manifest_path}（请先运行 make_manifest.sh 生成）")
    with open(manifest_path, "r", encoding="utf-8") as f:
        files = [line.strip() for line in f if line.strip()]
    if not files:
        raise ValueError("manifest.txt 为空，无文件可哈希（请先运行 make_manifest.sh）")

    lines = []
    for rel in files:
        path = os.path.join(project_dir, rel)
        hasher = hashlib.sha256()
        with open(path, "rb") as fp:
            for chunk in iter(lambda: fp.read(65536), b""):
                hasher.update(chunk)
        lines.append(f"{hasher.hexdigest()}  {rel}")

    out_path = os.path.join(project_dir, CHECKSUM_FILE)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return [(rel, line.split("  ", 1)[0]) for rel, line in zip(files, lines)]


def build_restart_command(service=SERVICE_NAME):
    """组装 systemctl 重启命令（独立函数便于测试断言）。"""
    return ["sudo", "systemctl", "restart", service]


def restart_service(service=SERVICE_NAME, runner=None):
    """重启 systemd 服务。runner 可注入便于单测 mock（默认 subprocess.run）。"""
    run = runner or subprocess.run
    return run(build_restart_command(service), check=True)


def write_security_log(project_dir, message):
    """追加安全日志到 logs/security.log。"""
    log_dir = os.path.join(project_dir, LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(log_dir, "security.log"), "a", encoding="utf-8") as f:
        f.write(f"[{now}] {message}\n")


def main():
    # 1. 生成 6 位动态验证码并展示（用户回输确认，参考实现口径）
    secret_code = generate_code()
    print("=" * 45)
    print("      🔐 小橘3号 - 一键重算哈希锁 (动态密码验证)")
    print("=" * 45)
    print(f"⚠️  您的动态验证码是: \033[1;31m{secret_code}\033[0m")
    print("     (输入错误将立即终止操作)")
    user_input = input("👉 请输入验证码以确认重算: ").strip()

    # 2. 验证动态密码
    if not verify_code(secret_code, user_input):
        print("\n❌ 验证码错误，已阻止本次操作！")
        sys.exit(1)

    print("\n✅ 验证通过，正在重新生成哈希指纹...")

    # 3. 执行重算、记录安全日志并重启服务
    try:
        recompute_checksums(PROJECT_DIR)
        write_security_log(PROJECT_DIR, "用户通过动态验证，重写了哈希锁。")
        print("✅ 哈希更新成功！")

        print("🚀 正在重启小橘3号...")
        restart_service()
        print("✅ 服务重启成功！小橘3号已满血复活。")
    except Exception as e:  # noqa: BLE001 —— 与参考实现一致：失败打印原因并以非零码退出
        print(f"❌ 执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
