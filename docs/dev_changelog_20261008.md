# 小橘3号 开发变更记录 · 2026-10-08（凌晨批次，含 10-07 夜段）

> 本文为 2026-10-07 夜 ~ 10-08 凌晨跨零点批次的事实清单，格式对齐 dev_changelog_20261007.md。
> 时间以 git 实际提交时间为准；真机验收结果单独成段。

---

## 一、按提交逐条

### `baff5e9` build(package): onefile → onedir 改造（冷启动根治拍板，10-07 18:37）

- spec EXE 改 `exclude_binaries=True` + 新增 COLLECT：产物 `dist\xiaoju3\`（xiaoju3.exe 19.4MB + `_internal\` 186MB/408 文件）
- 根因实锤：onefile 每次启动 **3 进程 × 各自解压 186MB**（%TEMP% 实测 _MEI 残留 46 个/8.3GB），冷启动 83s 大头
- iss [Files] 首行改整目录 recursesubdirs；bat 产物路径/缺失检查同步；paths.py 双根零改动（PyInstaller 6.22.3 onedir 亦设 _MEIPASS→_internal）
- 预估/实测：冷启动 83s → ~30s；暖启动 5s → 2-3s

### `a05011c` fix(desktop): #263 单实例门 + 白屏 env 快改（10-07 18:37）

- main 加命名互斥体 `Local\Xiaoju3_Desktop_SingleInstance`（已存在→枚举唤起已有窗口+return 0，不开第二窗不重复拉后端）
- 模块导入期设 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` 禁最小化挂起/后台化（恢复窗口无整页白闪）
- +3 锚（gate 二实例退出/mutex 语义唯一名/env setdefault）

### `e8b68d4` fix(boot): 黑框全谱清零（普查方案 A，10-08 00:09）

- 计划任务 Action 换 **wscript 静默壳**（autostart_launch.vbs 纯 ASCII 两行：Run powershell -Hidden, 0 窗口）——conhost 先建后隐的 1-2s 登录黑框根治
- hardware_profiler nvidia-smi 补 CREATE_NO_WINDOW（普查②：每进程首聊闪 ≤2s）
- desktop_launcher taskkill 兜底补同款（普查③：psutil 缺席罕见路径）
- 黑框三源（任务 powershell ①/nvidia-smi ②/taskkill ③）全打

### `4cc77d5` fix(desktop): #263 L1 跨版本双开兜底（10-08 01:20）

- 真机双开实锤为**双版本**：自启链指正式版（F:\XUNandxiaoju3，有门）；桌面/开始菜单快捷方式历史指向测试版（F:\测试\小橘3号 旧车，无互斥体代码，同版本门对其失明）
- 修：main 单实例门补 5003 端口探测（`_another_instance_serving`，跨版本通吃——端口占用即已有实例，不分通道），命中即唤起+return 0（先于 ensure 不重复拉后端）
- 门锚改旗标式+新增跨版本锚；快捷方式已改指正式版（运维操作）；测试版保留为预览通道（发布通道设计记 #279）

### `6b8a831` / `606799e` docs(conventions): AGENTS 两笔

- 6b8a831：通用性纪律——解决 bug 须通用可行，禁止本机特调（先例：火绒白名单被否→onedir）
- 606799e：先例 2——运维脚本（ps1/bat）一律纯 ASCII 或确保 UTF-8 带 BOM（PS 5.1 无 BOM 按 ANSI/GBK 读，中文注释炸解析；autostart_watch.ps1 真机实锤）

---

## 二、待办与运维操作（非 commit）

- #279 发布通道设计（P2）：L1 止血今晚做 / L2 通道切换赛后 / L3 版本交错远期
- #278 本地小模型"编造操作结果"防御（P1）：真机实锤"帮我删系统文件"→0 工具调用回"操作已完成"
- 计划任务 Xiaoju3_AutoStart：Action 两改（powershell → wscript+vbs），XML 实证
- 快捷方式双改指正式版（桌面 + 开始菜单）
- 回滚锚三件：onefile 旧车备份（_dev\onefile_backup_20261007）+ todos.db.bak-before-onedir + todos.db.bak-20261007-141525

---

## 三、真机验收（10-08 凌晨两次重启）

- 重启①（23:27）：autostart_watch.ps1 **编码爆炸**（UTF-8 无 BOM+中文注释，PS 5.1 按 ANSI 读）→ $exe 空值报错×N，exe 未拉起，自启链断——实锤进 AGENTS 先例 2
- 重启②（23:37）：黑框零 ✓；登录→窗口 **33s** ✓（掐表）；**双开两窗** ✗ → 诊断为双版本（非竞态）→ 4cc77d5 修复
- 部署含跨版本兜底的新车后受控复验：第二实例 **0.4s 退出 / ExitCode 0 / 不开第二窗 / 进程数不变** ✓

---

## 四、测试与推送

- 测试基线：**1902 passed + 4 skipped**（1901+4 → 跨版本锚 +1，只增不减）
- 6 笔推平：origin/main = `4cc77d5`（含黑框 A/跨版本兜底/onedir/AGENTS 两笔）
- `5045c30`（.gitignore 排除 AIC 两份材料+z*.png）重放为 `6860e35` 留本地顶，**永不推**

---

## 五、遗留（下次会话）

- 重启终验四项：黑框零（已过一次）/ 自启 wscript 链（脚本已修待真机重启复验）/ 双开拦截（跨版本门待真机复验）/ 白闪缓解（env 参数待体感）
- #262 待标 done；#275/#276 冒烟混入的生活待办待用户处置
