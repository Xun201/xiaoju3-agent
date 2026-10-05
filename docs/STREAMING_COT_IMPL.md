# 思维链真流式实施设计稿（方案 C，#244）

> 状态：**C1 实施中**（本稿为 STREAMING_COT_DESIGN.md 侦察结论的实施固化版）
> 日期：2026-10-05
> 拍板：#208 选 C（真流式）；分批 C1（纯后端）/ C2（SSE 接线+前端）/ C3（打磨）
> 关联：docs/STREAMING_COT_DESIGN.md（三方案对比）、brain.py smart_ask（原链，不动）

---

## 一、改造点清单（实测精确版）

| 位置 | 现状 | C 方案处置 |
|---|---|---|
| brain.py:1459 `ask_local` | Ollama `/api/chat`，`"stream": False` | **保留不动**（同步版供 QQ/CLI/心跳）；新增 `_ask_local_stream` 消费器 |
| brain.py:1470 `ask_cloud` | DeepSeek `/chat/completions`，`"stream": False` | **保留不动**；新增 `_ask_cloud_stream` |
| smart_ask（brain.py:1631-1890） | 首轮 → 工具环 → 汇总轮，返回最终串 | **保留不动**（QQ 链路零风险）；新增 `smart_ask_stream` 复刻回调版 |
| xiaoju3.py CLI 同构 ask_* | 终端文本通道 | 第一期不动（流式收益低） |

Ollama 流式形态：NDJSON 逐行 `{"message":{"content":"增量"},"done":false}`。
DeepSeek 流式形态：SSE `data: {"choices":[{"delta":{"content":"增量"}}]}`，`data: [DONE]` 结束。

## 二、调用链改造图

```
现状（不动）：
api_chat ──► smart_ask ──► (reply, source) ──► jsonify
                 │ 首轮 ask_local/ask_cloud → _extract_tool_json
                 │ → execute_tool（同步）→ 汇总轮 → _seal_tool_summary

新增（C1 后端，C2 接线）：
api_chat_stream ──► smart_ask_stream(msg, history, on_event)
                        │ on_event({"type":"think"|"answer","delta":str})
                        │ 工具执行前 on_event({"type":"tool","name":...})
                        ├ 复用 _capture_thinking / _extract_tool_json /
                        │       execute_tool / _seal_tool_summary /
                        │       _wrap_think / tool_fuse（全部静态/独立函数）
                        └ 返回与 smart_ask 同形的 (reply, source)
                          落盘（_compress_and_save 由调用方）/熔断计数一致
```

**为什么新写不复刻改原函数**：工具环是多步状态机，回调要穿插 130 行主链
——改原函数 = QQ 链路高风险；新函数复用全部静态件，行为可锚定对齐。

## 三、SSE 中间层选型（C2 用）

- **SSE**（`Response(generate(), mimetype="text/event-stream")`）：
  Flask 原生支持 generator response，零新依赖；localhost 直连无代理缓冲。
  事件协议：`event: think|tool|answer|done` + `data: <json 单行>`。
- WebSocket 否决（需 flask-sock，单用户 localhost 杀鸡用牛刀）。
- 前端用 fetch POST + `res.body.getReader()` 手解（EventSource 不支持
  POST）；**失败回退旧 /api/chat**（口径零回退）。

## 四、前端改造方案（C2 用）

- sendMessage 流式分支：请求 `/api/chat/stream`；首块前显示既有轮换文案
- think 渐进卡片：按 `THINK_STAGE_RE` 逐段 append（卡内已渲染行不重绘），
  tool 事件插"正在执行工具…"行；answer 增量写入正文气泡
- done 事件：走既有"等 1.5s → 折叠 → 收尾"节奏 + source 徽标
- 净化口径：增量 textContent（escapeHtml），CQ/sanitize 仍在 done 整文
- 回退：stream 请求失败/中断 → 自动转旧 /api/chat 整段重答

## 五、测试锚清单（C1 六条已实现 + C2/C3 另计）

1. 流式与同步同输出锚：mock 模型下 `smart_ask_stream` 最终 reply 与
   `smart_ask` 结构一致（<think> 包装等）
2. 事件顺序锚：think 事件先于 answer；每事件 delta 拼接 == 完整文本
3. 工具环流式锚：工具执行发 tool 事件、汇总轮 answer 事件、最终串含
   工具结果
4. 无 on_event（None）不崩（静默消费）
5. 流中断异常锚：消费器中途抛 → smart_ask_stream 向上抛（调用方回退）
6. 本地热切换云端锚：本地流式失败 → 云端流式接管、事件续传不重复

## 六、风险点

1. werkzeug 开发服务器：流式占用线程期间靠 ThreadingWSGIServer 多线程
   扛轮询——真机观测首 token 延迟与并发
2. Ollama 首 token 延迟 2-5s（观感=逐段非逐字）
3. 工具执行间隙 UX：think 卡保持展开 + tool 行提示（C2/C3 前端活）
4. 双脑热切换：流中途失败不续流——直接回退旧路整段重答（口径零回退）
5. 净化边界：增量 textContent 直注，[CQ: 原文可能闪现 1-2s（done 后校正）

## 七、分批

| 批 | 内容 | 估行 | 状态 |
|---|---|---|---|
| C1 | brain 流式消费器 + smart_ask_stream（纯后端，不接线） | ≈150-170 | **本批** |
| C2 | /api/chat/stream SSE + 前端接收/渐进卡片/回退 | ≈180-220 | 待排 |
| C3 | tool 事件 UI、断流恢复、首 token 观测 | ≈50-70 | 待排 |
