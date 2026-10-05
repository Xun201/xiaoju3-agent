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
