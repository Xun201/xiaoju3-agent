# 小橘3号 · exe 打包实施方案（草稿）

> 状态：草稿（2026-10-03 编制），**未动任何代码，未写 spec，未打包**，待用户拍板。
> 路线：**spawn-self**（保留 desktop_launcher → xiaoju3_launcher → xiaoju3_dashboard 三层链，onefile 下以 `freeze_support` + argv 角色标志分流），不打散三层为单进程——与 `desktop_launcher.py:54-57` 既有打包规划注记一脉相承。
> 目标形态：单文件 exe，Windows，双击起服务（:5003 唯一入口，5002 已废弃口径不变）。
> 数据依据：全仓 `PROJECT_ROOT`/`__file__` 锚点 grep（2026-10-03 现状）；测试断言逐文件核实。

---

## 一、路径双根设计

### 1.1 统一口径：新增 `paths.py`（全项目唯一路径锚）

```python
# paths.py —— 双根判定（唯一真相源；其余模块一律 from paths import ...）
import os, sys

FROZEN = getattr(sys, "frozen", False)          # PyInstaller onefile 下为 True
if FROZEN:
    RESOURCE_ROOT = sys._MEIPASS                         # 解压临时目录，只读，每次启动即焚
    DATA_ROOT = os.path.dirname(os.path.abspath(sys.executable))  # exe 旁，可写持久
else:
    RESOURCE_ROOT = os.path.dirname(os.path.abspath(__file__))
    DATA_ROOT = RESOURCE_ROOT                            # 非 frozen 两根同值：现有行为零变化
```

- 非 frozen 时 `RESOURCE_ROOT == DATA_ROOT`，所有切到双根的代码行为与今天**逐字节一致**——这是"每步全绿"的根基。
- `xiaoju3.py` 的 `PROJECT_ROOT` **保留名字**、重定义为"从 paths 取 DATA_ROOT"，30+ 处 import 零改动。

### 1.2 逐点标注表（grep 全仓核实，共 9 个锚定义点 + 各派生行）

| 位置 | 现状 | 归属 | 说明 |
|---|---|---|---|
| `xiaoju3.py:20` `ENV_FILE`（xiaoju3_data/.env） | `__file__` 锚 | **数据根** | 真实配置，exe 旁 `xiaoju3_data/.env`，首启引导生成 |
| `xiaoju3.py:23` `_LEGACY_ENV_FILE`（根 .env） | `__file__` 锚 | **数据根** | 迁移兼容口径跟随数据根 |
| `xiaoju3.py:111` `PROJECT_ROOT` | `__file__` 锚 | 拆分原点 | 重定义 = paths.DATA_ROOT（保名） |
| `xiaoju3.py:112` `WORKSPACE` | PROJECT_ROOT 派生 | **数据根** | 可写沙箱 |
| `xiaoju3.py:118` `AGENT_STATE_DIR` | PROJECT_ROOT 派生 | **数据根** | 身份/记忆/历史，可写 |
| `xiaoju3_dashboard.py:83` `PROJECT_ROOT` | `__file__` 锚 | 双用途拆分 | 见下三行 |
| `xiaoju3_dashboard.py:165` assets、`:177/:182` index.html、`:199` console.js/desktop-pet.js | PROJECT_ROOT 派生 | **资源根** | 只读静态资源，走 RESOURCE_ROOT |
| `xiaoju3_dashboard.py:186` getmtime（防缓存 `?v=`） | PROJECT_ROOT 派生 | **资源根** | datas 落盘后有真实 mtime，逻辑可原样保留；兜底加 frozen 时回退固定版本号 |
| `xiaoju3_launcher.py:49` `PROJECT_ROOT` | `__file__` 锚 | 双用途拆分 | `:226` 传给 build_launch_plan 找 dashboard 脚本（frozen 下见 §二）、`:167` 见下行 |
| `xiaoju3_launcher.py:167` `LOG_DIR`（xiaoju3_data/ 启动日志） | PROJECT_ROOT 派生 | **数据根** | 日志可写 |
| `migration.py:48,135,137,219,264,319` | import xiaoju3.PROJECT_ROOT | **数据根（自动归位）** | 灵魂包输出 `backups/`、导入恢复目标均为可写区；`:135` 旧口径 `PROJECT_ROOT/.env` 已核实为旧 export_bundle 故意设计（只记录存在性），随 PROJECT_ROOT→数据根重定义自动归位，无独立改动 |
| `emoji_manager.py:27,30` `EMOJI_DIR` | PROJECT_ROOT 派生 | **数据根（已定，1b 已迁）** | 读码定论：`download_emoji` 运行时落盘（`:112` makedirs + `:122-124` 写文件，触发链=get_emoji_path 未命中兜底下载/brain.translate_emoji），frozen 下 _MEIPASS 不可写——已迁 `xiaoju3_data/emoji`，头注与 docstring 同步 |
| `run_link_log.py:19,22` `DATA_DIR`（dev_logs/） | PROJECT_ROOT 派生 | **数据根** | 可写 |
| `desktop_launcher.py:190` launcher 脚本存在性检查 | `__file__` 拼接 | **分流改造点** | frozen 下不存在 .py 文件，改为 spawn-self 判定（§二），非 frozen 原样 |
| `main.py:327` creator.json base_dir 缺省 | `__file__` 锚 | **数据根** | 用户数据 |
| `xiaoju3_refresh.py:19` `PROJECT_DIR` | env 或 `__file__` | 不动 | 哈希锁+systemctl 属 Linux 部署侧，exe 形态不涉及；仅注释注明锚点语义 |

### 1.3 运行时数据策略（结论，配合 1.2）

- **不打包**：`xiaoju3_data/.env`（真实配置）、`agent_state/`（身份/记忆/历史）、`workspace/`、`backups/`、日志、`dev_logs/`——全部运行时在 DATA_ROOT 生成。
- **打包进 datas（只读）**：`assets/`、前端三件套、`plugins/`、`.env.example`、（可选 `manifest.txt`/`checksums.sha256`）。
- **外部依赖不进包**：Ollama（127.0.0.1:11434 外部服务）、NapCat（外部常驻服务，`ensure_napcat` 句柄不纳入生命周期，exe 化无影响）、Playwright Chromium（约 200MB，缺失优雅降级既有口径不变，exe 首机用 /gen_log 前需 `playwright install chromium`）。

---

## 二、spawn-self 分流设计

### 2.1 角色标志与三层链映射

| 角色 | argv 标志 | frozen 下进入 | 非 frozen 下（现状不变） |
|---|---|---|---|
| 桌面主进程（缺省） | （无标志） | 双击 exe → desktop_launcher 窗口逻辑 | `python desktop_launcher.py` |
| 统一启动器 | `--xj3-role=launcher` | xiaoju3_launcher.main()（argv 剥离标志后原逻辑） | desktop_launcher Popen `[pythonw, xiaoju3_launcher.py]` |
| 控制台服务 | `--xj3-role=dashboard` | xiaoju3_dashboard.serve()（`__main__` 逻辑抽函数） | launcher Popen `[python, xiaoju3_dashboard.py]` |

frozen 下的链路：

```
双击 xiaoju3.exe（无标志 → desktop 角色）
  └ Popen [sys.executable, "--xj3-role=launcher"]      # spawn 自身
      └ Popen [sys.executable, "--xj3-role=dashboard"] # spawn 自身 → :5003 承载一切
```

### 2.2 关键实现点

1. **`sys.executable` 双语义**：frozen 下即 exe 自身（spawn-self 的"解释器"）；`desktop_launcher._windowless_python()` 的 pythonw 孪生解析仅非 frozen 有意义，frozen 分支直接跳过（exe 无控制台窗口形态，由 `-w` 保证）。
2. **`freeze_support()` 位置**：`desktop_launcher.py` 的 `if __name__ == "__main__":` 首行（唯一用户入口）。launcher/dashboard 角色入口由主进程 spawn，不经 bootloader 二次引导，但入口处同样放 `freeze_support()` 无害且抗未来改 multiprocessing。
3. **`__main__` 分流骨架**（desktop_launcher / xiaoju3_launcher / xiaoju3_dashboard 三处同构）：

```python
if __name__ == "__main__":
    import multiprocessing; multiprocessing.freeze_support()
    if "--xj3-role=launcher" in sys.argv:   # 仅 dashboard 文件有此支
        xiaoju3_launcher.main([a for a in sys.argv[1:] if not a.startswith("--xj3-role")])
    elif "--xj3-role=dashboard" in sys.argv:
        serve()
    else:
        ...  # 现行主逻辑，零改动
```

4. **进程识别兼容**：`restart_clean.bat` 现按 `Name='python.exe'` + `CommandLine like '*xiaoju3*'` 清杀——exe 命名 `xiaoju3.exe` 后 CommandLine 仍含 xiaoju3，但 Name 过滤要放宽为 `xiaoju3*.exe`（列入步 3 函数化改造）。psutil 进程树 terminate/`taskkill /T` 对 exe 子链同样有效，关窗停服逻辑不变。
5. **单实例互斥**：desktop_launcher ":5003 在线 → 复用" 逻辑原样有效；双击第二个 exe 实例探测 :5003 后只开窗口不重复拉服务。

---

## 三、测试影响评估（1540 只增不减）

| 测试文件 | 碰到的断言 | 影响 | 处理 |
|---|---|---|---|
| `tests/test_xiaoju3_launcher.py` | `build_launch_plan(python=FAKE_PY, root=FAKE_ROOT)`（已参数化注入），断言 `[FAKE_PY, …/xiaoju3_dashboard.py]` | **近零** | plan 生成器加 `frozen=False` 参数，缺省走现行路径→旧断言一字不动；新增 frozen 自 spawn 用例（+） |
| `tests/test_desktop_launcher.py` | `:132` Popen 尾段 endswith `xiaoju3_launcher.py`、`:141` 提示文案、`:144-160` `_windowless_python` 三分支、`:163` 脚本缺失跳过 | **近零** | ensure_backend_services 加 frozen 分支、缺省非 frozen；`_windowless_python` frozen 下短路（加 guard 断言）；旧用例保留，新增 frozen 用例（+） |
| `tests/test_dashboard.py` | /console 静态断言 + mtime 防缓存 `?v=` 断言（regex 容忍已具备） | **小** | 路由读 RESOURCE_ROOT 后，测试经 monkeypatch/env 注入指向同一 tmp 资源；断言文案不变 |
| `tests/test_launch_bats.py` | bat 内容断言 | **步 3 前零** | restart_clean exe 适配（进程名过滤放宽）在步 3 函数化后同步断言 |
| 双根波及面（brain/tools/migration/permission/prompts 等经 `from xiaoju3 import …`） | tmp 目录注入（env 覆盖 WORKSPACE/AGENT_STATE_DIR）模式 | **零** | PROJECT_ROOT 保名重定义，注入机制不感知 |
| 新增 | `tests/test_paths.py`（FROZEN 判定/双根缺省）、frozen 分流用例 | + | 只增 |

预估：**删除 0、改写 ≈ 10 个用例的 setup/注入、新增 ≈ 15-25 用例**；每步收尾跑 `python -m unittest discover` 全绿（当前基线 1540）。

---

## 四、spec 草案要点（xiaoju3.spec，步 4 才创建）

- **datas**：`assets/`（含 pet/）、`index.html`、`console.js`、`desktop-pet.js`、`plugins/`、`.env.example`、（可选 `manifest.txt`+`checksums.sha256` 供启动校验）。
- **hiddenimports**：`webview`（pywebview Windows 后端）、`webview.platforms.winforms`、`pythonnet`/`clr`（WebView2 依赖链）、`wmi`、`win32api`/`win32con`/`win32com`（pywin32，wmi 传递 + 温度读取）、`psutil`、`edge_tts`、`bs4`、`openai`、`flask_cors`（全部显式列，防延迟导入漏收）。
- **excludes**：`playwright` 及其 driver（exe 形态不打 Chromium，保留优雅降级）、`tkinter`、`pytest`、`pip`、`setuptools` 视体积裁剪。
- **-w vs -c**：**推荐 `-w`**（免黑框，桌面窗口即主入口，与"像 exe 一样"的用户口径一致）。代价：`sys.stdout` 为 None 时裸 `print` 会崩——`desktop_launcher._print` 已防御，launcher/dashboard 的 print 须在步 3 统一收口（stdout None → 静默/落日志文件）。若步 4 冒烟受阻，`-c` 兜底先出包（保留黑窗），`-w` 降为步 5 目标。
- **icon/版本资源**：`assets/pet/normal_half.png` 转 .ico（可选，步 5）。
- **产物不入库**：`*.exe` 已被 .gitignore 拒绝（b8507dc 口径），spec 与 build_exe.bat 入库、exe 留本地。

---

## 五、分步实施计划（每步独立提交，收尾全绿；最后一步才出 exe）

| 步 | 内容 | 交付物 | 全绿口径 |
|---|---|---|---|
| 1 | **双根基建**：新增 `paths.py`；§1.2 表逐点切换（xiaoju3.py 保名重定义、dashboard 资源五处、launcher LOG_DIR、migration、run_link_log、main.py:327、emoji_manager 以读码定论）；非 frozen 行为零变化 | paths.py + 各模块 import 调整 + `tests/test_paths.py` | 1540+新增 |
| 2 | **spawn-self 分流**：dashboard `__main__` 抽 `serve()`；build_launch_plan 加 frozen/role 参数（缺省=现行）；desktop_launcher ensure_backend_services 加 frozen 自 spawn 分支；`_windowless_python` frozen 短路 | 三文件改造 + frozen 用例 | 同上 |
| 3 | **无控制台收口**：launcher/dashboard print 防御（stdout None → 日志文件，复用 timestamped_log_path）；restart_clean 清杀口径函数化（进程名参数化，兼容 python.exe 与 xiaoju3.exe）+ 对应 bat/测试同步 | print 收口 + restart_clean 适配 | 同上 |
| 4 | **出 exe**：写 `xiaoju3.spec` + `build_exe.bat`（入库），构建产物留本地；真机冒烟按下方「冒烟六项清单」逐项验收；测试不碰 exe 产物（全绿不变） | xiaoju3.exe + 冒烟记录 | 测试不受影响，全绿不变 |

#### 冒烟六项清单（步 4 验收标准，2026-10-03 定稿；逐项通过才算步 4 完成）

| # | 冒烟项 | 操作 | 预期 |
|---|---|---|---|
| 1 | **双击起服务** | 双击 `xiaoju3.exe`（无标志） | 桌面窗口打开（标题"小橘3号 · 控制台"），无黑框；数秒内后台自拉 launcher/dashboard 角色 exe 进程（任务管理器可见 `xiaoju3.exe` 带 `--xj3-role=…` 参数）；`xiaoju3_data\`、`agent_state\` 在 exe 旁自动生成 |
| 2 | **5003 可达** | 浏览器开 `http://127.0.0.1:5003/console`；`GET /api/status` | 控制台页 200 正常渲染；status 返回 cpu/memory 数据（资源根 `_MEIPASS` 的前端三件套与 assets 托管成功）；再次双击 exe → 提示复用现有进程，不重复拉起 |
| 3 | **QQ 收发** | 群里 @小橘3号 发 `/help`、私聊发一句话 | 指令路由命中（`[指令路由]` 日志），回复正常；webhook 地址 `http://127.0.0.1:5003/onebot` 不断连；`ensure_napcat` 静默拉起不受 exe 形态影响 |
| 4 | **桌宠渲染** | 控制台右下角查看桌宠，拖拽贴边/翻转 | 桌宠挂载、半身/全身状态机切换正常（assets 打进 datas 从 `_MEIPASS` 托管）；防缓存 `?v=` 版本参数正常下发 |
| 5 | **心跳感知** | 等 60 秒×2 轮，观察终端日志与 HA（若 .env 配置） | 心跳 daemon 宿主于 5003 进程运行（无第二心跳）；HA 未配置时管线静默零刷屏；数据根快照文件正常读写 |
| 6 | **重启入口** | 跑 `restart_clean.bat`；再直接关桌面窗口 | bat 清杀命中 `python.exe` 与 `xiaoju3*.exe` 两类进程、确认 5003 释放、隐藏窗口重启成功；关窗整树终止全部 exe 子进程，无孤儿进程、端口全释放 |
| 5 | （可选，1.0 后）首启 .env 引导 UI、图标/版本资源、杀软误报说明、README 安装章节 | 安装体验收尾 | — |

依赖关系：1 → 2 → 3 → 4（5 独立）。每步一次 commit，步 1-3 任何一步失败可独立回退，不影响现网 python 直跑形态。

---

## 六、风险清单

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| 1 | frozen 三层链是新运行形态，离线测试只能 mock，真机问题（句柄/并发/路径）在步 4 冒烟才首次暴露 | **高** | 步 2 只加分支不切缺省路径；冒烟清单进文档；出问题 `-c` 兜底、必要时回退 spawn-self 改单进程合并 |
| 2 | pywebview/pythonnet/WebView2 hook 漏收 → exe 启动即崩 | 中 | hiddenimports 显式全列；步 4 首包即验窗口 |
| 3 | `_MEIPASS` 只读踩写（emoji_manager 等漏改点） | 中 | 步 1 逐点表 + emoji_manager 读码定论；全仓再 grep 一遍写路径 |
| 4 | 杀软误报 onefile 中文 exe | 低（发布口径） | 文档声明 + 可选换 onedir 形态备用 |
| 5 | Chromium 缺失时 /gen_log 降级文案在 exe 下路径不同 | 低 | 既有 LinkFetchError 中文提示机制不变 |
