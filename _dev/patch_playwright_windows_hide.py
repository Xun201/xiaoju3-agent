# -*- coding: utf-8 -*-
"""playwright node driver windowsHide 补丁（2026-10-04 尾巴 A2 终版，幂等）。

根因：playwright driver 的 launchProcess（package/lib/coreBundle.js）在
spawnOptions 里**缺 windowsHide**——node 默认 windowsHide=false，Windows 上
以 console 子系统启动的子进程（chromium_headless_shell）会被配发**可见
conhost** = 冻结包抓取时的闪黑框。python 侧 CREATE_NO_WINDOW 只管 driver
自身，管不到 node→chromium 层（chromium 由 node 内部 spawn）。

修法：给 launchProcess 的 spawnOptions 注入 `windowsHide: true`——node
将其转译为 STARTF_USESHOWWINDOW + SW_HIDE，子进程的 conhost 窗口创建即
隐藏（进程功能不受影响）。build_exe.bat 构建前自动执行本脚本；collect_all
从 site-packages 复制 driver → 打进 exe 的 driver 自带补丁。

幂等：已含 windowsHide 则跳过；重复执行零副作用。
"""
import os
import sys

CORE = os.path.join(
    os.environ.get("APPDATA", ""),
    "Python", "Python314", "site-packages", "playwright",
    "driver", "package", "lib", "coreBundle.js")

ANCHOR = "  const spawnOptions = {"
PATCH = "  const spawnOptions = {\n    windowsHide: true,"


def main():
    if not os.path.isfile(CORE):
        print(f"[FAIL] driver coreBundle.js 不存在: {CORE}")
        return 1
    src = open(CORE, encoding="utf-8").read()
    if PATCH in src:
        # 精确串（锚点+注入组合）判幂等——playwright 原生别处的 windowsHide 不算
        print("[OK] 已打过补丁（幂等跳过）:", CORE)
        return 0
    if ANCHOR not in src:
        print("[FAIL] 未找到 spawnOptions 锚点——playwright 版本可能变化，需人工核对")
        return 1
    # 只 patch 第一处（launchProcess 是 chromium/driver 启动主路径）
    patched = src.replace(ANCHOR, PATCH, 1)
    open(CORE, "w", encoding="utf-8", newline="").write(patched)
    print("[OK] 已注入 windowsHide: true →", CORE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
