# -*- coding: utf-8 -*-
"""小橘3号 · 双根路径锚（exe 打包基建，方案见 docs/EXE_PACKAGING_PLAN.md §1）。

两根语义：
- RESOURCE_ROOT（资源根，只读）：程序自带静态资源的所在——assets/、前端三件套
  （index.html / console.js / desktop-pet.js）、plugins/、.env.example 等"随程序
  分发、运行期绝不写"的东西从这里读。非 frozen（python 直跑）即项目根；
  PyInstaller onefile 冻结后为 sys._MEIPASS（每次启动解压的临时目录，启动即焚）。
- DATA_ROOT（数据根，可写持久）：运行时数据的家——xiaoju3_data/（.env、启动日志）、
  agent_state/（身份/记忆/历史）、workspace/、backups/、dev_logs/ 等"首次运行自动
  生成、跨重启持久"的东西锚定这里。冻结后为 exe 所在目录。

判定基准：sys.frozen 由 PyInstaller bootloader 设置。非 frozen 下两根恒等——
这是"每步全绿、现网 python 直跑行为零变化"的根基（方案 §1.1）。

步 1a 口径：本模块为无人调用的新基建；步 1b 起各模块路径锚逐点切换到这里。
"""
import os
import sys

FROZEN = getattr(sys, "frozen", False)


def _resolve(frozen, meipass, executable):
    """纯函数：由 (frozen, _MEIPASS, sys.executable) 解析 (资源根, 数据根)。

    抽成纯函数供测试直接覆盖三种形态，无需真实冻结环境；
    非 frozen 分支以本模块自身位置（项目根）为锚。
    """
    if frozen:
        resource_root = meipass
        data_root = os.path.dirname(os.path.abspath(executable))
    else:
        resource_root = os.path.dirname(os.path.abspath(__file__))
        data_root = resource_root
    return resource_root, data_root


RESOURCE_ROOT, DATA_ROOT = _resolve(
    FROZEN, getattr(sys, "_MEIPASS", None), sys.executable
)
