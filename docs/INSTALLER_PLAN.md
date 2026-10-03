# 小橘3号 · 安装器实施方案（草稿）

> 状态：草稿（2026-10-03 编制），**未动代码、未装 Inno、未写脚本**，待用户拍板。
> 前置：exe 步骤 1-4 已全部落地（paths.py 双根、spawn-self 三角色、stdio 重定向、`dist\xiaoju3.exe` 43.1 MB 冒烟六项全过，见 EXE_PACKAGING_PLAN.md）。
> 目标：把「下载一个 zip 手动解压」升级为「双击 setup → 下一步到底 → 桌面窗口就绪」，即功能文档 §10"一键部署"的 1.0 形态。

---

## 1. 技术选型：Inno Setup（确认）

选 **Inno Setup 6**，不用 NSIS。理由：

| 维度 | Inno Setup | NSIS |
|---|---|---|
| 脚本形态 | 声明式分段（[Files]/[Icons]/[Registry]），一屏可读 | 宏+栈式指令流，逻辑藏进插件回调 |
| 内置能力 | 卸载器、开始菜单/桌面快捷方式、注册表读写、多语言（简中官方语言包）、Pascal Script 全都要 | 均靠插件拼装（UAC/多语言/卸载页各装各的） |
| 硬件自检 | Pascal Script 内联（COM 调 WMI、WinAPI 内存/磁盘） | 需要 NSIS 插件（System.dll 裸调） |
| 维护性 | 改一行重编译，非程序员也能审 | 脚本密度高，易改崩 |

**结论**：本项目安装器逻辑（自检页+勾选页+自启+保留数据卸载）恰好全部落在 Inno 的内置能力圈内；NSIS 的优势（极限体积、安装脚本复杂分支）本项目用不上。

## 2. 两层职责划清

### 安装器层（Inno 做）
复制文件（`dist\xiaoju3.exe`、`README.md`、`LICENSE`、`.env.example`、`docs\EXE_PACKAGING_PLAN.md` 摘要）→ 开始菜单/桌面快捷方式 → 硬件自检页（预判档位）→ 组件勾选页（自启项/桌面快捷方式）→ 注册表自启项 → 卸载器（默认保留数据）。

### 首装引导层（程序内做，步 5A 实现）
`.env` 生成（`xiaoju3_data\.env` 不存在时窗口内引导页）、三服务检测（Ollama 1 秒 probe / NapCat 6099 端口+进程扫描 / HA `/api/` 鉴权探测）、DeepSeek key 注册引导（给官方平台链接，用户自填，程序落盘 `.env`——新增"写配置"逻辑，与 `_load_env_file` 只读加载对称）。全部可跳过：中立缺省照常运行（xiaoju3.py 配置契约保证，未配置项走缺省不崩）。

### 外部三件套为什么不进安装器（Ollama+模型 / NapCat+QQ / Chromium）
1. **体积**：Ollama+Qwen2.5:7b 是 GB 级、Chromium 约 200MB——安装包会从 45MB 膨胀到 GB 级，分发光灾难；
2. **权限/系统**：Ollama 安装器要管理员 + GPU 驱动匹配，QQ 本体有自有安装与升级体系——替用户装反而埋坑；
3. **网络**：大文件下载应按需+断点+镜像，塞进安装器既慢又不可控。
策略：安装器自检页**检测并给出引导链接/命令**（如"未检测到 Ollama → 点击查看安装指引"），实际安装由用户按需完成；NapCat 已有 `setup_napcat.bat` 与 `ensure_napcat` 静默拉起链路，保持现状。

## 3. 安装器脚本结构（xiaoju3.iss）

- **[Setup]**：`AppId`（固定 GUID，卸载器身份）、`AppVersion=1.0.0`、`DefaultDirName={localappdata}\Programs\小橘3号`、`PrivilegesRequired=lowest`（零 UAC，见 §5/§10）、`Compression=lzma2`（45MB exe 预计压到 ~20MB 安装包）、`UninstallDisplayIcon`。
- **[Languages]**：简体中文（官方 ChineseSimplified.isl）。
- **[Files]**：`dist\xiaoju3.exe`、README/LICENSE/.env.example、docs 摘要——`DestDir: {app}`。
- **[Icons]**：开始菜单「小橘3号 · 控制台」+ 可选桌面（组件勾选联动）。
- **[Code]**：Pascal Script——`PrepareToInstall`/自定义页做硬件自检（§4）；组件勾选联动自启注册表；卸载页问"是否同时删除记忆与配置"（§7）。
- **[Registry]**：`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 自启键（§5）。
- **[Run]**：安装完成页勾选"立即启动小橘3号"（跑 `xiaoju3.exe`，desktop 角色免参数）。
- **[UninstallRun]**：删自启注册表值；**不**删数据目录（§7）。
- **[UninstallDelete]**：空（默认保留数据）；仅当用户勾选"彻底删除"时由 [Code] `DelTree` 处理。

## 4. 硬件自检与分档线

安装器检测三项（Pascal Script，全部无需管理员）：

| 指标 | 检测方式 | high（推荐完整版） | medium | low（推荐轻量版） |
|---|---|---|---|---|
| 内存 | `GlobalMemoryStatusEx`（WinAPI） | ≥16 GB | 8–16 GB | <8 GB |
| GPU | WMI COM（`WbemScripting.SWbemLocator` 查 Win32_VideoController 名称，匹配独显关键词 NVIDIA/AMD RX/Radeon） | 有独显 | 集显 | — |
| 磁盘可用 | `GetDiskFreeSpaceEx`（目标盘） | ≥20 GB | 10–20 GB | <10 GB |

**分档映射**（与 `hardware_profiler`/`DEVICE_TIER` 三档语义对齐）：high → 完整版（本地 Ollama 优先路线，引导装 Ollama+模型）；low → 轻量版（云端优先，跳过 Ollama 引导）；medium → 完整版但提示本地模型响应较慢。

**单一事实源原则**：安装器自检只是 **UI 预判**——真正生效的档位仍由程序内 `hardware_profiler` 首启复测决定（DEVICE_TIER env 可覆盖，契约不变）；安装器把预判结果写进安装日志供比对，不直接写死任何配置。

## 5. 自启：注册表 HKCU Run 键

选**注册表 Run 键**（`HKCU\...\Run`，值名 `Xiaoju3`，值 `"…\xiaoju3.exe"`），不用计划任务：计划任务要 schtasks 权限/管理面更重、普通用户看不懂；Run 键任务管理器"启动"标签页原生可见可关，亲民口径一致。
- **装时写**：组件勾选页默认勾选"开机自动启动"。
- **程序内可改**：首装引导/控制台设置写删同一键（路径同源，单一事实）。
- **卸载时清**：`[UninstallRun]` 删值；即使用户卸载前已在程序内关闭，删不存在的值无害（`reg delete /f` 容错）。
- `PrivilegesRequired=lowest` + HKCU：全程零 UAC，与"像 exe 一样"的亲民定位一致。

## 6. 首装引导流程（程序内，步 5A）

exe 首启（`paths.DATA_ROOT/xiaoju3_data/.env` 不存在）时，桌面窗口加载引导页（现有 pywebview 窗口 + 引导路由，不新开进程）：

1. **欢迎页**：一句话定位 + 隐私声明（数据不出家门口径）。
2. **环境检测**（并行只读探测，逐项亮灯）：Ollama（1s probe，通 → 🟢 完整版可用；不通 → 🟡 给安装指引链接，可跳过）；NapCat/QQ（进程/端口扫描，不通 → 提示后装也行，QQ 侧指引）；Home Assistant（`HA_URL`/`HA_TOKEN` 可选，未填直接跳过该项）；DeepSeek（`DEEPSEEK_API_KEY` 缺失 → 高亮引导：给 DeepSeek 开放平台注册链接，**用户自己注册充值**，把 key 粘进输入框 → 程序校验非空后写入 `.env`）。
3. **写 `.env`**：逐键落 `xiaoju3_data\.env`（隔离区口径，gitignore 同源）；写完提示"重启生效"或热加载。
4. **完成页**：档位结论（程序内 hardware_profiler 复测）+ 下一步入口。

任何一步可跳过：未配置项走中立缺省照常运行（契约既有行为），引导页只在 `.env` 不存在时出现一次。

## 7. 卸载：默认保留数据

- **默认保留**：`xiaoju3_data\`（.env/日志/表情库）、`agent_state\`（身份/记忆/历史）、`workspace\`——`[UninstallDelete]` **不列这些目录**，卸载器只删安装器写入的文件（exe/README/快捷方式）与 `[UninstallRun]` 注册表。
- **卸载完成页提示**：「你的配置、记忆与灵魂备份保留在 `<DATA_ROOT>`；重新安装后自动找回」。
- **可选彻底删除**：卸载向导加一页 checkbox"同时删除我的配置与记忆（不可恢复）"→ [Code] `DelTree(DATA_ROOT + 'xiaoju3_data')` 等三目录，默认不勾。
- **灵魂包护身**：`backups/soul_*.zip` 同在数据区，随之保留——"秽土转生"口径下，卸载≠失忆。

## 8. 版本号 1.0.0：三处统一

| 位置 | 写什么 | 统一机制 |
|---|---|---|
| `xiaoju3.py` | 新增 `XIAOJU3_VERSION = "1.0.0"` 常量（单一事实源，随 `/api/status` 暴露） | 源头 |
| `xiaoju3.spec` | 加 `version` 版本资源（PyInstaller 6 支持 `version_file`） | `build_exe.bat` 构建时从 xiaoju3.py 正则抓版本号**生成** `version_info.txt`（不手写） |
| `xiaoju3.iss` | `AppVersion`（Inno 预处理器 `#define` 同样由 build 脚本注入） | 同上 |

规则：**手写处只有 xiaoju3.py 一处**；build_exe.bat 顺序改为「抓版本 → 生成 version_info/iss 头 → PyInstaller → Inno」，杜绝三处漂移。

## 9. 分步实施计划（每步收尾全仓测试全绿，与 exe 同纪律）

| 步 | 内容 | 交付物 | 预估 |
|---|---|---|---|
| A | **版本统一 + 首装引导层**：`XIAOJU3_VERSION`；引导路由（检测 Ollama/NapCat/HA 三探针 + DeepSeek key 引导表单 + 写 `.env` 逻辑）；自启键读写函数 | 引导页 + 程序内自启开关 + 新测试（.env 写入/探针 mock/自启键 mock 注册表） | 1–2 天 |
| B | **xiaoju3.iss + 构建接入**：安装 Inno（独立工具，不进 requirements）；build_exe.bat 扩展为「app exe → version 注入 → ISCC 编译 setup」双产物 | `xiaoju3.iss` 入库、`dist\小橘3号-1.0.0-setup.exe` 留本地 | 0.5–1 天 |
| C | **真机安装/卸载演练**：装 → 自检页档位 → 引导 → 自启 → 重启验证 → 卸载 → 数据保留核对；附冒烟清单（与 exe 同格式） | 冒烟记录入本文档 | 0.5 天 |
| D | （1.0 后可选）图标/签名评估/README 安装章节 | 收尾 | — |

依赖：A → B → C（D 独立）。A/B 均可独立回退；C 前不产生任何安装器产物。

## 10. 风险点

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| 1 | **代码签名缺失 → SmartScreen/杀软误报**（已知问题，双 exe 叠加：app exe + installer exe 各一份被盯） | 高 | 1.0 口径：README/下载页写"已知 Windows 智屏警告，点『仍要运行』"+ 提供 SHA256 校验值；签名证书（OV/EV 年费数千）列入 1.0 后评估 |
| 2 | Inno 与 onefile exe 配合：45MB 单文件再经 lzma2 压缩，解压首启时间叠加 onefile 自解压 | 中 | 实测解压/首启耗时（步 C 冒烟项）；不达标可改 onedir 形态装目录（paths.py 双根无需改） |
| 3 | **数据目录位置**：exe 旁（`%LOCALAPPDATA%\Programs\小橘3号`）vs `%APPDATA%` | 中 | 拍板 **exe 旁**——paths.py 双根（DATA_ROOT=exe 目录）**零改动**；`PrivilegesRequired=lowest` 使该位置可写无需管理员；风险=用户自选含中文/空格路径（os.path 兼容已核实）；卸载误删由"默认保留+显式勾选才删"兜住 |
| 4 | Pascal Script 硬件自检在个别机器被组策略禁 COM/WMI | 低 | 自检失败降级为"无法预判，程序内将自动复测"，不阻塞安装 |
| 5 | 首装引导"写 .env"是新代码路径（此前只读加载） | 中 | 写入走隔离区 + 键白名单 + 覆盖前备份旧 .env；离线单测覆盖（步 A） |

## 11. 步 C（B3b）真机装卸演练验收记录（2026-10-03，三大场景全过）

演练环境：`dist\xiaoju3-1.0.0-setup.exe` 46,723,774 字节（含消费端 `590e7d8` + iss 重构 `4dd7a0b`），自定义中文安装路径 `F:\测试\小橘3号`，Inno 6.7.3 中文向导，全程零 UAC。前置：B3b 首装首测曾触发两个 Runtime error（①裸 `StrToInt64(WmiFirstValue(...))` 空串硬崩；②失败级联后 DeinitializeSetup 访问未创建的 WizardForm），定位后按 `docs/INSTALLER_STEP_B3_CODE_FIX_DESIGN.md` 重构 [Code] 段（`4dd7a0b`：探测归 InitializeSetup / 建页归 InitializeWizard / `WizardWasCreated` 旗守卫 / `WmiFirstInt` 哨兵 -1），**本记录为重构后的复测结论**。

#### 场景一：首装 ✅

- **零 Runtime error**（重构前三连炸根除）：自检页→组件页→安装完成全程无报错弹窗。
- **WMI 哨兵降级真机跑通**：安装瞬间 WMI 瞬时不稳，自检页三项显示"无法预判"，**不再误报"推荐轻量版 / 约 0 GB"**（§6 缺陷 #1 修复实锤）。
- **installer_report.txt 落盘**：97 字节，GBK 编码实锤（utf-8 解码失败、gbk 成功——`SaveStringToFile` AnsiString→系统 ANSI 代码页，消费端回退读法标的形态）；五行逐字吻合：`2026-10-03 17:55:13` / `硬件自检建议: 无法预判（程序首次运行将自动复测）` / `ollama=1` / `napcat=1` / `ha=1`。
- **自启覆盖语义**：HKCU Run `Xiaoju3` 由演练前指向 dist 的旧值被覆盖为 `"F:\测试\小橘3号\xiaoju3.exe"`（同键同名最后写入者胜）。
- **消费端真机被调用**：`xiaoju3_data\dashboard_live_20261003_175519.log` 行 15-17，17:55:20 三连全 200——`GET /api/first_run/status` → `installer_report` → `probes`（initFirstRun 特征链）。
- 装机清单核对：[Files] 三件 + `xiaoju3.exe` 45,371,010 字节 + 卸载器两件；卸载键 `{7E3A1C94-…}_is1` 全字段（DisplayName=小橘3号 版本 1.0.0）。**查询口径备忘：Inno 卸载键带 `_is1` 后缀，按裸 AppId 查恒"不存在"。**

#### 场景二：升级（覆盖安装）✅

- **报告覆写与用户目击逐秒闭环**：`installer_report.txt` 时间戳变为 `2026-10-03 18:04:42`，与用户目击浮层灰字「安装于 2026-10-03 18:04:42；安装器建议：无法预判（真实档位以本机复测为准）」**逐秒一致**——安装器写 → 消费端读同源同刻；徽标「安装时勾选：本地 Ollama / QQ(NapCat) / HA 心跳」与报告三意向 1/1/1 吻合。
- **数据保留零破坏**：旧三角色日志（dashboard 1,183 / desktop 146 / launcher 388 字节）与 `agent_state\long_term.db` 12,288 字节**字节 + mtime 逐项原样**。
- **口径注记**：`.env.example`/`QUICKSTART.md`/`xiaoju3.exe` 覆盖安装后 mtime 不刷新属 Inno 正常行为（复制时恢复源文件 mtime）；覆盖证据看新生成产物——`unins000.exe`→18:04:16、`unins000.dat`→18:04:40、报告→18:04:42。
- **注册表原位刷新**：`Selected Components=ollama,napcat,ha`、`Selected Tasks=desktopicon,autostart`、`InstallDate=20261003` 同键更新；Run 值同路径。
- **消费端两轮调用**：18:04 轮与 18:06 轮 dashboard 日志均三连 200（18:04:49 / 18:06:25）。

#### 场景三：卸载（默认保数据路径）✅

- **程序侧三清**：程序五件（exe / QUICKSTART.md / .env.example / unins000.exe / unins000.dat）全消失；桌面与开始菜单 `小橘3号 · 控制台.lnk` 消失；`_is1` 卸载键消失、`Run\Xiaoju3` 被 `uninsdeletevalue` 清除（Run 键全量 11 值零小橘残留）。
- **数据侧全保留**：`installer_report.txt` + 三轮×3 角色日志 + `long_term.db` 共 **11 项字节 + mtime 逐项原样**（含追加后的 1,317 字节日志）；`xiaoju3_data\`、`agent_state\` 两目录本体保留，安装根目录无任何文件残留。
- **"数据不装不删"承诺在默认卸载路径完整兑现。**

#### 遗留清单（如实记录，均非本轮缺陷）

| # | 遗留 | 状态 |
|---|---|---|
| 1 | 卸载向导无「彻底删除用户数据」复选（`[UninstallDelete]` 留空的当前实现即无此功能） | **未实现**——后续步 / 1.1（`CurUninstallStepChanged` + `DelTree` 方案已在 B 设计 §2/§6） |
| 2 | 卸载完成页「数据保留位置」提示文案未落地（B 设计 §2/§6 承诺过） | **未实现**——同属卸载侧待办 |
| 3 | 组件页无法改勾选（升级演练中用户未能改动勾选态，UI bug） | **待修**——bug 单独跟踪 |
| 4 | dashboard 绑 `0.0.0.0`（内网可达） | **加固候选**——改绑 127.0.0.1，1.0 后评估 |

#### B3b 复现命令

```bat
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{7E3A1C94-5B2D-4F68-9A03-18C45E7F2B60}_is1" /s
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v Xiaoju3
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall" | findstr /i "7E3A1C94"
dir /s /b "F:\测试\小橘3号"
```

（注意卸载键 `_is1` 后缀；路径与盘符按实际安装位置替换。）
