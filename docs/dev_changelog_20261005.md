# 小橘3号 开发变更记录 · 2026-10-05

> 本文为 2026-10-05 当日提交的事实清单，格式对齐 dev_changelog_20261002.md。
> 数据来源：`git log --since="2026-10-05 00:00"`（main 分支）。时间均为 git 实际提交时间。

---

## 深夜（00:37 – 01:31，提交 53b10a9 之后至 d7a7020，9 个提交）

> 本日主线：v1.0.3 发布两轮收官（升版本/构建/双部署/冒烟/push/tag/release，
> 提交 78e334f）→ help 菜单双修（57eb0a0）→ 待办独立拆库（15c0a2b）→
> 控制台斜杠接线 C'（22d9980）→ 填表指引（687587a）→ 流式 C1/C2
> （49c763d/178e0a7）→ C3a 拦截修复（b0f32db）。以下收录 C3a 一笔的
> 完整记录（本日志为该批次收官归档，本篇写作时点状态：b0f32db 未 push，
> origin/main = 178e0a7，本地领先 1 笔）。

### （时间以 git 实际为准）`b0f32db` fix(stream): stream 端点复用指令拦截（修 C' 在流式通道失效的回归）
- **文件**：2 个文件，+59/-7（xiaoju3_dashboard.py、tests/test_chat_stream.py）
- **内容**：`/api/chat/stream` generator 起始处（调 smart_ask_stream 之前）先过 `_console_slash_intercept`（与 api_chat 同款）——命中 → 不流式，直接发单帧 `done` 事件（reply+source 已净化）+ return，前端照常渲染；拦截函数补 `/help|菜单|帮助|指令` 四别名（api_chat 原独立 /help 块先执行仍原样，不冲突）。测试：C2 时期"现状锚"（/help 进模型）反转 + 新增 3 锚（/help 单帧 done 菜单且不进模型、/lv4_auth 权限警告、普通消息逐块流式回归）。
- **动机**：C2 上线后流式通道直连 brain，从未接指令拦截——/help、/register、/lv4_auth 等斜杠指令在流式通道进模型产生 LLM 幻觉，C' 接线成果失效。侦察发现双层叠加：① stream 端点零拦截调用（grep 实锤）；② `_console_slash_intercept` 缺 /help（C' 时由 api_chat 独立块承接，流式端点没有该块）。
- **设计决策**：方案 A——指令命中不流式、一次性 done 收口（指令不是流式内容）。
- **关联提交**：49c763d（C1 后端流式）、178e0a7（C2 SSE 接线，引入本回归的载体）、22d9980（C' 第一批）。

---

## 本日提交全景（补充索引，事实以 git log 为准）

| 提交 | 主题 |
|---|---|
| 78e334f | chore(version): 1.0.2 → 1.0.3 |
| 687587a | docs: 软著整机登记填表指引 |
| 49c763d | feat(stream): C1 后端流式消费器 + smart_ask_stream（纯后端） |
| 178e0a7 | feat(stream): C2 SSE 路由 + 前端流式接收 + 渐进卡片 |
| b0f32db | fix(stream): stream 端点复用指令拦截（C' 流式通道回归修复） |

---

## 下午（a67d59b 之后至 8dedb0d，2 个提交 + C3c 观测）

> 本时段主线：待办脏数据修复（a67d59b）→ push 老规矩固化（a12b262）→
> C3b 前端断流打磨（8dedb0d）→ C3c 首 token 观测（#244 关账数据）。
> 顺带：_dev/PROJECT_CONTEXT.md 接续上下文固化（不进 git）。

### `8dedb0d` fix(stream): C3b 前端断流打磨——救活半途断流回退 + 流式渲染层作用域修复
- **文件**：2 个，+75/−12（console.js、tests/test_chat_stream.py）
- **重大发现（C2 遗留）**：sendMessageStream/sendMessageLegacy 均为顶层函数，裸 `history` 解析到 window.history 内置对象（无 appendChild/contains）——流式渐进卡第一行 DOM 操作即 TypeError，**"实时卡"自 C2 起从未渲染过**（MutationObserver 现行实锤）；legacy .then/.catch 全链 DOM 操作炸，回退回复不显示，靠 appendBotMessage 自取元素+历史轮询兜底掩盖。修复=两函数开头自取 chat-history。
- **内容**：①pump().catch 闭包级清 thinkCard/toolEl/answerEl 再 rethrow（半途断流残件清理）②legacy loadingMsg contains 防御（流式回退时已被过程卡消费，裸 removeChild 会 DOMException）③think 渐进 append 模式（完整行 append+末行整刷，收 textContent 整刷 TODO）④tool 事件无卡也建卡⑤锚 +2。
- **验证**：全仓 1839 passed+4 skipped；dev 假流注入四项全过（残件清理/legacy 重答真渲染/零红字零 UNHANDLED/末行随 chunk）；真流式首验 liveCardSeen=true（C2 以来首次）。
- **动机**：C3 原定义"断流恢复"——半途断流三重坏（残件残留+removeChild DOMException+红字不重答），真机假流模拟暴露渲染层作用域断裂是其底座。

### C3c 首 token 观测（2026-10-05 下午，#244 关账数据，_dev/observe_first_token.py 直连流式端点掐表）

本地（Ollama，热模型）×3：

| 轮 | 消息 | 首事件 | done | 事件分布 |
|---|---|---|---|---|
| local-1 | 用一句话介绍你自己 | **0.73s** | 1.31s | think×23+done |
| local-2 | 数到三 | **0.10s** | 0.38s | think×11+done |
| local-3 | 今天星期几（试探） | **0.09s** | 0.40s | think×12+done |

云端（DeepSeek，假链接强制云端，受理即回——链接提取为后台 job 不阻塞流）×3：

| 轮 | 首事件 | done | 事件分布 |
|---|---|---|---|
| cloud-1（zcodeprobe07） | **0.36s** | 0.91s | answer×76+done |
| cloud-2（zcodeprobe08） | **0.83s** | 1.50s | answer×123+done |
| cloud-3（zcodeprobe09） | **0.92s** | 1.71s | answer×146+done |

ThreadingWSGI 并发实证：local-2 流式进行中并发 GET /api/status ×3 = **0.505s / 0.505s / 0.505s**（恒定，与平时无差，流式占线程不阻塞轮询）。

结论：设计稿风险预估"Ollama 首 token 2-5s"为**冷启动**保守值，热模型实测 0.1-0.7s（逐段观感优于预期）；云端受理即回亚秒级；werkzeug 并发无忧。cloud 轮无 think 帧为预期（deepseek-chat 非 reasoning 模型，C1 消费器按 <think> 标签分流，无标签全走 answer）。

---

## 傍晚（0910ecf 之后，2 个提交）

> 本时段主线：v1.0.4 发布车两段收官（7c22aa6 版本号+构建+双部署+双版冒烟+
> tag+Release，资产 sha256 双端核验）→ 比赛线情报入档（#213 AIC 官方截止
> 10-15 20:00/赛道拍板赛题2；#214 CACC 评估后放弃留档）→ #238 待办单条删除。
> 顺带：正式版两次"自己退出"定位=ZCode 后台任务空闲回收连带杀树，根治配方
> =schtasks 计划任务拉起（进程归系统服务，脱离回收），已入记忆档。

### `3aaa955` feat(todos): #238 单条删除——垃圾桶(仅已完成项)+confirm 二次确认+DELETE 硬删
- **文件**：6 个，+91/−1（agent_state/state_manager.py、xiaoju3_dashboard.py、console.js、index.html、tests/test_state_manager.py、tests/test_dashboard.py）
- **内容**：①state_manager 新增 `delete_todo`（通用单条硬删，后端不限 status=方案 A 拍板——#238 原文"删不掉单条"的完整解法；连接写法对齐 clear_todos）②dashboard 新增 `DELETE /api/todos/<int:todo_id>`（HTTP 方法与写系 POST 区分；404/200 code 口径对齐 done/reopen；安全口径同 api_todo_done）③console.js 垃圾桶仅对已完成项渲染（pending 无入口，拍板①）+click 委托第四分支 window.confirm 二次确认（拍板②）→DELETE 硬删（拍板③）→loadTodos④index.html `.todo-del` 红色系样式⑤锚 +3（state 单删/路由 404 链/前端静态锚含分支在 click 委托体内防 v12 式回流）。
- **测试**：1839→1842 全绿 skipped=4（只增不减）。
- **真机（dev 实例五发全过）**：done 项垃圾桶渲染 ✓/pending 无入口（对照行 delOnPending=0）✓/confirm 取消路径（dismiss 行还在）✓/确认路径（accept 行消失）✓/reload 持久=真删库 ✓；收尾用新 DELETE 端点实战清理测试行（200）。
- **附注**：dev 仓 .env 无 XIAOJU3_TODOS_DB_PATH → dev 实例回退本地库（long_term.db），真机验证全程用 dev 本地库插删测试行，生产共享 todos.db 零触碰；console.js+dashboard 均进 onefile 包，**部署随下一批重建**（不单独发车）。
- **动机**：#238"现在只能标记完成或全清，删不掉单条"；用户三拍板（仅已完成显示/confirm/硬删）+方案 A（后端通用删除）。
- **关联提交**：a67d59c（同面板脏数据防御）、15c0a2b（拆库，todos_db 路径）。

### `0910ecf` docs: C3b 归档 + C3c 首 token 观测数据（#244 关账）
- docs/dev_changelog_20261005.md 追加 C3b 条目与 C3c 观测数据节（见上文）；#244 同日打 done。

## 夜间（2117cee 之后：半成品接线车 + 部署车）

> 本时段主线：H1/H2 半成品接线（68eec4e/0ad013c）+ 侦察翻案文档批（2117cee）
> 三笔推送 → 控制台意图路由接线（ba2e06e，#247）→ 下一车部署+真机验收。

### `68eec4e` feat(home): 温度设定暴露给模型（H1）
- tool_registry params 补 set_temperature/temperature + prompts 示例行与【工具适用边界】边界规则（本地小模型曾把"调空调"误路由到 ui_tap_element 点手机屏）+ 快照锚 _LEGACY_PROMPT_BLOCK 第 5 行同步；+2 锚（registry/prompts 参数可见性）。
- 真模型验证：本地两轮工具环精确输出 climate.demo_ac + set_temperature + 26；云端行为正确（先取设备列表）。假欠账消除：功能文档 §8.4"温度设定尚未实现"实为已实现未暴露。

### `0ad013c` fix(ebook): 导出意图改挂 export_ebook_reply（H2）
- 真机抓到 bug：dispatch 直透 export_from_history 的 list[dict]，用户收到裸 Python repr。新增 export_ebook_reply 封装（历史→EPUB→"📚 已生成+章数+路径"，空历史转中文提示），意图表改挂；+3 锚。

### `2117cee` docs: 半成品侦察翻案批
- 架构文档 §5 三处"未接线"（前情提要/长期记忆/save_identity）核实实为已接线改"已接线（2026-10-05 核实）"；qq_send_image 标 P2 归档候选、dev_logger 标已归档；功能文档记账/电子书翻绿、安装器 🟡→🟢、§2.3 改已接入；DEMO_PACK soul ②口径刷新（控制台已接，HTTP API 未实现）。

### `ba2e06e` feat(console): 控制台意图路由直达（#247）
- **文件**：3 个，+147/−18（main.py 抽 handle_intent_command 三通道共用——route→ebook 历史注入〔非 system 截 50 条〕→dispatch→❌ 透传；_brain_reply 改调它，QQ/web 行为零变化 / xiaoju3_dashboard.py api_chat+stream 双挂拦截 + 两通道 _inject_recent_actions 补齐指代消解 / tests/test_dashboard.py +5 锚）。
- **闭包坑**：generate() 内赋值 history 须 `nonlocal`（RHS 读到未绑定名，流式锚当场抓住）。
- **真机（dev :5005 三发全过）**：记账直达 ⚙️ 指令不落 LLM ✓ / 电子书直达 EPUB 落盘 ✓ / 普通消息流式 31 帧 think+done（🏠 本地）✓。
- **部署（下一车）**：重建 exe 94,206,090B（20:44，含 ba2e06e+H1/H2）→ 双目录 cp（正式/测试）→ schtasks 拉起 health 200 + 4 进程 ✓。
- **部署后复验**：H2 QQ 事件→"📚 电子书已生成"+EPUB 落盘 1929B ✓；#247 控制台 /api/chat 记账直达（⚙️ 指令 + 正式版账本 -30 元落盘）✓ → **#247 done**（待办库 pending 29→28）。
- **挂起**：H9 三拍演练三次半途断链（Pi relay 闪断：复探 200 数分钟内即断）——演练脚本已备（$TEMP/h9_three_beats.py，每步探活自愈），链路稳定后一键重跑；灯/开关或停中间态，恢复后先归位再演练。
- **附注**：Pi 链路抖动坐实 HA 迁移动机（方案 B：本机 Docker 跑 HA——侦察已出稿：Docker/WSL2 本机均未装，Pi 22/8123 端口瞬时可通但 SSH 无免密凭证，设计稿待拍板）。

## 深夜（5298cf5：#248/#249/方向③ 控灯链路车）

> 本时段主线：控灯误路由三连修（#248 A+C → #249 B 案 → 方向③ 强制云端）
> + 正式版 HA 凭证空值实锤补齐 + H9/H1 真机双 PASS + PDF 干净版收口。

### `00f1fcc` fix(prompts): #248 控灯误路由 A+C 修复
- 【家电控制铁律】独立段（触发词清单→必走 control_ha_device→正例）+ registry 双向描述
  （control_ha_device 带触发词"必用此工具"；ui_tap/vision 标"仅限手机，家电控制禁止"）
  +【静默回退铁律】只增一句纠偏通道（家电误路由改道，不得中止文案收场）；+3 锚。
- 根因诊断：静默回退铁律（为真实手机点击链设计）把误路由后的纠偏通道锁死——
  误路由×铁律=必死，两发实测精确死在"❌ 视觉模型未连通"固定文案上。

### `328f781` feat(brain): #249 B 案家电上下文注入
- _inject_home_context：家电词命中首轮预喂【当前设备列表】（延迟导入 home_tools、
  1500 字符截断、静默降级），smart_ask/stream 双链挂载；+4 锚。
- 动机：本地小模型"查列表→控制"两跳工具环第二跳弃任务（两发复现）。

### `5298cf5` feat(brain): 方向③家电词强制云端
- 本地小模型工具遵循根本不可靠（四死法全实测：误路由点击/两跳弃任务/幻觉执行谎称
  "操作已完成"/纯闲聊无视请求）——仿 todo_link_mode 同构，smart_ask 插 elif home_cloud
  分支、stream 条件行同挂 home_cloud；+2 锚。云端全场景正确（温度两跳/关灯逻辑/铁律遵循）。

### 真机（三合一 ALL PASS，部署 exe 94,207,823B @22:39）
- **控灯两发**：☁️ 云端 (工具) 路由 + 灯真实翻转 on→off ×2。
- **H1 端到端**："把演示空调调到26度"→ 云端单跳直出 control_ha_device set_temperature
  （回复原话"设备ID已从列表中确认"——B 案+方向③协同）→ climate.yan_shi_kong_diao
  temperature 7→26.0 持久生效（演示空调=用户 File Editor 方式新造 generic_thermostat；
  state 停 off 系 target_sensor 挂时间戳实体不联动 heater，temp 达标即验收主指标）。
- **非家电不受影响**："今天天气不错"仍 🏠 本地。
- **H9 三拍 PASS**（此前挂三车后落地）：开关→检测器 off→on 联动 → 心跳 70s → 规则①命中
  （日志"📋 场景规则命中 1 条动作（本地规则，0 token）"+"⚡ turn_on 成功"）→ 灯自动开。

### 附带实锤与修正
- **正式版 .env HA_URL/HA_TOKEN 空值**：安装模板从未填过——正式版 HA/心跳此前一直
  "未配置"静默跳过；已从 dev 隔离区补齐（tokens 不进 git）。此前所有 HA 真机验证
  实际走的是 dev 实例+dev 隔离区凭证。
- #247 控制台意图路由 done（ba2e06e 三通道共用 handle_intent_command）；#248/#249 done。
- 技术方案 PDF 干净版收口（6be88c8）：MD 源稿本已无"秋季"污染段，工作树 docx/pdf
  经 python-docx 读回验证零残留 + 首页渲染抽验 PASS，入账。
- .gitignore 逐文件忽略 _dev/PROJECT_CONTEXT.md 与 _dev/ENVIRONMENT.md（环境事实档案新建）。
