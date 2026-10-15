# 自启动全景台账（startup_audit_20261015）

> 审计时间：2026-10-15 晚 ｜ 方法：HKCU/HKLM Run + 启动文件夹（用户级/全局级）+ 计划任务四路实查
> 归属四类：**项目** / **用户装的应用** / **第三方捆绑** / **系统驱动**
> 建议三档：**留** / **禁** / **待确认**（拍板后执行）
> 铁律：本台账纯只读产出，零进程被关零注册表被改

---

## 一、禁的排最前（✅ 2026-10-15 深夜用户管理员窗口执行全绿：NI 停+禁/PCManager 停+禁/AMDInstallLauncher 禁——:8080 裸奔面已消除）

### 需管理员（用户开管理员窗口复制运行）

| # | 项 | 来源 | 归属 | 内存/影响 | 建议 | 命令 |
|---|---|---|---|---|---|---|
| 1 | AMDInstallLauncher（计划任务） | 系统驱动(AMD) | 系统驱动 | 无常驻，装器 | **已禁 ✓**（2026-10-15 深夜用户执行） | `schtasks /change /tn "AMDInstallLauncher" /disable` |
| 2 | TX Mascot（HKLM Run） | 用户装(ASUS) | 用户应用 | 吉祥物装饰（进程已在） | **关+禁自启** | `reg delete "HKLM\Software\Microsoft\Windows\CurrentVersion\Run" /v "TX Mascot" /f` |
| 3 | PCManager Service Store（服务，微软电脑管家 133MB） | 用户装 | 用户应用 | 常驻 133MB | **已停+禁 ✓**（2026-10-15 深夜用户执行） | `sc stop "PCManager Service Store"` → `sc config "PCManager Service Store" start= disabled` |
| 4 | NIApplicationWebServer（服务，21MB，:8080 裸奔） | **第三方捆绑（Multisim 捆绑 WebServer，D:\learn and work\multisim\）** | 第三方捆绑 | 21MB+8080 裸奔面 | **已拍板禁用（2026-10-15 深夜，用户确认暂不用 Multisim）——待管理员执行两条命令；需要时手动恢复：`sc start NIApplicationWebServer`** | 同左两条 |

### 非管理员（ZCode 可代跑/用户点两下）

| # | 项 | 来源 | 归属 | 内存/影响 | 建议 |
|---|---|---|---|---|---|
| 5 | Edge AutoLaunch ×2（HKCU Run） | 系统/用户 | 系统驱动 | Edge 预热后台 | **禁**（任务管理器→启动应用→Microsoft Edge） |
| 6 | Chrome AutoLaunch（HKCU Run） | 用户装 | 用户应用 | Chrome 预热后台 | **禁**（同上） |
| 7 | TabbitBrowserUpdater（HKCU Run） | 用户装 | 用户应用 | 更新器常驻 | **禁** |
| 8 | UC浏览器（HKCU Run） | 用户装 | 用户应用 | 浏览器自启 | **禁/待确认** |
| 9 | Quark 网盘小组件（HKCU Run） | 用户装 | 用户应用 | 网盘挂件 | **禁/待确认** |
| 10 | TypeEasyNotify（计划任务） | 用户装 | 用户应用 | 打字练习通知 | **禁候选** |

## 二、待确认（你在用就留）

| # | 项 | 来源 | 归属 | 内存/影响 | 问题 |
|---|---|---|---|---|---|
| 11 | Steam -silent（HKCU Run） | 用户装 | 用户应用 | Steam 后台 | 还玩 Steam 吗？ |
| 12 | GameViewer --auto-run（HKCU Run）+ GameViewerServer 57MB | 用户装 | 用户应用 | uu远程服务端 | 还用 uu远程吗？ |
| 13 | Nutstore --autostart + NutstoreClient 91MB | 用户装 | 用户应用 | 坚果云同步 | 同步还在用吗？ |
| 14 | AMDNoiseSuppression（HKCU Run） | 系统驱动(AMD) | 系统驱动 | 麦克风降噪 | 用 AMD 降噪吗？ |
| 15 | Steamcommunity_302（计划任务） | 用户装 | 第三方工具 | Steam 社区加速修复 | 还用 Steam 社区吗？ |
| 16 | StartCN / StartDVR（计划任务） | **待查** | 第三方捆绑? | 待查 | 这俩是什么？（下一轮查证后归档） |
| 17 | GenuineService.lnk（启动夹） | **待查** | 第三方捆绑? | 待查 | "Genuine"正版服务——哪个软件装的？ |

## 三、留（A 档项目 + B 档系统）

| 项 | 来源 | 归属 | 说明 |
|---|---|---|---|
| Xiaoju3 + Xiaoju3Backend（HKCU Run ×2） | 项目 | 项目 | 生产车自启（方案 A，必需） |
| Ollama.lnk（启动夹） | 项目系 | 项目 | 本地模型引擎（LOCAL_URL=11434 在役） |
| llama-server.exe（Ollama 子进程） | Ollama 拉起 | **项目（改判 A 档不可关）** | 724MB（模型常驻，keep_alive=-1） | 深查实锤：父进程=ollama.exe，监听 127.0.0.1:3393 仅本机；杀它=杀本地大脑。早前 ":8080 裸奔"判定误配——真主人=NIApplicationWebServer |
| Tailscale.lnk（全局启动夹） | 项目系 | 项目 | Pi/HA/多端通道 |
| ctfmon / SecurityHealth / Sysdiag(火绒 HipsTray) | 系统/安全 | 系统驱动 | 输入法+安全 |
| RtkAudUService64_BG（计划任务） | 系统驱动 | 系统驱动 | Realtek 音频 |
| GHelper（计划任务，正在运行） | 用户装(ASUS) | 用户应用 | 笔记本管控（风扇/模式——**刚用它切了独显直连，留**） |
| NVIDIA App SelfUpdate + NIUpdate | 系统驱动 | 系统驱动 | 显卡更新（可禁候选但收益小） |
| OneDrive ×3（计划任务） | 用户装 | 用户应用 | 在用则留 |

## 四、汇总

- **能禁（管理员 4 项）**：AMDInstallLauncher/TX Mascot/PCManager/NI——省 RAM ≈ 133(PCManager)+21(NI) = **154MB** 常驻 + 8080 裸奔面消除
- **能禁（非管理员 6 项）**：Edge×2/Chrome/Tabbit updater/UC/Quark/TypeEasy——开机峰值省 ≈ 300-500MB + 开机提速
- **待确认 7 项**：逐个回答"在用吗"后归档
- **留**：项目三件+安全+驱动+GHelper

## 五、复查纪律（新增）

**一劳永逸做法=本台账即基线：新装任何软件后往台账加一行（项名/来源/归属/内存/建议），季度复查一次"禁-待确认-留"三档漂移。**

## 六、待确认 7 项拍板执行（2026-10-16 凌晨收官，用户逐项拍板）

**拍板结果：6 禁 2 留**（11 Steam 中途改判留——Wallpaper Engine 小红车依赖 Steam 后台常驻，禁则壁纸崩）。

| # | 项 | 拍板 | 执行 | 复验 |
|---|---|---|---|---|
| 11 | Steam -silent | **留**（改判） | 误删已恢复：`reg add HKCU...\Run /V Steam /D "\"D:\youxi\Steam\steam.exe\" -silent"` | ✓ 原值还原实抓 |
| 12 | GameViewer（uu远程） | 留 | — | — |
| 13 | Nutstore（坚果云） | 留 | — | — |
| 14 | AMDNoiseSuppression | 禁 | `reg delete HKCU...\Run /V AMDNoiseSuppression /F`（原值=C:\Windows\system32\AMD\ANR\AMDNoiseSuppression.exe） | ✓ 键消失实抓 |
| 15 | Steamcommunity_302 | 禁 | ✅ 已执行（管理员命令组，2026-10-16 凌晨）`schtasks /Change /TN "Steamcommunity_302" /DISABLE` | ✓ ZCode 复验"已禁用"实抓 |
| 16 | StartCN/StartDVR | 禁 | ✅ 已执行（同上；已破案=AMD Adrenalin 官方 cncmd.exe/RSServCmd.exe，UI 栈同族） | ✓ ZCode 复验"已禁用"实抓 ×2 |
| 17 | GenuineService | 禁 | 已破案=**Autodesk 正版验证**（非 Windows 服务——333 服务枚举零匹配；仅启动夹 lnk 指向 C:\Users\Xun\Autodesk\Genuine Service\GenuineService.exe）；lnk 已备份 `_dev/autostart_backup_20261016/GenuineService.lnk` 后删除 | ✓ 启动夹零残留 |

**管理员命令组（5 条，用户 2026-10-16 凌晨执行完毕，ZCode 复验全绿实抓）**：

```
schtasks /Change /TN "Steamcommunity_302" /DISABLE   # ✓ 复验"已禁用"
schtasks /Change /TN "StartCN" /DISABLE              # ✓ 复验"已禁用"
schtasks /Change /TN "StartDVR" /DISABLE             # ✓ 复验"已禁用"
sc stop NIApplicationWebServer                       # ✓ 报 1062=服务本就未起（假错误无害）
sc config NIApplicationWebServer start= disabled     # ✓ 复验 START_TYPE=4 DISABLED+STATE STOPPED
```

**至此：自启 7 项（6 禁 2 留）+ 管理员 5 条全部落地（2026-10-16 凌晨终态）。**

- 恢复命令：任务=schtasks /Change /TN "<名>" /ENABLE；NI= sc start NIApplicationWebServer（config 改回 auto 需另查原启动类型）；Steam 如需自启=reg add 原值（见上表）；GenuineService 恢复=从 _dev/autostart_backup_20261016/ 拷回启动夹
