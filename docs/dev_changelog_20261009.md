# 小橘3号 开发者日志 · 2026-10-08（凌晨批次，接 10-07 晚稿）

> ⚠️ 版本说明：本文件曾于 10-09 深夜被多终端同步删除（从未 commit，
> 无 git 历史）。当前版本为 10-10 重建版：凌晨批次按 git 提交信息重构
> （措辞或与原稿有出入，权威源=git log）；第二/三批为完整原文。
> 本文为 2026-10-07 晚 ~ 10-08 凌晨跨零点批次的事实清单，格式对齐
> dev_changelog_20261007.md。时间以 git 实际提交时间为准；真机验收
> 结果单独成点。

---

## 一、按提交逐条

### `baff5e9` build(package): onefile → onedir 改造（冷启动根治拍板，10-07 18:37）

- spec EXE 改 `exclude_binaries=True` + 新增 COLLECT：产物 `dist\xiaoju3\`（xiaoju3.exe 19.4MB + `_internal\` 186MB/408 文件）；
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
- desktop_launcher taskkill 兜底补同款（普查③，psutil 缺席罕见路径）
- 黑框三源（任务 powershell ①/nvidia-smi ②/taskkill ③）全打

### `4cc77d5` fix(desktop): #263 L1 跨版本双开兜底（10-08 01:20）

- main 单实例门补 5003 端口探测（_another_instance_serving，跨版本通吃——端口占用即已有实例，不分通道），命中即唤起+return 0（先于 ensure 不重复拉后端）
- 门锚改旗标式+新增跨版本锚；快捷方式已改指正式版（运维操作）。测试版保留为预览通道（发布通道设计记 #279，L2/L3 赛后）

### `e99d173` feat(brain): R4 危险词表扩容 20→31（安全侦察 R4 项）

- 收中文同义（移除/清除/销毁/覆写）+英文命令（cmd/powershell/bash/rm -rf/delete/format/uninstall）
- 泛用动词 7 词不收（跑/执行/运行/命令/脚本/替换/终端——误伤评估先行）；词表双向锚防回退

### `4cc77d5` fix(desktop): #263 L1 跨版本双开兜底（10-08 01:20，同上合并记录）

- 见上 a05011c/e8b68d4/4cc77d5 三笔连发段（本行占位避免格式断裂，内容已并入上方条目）

---

## 二、非提交事项（凌晨批）

- 黑框真机验收 PASS（12:39 真实提取 node≠0 + conhost 全 hwnd=0，flash_monitor 实录）→ #272 关账
- AIC2026_佐证材料/截图采集清单落 docs/（后来移出公开仓，见 10-09 批）
- _dev/ 自动化脚本族扩容（add_todo_*/fix_*/record_* 系列）

---

## 三、测试与推送

- 测试基线：**1902 passed + 4 skipped**（1901+4 → 跨版本锚 +1，只增不减）
- 推平记录：origin/main = `4cc77d5`（含黑框 A/跨版本兜底/onedir/AGENTS 两笔）
- `5045c30`（.gitignore 排除 AIC 两份材料+z*.png）重放为 `6860e35` 留本地顶，**永不推**

---

## 四、遗留（下次会话）

- 重启终验四项：黑框零（已过一次）/ 自启 wscript 链（脚本已修待真机重启复验）/ 双开拦截（跨版本门待真机复验）/ 白闪缓解（env 参数待体感）
- #262 待标 done；#275/#276 冒烟混入的生活待办待用户处置


---

## 五、10-09 午后~深夜批次（第二批，补记）

### 状态更新前置
- `6860e35`（.gitignore 排除 AIC 材料）已于当日推平；本批后续见第六节

### 交付摘要

- 视频 9 分镜素材定位：F:\Xun\Videos\屏幕录制\（OBS 配置 FilePath 实锤；Git Bash glob 大小写敏感漏 F:\Xun 小写目录的教训）
- 分镜 5 升级视频方案（4'22"+21s 采纳）；分镜 6 定性=镜头7 误标（74s 断网全程，用户目视）
- 分镜 7 半成品（物理开关✅/拒绝文案误录待补录）；SRT 28 条字幕底稿
- 剪辑交接包 _dev/aic_video_edit_handoff.md（八节）

---

## 六、10-09 深夜~10-09 深夜（第三批预留）

（本节由当晚后续批次填写）


---

## 七、10-09 深夜第三批（软著提交/E3 修复/北极星双层/实验轨道）

### 里程碑

- **软著申请提交成功（08:02）**：状态=待受理，申请流水号 **2026R11L3453611**（签章页 2026R11J453611=材料打印编号）；六件材料（登记表/身份证/源代码 61 页/说明书 63 页/签章页/AI 声明）；补正期 30 天留意站内信——P0 关账
- **北极星双层结构建立**：正档 xiaoju3-northstar.md（14 层愿景冻结）+ 路线图 xiaoju3-roadmap.md（活跃层 8 项=完成 4/设计稿 2/排队 2）；实验室镜像 git 1fc14af；正档清理（59-77 行按用户拍板：63 行改多终端定性/执行类五段删——路线图承接）
- **仿生实验室实验轨道三连**：exp01 记忆权重 MVP（#285 done）/ exp02 联想网络 MVP（#291 done）/ exp03 三乘子召回预演（#292 done）——weight×emotion×activation 三乘子召回链全部验证，为 #271② 铺路
- **AGENTS.md 两条新纪律**（2513b16 推平）：多终端协作（不同时改同一文件/一端写完另一端先重读）+ 文件写入安全（.bak 时间戳备份/open('w') 先 cp 再写）

### 提交逐条（10-09 午后~深夜，全部已推）

#### `0e10366` feat(intent): QQ 待办直达 + `c871120` feat(brain): 旁路 JSON 消毒

- todo_query 意图（查/看看/有哪些+待办，negative 排除添加语义）→ 新插件 plugins/todo_query.py:list_reply（get_todos 直查格式化清单，零模型参与——本地小模型对查待办会幻觉工具名+格式迁移直出原始 JSON，10-08 晚实锤 get_todo_list 全仓零命中）
- _strip_bare_json 旁路消毒（整条无 tool 键 JSON→剥除+/help 引导），挂 _wrap_think 统一出口
- spec hiddenimports 补 plugins.todo_query（动态引用铁律）；search 意图 negative 补「待办」
- +6 锚；v26 车（379f5893）部署，真机「看看待办」⚙️ 指令直达验证

#### `3b19cff` fix(boot): E3 两层修复 + 三轮全过

- ①监督真空：复用态也起监督线程（backend_pending 条件扩入）+_supervise_backend 加复用态端口监视分支（proc=None 且 5003 消失→respawn）
- ②Popen 引号 bug：ensure_napcat 改 cwd 参数形态（[cmd,/c,bat]+cwd=napcat_dir），勿回退 cd&& 拼接（list2cmdline+cmd 引号解析损坏——「文件名目录名语法不正确」bat 从未执行，「✅ 已后台启动」全为假象；**自愈链自 10-02 上线从未真正工作过**，历史 NapCat 复活实为手动 QQ）
- E3 三轮：轮 1 杀 dashboard 15s 复用态监督重生 / 轮 2 全链死→6s 全链活 / 轮 3 登录态跨强杀保留（3000 OneBot 活）
- v27 车（bf82d0e0）部署

#### `836d9f6` docs(tools): Lv.3 门槛段注释修正

- 旧注释误列 adb 族为 Lv.3（10-02 已升 Lv.4）；manifest=唯一事实源，文档债清

#### `dc35a7e` docs(conventions): AGENTS.md 决策纪律节

- 三步对抗论证（①全力反驳 ②支持视角 ③中立对比+反转条件拒绝五五开）；适用=方案选择/架构变更/新依赖/删改功能
- 专利筛查=通用方法论零新点，已推

#### `2513b16` docs(conventions): AGENTS.md 两条新纪律

- 多终端协作（不同时改同一文件/一端写完另一端先重读——记忆区无锁后写覆盖先写实锤）
- 文件写入安全（.bak 时间戳备份/open('w') 先 cp 再写——交接包竞态截空实锤）

#### 实验 1-3（仿生实验室，本地 git da7bbd2→8ab017d）

- exp01 记忆权重 MVP（#285 done）：判据三条活体验证（被召回 20 天前旧记忆反超新记忆）
- exp02 联想网络 MVP（#291 done）：查「毕业答辩」LIKE 2 条 vs 扩散 13 条（12 条字面不含关键词只有联想能到）
- exp03 三乘子召回预演（#292 done）：三 mood 排序翻转活体（happy Top1=导师表扬 joy vs anxious Top1=论文被打回 negative）+mood-congruent 占比 3/5→4/5
- 种子基础激活回溯：exp02 同款缺陷（种子不在 gained）已修

### 非提交事项（10-09 午后~深夜）

- 软著 AI 声明三件套（F:\注册著作权\\）； NapCat 自愈链两层修复+三层诊断；蓝图正档清理（59-77 行按拍板）+路线图镜像；分镜素材归档 103MB
- 多终端时滞两次实战（正档并行会话误判/交接包竞态截空）——纪律已入 AGENTS.md（2513b16）
- 北极星实验轨道三连 MVP 全过：weight/emotion/activation 三乘子召回链全部验证——#271② 赛后落地的全部前置验证完成

---

## 八、测试与推送（10-09 全天总账）

- 测试基线演进：1902+4 → 1912+4（#278 批+10）→ 1915+4（R2R3+3）→ **1923+4**（E3/竞速+2+种子回溯+1…累计今日 +21）
- 推平链（10-08 全天 12 笔+10-09 6 笔）：… → c225f8f → be97b4f → 7fffc91 → c275e09 → 956dd02 → 03a3070 → afff438 → 4b308cc → e99d173 → 836d9f6 → 5088946 → dc35a7e → **3b19cff（现 HEAD）**
- 本地未推：0 笔（1adc72c 已在 3b19cff 前推平链中）
