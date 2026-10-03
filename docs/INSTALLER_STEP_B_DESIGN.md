# 安装器步 B 设计细则：Inno 安装器 + 双产物构建

> 状态：设计稿（2026-10-03），**未动代码、未装 Inno**。总方案 `docs/INSTALLER_PLAN.md`（步 B），版本管线承接步 A（`XIAOJU3_VERSION = "1.0.0"`，xiaoju3.py:225）。
> 侦察结论（2026-10-03）：Inno Setup **未安装**（PATH 与标准目录均无 ISCC.exe）；Pillow 12.3.0 在（可生成 ico）；`xiaoju3.spec` 无 version 资源、`icon=None`；`build_exe.bat` 无版本抓取；`assets/pet/normal_half.png` 为 JPG 字节占位（无透明通道，做图标质量受限——见 §8 风险）。

---

## 1. 安装目录默认位置：**用户级 `{localappdata}\Programs\小橘3号`**（推荐定稿）

`[Setup] PrivilegesRequired=lowest` + `DefaultDirName={localappdata}\Programs\小橘3号`。

**这是步 B 核心难题（数据目录）的解**：frozen 下 `paths.py` 的 `DATA_ROOT = exe 所在目录`——装进 `%LOCALAPPDATA%\Programs\` 后该目录**当前用户可写**，`xiaoju3_data/`、`agent_state/`、`workspace/` 照常在 exe 旁生成，**双根设计零代码改动**。已验证链路全部兼容：spawn-self 的 launcher 角色 `cwd=DATA_ROOT`、`LOG_DIR`、`save_env_file` 的 makedirs——全在可写区。

**否决 Program Files（机器级）方案**：exe 旁不可写 → frozen `DATA_ROOT` 必须改造（改 `%LOCALAPPDATA%\xiaoju3` 或"标记文件探测"），动 paths.py 核心 + 连带验证全部已测链路，且需管理员 UAC——与"像 exe 一样亲民"定位相悖。多用户/机器级安装列为 1.0 后评估（届时 paths.py 加"数据根 env 覆盖 + 标记文件探测"两段，`AGENT_STATE_DIR`/`WORKSPACE` 的 env 覆盖机制其实已预留）。

**便携模式不受影响**：exe 不经安装器直接跑（现状）仍是 exe 旁 = 数据根，两种形态同源。

## 2. 数据目录策略与升级不清数据

- **数据与程序同目录但互不隶属**：安装器 `[Files]` 只装它带的文件（exe/README/.env.example）；`xiaoju3_data/`、`agent_state/` 等由程序首启生成，**不在安装清单里** → 覆盖安装/升级时 Inno 只替换清单内文件，数据天然保留。
- **`build_exe.bat` 清 dist 是开发流程**（已有交接摘要待办：升级分发不能这么干）——安装器分发的升级 = 新 setup 覆盖安装，与 dist 清理无关。
- **卸载**：`[UninstallDelete]` 留空 → 只删清单内文件；卸载完成页文案提示数据位置；"彻底删除"复选框默认不勾，勾选才 `DelTree`（INSTALLER_PLAN §7 已定）。
- **目录名含中文/空格**（"小橘3号"）：os.path 兼容已核实；Inno 对 `{localappdata}` 常量原生处理。

## 3. Inno 脚本结构（xiaoju3.iss）

```ini
[Setup]
AppId={{固定 GUID（生成一次写死）}
AppVersion={AppVersion}                     ; 预处理器注入（§7）
AppName=小橘3号
DefaultDirName={localappdata}\Programs\小橘3号
PrivilegesRequired=lowest                   ; 全程零 UAC
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\xiaoju3.exe
OutputDir=dist                              ; 与 exe 同目录
OutputBaseFilename=小橘3号-{AppVersion}-setup

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "dist\xiaoju3.exe"; DestDir: "{app}"
Source: ".env.example"; DestDir: "{app}"
Source: "README.md"; DestDir: "{app}"

[Icons]
Name: "{autoprograms}\小橘3号 · 控制台"; Filename: "{app}\xiaoju3.exe"
Name: "{autodesktop}\小橘3号 · 控制台"; Filename: "{app}\xiaoju3.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked
Name: "autostart"; Description: "开机自动启动小橘3号"; Flags: checkedonce

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "Xiaoju3"; \
  ValueData: """{app}\xiaoju3.exe"""; Tasks: autostart; \
  Flags: uninsdeletevalue

[Run]
Filename: "{app}\xiaoju3.exe"; Description: "立即启动小橘3号"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
RunOnceId: "DelAutostart"; Filename: "{regdelete...}"   ; 见 §6（reg delete 容错删 Run 值）

[UninstallDelete]
; 故意留空——数据目录（xiaoju3_data/agent_state/workspace/backups）默认保留
```

要点：自启写 HKCU Run（`ValueName=Xiaoju3` 与 `autostart.py` **同键同名**，程序内开关/Inno 写入最后写入者胜，语义一致）；`uninsdeletevalue` 让卸载自动清该值。

## 4. 硬件自检页 + 组件勾选（[Code] Pascal Script）

自检三项全部 Inno 原生能力（零 DLL）：

| 指标 | Pascal Script 实现 |
|---|---|
| 内存 | `CreateOleObject('WbemScripting.SWbemLocator')` → WMI `Win32_ComputerSystem.TotalPhysicalMemory` |
| GPU | WMI `Win32_VideoController.Name` 匹配 NVIDIA / Radeon / RX / GTX（独显关键词） |
| 磁盘 | `GetSpaceOnDisk(ExpandConstant('{localappdata}'), True)`（Inno 内置，测安装目标盘） |

- 分档线沿用 INSTALLER_PLAN §4（≥16G+独显+≥20G = high 完整版；<8G = low 轻量版；中档提示）——**仅 UI 预判与建议文案**，真档位由程序内 `hardware_profiler` 复测（单一事实源口径不变）。
- 页面结构：自定义 `CreateCustomPage`（放自检结果行）置于组件页之前；WMI 失败（组策略禁 COM）降级为"无法预判，程序内将自动复测"，不阻塞安装。
- 组件页即 `[Types]/[Components]` 或 [Tasks] 承担（桌面图标/自启两项已覆盖主需求），自检页只读展示。

## 5. 自启：Inno 写 + 程序改 + 卸载清

- 装时：[Registry] 按 Tasks:autostart 勾选写入（`unchecked/checkedonce` 语义：升级安装不再重复弹问）。
- 程序内：`autostart.py` 读写**同一键同一值名**（HKCU Run / Xiaoju3）——设置页/引导勾选改的是同一事实。
- 卸载：`Flags: uninsdeletevalue` 自动清值（即使程序内已关过，删不存在的值无害）。

## 6. 卸载默认保留数据

见 §2 末两条 + `[UninstallDelete]` 留空 + 卸载页可选"彻底删除"（[Code] `CurUninstallStepChanged` 里 `DelTree({app}\xiaoju3_data)` 等三目录，默认不勾）。卸载完成页 `MsgBox` 提示数据保留位置。

## 7. build_exe.bat 扩展：单产物 → 双产物

```
[1/6] 清理 build/ dist/
[2/6] 从 xiaoju3.py 抓 XIAOJU3_VERSION（正则）→ 生成 version_info.txt
      （PyInstaller 版本资源模板：FileVersion/ProductVersion=1.0.0）
[3/6] python -m PyInstaller xiaoju3.spec            （spec 增 version='version_info.txt'）
[4/6] ISCC /DAppVersion=%VER% xiaoju3.iss           （Inno 预处理器接收版本）
[5/6] 产物报告：exe + setup 大小 + SHA256（供下载页校验，对冲 SmartScreen 误报）
[6/6] 完成
```

- 前置：安装 Inno 6（B0；`winget install JRSoftware.InnoSetup` 或官网安装包，装完 ISCC 进 PATH 或 bat 内写绝对路径——bat 探测两个标准目录）。
- 版本单一来源纪律：手写处仍只有 `xiaoju3.py` 一处；bat 抓取失败（正则不中）→ 立刻退出报错，不带版本出包。

## 8. 分步实施（B0 用户配合一次，B1-B4 每步可独立验证）

| 步 | 内容 | 依赖 | 验证 |
|---|---|---|---|
| B0 | 安装 Inno Setup 6（winget 或官网，需你机器上执行一次；或授权我用 winget 装） | — | `iscc` 可用 |
| B1 | 版本管线：bat 抓版本 → version_info.txt → spec 接入；顺带 Pillow 生成 `build/xiaoju3.ico` → spec `icon=`（first icon 用 normal_half.png 方图加圆角遮罩，透明 PNG 待办后再换） | — | exe 属性显示 1.0.0 + 有图标 |
| B2 | xiaoju3.iss v1（§3 全段）+ bat 扩为双产物 | B0+B1 | 装到 %LOCALAPPDATA%\Programs → 双击占位窗→控制台 → 数据目录生成在 {app} → 覆盖安装数据保留 |
| B3 | 自检页 + 组件/自启 + 升级卸载演练（装→升级→卸载→数据核对） | B2 | 冒烟清单（与 exe 同格式）入 INSTALLER_PLAN |
| B4 | 可选：真透明 PNG 图标、README 安装章节、SHA256 下载页 | B3 | — |

## 风险点

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| 1 | **数据目录**：若未来被要求改机器级安装（Program Files），frozen DATA_ROOT=exe 目录的现设计会崩 | 中（已用用户级安装规避） | §1 定稿用户级；机器级需求出现时再动 paths.py（env 覆盖已预留），1.0 不碰 |
| 2 | Inno 未装（B0 需一次机器操作） | 低 | winget 一条命令；或 bat 检测缺失给安装指引 |
| 3 | onefile exe 过 Inno 再压缩：安装包体积 ~20MB，但用户首启要解两层（setup 解压 + onefile 自解压）首启略慢 | 低 | P2 已实锤占位窗体验；不达标退 onedir |
| 4 | SmartScreen/杀软对 setup.exe + app.exe 双文件误报 | 中（已知，发布口径） | SHA256 公示 + README 声明；签名证书 1.0 后评估 |
| 5 | 图标用 JPG 占位 PNG 生成：视觉质量差（无透明） | 低 | B1 先出"能用"版；真透明 PNG（待办）落地后重生成即换 |
| 6 | Inno 中文语言包文件名/路径随版本差异 | 低 | 6.x 标准自带 ChineseSimplified.isl；缺失时退英文 + README 中文 |
