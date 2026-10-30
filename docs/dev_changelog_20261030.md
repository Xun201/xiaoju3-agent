# 开发者日志 2026-10-30

## 批十二 — feat(AI 多方协作控制台·Multi-Agent UI)（v2.2.1 内部补丁，重建 exe f9040416/14ac194f 部署，全仓 2936+5）

### 改了什么
- **collab_hub.py 协作总线服务**（新模块，进 PYZ）：SYNC/TASK_BUS 增量监听（1.5s 轮询）→ 角色消息（zcode/secretary/boss）ui_events.publish("collab_msg") SSE 实时推送 + 内存 deque(maxlen=200) 历史回放；秘书自动回话（XIAOJU3_BUS_ENABLED=1 才联网，日帽 15+黑名单+留痕）回复写 TASK_BUS[秘书回复]节自然闭环；emit_boss 老板拍板写[老板拍板]节；HITL=文本含「@老板」→ hitl 标记。
- **dashboard 两端点**：GET /api/collab/history（回放）/ POST /api/collab/send（老板发言，空消息 400 零静默）；启动挂载（失败不影响主流程）。
- **前端「协作」pane**：CHAT_TABS 五方互斥（四方 hide 清单全补 collabPaneEl）；三色气泡（秘书蓝/包工头灰/老板绿+内联 SVG 角标 brain/wrench/crown）；renderRich 复用（md-code）；HITL 确认卡片（@老板→醒目黄卡+同意/驳回写回+防重入）；输入框 Enter/按钮发送；🧰 工具面板入口卡。
- **APK 崩溃批（c6d0a09）**：index.html 注入启动错误可视化横幅（window error→红条上屏）；新 APK d848f2de 交付。
- **ClawChat 查证（法则 2）**：github.com/alexrudloff/clawchat 真实存在但=OpenClaw 生态 P2P 附件（前提=两端各跑 OpenClaw agent），不适用小橘自研体系——队长核心诉求由自研协作控制台覆盖，未部署。

### 踩坑与修复（同批）
- **frozen 路径陷阱二次现身**：collab_hub 按 __file__ 拼 _dev 路径，PYZ 内 __file__=_MEIPASS（_internal）→ 监听不存在路径 history 恒空（部署实锤：线程正常启动但零消息）——修=frozen 下 _ROOT=dirname(sys.executable)。
- **生产 _dev 无总线文件**：hub 监听的生产 _dev 只有旧素材——修=路径 env 覆盖（XIAOJU3_COLLAB_SYNC/TASK），生产 .env 指向本机仓库 _dev 绝对路径（hub 与 ZCode 同机零拷贝实时监听）。

### 怎么验证的
- 全仓 **2936+5 全绿**（+7 collab 锚+互斥锚五方化）；三重建部署（f9040416/14ac194f → 终版）；Mock 演示全链=写 SYNC→zcode 气泡/TASK_BUS 秘书节→🧠气泡/@老板→HITL 卡/POST send→boss 气泡，**真浏览器实拍三色气泡+HITL 卡（_dev/shot_collab_panel_20261030.png）**。
- 演示数据说明：SYNC/TASK_BUS 尾部有【演示】标记节（截图内容），验收后可清；历史内存 200 条自滚动。

### 回滚
- git revert 03c6fd8..本笔；重建回滚；.env.bak-20261030-collab 还原协作两行。


## 批十一 — 🚑 紧急排障：QQ 不回复案三刀根治（v2.2.1 内部补丁，重建 exe 7454a174 部署 11:45 三进程全新）

### 破案链
队长 11:07 发"记住，我最喜欢玩明日方舟"零回复。排查：进程活/health ok/NapCat 活/手动发送 API retcode 0 全通；日志实锤回复已生成（去重修复同时实证工作：💾 记忆已存在刷新鲜活度）——断点在发送环节静默吞。生产失败日志（新回执校验第一发就抓到）：`retcode=200 请指定正确的 group_id 或 user_id`；本地精确复现=user_id None/缺失。**根因=NapCat 某些事件形态 sender 结构异常（user_id=None）→webhook 只从 sender 取 user_id→发送 payload user_id=None 被拒→旧代码不校验回执静默吞（#259 老雷）**。

### 三刀修复
①发送回执校验（_send_reply_segments）：retcode==0+message_id 才算成功，失败显式日志（HTTP/retcode/wording），#259 老雷根治——本次排障正是它抓的真凶；②_persona_guard_pipeline(message) NameError 修正（作用域是 raw_message）——仲裁脑改写管线自 10-27 v2 引入即每次失效原样放行，今复活；③user_id 双源兜底：sender 缺失回退事件顶层 user_id，双双缺失=垃圾事件记日志早退（零静默）。

### 怎么验证的
- 全仓 **2929+5 全绿**（+2 回执锚+2 兜底锚）；生产同构场景终验：sender 缺失+顶层 user_id 事件 → 云端直回+发送**零 ❌**（修复前同构=静默失败）；三连模拟/手动发送各形态全过。
- 排障期间向队长 QQ 发送测试消息 4 条（🔧 排障测试/类型测试×2/模拟回复若干）——如有多条打扰请忽略。

### 回滚
- git revert daccf5e/4465f51；重建回滚；main.py.bak-20261030-sendfix。


## 批十 — fix(记住链去重根治+占位文案退役)（v2.2.1 内部补丁，重建 exe b32d1b92 部署 11:02 三进程全新）

### 改了什么
- `state_manager.save_memory` 内容去重：**UPDATE 优先模式**（rowcount==0 才 INSERT）——同 content 已存在→刷新 timestamp（鲜活度回写，注入排序靠前）+更新情绪标签，绝不插新行。唯一写入口修=记住链（main:1278）/summary_facts 沉淀/人格四维沉淀全部写入方统一受保护（通用性纪律）。生产实锤根因：10 条重复"明日方舟"=同句重复"记住"每几分钟一条（memories 表无 UNIQUE，facts 有）。
- 工具面板过时占位文案"其余卡片为占位"退役（面板已全功能，优雅留白）。

### 怎么验证的
- 全仓 pytest **2925+5 全绿**（+3 去重锚：三次同文仍 1 条/异文共存/timestamp 刷新）；node --check 过。
- 重建 exe b32d1b92 双端 MATCH 部署 11:02 三进程全新；**生产库实证**：对现有"明日方舟"条目实跑修复版 save_memory → 打印"记忆已存在，刷新鲜活度"、2→2 零新增；PYZ 锚双验（刷新鲜活度/rowcount 在包内）。

### 回滚
- git revert 4492d53；重建回滚；state_manager.py.bak-20261030-dedup。


## 批八 — feat(#363 记忆管理面板一期+社交监控日志+Today 衍生入库)（v2.2.1 内部补丁，重建部署 10:38 三进程全新）

### 改了什么
- **Today 衍生三件入库**（_dev/add_todo_20261030_today.py，生产 todos.db 备份 .bak-20261030-today）：#363 P1 记忆管理面板/#364 P2 唤醒节奏锚点/#365 P2 连接器生态。
- **记忆管理面板一期**（对齐 Today Living Memory"可删"）：升级既有 🧰 记忆查看卡——/api/memory/list 带 id 字段；新 POST /api/memory/delete（物理删除，非法 id 400/不存在 404/成功回剩余数，零静默假成功，stdout 留痕 🗑）；前端每条记忆 trash 矢量钮（ICON_SVGS.trash，禁 Emoji）+showConfirm 确认（内容预览+不可恢复警示）+toast 反馈+即删即刷（降级形态无 id 不渲染钮）。编辑功能=二期。
- **社交串门监控日志**（今晚首跑盯梢，队长拍板）：social_visit 跳过原因全量日志化（额度满/计数异常 fail-closed/生成失败/发送失败/无可串目标）——grep 🦊 [social] 可见完整决策链。

### 怎么验证的
- 全仓 pytest **2922+5 全绿**（+5 端点锚：list 带 id/删除真删副本库/400/404/监控日志锚）；node --check+py_compile 双语法门。
- 重建 exe（c80b0980 双端 MATCH）+deploy_shutil 全量对账+插件/前端三处同步 md5 一致；生产负路径实测（list 首 id=11/delete 400/delete 404）。
- 真浏览器全链：面板 11 条全带 trash 钮截图 _dev/shot_memory_panel_20261030.png；点删→showConfirm 弹窗（标题"删除这条记忆"+内容预览+确定钮）→取消→关闭→条目不动（DOM 断言；生产真删留队长手点——4 条重复"明日方舟"正好练手）。

### 回滚
- git revert 7050268；重建回滚；todos.db.bak-20261030-today 还原待办。


## 批六 — fix(侧栏卡片排版全打平)（v2.2.1 内部补丁，生产热同步不重启）

### 改了什么
- **卡头折行根因**："系统状态"标签是卡头 flex 行里唯一无 nowrap 的可压缩项——队长拖窄（ui_pref 实锤 308）时被挤压成"系统/状态"竖排。修=标签 `white-space: nowrap; flex-shrink: 0`；**容器查询降档**（队长授权"宽度不够就缩小"）：.sidebar 设 container-type: inline-size，<360px 时标签 10px+温度 26px（特异性特意压过后方常规规则——@container 在样式表前部，同特异性会输给位置的坑当场踩到并修复）；375 默认档不触发零观感变化。
- **待办高低不平双根因**：①行 `align-items: flex-start`（时间/P0 吊顶）→ center 垂直居中；②`.todo-text` `word-break: break-all`（英文词腰斩"Dashboar/d"实锤）→ `word-break: normal; overflow-wrap: anywhere; min-width: 0` 整词换行；③`.todo-time` float:right 退役（flex 行内本被忽略+吊顶参差同根）→ flex:none+nowrap；④P0 徽标 nowrap。
- 清生产 ui_pref 残留 sidebar_width=308（备份 .bak-20261030-flatten）。

### 怎么验证的
- 全仓 pytest 2911+5 全绿；生产页双档验证：375 档（containerType=inline-size/标签温度单行/待办 center）+**模拟拖窄 308 档（降档 10px/26px 生效、单行、零横向溢出）**；待办+系统卡实拍 _dev/shot_flatten_*.png；PIL 扫接缝=hover 蓝线右缘仍精确贴 375 交界。
- APK assets 同步+重建+**解包验证**（container-type/align-items:center/overflow-wrap 在包内），9b820d81 dist 双位置。

### 回滚
- git revert 本笔；index.html.bak-20261030-flatten / ui_pref.json.bak-20261030-flatten 还原。

## 批五 — tweak(侧栏 375px+系统卡排版呼吸感)（v2.2.1 内部补丁，生产热同步不重启）

### 改了什么
- 宽度 360→375px（队长定稿黄金比例终版）；清生产 ui_pref 残留 sidebar_width=302（备份 .bak-20261030-typo375）。
- 系统卡排版四件（360px 实锤病根=GPU 温度无 nowrap 被 30px 大字挤成竖排断行）：①卡头标签降档 11px/400（辅助信息，作用域 .v0-card-head 内=系统/天气两卡一致）②GPU 温度升档 32px/700+letter-spacing+**white-space:nowrap**（禁"GPU/45°C"竖排）③运行正常 nowrap（禁"运行正/常"断行）④行距 .stat-row 12→16px+行头下距 6→8px。
- 百分比等宽数字核实：`.stat-header span:last-child` 与 1006 行 tabular-nums 组**本来就在**（逐项计算样式实测 tabular-nums），零改动。

### 怎么验证的
- 全仓 pytest 2911+5 全绿；生产页计算样式六连（375/11px·400/32px·700·nowrap·单行/16px/tabular-nums）；PIL 扫描常态接缝=灰[..374]→白[376..]交界精确 375；hover 蓝线贴线截图三件 _dev/shot_typo375_*.png。
- APK assets 同步+重建+**解包验证三处新样式在包内**（width:375px/32px·700/16px），1c2239cc dist 双位置。

### 回滚
- git revert 本笔；index.html.bak-20261030-typo375 / ui_pref.json.bak-20261030-typo375 还原。

## 批四 — tweak(侧栏默认宽 400→360 黄金比例)（v2.2.1 内部补丁，生产热同步不重启）

### 改了什么
- v0 `.sidebar` width 400px→360px（队长定稿黄金比例）；清生产 ui_pref 新残留 sidebar_width=310（队长拖宽试手感写入，备份 .bak-20261030-width360）。
- APK assets 同步步照「陈旧资产案」正解执行：www→assets/public→重建→**unzip 解包验证 width: 360px 在包内**（d1f14c16，dist 双位置）。

### 怎么验证的
- 全仓 pytest 2911+5 全绿；三点热同步 md5 一致（仓库/生产 _internal/APK assets=80c8c6c2）；APK 解包 grep 实锤。

### 回滚
- git revert c801a27；ui_pref.json.bak-20261030-width360 / index.html.bak-20261030-width360 还原。

## 批三 — tweak(侧栏默认宽 320→400)（v2.2.1 内部补丁，生产热同步部署）

### 改了什么
- v0 `.sidebar` width 320px→400px（队长拍板区间 380/400 取 400）；用户拖宽仍走 ui_pref 覆盖，双击复位=回 400。
- 清生产 ui_pref.json 旧宽度记忆 sidebar_width=325（备份 .bak-20261030-width400）——不清则桌面端永远读旧值，新默认永不生效。

### 怎么验证的
- 全仓 pytest 2911+5 全绿；生产重启后真浏览器默认宽实测 400（无测试锚依赖 320，零锚改动）。

### 回滚
- git revert 本笔；ui_pref.json.bak-20261030-width400 还原；index.html.bak-20261030-width400。

### 坑录（APK 陈旧资产案，本批自查实锤）
- **gradle 对 android_app/www/ 零感知**——Capacitor 的打包真源是 `android_app/android/app/src/main/assets/public/`（www→assets 需手动同步步，gradle 不会替你拷）。本日早些时候两次"APK 重打"（蓝线批 b2888c20）实际打包的是**今天之前**的旧 assets——82 任务全 up-to-date+md5 不变就是信号，当时被当增量放过。
- 正解=同步 www 两文件（index.html/console.js）→assets/public→重建→**unzip -p 解包验内容**（width: 400px/border 契约/divider-dragging 逐项在位，::after 零命中）。修正版 APK=09d6c2d1（3.98MB）dist 双位置。

## 批一 — fix(蓝线贴线根因根除:resizer 白底融白区+border 方案定稿)（v2.2.1 内部补丁，生产热同步部署）

### 改了什么
- **根因实锤**（真浏览器几何量测）：`#sidebar-resizer` 是 10px 透明热区夹在侧栏与右区之间，透出 body 灰底 #e5e5e5——灰白交界的物理位置在热区**右缘**（330px），而此前所有画线方案（`::after` left:50%/left:0）都把线画在热区左缘附近（320px）——**怎么调都差一个热区宽度**，这就是队长三连实锤"蓝线不贴交界"的真根因。
- **修法（队长指令：最粗暴简单）**：分界线渲染权移交 `.sidebar border-right`（2px solid transparent，hover 侧栏/悬浮热区/拖拽中染 #2563eb）——border 是 sidebar 盒最右条带，右缘物理=灰白交界，**结构性零偏移**（跟 box-sizing/拖宽都无关）。
- `#sidebar-resizer` 底色 transparent→**#ffffff**（热区整条融入白区，交界物理移到 sidebar 右缘=蓝线位置）；::after 规则物理删除；热区 10px 保持好抓。
- 清理尸体：基础 `.sidebar` 块内被 v0 覆盖的死声明 `border-right: 1px solid var(--color-border)` 删除；2026-10-27 过时注释块（负外边距/狐毛橙描述）重写为当前事实。
- console.js：拖拽起止加/摘 `.sidebar` 的 `divider-dragging` class（拖拽中蓝线常亮，上个会话已写、本批纳入提交）。
- test_sidebar_resize 锚随新契约（flex 10px/背景 #ffffff/border 方案/hover 选择器组/divider-dragging；`::after` 三锚改版+assertNotIn 禁回归）。

### 怎么验证的（真浏览器像素级铁证，烟雾服 5099+IAB）
- 几何：sidebar [0..320] 灰、resizer [320..330] **纯白**、chat [330..1280] 白——交界=320=蓝线位置。
- PIL 扫描线（y=360）：常态交界精确 x=320、零蓝像素、零第三色；hover 蓝能量 [318..320) 右缘=320=交界，左灰右白。
- 真鼠标拖宽 320→420：sidebarRight==resizerLeft==420，蓝能量 [418..420) 右缘=420=新交界——**拖到哪贴到哪**。
- 拖拽态计算样式=rgb(37,99,235) 精确 #2563eb（截图偏浅系合成层截图重采样伪影，DOM 实色精确）。
- 双击复位 320 回归。全仓 pytest **2911 passed, 5 skipped, 0 失败**。
- 截图三件：_dev/shot_seam_{normal,hover,wide_hover}_20261030.png。

### 回滚
- 代码：git revert 本笔；index.html 备份 .bak-20261030-blueline（仓库）+ 生产 .bak 同日戳。

## 批二 — feat(社交池灌好友+保命双雷修复)（v2.2.1 内部补丁，生产热部署）

### 改了什么
- **NapCat get_friend_list 实拉**：小橘（1706205831）好友 5 个——排除主人 3779888268（走专属唤醒通道带全量记忆，绝不进社交池）与 bot 自己，**3 好友入池**。生产 .env：`XIAOJU3_SOCIAL_POOL=f:3075461518,f:1598998793,f:1773609145,g:1061438268`（备份 .env.bak-20261030-socialpool）。
- **保命双雷修复（2026-10-30 实锤，灌池前必须修否则红线纸糊）**：
  ① `social_visit` 日限计数按 `meta(key,value)` 列名读写，实际表是 `meta(k,v)`——OperationalError 被 except 吞、计数永远 0，**全局日限 3 从不生效**；
  ② `social_log` 表全仓零建表语句——24h 冷却同样静默失效。
  修=`_ensure_social_tables` 幂等建表（meta+social_log）+读写统一 meta_get/meta_set（k/v）+计数读不到改 **fail-closed**（宁可不出手）。
- 主人豁免代码化：目标循环跳过 `XIAOJU3_OWNER_QQ`（防误配进池）。
- `_SOCIAL_DELAY=(3,6)` 接线：发送前拟人打字延迟 3-6s（旧版定义了从未用）。
- 新增 tests/test_waker_social.py 11 枚：池解析五形态/日限 3 真实计数+第 4 次阻断/fail-closed/主人豁免/冷却落账/隐私红线原文/场景隔离 prompt/延迟区间。

### 怎么验证的
- 全仓 pytest 2911+5 全绿（+10）；社交安全四件（日限/豁免/fail-closed/冷却）全部异常用例覆盖。
- NapCat get_friend_list retcode 0 实拉（列条目见战报）。

### 回滚
- .env：还原备份 .bak-20261030-socialpool；waker.py：.bak-20261030-socialdelay；代码 git revert 本笔。
