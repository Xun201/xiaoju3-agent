# 小橘3号（xiaoju3-agent）· 四大创新点演示包

| 项 | 内容 |
| --- | --- |
| 项目 | 小橘3号（xiaoju3-agent）——住在家用设备里的私人 AI 管家 |
| 文档名 | 四大创新点演示包（DEMO_PACK） |
| 编制日期 | 2026-10-03 |
| 仓库 | https://github.com/Xun201/xiaoju3-agent（main） |
| 基线 | c1fb69d（1482 项离线测试全绿） |
| 用途 | 演示/评审四大创新点的"是什么 → 代码在哪 → 怎么验证"一页通；`[SCREENSHOT: …]` 为截图占位，补图后即为完整演示稿 |

状态标记沿用三份主文档口径：🟢 已实现（代码可核对）｜🟡 模块已就绪·接线中｜🔜 规划中。

## 总览

| # | 创新点 | 一句话 | 状态 |
| --- | --- | --- | --- |
| 1 | 物理安全底线 + 软件四级权限 | 物理开关绝对优先于一切软件等级（含 Lv.4），软件侧再叠四级门禁 + 儿童锁人在环路 | 🟢 |
| 2 | 设备自动迁移 / 灵魂备份 | 一个 zip 带走"自己是谁、记得什么"，新设备解包即活；多设备互相守望 | 🟡（migration.py 已就绪，一键指令 10-04 接线） |
| 3 | 本地优先双脑 + 完整设备接管链 | 本地模型优先、云端兜底；同一具身体控手机、控家电、控文件 | 🟢 |
| 4 | QQ 家庭入口 + 桌宠人格 | 全家人用现成的 QQ 就能召唤它；桌面狐狸娘是它的"脸" | 🟢（桌宠 JS 完整、页面暂载加速球，10-07 完整形态回归） |

---

## 创新点 1：物理安全底线 + 软件四级权限 🟢

### 是什么

两件事拧成一条安全链：

1. **物理安全底线（凌驾一切）**：功能文档 §8.0 把它列为最高优先级——"所有危险设备必须保留独立的物理机械开关。本项目的软件智能控制仅作为辅助，物理开关的优先级绝对高于任何软件权限等级。"无论软件处于哪个等级（包括 Lv.4 主人级），物理开关都能直接切断危险设备；软件失效、被绕过或误动作时，它是最后保障。
2. **软件四级权限（Lv.1→Lv.4 递进继承）**：架构文档 §6（2026-10-02 重构定稿）——Lv.1 路人（聊天/搜索）→ Lv.2 普通用户（写文件/列目录，`/register` 密码）→ Lv.3 代码编写者（改代码 + 安全家居六类 domain，`/coder_auth` TOTP）→ Lv.4 主人级（危险设备 lock/valve/阀 + ADB 全套 + 发图 + 重启自身 + 装卸组件 + 核心记忆，`/lv4_auth confirm` 授权级验证）。高级自动包含低级全部能力。

再往上的 insurance 是**儿童锁（批次②）**：`CHILD_LOCK_ENABLED=true` 时，被登记为儿童的用户触发**危险家电**（门锁/燃气阀等）控制 → 工具不执行，挂起请求并向"在线成人 Lv.4"（最近 5 分钟内交互过且等级 ≥4）QQ 私聊推送 🔒 请求，成人回 `/approve`（以主人级权限代为执行）或 `/deny`；5 分钟超时或无在线成人 → 直接拒绝。网页控制台视为成人设备。成人标记按 user_id 存 `agent_state/identity.json` 的 `is_adults` 映射，缺省成人（绝不因旧数据把人锁在外面）。

### 代码位置

| 证据 | 位置 |
| --- | --- |
| 能力→最低等级矩阵 `ACTION_LEVELS`（14 个能力键，含注释"物理开关绝对优先"的体系落位） | `permission.py:67-82` |
| 继承语义判定 `has_permission`（level ≥ 门槛即过） | `permission.py:202-207` |
| 三档工具门禁清单 `_LV2_TOOLS` / `_LV3_TOOLS` / `_LV4_TOOLS` | `tools.py:78-84` |
| `execute_tool` 前置门禁（Lv.2/Lv.3/Lv.4 逐一拦截，拒绝文案附升级引导） | `tools.py:284-303` |
| 危险实体判定与 domain 自动路由（lock.*/gas/valve/阀 + `DANGER_ENTITIES` 白名单 → Lv.4；六类安全 domain → Lv.3） | `home_tools.py` `is_dangerous_entity()`；`tools.py` `control_ha_device` 分支 |
| 儿童锁总开关（env） | `xiaoju3.py:145` `CHILD_LOCK_ENABLED` |
| 儿童锁流程：在线成人判定 / QQ 私聊通知 / 挂起-裁决包装器 | `main.py:183-258`（`_is_online_adult_lv4` / `_notify_online_adults` / `_smart_ask_with_child_lock`） |
| 文档锚点 | 功能文档 §8.0（功能文档.md:131-135）；架构设计文档 §6（架构设计文档.md:193-215） |

### 可验证证据

- **离线可复跑**：`tests/test_permission.py`、`tests/test_tools.py`、`tests/test_home_tools.py` 全绿（全仓 1482 测试内）。
- **现场演示脚本**（QQ 端三连）：
  1. Lv.1 账号说"把工作区里写个 test.txt" → 工具门禁拒绝并引导 `/register`；
  2. `/coder_auth <动态密码>` 升 Lv.3 → 控"客厅灯"成功；说"开车库门"（危险实体）→ Lv.4 拒绝文案；
  3. 开 `CHILD_LOCK_ENABLED=true` + 子账号登记 `is_adult=false` → 子账号让"开燃气阀" → 成人 QQ 私聊收到 🔒 请求 → 回 `/approve` 才执行（或 `/deny`/超时拒绝）。
- **物理底线当场证伪法**：任意 Lv.4 状态下，直接按下家电的物理开关——永远有效。软件等级再高也"夺不走"这道控制权，这就是 §8.0 的可演示形态。

### 为什么业内无第二家把"物理开关绝对优先"写进权限体系

- **主流竞品的权限是"账号-云端"模型**：小爱/天猫精灵/小度/HomeKit/Siri 的家庭权限解决的是"谁能对音箱说话"，安全兜底靠云端风控与免责条款；物理开关在它们的体系里是"用户自己注意事项"，不是权限矩阵之上的**不可变约束**。
- **小橘3号把它写成了体系的第一公理**：文档层面 §8.0 列为最高优先级；代码层面危险实体自动路由到最高门禁（Lv.4）、儿童锁再叠一层"人在环路"裁决——软件四级再高，自认"上限"，物理层永远在它之上。这是把"家中最后一道控制权永远属于人"产品化为可执行规则。
- **它是家庭场景的信任基础**：老人不会用 App、停电断网软件全瞎、AI 误触发——三种场景下家庭成员都还有 100% 确定性的手段。评审者可用"当场证伪法"验证，这是竞品给不出的演示。

> 📷 截图占位 [SCREENSHOT: 儿童锁三连——子账号请求开燃气阀的 QQ 对话 + 成人私聊收到"🔒 儿童操作请求" + 回复 /approve 后执行结果]

---

## 创新点 2：设备自动迁移 / 灵魂备份 🟡（模块已就绪，10-04 接线一键指令）

### 当前状态

- **代码已落仓库**：`migration.py`（设备自动迁移 + 多设备互相守望模块）——
  - `export_bundle(path=None)`：把"自己是谁、记得什么、喜欢什么、设置成什么样"打包为单一 zip（`xiaoju3_soul_*.zip`）；密钥**不进包**，包内 `MANIFEST.txt` 只列应手工迁移的配置键名（不含值）；
  - `import_bundle(zip_path, overwrite=False)`：解包恢复到 `agent_state/`；冲突默认跳过；成员路径防穿越（绝对路径 / `..` 一律拒绝）；
  - `PeerWatch`：对端列表 env `XIAOJU3_PEERS`（逗号分隔 http://host:port），逐个 GET `/api/health`（3 秒超时），连续 3 次失联触发 `on_peer_down` 回调——默认中文告警 + 自动 `export_bundle` 留最新备份，**不自动抢班**（抢班交给部署编排层，本模块提供钩子）；
  - `health_bp`：`/api/health` Flask Blueprint，已注册于 `xiaoju3_dashboard.py:72,80`（:5003 可被对端探测）。
- **已接线部分**：`/api/health` 端点 🟢；PeerWatch 守护线程挂进 `main.py:829-832` `start_background_services()`（默认关闭，env `XIAOJU3_WATCH=1` + `XIAOJU3_PEERS` 才启动）🟢；`xiaoju3_soul_*.zip` 已进 `.gitignore:30` 🟢。
- **待接线部分（10-04 冲刺项）**：`export_bundle` / `import_bundle` 尚无生产调用点——将落成 `/soul_export`、`/soul_import` 一键指令（QQ/控制台/CLI 三入口），即"最小可用版"。

### 要迁移的核心数据

| 数据 | 实际位置 | 内容 | 策略 |
| --- | --- | --- | --- |
| `identity.json` | `agent_state/identity.json` | 权限等级、Lv.4 主人标记、用户称呼、儿童锁 `is_adults` 映射 | 打包 |
| `history_qq.json` | `agent_state/history_qq.json` | QQ 通道对话记忆 | 打包 |
| `history_web.json` | `agent_state/history_web.json` | 网页控制台通道对话记忆 | 打包 |
| `history_cli.json` / `history_console.json` | `agent_state/` | 终端 / 控制台通道记忆（`history_*.json` 通配全打包） | 打包 |
| `conversations/` | `agent_state/conversations/` | 会话明细 | 打包 |
| `long_term.db` | `agent_state/long_term.db` | SQLite 长期记忆库（memories 表） | 打包 |
| `emoji_links.json` | `agent_state/` | 表情包链接收藏库 | 打包 |
| `.env` 配置项 | `xiaoju3_data/.env`（隔离区，gitignore） | `DEEPSEEK_API_KEY`、`HA_URL`/`HA_TOKEN`、`ONEBOT_API_URL`/`ONEBOT_TOKEN`、`XIAOJU3_TOTP_SECRET`、`XIAOJU3_REGISTER_PASSWORD`、`DANGER_ENTITIES` 等 | **不打包**——`MANIFEST.txt` 只列键名，值由用户在新设备手工核对 |

### 一键导出 / 导入接口草图（10-04 落地口径）

```python
# ===== 已就绪（migration.py 实测签名）=====
export_bundle(path=None)                    # → xiaoju3_soul_YYYYMMDD_HHMMSS.zip
import_bundle(zip_path, overwrite=False)    # → 恢复 agent_state/，防穿越校验
PeerWatch().watch_loop(interval=60)         # → 失联 3 次触发 on_peer_down（默认自动留最新备份）

# ===== 待接线草图（10-04 最小可用版）=====
# ① QQ / 控制台指令（主人级 Lv.4 门禁——灵魂包含身份与记忆）
#   /soul_export                → 执行 export_bundle()，回复包路径与大小
#   /soul_import <zip绝对路径>   → 执行 import_bundle(zip, overwrite=False)，
#                                 回复恢复清单 + 提醒按 MANIFEST.txt 手工补 .env
# ② HTTP API（:5003，复用 /api 族风格）
#   POST /api/soul/export                 → {"code":0,"data":{"bundle":"...zip","bytes":N}}
#   POST /api/soul/import {"path":..., "overwrite":false} → 恢复结果逐项清单
# ③ CLI（migration.py 自带 __main__ 参数）
#   python migration.py --export [输出路径]
#   python migration.py --import <zip> [--overwrite]
# ④ 守望联动（已留钩子）：on_peer_down → 告警日志 + export_bundle 留最新备份；
#   新设备拉起后 /api/health 恢复心跳，PeerWatch 快照翻绿
```

### 可验证证据

- 离线：`tests/test_migration.py`（导出/导入/防穿越/守望探测）全绿。
- 现场（接线后）：A 机 `/soul_export` → 把 zip 拷到 B 机 → `/soul_import` → 重启后身份、等级、两通道记忆原样续聊。

> 📷 截图占位 [SCREENSHOT: /soul_export 的 QQ 回复（含 xiaoju3_soul_*.zip 路径与大小）+ 新设备 /soul_import 后"我是谁/记得什么"续聊对比]

---

## 创新点 3：本地优先双脑 + 完整设备接管链 🟢

### 是什么

**双脑**：每条消息先进 `brain.smart_ask`（brain.py:1635 起）——本地 Ollama 优先、云端 DeepSeek 兜底、异常热切换，用户无感。**接管链**：同一个大脑的输出可落成三类执行——控手机（ADB）、控家电（Home Assistant）、控文件（工作区沙箱），全部走同一张工具白名单与同一套四级权限门禁。

`smart_ask` 流程（可对照源码逐步讲）：

1. 长期记忆关键词提取落库（`_remember_user_facts`，brain.py:1647）；
2. 位置隐私静默期硬拦截：位置未知 + 地点敏感问题 → 不进模型，代码层强制询问（brain.py:1654-1669）；
3. 消息含 URL → 先抓网页正文（剔除 script/style）再总结（brain.py:1671-1696）；
4. 组装上下文：前情提要压缩（>20 条浓缩）→ 长期记忆注入 → 位置状态注入（brain.py:1673-1681）；
5. 防死循环熔断：已熔断会话剥夺本轮工具调用权（brain.py:1700-1702）；
6. **硬件自适应路由**：低配设备跳过本地探测直接云端（省 1 秒）；中配在线则优先小模型；否则探测本地 Ollama（1 秒超时）→ 在线走 `ask_local`，异常自动切 `ask_cloud`（brain.py:1704-1735）；
7. 回复含工具 JSON → 正则提取 → 白名单校验 → `execute_tool` 执行 → 结果喂回模型生成自然语言答复，全程 `<think>…</think>` 包装供前端推理卡片。

### 代码位置

| 证据 | 位置 |
| --- | --- |
| `smart_ask` 双脑决策入口 | `brain.py:1635` |
| 本地探测 / 热切换 / 硬件分档 | `brain.py:1704-1735`（`probe_local` / `_resolve_tier` / `ask_local` / `ask_cloud`） |
| 终端日志"🏠 本地大脑在线，优先使用本地算力！" | `brain.py:1717`（🧩 medium 档 `:1715`；📱 low 档 `:1709`；📡 云端 `:1719`） |
| 工具白名单 `TOOL_WHITELIST` | `brain.py:146-153` |
| 工具执行唯一入口与分级门禁 | `tools.py:276` `execute_tool`（门禁 `:284-303`） |

### 10→14 项工具白名单（brain.py:146）

> 注：创新点立项时的白名单为前 10 项；1.0 冲刺中已扩至 14 项（后 4 项为第二阶段新增：联网搜索、系统组件管理、核心记忆读取、重启自身）。如实列出：

| # | 工具 | 接管对象 | 门禁 |
| --- | --- | --- | --- |
| 1 | `list_files` | 文件 | Lv.2 |
| 2 | `read_file` | 文件 | Lv.2 |
| 3 | `write_file` | 文件 | Lv.3 |
| 4 | `get_ha_devices` | 家电（读六类实体） | Lv.1+（能力键） |
| 5 | `control_ha_device` | 家电（开关/切换；危险实体自动升 Lv.4） | Lv.3 / Lv.4 |
| 6 | `adb_screenshot` | 手机 | Lv.4 |
| 7 | `adb_tap` | 手机 | Lv.4 |
| 8 | `adb_swipe` | 手机 | Lv.4 |
| 9 | `vision_tap_element` | 手机（云端视觉点击兜底） | Lv.4 |
| 10 | `ui_tap_element` | 手机（uiautomator 元素精准点击） | Lv.4 |
| 11 | `web_search` | 联网搜索 | Lv.1 |
| 12 | `system_manage` | 系统组件装卸 | Lv.4 |
| 13 | `read_core_memory` | 核心记忆库 | Lv.4 |
| 14 | `restart_service` | 重启小橘自身进程（无 OS 级调用面） | Lv.4 |

### 可验证证据

- **终端日志**：本地在线时启动/对话可见 `🏠 本地大脑在线，优先使用本地算力！`（brain.py:1717）——截图占位见下。
- **离线**：`tests/test_brain.py`（双脑切换、白名单校验、熔断）、`tests/test_tools.py`（分级门禁）全绿。
- **现场演示**：拔网线（断云端）→ 群里继续对话、继续控灯——本地大脑独立成事；插回网线无感恢复。

### 本地模型 + 控手机 + 控家电 + 控文件，为什么这个组合稀缺

- **纯本地方案（Ollama 生态、各类"本地助手"）**：只有聊天，没有执行臂——能说不能做；
- **云端助手（小爱/小度/Siri/音箱家族）**：有执行臂，但大脑在云、数据出门、断网即聋，且能力被厂商白名单锁死；
- **开源家居中枢（Home Assistant 系玩法）**：控家电强，但"控手机（ADB 三原语 + UI 元素解析 + 视觉点击三级点击链）""控文件（realpath 沙箱）"与"本地大脑"不在同一具身体里，更没有统一的四级权限与儿童锁。
- **小橘3号把四件事装进同一具家用单体**：一个 `smart_ask` 出口、一张白名单、一套权限矩阵——本地优先保证"数据不出家门 + 断网可用"，执行臂保证"说得算数"。单看每一项都有人做，**四合一 + 统一权限**目前没有第二家。

> 📷 截图占位 [SCREENSHOT: 终端日志"🏠 本地大脑在线，优先使用本地算力！"整屏（含启动横幅与一条本地应答)]

---

## 创新点 4：QQ 家庭入口 + 桌宠人格 🟢

### 是什么

**QQ 入口**：QQ 侧经 OneBot 11 协议接入（NapCat / LLOneBot 自托管实现），webhook 宿主于 `:5003` 控制台进程的 `/onebot` 路由，业务体为 `main.py` 纯函数 `onebot_event(data)`——收到消息 → 清洗 → `handle_message` 路由 → 回复发回（`send_group_msg` / `send_private_msg`）。私聊直接响应；群聊需 @（含纯文本 @ 形态）或触发词（小橘/小桔/橘3号/橘三号/AI测试）防刷屏；还有"戳一戳"彩蛋（会痒得回话）。

**桌宠人格**：`desktop-pet.js`（598 行，IIFE 单例注入）——Q 版橘色狐狸娘挂在网页控制台右下角：Pointer Events 拖拽 + 按压形变、距屏幕左右边缘 <24px 磁吸贴边、`scaleX(-1)` 左右翻转（始终朝屏幕中心）、**双版本状态机**（吸附时半身像 `normal_half.png` 只露上半身，拖拽中自动切全身像 `normal_full.png`，素材缺失逐级回退绝不裂图）、随机台词气泡与余额轮换、WebAudio 程序合成音效（零音频文件）、移动端视口自动缩放。`PET_STATE_IMAGES` 常量表即情绪扩展接口（新增情绪 = 补素材 + 表内登记）。

**现状注记（如实）**：桌宠 JS 功能已完备，但按 2026-10-01 口径暂从 `index.html` 停载（index.html:538-543 注释保留，右下角当前唯一悬浮元素是加速球）；10-07 冲刺日以完整形态回归上线。`assets/pet/normal_half|full.png` 目前为 JPG 占位字节，待替换为即梦 AI 生成的透明 PNG。

### 代码位置

| 证据 | 位置 |
| --- | --- |
| OneBot 11 webhook 业务体（消息处理 / 戳一戳彩蛋 / 单条异常不崩接入层） | `main.py:750-815` `onebot_event` |
| webhook 宿主（:5003 `/onebot`，LLOneBot/NapCat 上报地址） | `xiaoju3_dashboard.py`（路由）+ `main.py:75`（端口 3001 口径注释） |
| 群聊 @/触发词过滤（纯文本 @ 形态兼容） | `main.py:18,140-144,650-670` |
| NapCat 静默拉起 | `setup_napcat.bat`、`start_napcat_silent.vbs` |
| 桌宠实现（贴边/翻转/双状态机/台词/音效） | `desktop-pet.js:1-27`（能力头注）、`:33-37`（`PET_STATE_IMAGES`）、`:131`（翻转层） |
| 桌宠前端停载现场 | `index.html:538-543` |
| 离线测试 | `tests/test_pet_desktop.py`、`tests/test_pet_edge_frontend.py` 全绿 |

### 中国家庭场景下，QQ 作为 AI 入口的天然优势

1. **零安装门槛**：爸妈爷奶手机里已经有 QQ。AI 入口不是"再装一个 App"，而是"加个好友"——家庭 AI 落地最大的一步被抹掉了。
2. **家庭群 = 天然多用户系统**：一家人本来就在一个群里；@小橘3号 即召唤，触发词防刷屏，而权限等级、儿童锁成人登记全部按 QQ user_id 逐人管理——客厅音箱做不到"按人分级"，QQ 天然做得到。
3. **私聊推送是现成的"家庭协同总线"**：创新点 1 的儿童锁裁决（成人 QQ 私聊收 🔒 请求 → `/approve` / `/deny`）全靠它闭环，不需要任何额外通知渠道。
4. **协议生态成熟且自托管**：OneBot 11 + NapCat/LLOneBot 全家桶本地部署、不依赖厂商云——与"数据不出家门"的产品原则严丝合缝。
5. **入口即人格**：戳一戳会痒、桌宠会翻面、回复带 Edge-TTS 语音——QQ 不只是遥控器，是这只橘色狐狸娘"住在"的地方。

> 📷 截图占位 [SCREENSHOT: 双拼左=QQ 群 @小橘3号 对话（含戳一戳彩蛋），右=控制台右下角桌宠半身吸附 + 台词气泡]

---

## 附：演示前检查单

- [ ] `.env` 就位：`XIAOJU3_TOTP_SECRET`（Lv.3/Lv.4 提权）、`HA_URL`/`HA_TOKEN`（家电演示）、`ONEBOT_API_URL`（QQ 演示）
- [ ] 本地 Ollama 在线（创新点 3 的 🏠 日志与断网演示）
- [ ] `CHILD_LOCK_ENABLED=true` 且儿童/成人两账号就位（创新点 1 三连演示）
- [ ] 四张 `[SCREENSHOT: …]` 补图完成
- [ ] 全仓测试基线：`python -m unittest discover`（1482 全绿）
