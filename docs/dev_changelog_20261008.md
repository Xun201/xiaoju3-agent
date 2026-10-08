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


---

## 六、10-08 午后~深夜批次（第二批，挂机补记）

### `c225f8f` fix(repo): AIC2026 材料排除规则撤出公开 .gitignore

- 6860e35 曾把两份 AIC2026 私有材料**文件名+拍板注释**推进公开 .gitignore（违纪实锤）
- 修复=公开 .gitignore 删整段；排除效果迁 `.git/info/exclude`（纯本地永不进仓），佐证材料通配 md/docx/pdf + 佐证截图 z* 段同迁
- 新规矩：**私有材料一律只走 info/exclude，文件名不进公开 .gitignore**
- 历史残留拍板=L1 即止不重写历史

### `be97b4f` feat(brain): #278 危险操作强制云端（一期）

- `_DANGER_CLOUD_KEYWORDS` 初版 19 词；smart_ask / smart_ask_stream 双侧强制云端
- 真机三连验收 PASS：删系统文件→云端按权限口径拒绝零编造；写诗/重启路由器→本地照走
- 一期不做结果断言校验层（留 #270 赛后）

### `7fffc91` feat(brain): #278 词表收编「重启」

- 真机发现本地对「重启路由器」同样零工具编造「操作已完成」→收编（20 词）
- restart 锚从「不触发」反转为「触发」

### `c275e09` / `956dd02` / `03a3070` / `afff438` fix(boot): 方案 A 自启改造批（四笔）

- `c275e09` 桌面窗探测等待+快速 fallback：新增 `_backend_warming_up`（5003 在线 OR 其他 xiaoju3 进程在=后端拉起途中）；ensure 三态化（就绪复用/途中等待/全无才 spawn 兜底）；wait 15s→60s
- `956dd02` **NameError 祖传 bug 修复**：`_another_instance_serving` 签名漏 timeout（4cc77d5 起所有车带病）；测试全量 mock + 门 or 短路双盲区实锤（5003 探测分支部署至今真机零跑通）；补真跑锚
- `03a3070` 门 5003 分支精化：后端在跑且唤不到窗=登录链标准态→出窗复用不退出（v22 冒烟永无窗实锤）
- `afff438` **导入期互斥体角色守卫**：exe 单一入口后端角色也持锁，污染桌面窗 `_SI_ALREADY`（v23 冒烟永无窗第二根因）
- 连带处置：火绒拦 wscript→powershell -Hidden 链 → **自启载体改 HKCU Run 键双通道**（Xiaoju3 桌面窗+Xiaoju3Backend 后端直启）；计划任务方案=ZCode shell 权限墙否决；v21-v24 四车迭代；双击 spawn 兜底实测火绒未拦；wscript/vbs 归档 `_dev/retired_autostart_20261008/`

### `4b308cc` sec(adb): R1 安全边界显式化

- adb_tap/adb_swipe f-string shell 拼接补【安全边界】注释 + int() 纵深强转
- 侦察实锤：模型→shell 直达注入链=零（int() 隐式封死，本笔文档化+加固）

### `e99d173` sec(brain): R4 危险词表扩容 20→31

- 收中文同义（移除/清除/销毁/覆写）+英文命令（cmd/powershell/bash/rm -rf/delete/format/uninstall）
- 泛用动词 7 词不收（跑/执行/运行/命令/脚本/替换/终端——误伤评估先行）；词表双向锚防回退

### `836d9f6` docs(tools): Lv.3 门槛段注释修正

- 旧注释误列 adb 族为 Lv.3（2026-10-02 已升 Lv.4）；manifest=唯一事实源，文档债清

### `5088946` refactor(napcat): 方案 E 自愈链去提权化

- 起因=火绒拦 xiaoju3.exe「隐藏执行 PowerShell」（ensure_napcat 非管理员分支 powershell runAs）
- 侦察重大发现=NapCat 官方免提权变体 `launcher-user.bat` 在案 + QQ 装用户可写目录（D:\Ruanjian\QQ 写探针过）=提权非硬需求
- ensure_napcat 统一 cmd /c launcher-user.bat，删 powershell 分支与 `_is_windows_admin`
- E1 试点 user 版注入成功（NapCatWinBootMain+QQ×4+6099）；E3 复活+全程 powershell=0+火绒零拦截；强杀后 10 秒秒崩=QQ 残留单实例锁时序（延迟复跑成功，非代码缺陷）
- **QQ 登录态恢复**（用户扫码 qrcode.png + 群发「在吗」验回）——方案 E 四段全过；v25 车（1160dc85）部署在线

### `1adc72c` sec(tools): 挂机安全加固批 R2+R3（**本地未推**）

- R2 write_file 覆盖保护：覆盖已有文件前自动落 `.bak-时间戳` 副本（shutil.copy2，无交互场景静默备份）
- R3 system_manage 安装白名单 29 库：白名单外 install 拒绝+引导手动安装（任意 PyPI 包=安装钩子任意代码执行）；uninstall 不受限；extras/版本形态走防注入校验先于白名单
- R2 两锚+R3 锚（call_count 精确断言）；全仓 1915+4

## 七、测试与推送（第二批）

- 测试基线演进：1902+4 → 1912+4（方案 A 批+5）→ **1915+4**（R2/R3+3），只增不减
- 推平链：c225f8f → be97b4f → 7fffc91 → c275e09 → 956dd02 → 03a3070 → afff438 → 4b308cc → e99d173 → 836d9f6 → 5088946（**origin/main = 5088946，共 11 笔**）；`1adc72c` 本地未推（挂机批，明早人工过目后推）
- 非提交事项：软著申报（实名过/登记表填毕/材料已上传，流水号 2026R11J453611=**签章页材料流水号**非受理号，**已上传未提交**待明早 8:00 系统维护结束提交）；DeepSeek 顾问记忆本建立（`_dev/DEEPSEEK_ADVISOR_MEMORY.md`，info/exclude 排除）

## 八、遗留（第二批后更新）

- QQ 通道已恢复（扫码+「在吗」验回）；E3 多轮自愈验证（明晚：杀 NapCat→重启→复活 ×N + 强杀-秒重启时序观察）
- 重启终验：Run 键自启链 3 进程自动拉齐 / 黑框零 / 「重启」词走云端
- 软著提交（明早 8:00，P0，提交后记新受理号）
