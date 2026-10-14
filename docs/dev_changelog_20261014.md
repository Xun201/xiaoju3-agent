# 开发者日志 · 2026-10-14（日期快照式，按提交逐条）

> 本文件起始于「会话收官纪律」固化当日（e7534de）；此前各笔补记如实在案。

## 一、b295cf2 测试隔离修复（凌晨 01:3x，已推）

- HistoryApiTestsBase 补 RECENT_ACTIONS_FILE 隔离——dev agent_state/recent_actions 被当晚 pytest 内真跑的 HA 心跳污染（测试进程起真心跳线程触发 HA 测试灯开灯×3→写 dev recent_actions），ChatApiTests 的 smart_ask 注入 block 混入设备操作记录断言全挂（凌晨实锤 4 个）
- 基类统一注入 tmp 空文件（OnebotWebhookMigratedBase 先例对齐）；#302/#303 同族：测试真跑外部副作用

## 二、909cd74 设置页打不开根因修复+幂等重建部署（凌晨 01:5x，已推）

- 根因（真浏览器实锤）：tab 退役批删 tabConsoleBtn/tabTerminalBtn 常量定义，CHAT_TABS console/terminal 条目 btn 闭包仍引用→switchChatTab 的 d.btn() 遍历抛 ReferenceError 中断→一切页签切换全断（#14 删引用不删绑定同族）
- 修复：两 btn 闭包改 null+小工具面板段移入 IIFE+toggleToolBody 首点折叠 bug+API 空库首查建表；真浏览器四项验证过（齿轮/设置卡/记忆查看/零 JS 错误）
- 重建产物与 01:02 车哈希相同（C70B22BC 可复现构建）=幂等重建部署确认
- +3 锚 全仓 2204→2208+4；教训候选：锚静态存在性查不出运行时 ReferenceError（真浏览器冒烟=前端运行时唯一可靠验证层）

## 三、309bc95 关系化人格演化批 1（晨，本地未推）

- 三阶段会话（用户不在，纯代码零部署零真机）：侦察→设计稿 v2→批 1 存储
- 设计稿 v2 落盘：_dev/design_271_personality_evolution_v2.md（判定五规则表/rel_mode 表+persona_pref.json/后缀链模式段/分 4 批/D1-D5 决策点待拍板）
- 批 1=存储层：relationship.db 增 rel_mode 表（幂等建表）+relationship 公共 db_path()/event_stats()（逐用户事件统计=批 2 判定输入）+新模块 personality.py（get_mode/set_mode_manual 手动锁/clear_mode_manual+persona_pref.json 6 开关 tri-state auto/on/off+XIAOJU3_PERSONA_ENABLED 表现层缺省关）
- 零行为变化（无调用方消费）；+14 锚 全仓 2214→2228+4（#303 既有失败除外全绿）；备份 relationship.py.bak-20261014-persona 在案
- 顺修：STATE.md 三段重复+过时残行去重重写（多终端后写覆盖残迹，.bak-20261014-persona 在案）

## 四、e7534de 会话收官纪律固化（本批，本地未推）

- AGENTS.md 新增「会话收官纪律」节：换会话/换对话框前必写开发者日志（交接靠文档不靠记忆）；BOOT.md 基础规矩加第 9 条（info/exclude 不随 commit）
- Hindsight retain 落库验证（bank 59→60，条目 edd186d7 text 实抓）；纯文档零代码

## 五、本笔 changelog 自身（同批收尾）

- dev_changelog_20261014.md 建（补记今日五笔）；基线 2228+4；待推 3（309bc95 人格批1+e7534de 纪律+本笔）
