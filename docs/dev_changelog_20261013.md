# 开发者日志 · 2026-10-13（Phase 0 收窗 + #326 模块化 + #322 全链 + 拟人节奏 + 库大扫除 + 规则落盘）

> 承接 dev_changelog_20261011.md（10-11 全天账）+ dev_changelog_20261012.md（10-12 全天账）。

## 一、时间线总览

| 时段 | 批次 | commit | 生产车 |
|---|---|---|---|
| 凌晨 | 库大扫除（90 行四类审查：13 done + 22 backlog P4 + 优先级 8 条） | — | — |
| 早 | 坑库 #19/#20/#21 + 思维笔记体系 + AI 协作纪律 AGENTS.md 两节 | — | — |
| 上午 | #318 roadmap 四处修正 + #326 模块化 + #322 全链 + 拟人节奏 | 多笔 | — |
| 午后 | #227 评估报告 + 硬门 v1→v2 + OTS 存证 | 多笔 | — |
| 晚 | Phase 0 收窗 + 哑火修复部署 + 短窗验证 + #326 收口 + 拟人节奏收口 | 多笔 | **754977CC 现行** |

## 二、Phase 0 收窗报告

| 项 | 数据 | 判定 |
|---|---|---|
| 满窗 24h | 1287 tick 零断档 / quiet_hours 419 零误标 / fire 0（哑火期） | 抑制路径 ✅ |
| 短窗（f01e811 后） | **tension 0→0.30→0.60→fire 铁证** + event_source_error=0 | 累积路径 ✅ |
| 累计 fire | 4 次（≈30min/次，25 条 stale 真实驱动，非自激） | ✅ |
| 判定 | **Phase 0 通过**（抑制✅ + 累积✅ + 频率基线≈48 次/天） | — |

## 三、#326 思维链模块化

- **chain_of_thought.py**：VARIANTS 变体表 + normalize（冒号归一化）+ strip_pollution（全变体剥除）+ parse_thinking_field（D1 Ollama thinking 字段直读）
- **brain.py 迁移**：_normalize_think_labels 改 import；ask_local/_ask_local_stream D1 读点改调 parse_thinking_field；_seal_bare_cot 头部归一化经 import 自动生效
- **main.py 迁移**：_strip_llm_pollution 改调 strip_pollution（入口名保留防断裂）
- **坑库 #21（mock 全绿 ≠ 真链路通）**：哑火修复 +3 真集成锚堵盲区

## 四、#322 QQ 输出污染全链

- **Bug A（图片谎报收藏）**：prompts.py 第 4 条毒教材（教模型谎报"已存进小仓库"）→ 重写为诚实指令
- **Bug B（思考：/计划：冒号漏剥）**：brain `_normalize_think_labels`（六式归一化）→ `_seal_bare_cot` 头部归一化
- **F1 出口消毒**：`_strip_llm_pollution` → `chain_of_thought.strip_pollution`（五形态全剥）
- **F2 入口翻译**：`_translate_cq_for_brain`（CQ 码全类型→人类可读，图片改剥离）
- **硬门 v1→v2**：纯图确定性 → 图文+指代图词确定性 → 无关文字放行

## 五、Phase 0 哑火修复（f01e811）

- **根因**：_collect_events SQL 查 todos 表**不存在的 due_date 列**（方案稿凭空写、实施照抄未核验 schema）→ OperationalError 被裸 except 吞 → 880 分钟静默失败（tension 恒 0/零 fire）；9 mock 锚全绿掩盖
- **修复**：①事件源改查真实列（created_at 老化 >7 天判 todo_stale，生产 25 条命中）②事件源失败审计 proactive_log 记 event_source_error（#316 自我适用）③+3 真集成锚（临时真 todos.db 走真 SQL，不打 mock）
- **坑库 #21**：mock 全绿 ≠ 真链路通（测试隔离掩盖集成断链）

## 六、QQ 闲聊拟人节奏（796997a，开关制默认 OFF）

- 纯文字闲聊经每用户防抖桶（10s 静默/≥6 条/≥120s/单条>100 字）→ 生成 → 随机延迟 20-30s → ONEBOT API 异步发送（静默等待不发"正在输入"）
- 豁免即时：斜杠/分享链接/记住/CQ 媒体/route 工具意图
- `XIAOJU3_CHAT_RHYTHM_ENABLED` **缺省关**（生产默认秒回旧契约；手动开=MOOD_TONE 同款模式）
- 家电词直查按收口指令砍掉（单独排期）

## 七、库大扫除

- 90 行四类审查（A55/B13/C6/D4）→ 13 标 done、22 条 P4+[backlog] 沉底、优先级 8 条调整
- 新增待办 #311-#325（多终端/插件体系/自动更新/防漂移纪律/桌宠设置页/静默可解释/气泡回收/OTS 验证）
- 坑库 18→21 条（+#19 过拟合+茧房校准维度 / +#20 消毒通道不对齐 / +#21 测试隔离掩盖集成断链）

## 八、思维笔记体系 + AI 协作纪律

- **thinking_notes.md** 建（要做/要懂/要躲/待验证四门分立+入口纪律）
- **AGENTS.md 两节**：协作交付（强制三件/一指令一目标/异常升级门/STATE.md/验证纪律）+ 新能力启动纪律（生态侦察/学习架构/明确借鉴边界/禁闭门造车）
- **PROJECT_CONTEXT**：AI 协作分工三角色 + 注意力纪律 + 为什么记

## 九、基线与车

- 全仓：2056+4 → **2109+4**（今日 +53 锚；#303 除外全绿）
- 生产车迭代链：4098C2EF → … → **754977CC 现行**
- 待推 0；git 净
