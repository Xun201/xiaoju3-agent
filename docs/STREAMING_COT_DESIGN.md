# 思维链实时流式设计稿（像 DeepSeek：思考中实时展开，逐字增长）

> 状态：**设计稿，待评审**（本轮零代码改动；涉及架构改动，拍板后实施）
> 日期：2026-10-04
> 诉求：现在思考中只有轮换文案的转圈卡片、回复一次性到达后思维链才整卡刷出
> （渲染完 1.5s → 折叠）；想要 DeepSeek 式"思考中就能看到内容实时增长"
> 侦察基线：全部结论出自当前 HEAD 实码（含行号），模型端能力为公开接口行为
> 关联：docs/ARCHITECTURE_BOUNDARY.md（§1.1 缝 B 模型工具协议）、test_dashboard
> ThinkProgressiveAnchorTests（既有渐进渲染锚）

---

## 一、现状侦察：全链四处显式非流式（实锤）

| 环节 | 位置 | 现状 |
|---|---|---|
| 本地模型调用 | brain.py:1459（ask_local → Ollama `/api/chat`） | payload 显式 `"stream": False`，requests.post 一次性取整回复 |
| 云端模型调用 | brain.py:1470（ask_cloud → `api.deepseek.com/chat/completions`） | payload 显式 `"stream": False`，一次性 `.json()` |
| 控制台通道 | xiaoju3_dashboard.py:737-800（`POST /api/chat`） | 普通路由，阻塞至 smart_ask 完成，`jsonify` 一次性返回 `{reply, source}` |
| 前端接收 | console.js:1144（sendMessage） | 裸 `fetch` → `res.json()`；等待期 = "🧠 正在思考" + 900ms 轮换文案（THINKING_STATUS），无 EventSource / getReader / SSE 任何流式件 |

**思维链为何"完成后才整卡刷出"**：think 卡片渲染管线（console.js:700-900）
吃的是 `appendBotMessage(res.data.reply)` 里的**完整回复**——`splitThinkBlock`
拆段 → 徽章分色一次性渲染所有行 → 等 1.5s → 动画折叠 300ms → 放行正文。
既有"打字机"（THINK_TYPE_MS=15）是**完成文本的事后动画**（且仅在无阶段
标记时降级启用），不是网络层流式。

**smart_ask 的多轮结构（流式必须适配的形状）**：首轮=推理轮（产出
[思考]/[计划]/[行动]，brain.py:1631 起）→ 命中工具则**暂停**执行工具 →
汇总轮产出最终回答（两轮思考合并一张卡片，`_seal_tool_summary` 封口）。
即一次 /api/chat 里可能有 **2 段模型生成 + 1 段工具执行间隙**。

## 二、模型端能力：两端都原生支持，现网只是显式关着

| 端点 | 流式协议 | 改动 |
|---|---|---|
| Ollama `/api/chat`（LOCAL_URL，xiaoju3.py:171） | `"stream": true`（且本就是**缺省值**）→ NDJSON 逐行 `{"message":{"content":"增量"}}` | 改参数 + `iter_lines` 消费 |
| DeepSeek `/chat/completions`（CLOUD_URL，xiaoju3.py:178，deepseek-chat） | OpenAI 兼容 SSE：`stream: true` → `data: {...choices[0].delta.content}` 行 | 改参数 + `stream=True, iter_lines` 消费 |

结论：**模型层零障碍**——不是"能不能"问题，是"要不要把三段链路接通"问题。

## 三、真流式方案（推荐）：三段改造

```
console.js                    dashboard                      brain
┌─────────────┐   SSE    ┌──────────────────┐  回调  ┌──────────────────┐
│ fetch POST   │◄────────│ /api/chat/stream  │◄──────│ smart_ask_stream  │
│ + ReadableS  │  事件流  │ (generator, SSE)  │ 增量   │ (stream=True 调用)│
│ 渐进渲染卡片  │         │ 保留 /api/chat 兼容 │       │ Ollama NDJSON /   │
└─────────────┘          └──────────────────┘       │ DeepSeek SSE      │
                                                     └──────────────────┘
事件协议（text/event-stream，每事件一行 JSON）：
  event: think   data: {"delta": "[思考] 我先看看…"}     ← 首轮逐字
  event: tool    data: {"name": "web_search", "query": …} ← 工具执行间隙
  event: answer  data: {"delta": "主人，今天…"}           ← 汇总轮逐字
  event: done    data: {"reply": 全文, "source": "🏠 本地"} ← 收口（历史/落盘口径）
```

1. **brain 层**（新函数，老 smart_ask 一字不动）：`smart_ask_stream(message,
   history, on_event)`——首轮/汇总轮以 stream=True 调模型（ask_local_stream /
   ask_cloud_stream 两个新消费器），按行增量回调 `think`/`answer` 事件；
   工具执行处发 `tool` 事件；结束时返回与现版同形的 `(reply, source)` 并照旧
   落盘历史/熔断计数（**服务端落盘口径不变**，流式只是把"生成过程"多吐一份）。
2. **通道层**：新增 `POST /api/chat/stream`——前置拦截（位置/儿童锁/指令族）
   命中则发一条 done 事件原路收口；真对话则把 brain 回调包成 generator，
   `Response(generate(), mimetype="text/event-stream")`（Flask 原生支持，
   localhost 直连无代理缓冲问题）。**/api/chat 原样保留**：QQ 通道（onebot
   无法流式）、刷新重试、历史回放、TTS 全走旧路，零风险并存。
3. **前端层**（工作量最大头）：sendMessage 增加流式分支——fetch POST +
   `res.body.getReader()` 手解 SSE（EventSource 不支持 POST）；首个 think
   增量到达即建 think 卡（替代轮换文案），按既有 `THINK_STAGE_RE` 分段管线
   **逐段追加**；tool 事件在卡片内插"正在执行工具…"行；answer 增量逐步写入
   正文气泡；done 事件后走既有"等 1.5s → 折叠 → 收尾"节奏与 source 徽标。
   流式失败/异常 → 自动回退旧的一次性 /api/chat 路径（口径零回退原则）。

**工作量估算**：brain 流式变体 ≈100-130 行（两个消费器 + 回调包装）、
dashboard SSE 路由 ≈60-80 行、console.js 流式分支 + 渐进卡片 ≈150-200 行、
测试锚 ≈12-18 条（协议行格式/回退路径/既有 ThinkProgressive 锚保持）。
合计 ≈350-450 行，一个专注批次（半天级）可收，**中等风险**——动的是全项目
磨得最久的 CoT 渲染管线，靠"旧路全保留 + 新路失败回退旧路"兜底。

**必须直面的四个复杂点**：
① 多轮间隙——工具执行秒级到分钟级，think 卡需在间隙保持展开并显示 tool 行
  （这正是 DeepSeek 观感的关键，也是前端状态机最繁的一段）；
② 净化口径——增量阶段走 textContent 注入（与现管线同口径、免 XSS），CQ 码
  表情、sanitize_for_web 仍在 done 后整文走既有链，不逐字净化；
③ 存量锚——ThinkProgressiveAnchorTests（打字机渐进/完成折叠/手动重开/历史
  回放折叠四锚）锁的是"完成后"的渲染节奏，流式分支不得绕开 appendBotMessage
  单渲染管线（锚已在测试里写死）；
④ 部署耦合——前端内嵌 _MEIPASS，改 console.js 必须重建部署（既有已知约束）。

## 四、退而求其次方案对比（若评审不立真流式）

| 方案 | 内容 | 工作量 | 观感 |
|---|---|---|---|
| A. 完成后自动展开 | 回复到达后 think 卡默认**展开态**停留 N 秒（替代 1.5s 即折叠），再折叠；纯前端常量级改动 | ≈20 行，半小时 | 内容可见但仍"整卡刷出"，非实时 |
| B. 阶段进度轮询 | smart_ask 把阶段（推理中/执行工具 xx/总结中）写 agent_state，前端等待期轮询 /api/chat/status 显示在转圈文案位置 | ≈50-70 行，2 小时级 | 知道"卡在哪一步"，但无逐字内容 |
| C. 真流式（§三） | DeepSeek 式逐字 | ≈350-450 行 | 目标观感本尊 |

方案 A/B 与 C 不互斥：可先 A（立竿见影）或 B（阶段感），C 作为独立批次立项。

## 五、结论

1. **能做真流式**：模型两端原生支持且现网只是显式 `"stream": False`（brain.py
   :1459/:1470）；瓶颈在 Flask 通道与前端渲染，均为可落地改造，无新技术依赖。
2. **必须动架构**（新增 SSE 通道 + brain 流式变体 + 前端流式分支），按约定
   先评审后动码；QQ 通道与既有 /api/chat 全保留，风险被"并存 + 回退"兜住。
3. 若只要 80% 观感的 20% 成本：先做方案 A（≈20 行）解"整卡刷出"突兀感，
   真流式 C 单独排期。

## 六、待拍板

1. 立项哪档：C 真流式（推荐，一次到位）/ 先 A 后 C / 只做 A 或 B；
2. 若立 C：SSE 事件协议（§三表）是否认可；tool 事件在卡内的文案口径；
3. 若立 C：实施批次安排（建议独立批次，不与智能家居/发版混车）。
