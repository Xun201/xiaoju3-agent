# 启动性能优化设计稿（import 剖析 + 延迟加载 + _MEI 清理）

> 状态：**设计稿，待评审**（本轮零代码改动）
> 日期：2026-10-04
> 实测基线：v13 冻结 exe 冷启动（干净基线：_MEI 残留清零 + 旧实例关闭 + psutil 0.04s 探针）
> 关联：docs/STARTUP_UX_DESIGN.md（启动体验/splash 方向，共享本稿时序数据）

---

## 一、实测数据

### 1.1 冷启动三段分布（T0→5003 就绪 = 7.74s）

| 段 | 时间窗 | 耗时 | 内容 |
|---|---|---|---|
| ① onefile 解包 | 0 → 1.86s | ≈1.9s | 173.5MB 写盘（exe 85MB 压缩态；**playwright lib+driver 占约 62%**） |
| ② 主进程 python 启动 + import + spawn | 1.86 → 3.76s | ≈1.9s | desktop_launcher 角色：含**顶层 `from xiaoju3_dashboard import app` 全链 ≈1.1s** |
| ③ dashboard 子进程 python 启动 + import 全链 + Flask | 3.76 → 7.74s | **≈4.0s** | 同一份 1.1s import 链在**第二个进程**再走一遍 + Flask bind |

交叉验证：dashboard 日志"启动"行 17:19:23 vs T0 17:19:15.7 = 7.3s ✓。webview2 窗口 @5.40s（用户 5.4s 见窗，7.7s 服务通）。

### 1.2 import 链剖析（`python -X importtime -c "import xiaoju3_dashboard"`，1204 行）

全链 **self 合计 ≈1.1s**——import 优化收益上限即此（乐观全部清零，7.74→6.6s）。

| 模块 | cumulative | 用途 | 定性 |
|---|---|---|---|
| xiaoju3_dashboard | 1110ms | 控制台服务入口（全链根） | 必须 |
| main | 1065ms | QQ/指令/消息处理 | 必须 |
| brain | 827ms | 双脑决策 | 必须 |
| tools | 816ms | 工具分发 | 必须 |
| **vision_tools** | **636ms** | **ADB 视觉回退点击（openai SDK 609ms + 依赖链）** | **可延迟——唯一消费者是 ui_tap_element 的视觉回退分支** |
| openai（及 types/graders 子树） | 609ms | vision_tools 顶层 try-import 引入 | 随 vision_tools |
| aiohttp（helpers+connector 等） | ≈100ms | openai 依赖链 | 随 vision_tools |
| search_tools | 36.5ms | 联网搜索 | 小头不动 |
| migration | 106ms | 迁移/守望 | 小头不动 |
| plugins.todo_extractor | 135ms | 待办提炼 | 小头不动 |

> 其余 self 大头（asyncio/email/_ssl/http.server）为标准库或 requests/flask 链，分散且属必需。

---

## 二、延迟加载设计（核心：vision_tools 单点 636ms）

### 2.1 vision_tools 延迟导入（主推）——✅ 已拍板（2026-10-04）

> **拍板结果**：做，且增强为「延迟导入 + 后台预热」——启动路径零 openai；
> 主界面就绪后（dashboard serve() 内 app.run 前）daemon 线程延迟
> OPENAI_PREHEAT_DELAY=5.0s 调 `_ensure_openai()` 预热，用户真用到视觉
> 回退点击时 SDK 已就绪；预热完成前就调用的罕见场景由入口同步导入兜底
> （最多卡 ≈0.6s）。已实施：vision_tools.py（惰性导入 + preheat_openai_async）
> + xiaoju3_dashboard.py serve() 挂钩 + 子进程锚等 6 测试。

- **现状**：vision_tools.py:163-166 顶层 `try: from openai import OpenAI ... except ImportError`——注释自称"延迟可用性检查"，实际**只防缺库不延迟时机**：openai（609ms）+ 依赖链（aiohttp ≈100ms、pydantic_core 等）在模块 import 时全量执行。
- **策略**：**首次真实调用时导入**（惰性导入 + 模块级缓存哨兵）：
  - 删除顶层 try-import；
  - 新增 `_ensure_openai()`：`_OpenAIClient/_openai` 均为 None 时执行导入并赋全局；ImportError 时置 `_openai = False` 哨兵（保持现有"None=未尝试则提示缺库"语义：调用点改为 `_ensure_openai(); if not _openai: return 缺库提示`）；
  - 消费点（`vision_tap_element` 主流程入口）先 `_ensure_openai()`。
- **改动位置**：vision_tools.py 顶层 import 块 + `_ensure_openai()` 新函数 + `vision_tap_element` 入口一行；**tools.py 零改动**（`from vision_tools import vision_tap_element` 仍顶层——vision_tools 本体只剩轻 stdio imports）。
- **预期收益**：**636ms × 2 个进程**（desktop_launcher 主进程与 dashboard 子进程各走一遍同链）= 端到端 **≈0.6-1.2s**。
- **风险**：低——首用（视觉回退点击）时一次 ~0.6s 的 openai 导入延迟，发生频率极低且非交互关键路径；无循环依赖（openai 不回引项目）；线程安全（import 原子性 + 幂等）。
- **先例**：link_logger 的 playwright 延迟导入同模式（项目既有惯例）。

### 2.2 desktop_launcher 顶层 dashboard-import 延迟（占位窗提前 ≈0.7-1.1s）

- **现状**：desktop_launcher.py:70 顶层 `from xiaoju3_dashboard import app`（注释"PyInstaller 收录锚"）——**1.1s 全链在占位窗创建之前执行**。
- **策略**：顶层 import 移除；收录依赖已由 **xiaoju3.spec hiddenimports 静态收录**（`xiaoju3_dashboard`/`main` 等均在列表）——运行时 import 不承担收录职责；:435 `serve()` 分支已有函数内延迟导入（先例），`app` 的引用面经 grep **无其它消费点**。
- **改动位置**：desktop_launcher.py:70 删除（或改注释说明收录走 spec）；核对 :435 分支保持。
- **预期收益**：占位窗/主进程就绪 **≈0.7-1.1s 提前**（本进程 import 链等量缩短）。
- **风险**：中低——需确认 `app` 确无隐藏引用（本轮 grep 已核：desktop_launcher 内 `app.` 零消费点，仅 :435 的 serve 分支用延迟 import）；测试影响：tests/test_dashboard 的 `test_main_module_has_no_flask_app` 反向锚不涉及；需补一条"desktop_launcher 顶层不 import xiaoju3_dashboard"静态锚（防回流）。

### 2.3 不推荐项（如实排除）

- search_tools/migration/todo_extractor（36/106/135ms）：收益小、动链风险不值；
- brain/main 本体：已是薄壳（cum≈self），无肉可延。

### 2.4 汇总

| 项 | 收益（端到端） | 改动文件 | 风险 |
|---|---|---|---|
| vision_tools 延迟导入 | ≈0.6-1.2s | vision_tools.py | 低 |
| desktop_launcher 顶层 import 延迟 | 占位窗 ≈0.7-1.1s 提前 | desktop_launcher.py | 中低 |
| **合计** | **≈1.3-2.3s** | **2 文件** | — |

---

## 三、_MEI 残留清理设计

### 3.1 现状

Temp\_MEI* 强杀（Stop-Process/taskkill）残留累积实测 **5 目录 868MB**（10 代 ×85-173MB）；正常退出 PyInstaller 自清。

### 3.2 方案：desktop_launcher 启动早期自清旧 _MEI（frozen 才执行）

- **位置**：desktop_launcher.py `main()` 最早期（import paths 之后、重量 import 之前）——此时尚未创建本进程 _MEIPASS 依赖之外的窗口/资源。
- **安全约束（三条全满足）**：
  1. **跳过当前进程自己的 _MEIPASS**：对比 `sys._MEIPASS` 前缀（onefile 本代解包目录绝不可删）；
  2. **只删超过 N=10 分钟未修改的目录**（目录 mtime 判定）：防误删**并行实例**正在使用的解包目录（用户双开场景）；
  3. **删除失败静默忽略**（`shutil.rmtree(ignore_errors=True)` + 单目录 try）：权限/占用（Explorer/杀软句柄）不报错不阻塞。
- **实现思路**（~25 行，desktop_launcher.py 内私有函数 `_cleanup_stale_meipass()`）：
  - `glob(os.path.join(tempfile.gettempdir(), "_MEI*"))` 枚举；
  - 排除 `sys._MEIPASS`；`os.path.getmtime(dir) < time.time() - 600` 才删；
  - 日志一行（清理 N 处 / 释放 X MB），异常静默。
- **收益**：磁盘回收（868MB 级）；对启动耗时**无直接收益**（onefile 每次新解包，不清也不复用）——纯卫生项，与方案 1（onedir）互斥（onedir 无 _MEI，该项自动退役）。

---

## 四、测试影响

| 项 | 测试 |
|---|---|
| vision_tools 延迟导入 | tests/test_tools 或新增：import vision_tools 后 `sys.modules` 无 openai（延迟生效锚）；`_ensure_openai` 缺库哨兵语义（mock ImportError） |
| desktop_launcher 顶层 import 延迟 | 静态锚：desktop_launcher.py 顶层无 `from xiaoju3_dashboard import app`（现锚 `test_main_module_has_no_flask_app` 不受影响）；:435 serve 分支延迟导入锚保留 |
| _MEI 清理 | 单测：临时目录造 2 个假 _MEI（一新一旧）→ 调 `_cleanup_stale_meipass()` → 旧的删、新的与 _MEIPASS 保留；monkeypatch sys.frozen |
| 全仓 | 1749 只增不减 |

---

## 五、与 STARTUP_UX_DESIGN.md 的关系

互补不冲突：本稿压"服务就绪"时间线（7.74→≈6.5s）；UX 稿优化"感知"（占位骨架窗提前至 ≈2.5s、失败加载态）。两稿合并实施后的预期时间线见 UX 稿 §预期。
