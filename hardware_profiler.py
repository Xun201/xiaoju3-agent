#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""硬件自适应探测：给出 DEVICE_TIER 的 high / medium / low 推荐值。

探测维度（全部只读，不修改任何系统配置）：
- 独立显卡：subprocess 调 nvidia-smi（2 秒超时），成功即视为带独显；
- 内存总量：psutil.virtual_memory().total；
- 平台架构：ARM（aarch64/armv*）视为开发板类终端。

推荐规则（可被环境变量 DEVICE_TIER 显式覆盖，见 xiaoju3.py）：
- 带独显                    → high（本地大模型优先，工具汇总走本地）
- 无独显、ARM 架构           → low （开发板：跳过本地，云端优先）
- 无独显、内存 >= 8GB        → medium（本地小模型优先，工具汇总走云端）
- 其余（无独显且内存 < 8GB）  → low

用法：
    python hardware_profiler.py    # 打印探测报告与推荐配置行
    代码内：hardware_profiler.detect_tier() -> "high" | "medium" | "low"
"""
import platform
import subprocess

try:
    import psutil
except ImportError:  # pragma: no cover - psutil 属白名单依赖，缺失时降级
    psutil = None

_MEDIUM_RAM_GB = 8.0  # 无独显时进入 medium 档的内存门槛


def total_ram_gb():
    """物理内存总量（GB）；psutil 不可用时返回 None。"""
    if psutil is None:
        return None
    try:
        return psutil.virtual_memory().total / (1024.0 ** 3)
    except Exception:
        return None


def has_discrete_gpu():
    """能否检测到独立显卡（nvidia-smi 可执行且返回 0）；异常一律视为无。"""
    try:
        result = subprocess.run(["nvidia-smi"], capture_output=True, timeout=2)
        return result.returncode == 0
    except Exception:
        return False


def is_arm():
    """是否 ARM 架构终端（开发板类）。"""
    machine = (platform.machine() or "").lower()
    return machine.startswith("aarch64") or machine.startswith("armv")


def detect_tier():
    """按推荐规则返回 "high" / "medium" / "low"；任何探测异常降级为 medium。"""
    try:
        if has_discrete_gpu():
            return "high"
        if is_arm():
            return "low"
        ram = total_ram_gb()
        if ram is None:
            return "medium"
        return "medium" if ram >= _MEDIUM_RAM_GB else "low"
    except Exception:
        return "medium"


def print_report():
    """打印探测报告与推荐配置行（供 python hardware_profiler.py 使用）。"""
    ram = total_ram_gb()
    ram_text = f"{ram:.1f} GB" if ram is not None else "未知（psutil 不可用）"
    gpu_text = "检测到独显（nvidia-smi）" if has_discrete_gpu() else "未检测到独显"
    arch = platform.machine() or "未知"
    tier = detect_tier()
    tier_meaning = {
        "high": "高配：本地大模型优先（qwen2.5:7b/14b），工具汇总走本地，失败切云端",
        "medium": "混合：本地小模型优先（qwen2.5:0.5b），工具汇总走云端",
        "low": "低配：跳过本地探测，直接使用云端",
    }[tier]
    print("=" * 50)
    print("🦊 小橘3号 · 硬件自适应探测报告")
    print("=" * 50)
    print(f"架构：{arch}")
    print(f"内存：{ram_text}")
    print(f"显卡：{gpu_text}")
    print(f"推荐档位：{tier}（{tier_meaning}）")
    print("")
    print("启用方式（任选其一）：")
    print('  1. .env 写入：DEVICE_TIER=%s' % tier)
    print("  2. 环境变量：export DEVICE_TIER=%s" % tier)
    print("  3. 保持默认 auto：每次启动自动按本报告口径探测")
    print("     （medium 档小模型可用 LOCAL_MODEL_SMALL 覆盖，默认 qwen2.5:0.5b）")
    return tier


if __name__ == "__main__":
    print_report()
