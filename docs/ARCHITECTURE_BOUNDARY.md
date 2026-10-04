# 架构边界文档：主体 vs 插件（只定规则，不做全面重构）

> 状态：**正式文档 v1（已定稿 2026-10-04，四点拍板全做，拍板记录见 §七）**
> 日期：2026-10-04
> 约束（用户已定）：不全面重构；只定规则；**新功能按插件写、老代码不动**；不打断发版/软著/比赛节奏
> 侦察基线：全部结论出自当前 HEAD 实码（含行号证据），非设想
> 关联：架构设计文档 §5/§7/§10（术语来源）、TODO_EXTRACT_DESIGN.md（最重插件的出处）、tool_registry.py（§3.3 登记表实现）

---

## 一、现状侦察：扩展缝的真实形态（本稿立足点）

### 1.1 项目已有两条注册缝——不是从零设计，是"补齐第三处"

**缝 A：直达意图（数据驱动，已是好形态）。**
`intent_router.INTENT_PATTERNS` 表驱动（name/patterns/extractor/handler_name/negative_patterns），
处理器用延迟字符串引用（`"plugins.accounting:add_record"`），dispatch 动态 import。
模块注释明文："新增意图只加表项，不改路由逻辑"——accounting / ebook_export / web_search
已走通。**这一缝基本不用动**，规则只需承认它。

**缝 B：模型工具（CoT 协议）——"四处税"的实锤定位。**
新增一个模型可调工具（如 extract_todos）今天要同步：
| 处 | 位置 | 动什么 |
|---|---|---|
| ① | tools.py:69-74 `TOOL_WHITELIST`（15 项） | 加名 |
| ② | **brain.py:146-151 `TOOL_WHITELIST`（重复清单！）** | 加名——tools 注释自证："brain.TOOL_WHITELIST 需同步追加，工具才可经 smart_ask 链路触发"；忘加 = brain.py:1875 "不在白名单内，已拒绝执行" |
| ③ | prompts.py 工具协议（编号清单 1-15 行 + 权限口径段） | 加描述行 |
| ④ | tools.py `execute_tool` if/elif 链（400-507 行） | 加分支 + import |
| ⑤ | tools.py 权限分组 `_LV2/_LV3/_LV4/DANGER/ACTION_TOOLS` | 视情况加组 |

**缝 C（隐性第五处）：冻结收录。** `xiaoju3.spec` hiddenimports 显式列 9 个
`plugins.*` 模块——因为 handler_name 是字符串动态 import，PyInstaller 静态
分析抓不到；漏加 = dev 正常跑、exe 里 ModuleNotFoundError（最阴的坑）。

### 1.2 反向依赖现状清单（core → plugins 顶层 import 的既有点，全部豁免、冻结不再扩散）

| 位置 | 形态 | 评价 |
|---|---|---|
| main.py:69（context_manager）、:70（todo_extractor） | 顶层 | 既有事实，豁免 |
| tools.py:57-58（todo_extractor、link_logger） | 顶层 | 既有事实，豁免 |
| xiaoju3_dashboard.py:76（todo_extractor） | 顶层 | 既有事实，豁免 |
| brain.py:1331（context_manager）、main.py:775（help_menu）、xiaoju3.py:540（help_menu） | 函数内延迟 | 合规形态，新代码照此写 |

插件侧对核心的依赖已有成文先例：batch_logger 延迟导入 brain.ask_cloud
（缺席优雅降级）；accounting 自读 env、import 零副作用——**契约就是把既有好实践成文，不是发明新框架。**

### 1.3 存量 9 插件定位表（问题 1 的插件侧答案，兼作豁免清单）

| 插件 | 形态 | 消费点 | 定位 |
|---|---|---|---|
| todo_extractor | **混合**（模型工具 extract_todos + main.py:593-640 /todo_from_link 指令拦截 + dashboard 待办卡片数据源） | tools/main/dashboard 三方 | 最重耦合案例（刚验收，**不动**）；记为"混合形态的上限样本" |
| accounting | 直达意图 | intent_router 表 | **标准模板**（新直达功能照此写） |
| ebook_export | 直达意图（需 history 参数注入） | intent_router 表 | 标准模板 |
| link_logger | 基础设施 | tools:58 / run_link_log / todo_extractor | **插件基础设施**（被同行依赖） |
| batch_logger | 基础设施 | link_logger / run_link_log | 插件基础设施 |
| context_manager | 主体延伸 | main.py:69 顶层 + brain.py:1331 | 事实上是主体库（标注定性，不迁移） |
| help_menu | UI 型 | main.py:775 / xiaoju3.py:540（均延迟） | UI 型插件先例 |
| qq_send_image | 半接线 | 能力声明在 tools（send_image），门禁在 main /send_image | 半接线存量，豁免 |
| dev_logger | 死代码 | 零消费（已被 link_logger+batch_logger 替代，注释自认） | **归档候选**（单独小批处理，本稿不动） |

---

## 二、边界划分清单（问题 1：哪些归主体、哪些归插件）

### 2.1 主体（底盘，冻结不动）

判据：删掉它小橘就不再是小橘；或它是别人赖以运行的安全/进程/协议收口。

| 层 | 模块 | 为什么是主体 |
|---|---|---|
| 进程壳 | xiaoju3_launcher / desktop_launcher / xiaoju3_refresh | spawn-self 三角色、窗口、守护 |
| 消息接入 | main.py | QQ/onebot webhook、指令族、意图接线、通知注入 |
| 决策 | brain.py / prompts.py | CoT 工具协议、双脑调度、系统提示词 |
| 分发与安全 | tools.py / permission.py / web_sanitize.py | 工具白名单、四档权限、Web 出口净化——**安全收口永不下放** |
| 意图路由 | intent_router.py | 规则层本体（表是数据，路由逻辑是主体） |
| 控制台服务 | xiaoju3_dashboard.py | 5003、前端托管 |
| 配置/状态 | xiaoju3.py / paths.py / agent_state/ | 配置单一来源、双根、状态外置 |
| 平台适配器（内置工具） | home_tools / adb_tools / android_ui_tools / vision_tools / search_tools / win_process / emoji_manager | **名义插件形态、事实上主体**——老代码原地不动（见 2.3 裁决①） |
| 运维 | migration / heartbeat / first_run / autostart / hardware_profiler | 灵魂打包、守望、首装、自启 |

### 2.2 插件（plugins/，新功能默认形态）

判据：能独立回答"它为主人多做了什么"，且删掉后主体其余部分照常工作。
plugins/ = 可独立卸载的用户功能。按 §1.3 定位表：标准插件 = accounting /
ebook_export / help_menu 形态；基础设施 = link_logger / batch_logger；
存量混合者（todo_extractor / context_manager / qq_send_image）豁免、随触碰随靠拢。

### 2.3 灰区裁决三条（评审重点）

1. **内置工具适配器不迁目录**：home_tools/adb/vision/search 留在根目录、保持主体身份
   （它们是能力底盘 + spec 收录 + prompts 协议的一部分）。"从现在开始"只约束**新增**——
   新的品牌适配器、新的外部系统对接才进 plugins/。
2. **插件间依赖**：允许，但方向只能"功能插件 → 基础设施插件 / 老插件"（link_logger←todo_extractor
   为既有正例）；**禁止循环**、禁止新插件顶层 import 主体决策层（见 §3.5）。
3. **context_manager 定性**为主体延伸库（虽然住在 plugins/），不改名不迁移——目录不是边界，
   **登记表才是边界**（§3.3）。

---

## 三、插件接口契约（问题 2）

设计原则：延续两条既有缝、零新框架、冻结态安全、删掉即卸载。

### 3.1 形态三分类

| kind | 触达方式 | 例 | 注册点 |
|---|---|---|---|
| `direct_intent` | 用户一句话直达（正则命中，不经模型） | accounting, ebook_export | intent_router 表项（现状即零逻辑改动） |
| `model_tool` | 模型 CoT [行动] JSON 调用 | extract_todos（新工具照此） | 登记表（钩子拍板后，见 §3.3+§七-1） |
| `infra` | 被其他插件/工具层调用，无用户入口 | batch_logger | 仅登记表声明（无机制） |

UI 附着属性：插件可带后端路由（`/api/plugins/<name>/*`），**第一期不动
index.html/console.js**（控制台卡片是硬编码，动态化成本不匹配节奏；§四缺口②）。

### 3.2 生命周期（极简四条，全部有先例）

1. **import 零副作用**（不建文件、不打印、不连网）——accounting/help_menu docstring 已自证，
   升格为铁律；这保证 spec 收录、测试、冻结态都安全。
2. **可选 `setup(state_dir)` 惰性初始化**：首次业务调用时自建 agent_state/ 子目录；
   无 on_load/on_unload 热插拔——进程即生命周期，"卸载" = 登记表移除 + spec 移除 + 重启。
3. **后台线程纪律**（todo_extractor 先例）：daemon=True、受理即返回、崩溃自兜底、
   完成经注入的 notify 回调通知。
4. **失败口径**：返回面向用户的中文文本；`❌` 开头 = 明确失败（全项目既有语义，可切断
   brain 重试链）；插件内不打印指引性废话进聊天框（vision_tools 收口先例）。

### 3.3 注册方式：一张登记表（plugins/registry.py，唯一真相）

```python
PLUGIN_MANIFEST = [
    {
        "name": "smarthome_mihome",            # 唯一名
        "module": "plugins.smarthome_mihome",  # spec hiddenimports 抄这里
        "kind": "model_tool",                  # direct_intent | model_tool | infra
        "version": "1.0.0",
        "tool": {                              # kind=model_tool 时必填
            "name": "mihome_control",
            "description": "控制米家设备。参数：entity_id, action",
            "min_level": 2,                    # 声明式权限，主体执行
            "dangerous": False,
        },
        "intents": [],                         # kind=direct_intent 时同步 intent_router 表项
        "env_keys": ["MIHOME_URL", "MIHOME_TOKEN"],   # 配置自读，登记供文档/软著
        "uses": ["brain.ask_cloud"],           # 延迟导入声明（文档用）
    },
]
```

- **direct_intent**：机制沿用 intent_router 表（不动）；登记表只做存在性声明 + 文档汇总。
- **model_tool**：✅ 合并钩子已拍板并同日实施（2026-10-04 refactor 笔）——落地形态 =
  **根模块 `tool_registry.py` 统一工具登记表**（`TOOL_MANIFEST`，唯一真相，含全部
  15 项协议工具 + send_image 非协议能力声明，每条带 desc/params/level/dangerous/
  is_action/in_protocol/module 字段；插件工具条目另带 `handler: "模块:函数"` 字符串，
  module 字段即 spec hiddenimports 抄录源）。tools.py 白名单与权限组、brain.py 白名单、
  prompts.py 工具协议段全部**派生自登记表**（双白名单手工同步旧债就此消灭）；
  execute_tool 尾部保留插件工具统一分派分支（importlib 解析 handler，缺库/异常返回
  中文 ❌ 串）。新增模型工具 = 登记表加一条（插件工具）或登记表 + execute_tool 分支
  （核心工具），三处自动同步。
- **infra**：无机制，登记即可。
- spec 收录：新插件在 xiaoju3.spec hiddenimports 加一行（module 字段照抄）——
  §1.1-缝 C 的坑写进交付检查清单。

### 3.4 依赖注入（不搞容器；三条注入面，全部有先例）

1. **配置**：插件自读 env/.env（accounting §6.2 先例），键名登记 `env_keys`；
   主体 xiaoju3.py 不为新插件加配置项。
2. **平台能力**：`brain.ask_cloud` / 决策层一律**函数内延迟导入**（batch_logger 先例成文）；
   禁止插件顶层 import brain/tools/main（防循环依赖 + 测试耦合）。
3. **消息回调**：需要主动通知/发图时由 main 在 dispatch 时以参数注入
   （todo_extractor 的 `notify=` 先例），插件不自行持有 QQ 通道。

### 3.5 安全边界（权限不下放）

- min_level / dangerous 在登记表**声明**，执行收口在 tools.execute_tool 统一门禁——
  插件内不做二次权限判断（安全语义单点化，permission.py 仍是唯一权威）。
- 落盘一律 agent_state/ 自建子目录 + 原子写（accounting 临时文件+os.replace 先例）。
- 插件不得绕过 web_sanitize 自行触达 Web 出口。

---

## 四、问题 3裁决：新按插件写、老代码不动——可行吗？

**结论：可行，但只覆盖一半，另一半取决于一处拍板。** 如实拆开：

| 功能形态 | "老代码不动"下能否按插件写 | 说明 |
|---|---|---|
| 直达意图类（记账/导出/查询类新功能） | ✅ 完全可行 | intent_router 表项 + 插件文件，零核心改动（accounting 已证明） |
| 模型工具类（要让大脑主动调用的能力） | ✅ 可行（钩子已拍板并实施） | 合并钩子落地后登记表即唯一真相；核心工具另加 execute_tool 分支 |
| 控制台 UI 类（新前端卡片） | ❌ 第一期不做 | 前端硬编码，动态化不匹配节奏；规则=插件 UI 只做后端路由 |
| 基础设施类 | ✅ 可行 | 写完登记即可 |

**老代码不动的隐患清单（保留它不是零成本，如实列出）：**
1. brain/tools 双白名单是现存的手工同步债（无锚测试，靠注释自觉）——建议一次性加
   一致性锚测试（1 条：两清单相等），独立于钩子拍板，随时可做；
2. 存量豁免清单（§1.3）会随时间腐化——规则：**随触碰随靠拢**（改到哪个老插件就顺手
   补登记），不做专项迁移；
3. spec hiddenimports 漏加新插件是最可能的翻车点——交付检查清单写死（§3.3）。

---

## 五、问题 4：最小可行边界文档条款（定稿版收敛为 8 条铁律）

本稿评审通过后，ARCHITECTURE_BOUNDARY.md 收敛为以下 8 条（其余降为附录豁免清单）：

1. **目录语义**：plugins/ = 可独立卸载的用户功能；主体根目录模块不得新增顶层
   `import plugins`（既有三处白名单冻结：main.py:69,70 / tools.py:57,58 /
   xiaoju3_dashboard.py:76）。
2. **依赖方向**：插件 → {xiaoju3 配置、paths、permission、主体适配器} 可顶层；
   插件 → {brain、tools、main} 仅函数内延迟导入；插件间只许"功能 → 基础设施/老插件"，
   禁循环。
3. **注册**：新功能必须按三分类（direct_intent / model_tool / infra）落
   tool_registry.TOOL_MANIFEST 登记表；direct_intent 同步 intent_router 表项，
   model_tool 同步 spec hiddenimports（插件模块时）。
4. **import 零副作用**：插件模块导入不建文件、不打印、不连网。
5. **权限不下放**：min_level/dangerous 声明于登记表，门禁执行收口 tools.execute_tool；
   插件不做二次权限判断。
6. **返回串契约**：中文文本面向用户；`❌` 开头 = 失败；指引/诊断只进控制台不进聊天框。
7. **落盘纪律**：agent_state/ 自建子目录 + 原子写；配置自读 env 并登记 env_keys。
8. **豁免清单即存量真相**：§1.3 表 + §2.1 主体清单是唯一豁免依据；改到谁谁补登记，
   不做专项重构。

---

## 六、问题 5：多品牌智能家居（P1）作为第一个标准试点的注意点

现状地基：home_tools.py（单 HA：HA_URL/HA_TOKEN 单实例、八类实体过滤、
turn_on/off/toggle + set_temperature、is_dangerous_entity 高危分类）；
消费方三条：tools 两模型工具（get_ha_devices / control_ha_device）、
prompts 工具协议第 4/5 行、heartbeat.py:52 快照 diff（多设备守望）。

试点设计七要点：

1. **模型协议冻结（最重要手法）**：大脑看到的仍是 `get_ha_devices` / `control_ha_device`
   两个工具名——prompts/brain/白名单零改动，home_tools.py 升级为**聚合路由层**
   （主体），按 entity_id 前缀把调用分发给品牌插件。"新功能按插件写"在这里的落法 =
   每个品牌一个插件，模型层毫无感知。
2. **entity_id 强制命名空间前缀**：`ha.light.xxx` / `mihome.light.xxx` /
   `tuya.switch.xxx`——多品牌最容易翻车的点就是跨品牌实体撞名；聚合层靠前缀路由，
   前缀即插件名（登记表 `namespace` 字段）。
3. **品牌适配器最小协议**（四函数，对齐 home_tools 现有形状）：
   `list_devices() -> str（行式文本摘要）/ get_states() -> list[dict] /
   control(entity_id, action, temperature=None) -> str / is_dangerous(entity_id) -> bool(交主体复核)`。
4. **高危判定主体收口**：门锁/燃气模式匹配留在聚合层（permission/危险设备门禁是主体
   安全语义），品牌插件只提供数据与建议——同 §3.5 权限不下放。
5. **heartbeat 文本快照契约**：心跳守望消费的是 get_ha_devices 的**行式文本** diff
   （剔除时间型实体行）——品牌插件的 list_devices 输出必须保持行式格式（加锚测试锁格式），
   否则多设备守望静默失明。
6. **配置命名空间**：每品牌自读自己的 env（MIHOME_* / TUYA_*…），登记 env_keys；
   存量 HA_URL/HA_TOKEN 不迁移（老代码不动）。
7. **单品牌降级不互拖**：某品牌未配置/离线 → 中文错误串占位（`_UNSET_HA` 先例），
   聚合层拼装各品牌结果，一品牌挂不影响其余品牌可见可控行为。

**试点顺序建议**：~~拍板 §七-1（合并钩子）~~（✅ 已拍板并实施，2026-10-04）→
品牌插件（先做第二品牌验证协议）→ home_tools 聚合改造（老代码一次小动，届时单独出
小设计稿）→ heartbeat 锚测试补齐。合并钩子已就位，本试点对节奏最友好：品牌插件
即第一个走"登记表一条 + 插件文件"标准路径的 model_tool 家族。

---

## 七、拍板记录（2026-10-04，四点全做）

1. **model_tool 合并钩子——✅ 立**（同日 refactor 笔实施）：落地为根模块
   `tool_registry.py` 统一工具登记表（含老工具全部迁移），tools/brain/prompts
   三处派生，execute_tool 尾部插件统一分派；双白名单旧债同步消灭。
2. **双白名单一致性锚——✅ 已确认存在**：tests/test_tools.py:188
   `test_brain_whitelist_in_sync_with_tools` 既有逐元素一致锚（extract_todos
   漏加 brain 侧的历史教训所立），无需重复添加；数量锚 = tests/test_brain.py:561
   `test_whitelist_matches_fifteen_tools`（15 项，保持不变）。
3. **dev_logger.py 归档——✅ 做**（同日 chore 笔）：移 _dev/archive/，
   spec hiddenimports 同步移除，test_link_batch 专节改指归档路径保持活性。
4. **本文档定稿——✅ 即本版**（正式文档 v1），后续新功能设计稿引用其条款编号。

## 八、未来路线 · 待实现设计约束（B 路：常驻模式）

> 2026-10-04 用户拍板，记入路线图、本期不实现；后续常驻/托盘相关设计稿必须遵守。

**B 路约束（常驻模式与退出语义）**：
- 常驻模式（关窗后后台留守）**仅在开机自启开启时生效**；
- 关闭开机自启 → 关窗即退出，**不后台留守**；
- 显式退出操作无论如何**彻底退出**（含常驻模式下）。

即：常驻是自启的从属能力，二者绑定；用户对"关窗后还在不在"的预期由自启开关
唯一决定，且显式退出永远拥有最高优先级。实现落点候选（届时勘察定）：desktop_launcher
关窗清理链（stop_backend_launcher / finally 兜底）与 autostart.py 开关状态读取。

## 附：与硬节点的相容性

- 软著分模块登记（10-08 前）：登记表 + 边界清单 = 模块划分天然材料，**利好**；
- 比赛（11 月）：智能家居按本稿试点，不引入新框架、不阻塞发版 1.0.2/1.1.0；
- 本稿零代码改动，随时可搁置，不产生半成品状态。
