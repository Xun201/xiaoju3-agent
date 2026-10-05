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
