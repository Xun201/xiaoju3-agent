# 小橘3号 · 状态单一事实源（STATE.md）

> 用途：AI 协作的当前状态快照——回执尾部附上，替代口头报状态。
> 维护：ZCode 每次部署/优先级调整/收窗后更新。
> （2026-10-14 顺修：本文件曾有「设置页打不开修复」段×3+待推行×3 重复——多终端后写覆盖残迹，本版去重；.bak-20261014-persona 在案）

---

## 当前生产车

- 哈希：**15a6f53f**（1.0.5.1 内部补丁版=修 B v3 A+B；QQ 真机三连全过；不打 tag——版本策略见 AGENTS.md）
- 部署时间：2026-10-14 15:36 部署 / 15:39 三进程活体（桌面壳/launcher/dashboard；/api/health 200 ok device=Xun-tx5）
- 测试基线：**2368+4（#303 既有失败除外全绿；#319 批 1 +29、修 B v2/v3 +24、批 4 UI 卡 +11、category 列 +2 锚）**
- 部署冒烟四项全过：①/api/chat 闲聊 200 本地模型正常回复（think 卡包装，零 persona 段泄漏）②_internal/persona_expressions.json 上车（5 模式+6 开关实抓）③brain 三段拼接 PYZ 锁（_persona_suffix 函数名+docstring"拼在关系段之后"）④.env 零 XIAOJU3_PERSONA_ENABLED=缺省关；**owner 首判活体**（fallback polite conf 0.3 n_int=33，数据层无表现）
- 设置页 UI 人工验收待用户；**人格真机冒烟待用户（11:40 回来：拨 XIAOJU3_PERSONA_ENABLED=1+攒 50 条+观察语气偏移）**

## 待推数

- **0（origin/main=83855ef：72765fb 批1+1f7cc91 坑#29+e274e28 修B v2 三修+5fc1b5f 坑#30+83855ef 思维笔记，2026-10-14 晚全推平）**

## 冒烟收尾 + 修 B 诊断+方案（2026-10-14 12:2x-12:3x）

- **阶段一冒烟收尾全确认**：rollback（50 标记删/affinity 还原 0.0/手动锁解除）+.env 开关移除（.bak 还原，计数 0）+12:27 重启三进程 health ok+车哈希 90DF9DCA 不变；rel_mode 剩 1 行=owner 自动首判（09:10:51 有机数据，保留）
- **阶段二诊断定案：来源=代码层兜底，非模型生成**——brain.py:183 `DEFAULT_BODY_PLACEHOLDER="操作已完成。"`；触发链=裸 CoT（[思考]/[计划] 无合法 [行动] JSON）→_capture_thinking 吃掉诚实正文→_strip_bare_cot 剥空→占位回补失败→兜底注入；**直调 1.5b 三探针全中**（关电脑→幻觉 JSON/音乐→散文已完成/邮件→虚构全文）=无工具请求系统性编造（模型能力层次因）；影响面=本地系统性+云端链级可中低频
- **阶段三方案落盘**：_dev/design_fix_no_fake_completion.md——推荐 D=A+B：A 出口否定感知兜底（think 含否定→诚实文案而非"已完成"，真完成场景逐字节不变）+B prompt 协议补条（正文思考必须一致）；C 强制云端不推荐本期；+8 锚清单/修 B-1 A+修 B-2 B 分批；**等拍板后动工，随下次部署**
## #319 灵魂架构落地设计稿 v2（2026-10-14 深夜，纯设计零代码等拍板）

- 侦察六项实测（生产 agent_state 25 项盘点/paths 双根锚债清/migration 家底复用/#227 阻碍小/Pi 中枢候选/user_id 无终端维度）
- 设计稿落盘：_dev/design_319_soul_landing_v2.md——灵魂核三档清单（core 必迁/ext 可选/派生不迁）+soul_manifest.py 单点化+migration v2 复用（soul_meta/sha256/integrity 前检/导入自动备份）+回写协议（/api/soul/writeback+outbox 退避+下线全量）+冲突判定（A2 核心权威文件级一期+conflicts 表：偏好类分身赢事实类核心赢）+五批计划（锚 ~10/8/6/6）
- **推荐路线 B 渐进**（批 1 单机迁移→批 2 自回写→批 3 Pi 双端→批 4 冲突；15-20 天每批可验可回退）vs 路线 A 激进（10-15 天一次性，迁移风险集中）——等拍板后新会话实施

## 1.0.5 收官（2026-10-14 晚，用户放行四冒烟全过）

- **persona 还原**：50 标记删+affinity 还原 4.0+锁解除（生产库零残留）；**.env 双开关保持 ON**（用户拍板日常用：persona+typing）
- **tag v1.0.5 → 6278678**（构建点=版本一致性核验）+**Release** https://github.com/Xun201/xiaoju3-agent/releases/tag/v1.0.5 ——资产 xiaoju3-1.0.5-setup.exe 72,487,225B **sha256 双端核验 PASS**（b1f0535c…）；三段式文案（新特性/修复与安全/工程与体验）
- **1.0.6 候选登记**：todos **#330 P1**——虚假能力声明修复（A=prompt 白名单式能力边界+C 限定版高危动词强制云端；B regex 不推荐；诊断档日志 §二十一）；插入脚本 _dev/add_todo_106_capability.py
- **交接全落**：changelog §二十二+_dev/PROJECT_CONTEXT 追加（10-14 晚批 225-227）+BOOT 快照+Hindsight retain（release_v105 条，bank 62）
- 生产车 **5F89ED9B** 在线（.env 双开关 ON）；origin/main=6278678 待推 0；1.0.4→1.0.5 全链收官

## 新变体诊断：虚假能力声明"我能做"（2026-10-14 晚，纯只读等拍板）

- 1.0.5 真机：修 B+裸 JSON 双修生效 ✓，新变体=QQ 回"当然可以/这个我能做"（无删除工具却宣称能做）
- **直调 4 探针关键数据**：删除×2（1 诚实/1 谎称可做）+关电脑（零诚实）+订外卖（**完成级编造**"已为你订好了"）；4 条全**无标记纯闲聊形态**→修 B/修②修③全盲（各需 think/标记/JSON 信号）
- 根因：prompt 层主因（清单在但缺"未列出=做不到"白名单式声明，1.5b 不做清单推理）+模型层上限+出口层无检测信号（regex 化高误伤不推荐）
- 修法候选：A=prompt 白名单式能力边界声明（推荐）/C 限定版=高危现实动词强制云端（#278 同构）/B 出口 regex 不推荐/D 模型上限长期靠云端；影响面=本地 1.5b 系统性（3/4 编造）云端低风险
- .env 双开关确认 ON 未动（与本案独立，不干扰用户 ②③ 冒烟）；1.0.5 四冒烟仍等用户

## 1.0.5 构建部署完成（2026-10-14 15:39，新车 5F89ED9B，等用户四冒烟）

- **推平+bump**：3 笔修复推平+bump 1.0.5（6278678）→ origin/main=6278678 待推 0
- **构建**：PYZ 八锁 ALL PASS（brain 修B/修②+chain_of_thought+personality+prompts+main 打字机/版本+permission/memory handler）→新车 **5F89ED9B**（19,784,350B）
- **部署**：shutil 绕锁（421+2 同版保留，422/422 对账）→schtasks 15:39 三进程全新+health ok；.env 双开关随重启已生效（persona+typing）
- 快速冒烟："在吗"→200 本地正常回复零异常
- **停下等用户四冒烟**：①修 B+裸 JSON（删文件请求→诚实文案）②persona（set_mode_manual(owner,"banter") 后闲聊；owner 34 事件<50 闸注意）③打字机（长问题→2-3 段）④常规闲聊
- 冒烟通过 → tag v1.0.5+Release 等放行

## 裸 JSON bug 双修落地，1.0.5 构建前停（2026-10-14 晚，4e56bcd 本地未推）

- **修①**：strip_pollution 增 _strip_toolkey_json——剥"顶层键=注册工具名"可解析 JSON（注册表校验防误伤+懒加载+异常原样返回）
- **修②**：brain._hallucinated_tool_reply——解析失败+幻觉调用证据（[行动]+工具名/工具名键 JSON）→ HALLUCINATED_TOOL_BODY 诚实兜底；双入口接线；无证据维持旁路
- **隐患③**：ui_tap_element=注册真工具 Lv.4——合法形态幻觉被权限门拦（Lv<4）；Lv.4 owner 会真执行手机 UI 点击（残余=模型侧，prompt+强制云端缓解已登记）
- **锚随拍板更新**：test_brain 旧锚（残缺 [行动]→"操作已完成。"）锚的是废止缺陷行为 → 改 honest_fallback 新契约；+8 新锚（冒烟形态/假名不剥/普通 JSON 不剥/两形态检测/None/讨论不误伤/接线）
- 全仓 2294→**2302+4**（#303 既有除外全绿）黄金 39×2 一致；预演三路：消毒剥净 ✓/brain 链诚实文案 ✓/闲聊+JSON 讨论零变化 ✓
- **停下等用户**：1.0.5 批四修全齐（修 B f8cbe76/persona 5512711/打字机 3ac290a/裸 JSON 4e56bcd）——确认后 bump 1.0.5→构建部署→真机四冒烟→tag v1.0.5+Release→changelog+交接

## QQ 裸 JSON 新 bug 诊断 + .env 双开关预配（2026-10-14 晚，零代码）

- **用户新测试**：闲聊 ✓/修 B 场景 ❌ 暴露新 bug——QQ 回复裸 JSON `{"ui_tap_element":{...}}`（非修 B 目标形态：正文非空）
- **诊断定案**：来源=模型生成（工具名作键嵌套 JSON 幻觉）；**双缺口漏出**：① `_extract_tool_json` 只认 "tool" 键→解析失败旁路（**意外幸运：没真执行手机 UI 自动化**——合法形态反而会执行）② strip_pollution 只剥 "action" 键形态→工具名键形态漏出（#20 同族第三形态）；直调×5 形态普查=编造高度随机（闲聊式完成/假链接/散文伪 [行动]/嵌套 JSON）
- 修复方向（等拍板）：strip_pollution 补"顶层键=注册表工具名"剥除+解析失败含工具名 JSON 诚实兜底（修 B 同族）；"删除"词入 #278 表赛后评估
- **.env 双开关预配**（.bak-20261014-switches，**未重启**）：XIAOJU3_PERSONA_ENABLED=1+XIAOJU3_CHAT_TYPING=1——等 bug 修完一起重启生效

## 1.0.5 发布批：修 B+persona+打字机落地，构建前停（2026-10-14，f8cbe76 已推+5512711/3ac290a 本地）

- **推平 4 笔**（批 B 三笔+4fc9838）→ origin/main=4fc9838 起点干净
- **修 B 落地（f8cbe76 已推）**：A=brain THINK_NEGATION_RE（八否定词）+NO_ABILITY_BODY_PLACEHOLDER——_wrap_think ④ 注入"操作已完成。"前扫思考卡，含否定改注"这件事我做不到——我没有对应的能力或工具。（详情见上方思考）"；真完成/双空逐字节不变；回补优先在前。B=SYSTEM_PROMPT 拟人化规则第 4 条（正文思考一致，正文为空比说谎好）
- **persona console 修（5512711 本地未推）**：dashboard 两端点传 user_id="owner"+3 锚；**冒烟预演过**（in-process 生产库行级备份还原：owner 手动 banter+补 20 标记事件过 50 闸→【关系模式参数】斗嘴型注入 ✓/uid=None 对照不注入 ✓→验后即删 34 事件+auto polite 行还原）
- **打字机 B（3ac290a 本地未推）**：split_reply_for_typing 纯函数+统一发送出口（XIAOJU3_CHAT_TYPING 缺省关，关/短单发逐字节一致；与拟人节奏叠加=等待→逐段）；+7 锚；预演三场景过（开+长 2 段延迟 1.36s/短原样/关单发）
- 全仓 2285→2287→**2294+4**（#303 既有除外全绿）+3+7 锚；黄金 39×2 每步一致
- **停下等用户**：版本号仍 1.0.4 未 bump——确认后 阶段五 bump 1.0.5（xiaoju3.py:225）→六 构建+部署（三修全上车：修 B+persona console+打字机）→七 真机三冒烟（R2 消息诚实文案+QQ persona 语气+打字机分段）→八 tag v1.0.5+Release（三段式文案：人格演化/#227/修 B/打字机/Hindsight/白屏修复）→九 changelog+交接
- R1 旁证观察项：本地模型 history 污染（在干嘛答天气）——与 #309/#314 同域低危

- **验收分工纪律落地**（4fc9838）：AGENTS.md 新节+BOOT 第 10 条+Hindsight bank 61

## 人格冒烟阶段 1 现场（12:1x，已收尾归档）

- **冒烟改道 QQ 通道（重要发现）**：console 两端点（/api/chat+/api/chat/stream）调 smart_ask **均不传 user_id** → mode_suffix uid 空串 → **控制台路径 persona 永不生效=批 3 真实缺陷**（mode_suffix 缺 owner 兜底，与 relationship 不一致；修复随下次部署）。冒烟改走 /onebot 假私聊事件（QQ 号 3779888268）
- 冒烟现场保持：.env 开关 ON（.bak-20261014-persona-smoke 在案）+12:18 重启三进程（哈希 90DF9DCA 不变）+种 3779888268 banter 置信 1.0（n_int=65，50 种+15 真实）+两条消息已发，回复全文已存 _dev/persona_smoke_replies.json；**阶段 3（rollback+开关移除+重启）等用户答完 Q1/Q2 自动执行**
- **R2 重大发现（待用户判定）**：删除请求的诚实内容全在 think 块里（"没有删除工具不能假装删了"），QQ 剥 think 后可见文本只剩"**操作已完成。**"=虚假完成表述——think 内诚实/正文编造的新形态
- **白屏并行诊断（只读）→结论 B**：四参数全在（CalculateNativeWinOcclusion/timer-throttling/backgrounding-occluded/renderer-backgrounding features 段实抓）+WebView2 155.0.4283.45 未变（154 系 SearchHost 系统组件）+无新 Windows 更新+**内存 80.3%（原 76-78%，升 3 点）**→参数已到头，建议查内存大户（python 1GB/Weixin 490MB/llama-server 598MB），内存缓解后仍 5-8s 再议新修法 C
- **验收分工纪律落地**（4fc9838）：AGENTS.md 新节+BOOT 第 10 条+Hindsight bank 61

## #227 批 B：memory 域三小步收官（2026-10-14 续，三笔本地未推）

- DB1-DB5 全按推荐落地；B-0 web /clear 样本补位（39 条重采咬合）→ B-1 handle_remember（8430bf3，+5 锚）→ B-2 gen_log（dd05e79，线程随迁+_arg_after 借 permission_handler+Thread 打桩覆盖受理分支，+4 锚）→ B-3 handle_clear（2625d55，本体留 main 全局不出 main 红线+切片赋值不重绑定，+2 锚）
- **方案修正（grep-before-delete 兑现）**：main._arg_after/SHARE_PREFIX 不退役——本体用户仍在（soul/todo），退役顺延批 C
- 黄金 39×2 每步一致；全仓 2266→2277+4；**v2 分派层拆分全图完成（content/system/permission/memory 四 handler）——剩批 C 本体搬家（赛后）**

## 坑库 #28+批 B 方案（2026-10-14 续）

- **坑库 #28 落库（58de93d）**：验收门形式与实质背离——黄金 expected 全空→比对静默 continue→绿而不真验；修法=负测试+实抓断言路径+expected 禁留空+单一事实源；failure_patterns.md **首次入库**（敏感扫描零命中）
- **批 B 方案落盘**：_dev/design_227c_batch_b_memory.md——三处 inline 依赖清单（/clear 全局切片+gen_log 线程+记住正则）/三入口签名（handle_clear(cmd,source,cb)+gen_log+handle_remember，全局不出 main）/风险六级/扩样 1 条（web /clear 支路零覆盖）/B-1→B-3 小步序/五决策点 DB1-DB5 等拍板

## #227 批 A：黄金统一 38 条+config 域抽离（2026-10-14 续，0939cc3 本地未推）

- D1-D6 按推荐拍板（用户授权复核）；阶段一黄金准备：消费源改指 tests/data 正档+扩 11 样本（38 条）+GOLDEN_CAPTURE 真采+**expected 回写=比对门首次真咬合**（旧 27 条 expected 全空=门形同虚设实锤）
- 阶段二批 A：permission_handler.py（handle_auth 六命令 pm 整体传入+handle_reset_fuse 独立）+main 九块收敛两段+_ensure_biometric_sim 委托壳（dashboard 同名调用）+零 import main；**初版漏抄 _arg_after 尾段被黄金门当场拦下→补全重跑全绿=验收门价值实证**
- 阶段三：+6 单元锚 全仓 2260→2266+4；黄金 38×2 逐字节改前改后一致；备份 .bak-20261014-batchA/golden 在案；**批 B（memory 域）等用户再议**

## 人格批 2+3 部署收官（2026-10-14 09:08，生产车 90DF9DCA）

- 批 2 判定+批 3 表现层随本车上线（开关缺省关=零行为变化）；robocopy 卡 VCRUNTIME 双锁复现（12 分钟 38/423 文件）→ 杀 robocopy 走 shutil 绕锁 421+2 同版保留（10-13 同款前例）
- PYZ 校验方法论补充：源码表达式（如 "_rel + _persona + _tone"）不进 code object——锁函数名常量+docstring 子串，不锁源码文本
- owner 首判 09:10:51 活体（fallback polite/33 事件窗口）——判定层已真跑，表现层等用户拨开关
- **冒烟脚本已备（09:3x）**：_dev/seed_persona_test.py（info/exclude 私有）——五模式配比种子+judge_mode 直调绕双闸+manual 锁落库/note 标记精确回滚+affinity 前值还原；自测全绿（五模式命中 banter1.0/caring0.75/dependent0.625/familiar1.0/polite0.3+幂等+owner 流还原，临时库零碰生产，生产 db LastWriteTime 09:11:00 未动实锤）；**用户 11:40 冒烟四步见 BOOT.md 快照段**

## 关系化人格演化批 3 表现层（2026-10-14 续，fc8e409 本地未推，零部署零真机）

- **第一可感批**：XIAOJU3_PERSONA_ENABLED 缺省关+单用户事件 ≥50 表现闸——拨开关且证据够才可见；缺省路径逐字节现状
- persona_expressions.json（5 模式×auto/on+6 开关加码行+verdict 红线尾注）+spec datas 注册；personality.mode_suffix（空串路径六重）+brain 后缀链**三段注入**（关系段→模式段→情绪段）
- 锚随结构改动同步两处：test_relationship/test_mood 旧双注入锚→三段（拍板结构变更锚随改）
- 会话收官纪律二次扩充（6b64499）：换会话前必做两件=开发者日志+BOOT.md 状态快照段；BOOT.md 增「状态快照」段；Hindsight 旧条删新条换新（bank 60 零残留）
- +15 锚 全仓 2245→2260+4；备份 *.bak-20261014-batch3/closing2 在案；**真机冒烟等用户**（拨开关验收五路径/四模式合成/开关覆盖）

## 关系化人格演化批 2（2026-10-14 续，f52690b 本地未推，零部署）

- **推平 3 笔**（专利筛查零方法级新点通过）：309bc95 人格批1/e7534de 收官纪律/c073761 日志 → origin/main=c073761
- **设计稿 v2.1 五拍板落档**（_dev/design_271_personality_evolution_v2.md）：①熟络型 familiar 第五模式（客气<熟络<斗嘴/依赖/照顾）②照顾放宽 n_scold≤2 ③节流改事件触发 N=20+6h 防抖+evidence.baseline_id 基线 ④表现层单用户闸事件 ≥50 开闸 ⑤thinking_notes「演化放权框架」（情绪记忆军训三态+判定/表现分离=同款哲学，二期统一抽象）
- **批 2 判定算法**：judge_mode 六规则纯函数（退化>斗嘴>照顾>依赖>熟络>客气兜底；n_int<10 不判；置信度饱和公式）+maybe_rejudge（事件触发+6h 防抖+手动锁优先+退化可逆）+_is_expression_ready；brain 双入口挂钩（静默旁路）；MODES+familiar
- **零行为变化**：判定只写 rel_mode，mode_suffix 未接+总开关缺省关——无消费方前逐字节一致；批 3（persona_expressions.json+mode_suffix+真机冒烟）等用户发话
- +17 锚 全仓 2228→2245+4；备份 personality.py/brain.py.bak-20261014-batch2 在案

## 会话收官纪律固化（2026-10-14，e7534de 已推）

- AGENTS.md「会话收官纪律」节（换会话前必写开发者日志）+BOOT.md 第 9 条（exclude 不随 commit）+Hindsight retain 落库（bank 60 条目 edd186d7）；首次执行补建 docs/dev_changelog_20261014.md

## 关系化人格演化批 1（2026-10-14 晨，309bc95 已推）

- **三阶段会话**（用户 8:00-11:40 不在，纯代码零部署零真机）：侦察→设计稿 v2→批 1 实施
- **设计稿 v2 落盘**：_dev/design_271_personality_evolution_v2.md（未跟踪区）——判定算法规则版五规则表/rel_mode 表+persona_pref.json 数据结构/M2 对接=后缀链加模式段/分 4 批计划/**5 个决策点 D1-D5 等用户拍板**（批 1 不依赖未决项）
- **批 1=存储层**：relationship.db 增 rel_mode 表（幂等建表，枚举无负档=结构上无恶意）+relationship 增公共 db_path()/event_stats()（逐用户事件统计=批 2 判定输入）；新模块 personality.py（get_mode/set_mode_manual 手动锁/clear_mode_manual+persona_pref.json 6 开关 tri-state auto/on/off+XIAOJU3_PERSONA_ENABLED 表现层缺省关）
- **零行为变化**：无调用方消费前全仓行为与现状逐字节一致；批 2 判定算法/批 3 brain 后缀链挂点待用户发话
- +14 锚 全仓 2214→2228+4；备份 relationship.py.bak-20261014-persona 在案

## 设置页打不开修复+部署收官（2026-10-14 01:5x，重建部署=幂等确认）

- **根因**（真浏览器实锤）：tab 退役批删 btn 常量定义，CHAT_TABS console/terminal 条目 btn 闭包残留引用→switchChatTab 的 d.btn() 遍历抛 ReferenceError 中断→**一切页签切换全断**（#14 同族+锚静态存在性盲区）
- **修复**：两 btn 闭包 null（settings 条目同款）+面板段入 IIFE+toggleToolBody 首点 bug+API 空库建表+时间脆弱锚两型+HistoryApiTestsBase RECENT_ACTIONS 隔离（dev recent_actions 被今晚 pytest 真跑 HA 心跳污染实锤）
- **部署**：重建产物与 01:02 车哈希相同（C70B22BC=可复现构建，生产车自 01:02 已含全部修复）——本轮幂等重建部署确认；**生产 5003 冒烟四项全过**（齿轮/设置卡/记忆查看/零错误/dev 行隐藏）
- 教训入坑库候选：#14 同族「删定义留引用」+「锚断字符串存在性查不出运行时 ReferenceError」（真浏览器冒烟=前端运行时的唯一可靠验证层）

**安全侦察报告已出**：_dev/eval_prompt_injection.md（提示注入暴露面：最大剩余暴露=记忆召回无隔离标记+SYSTEM_PROMPT 无全局约束，两者 ~15 行低成本可修，等拍板）

## P0 状态

| 条目 | 状态 | 备注 |
|---|---|---|
| #326 思维链模块化 | ✅ 补做完成 | chain_of_thought.py + 5/5 迁移 + D1 兼容 |
| #297 记忆系统并入 | ✅ 批1+2 完成 | 批1 1e6c632 已推平（changelog d4dd1e7 补记 schema 4→11 列）；批2 9948f21 已推平（坑库 #23 已记）；+33 锚 2142+4；等验收→统一部署→手动开 V2 A/B |
| #227 解耦三件套 | ✅ 批 A+B 已落地 | 四 handler 分派层全图完成（content/system/permission/memory）；批 B 三笔 8430bf3/dd05e79/2625d55 本地待验收；**批 C 本体搬家=赛后**；#319 侦察报告已出待拍板 |
| #271③ Phase 1 | ✅ 批1+2 完成 | 批1 c88a53e 已推；批2 a6fb8cf 本地（双 API+主动性卡+6 锚）；统一部署等用户确认（含 #329 批A 9bdeeed） |
| #271 人格演化 | ✅ 批1+2+3 完成 | 批1 309bc95 已推；批2 f52690b+批3 fc8e409 本地（判定+表现层全链，缺省关零行为变化）；**真机冒烟等用户**（拨 XIAOJU3_PERSONA_ENABLED 验收）；批 4 赛后 |

## 自检窗

- ❌ 已关闭（2026-10-12 20:45 满窗+短窗铁证，不再挂窗）
- 引擎 ON 常态运行

## 拟人节奏

- 已部署（796997a），XIAOJU3_CHAT_RHYTHM_ENABLED 缺省 OFF
- 用户手动开=MOOD_TONE 同款模式

## AIC 提交三 PDF（2026-10-13 已备）

- docs/AIC2026_技术方案.pdf — 11 页 / 0.88MB（=TECH_REPORT 拷贝）
- docs/AIC2026_演示PPT.pdf — 16 页 / 2.37MB / 16:9（WPS Kwpp COM 自比赛目录 PPTX 转）
- docs/AIC2026_佐证材料.pdf — 13 页 / 2.1MB（10-07 原版直接用）
- 三份 <10MB ✓；红线机检过（DeepSeek 出现=产品云端组件口径判定保留，隐去失真）
- 佐证 v3 已更新（拍板 B）：第 3 页文字 1898→**2,197**（docx run 级替换+WPS 重导出）+ **z4 真终端新截图**（新控制台真跑 pytest 114.53s，PrintWindow 截 Windows Terminal，裁剪留 summary 段——如实含 #303 红字 1 failed）；TECH_REPORT 1862→2197×8 处（md 7+docx 段 6+表格 1）同步对齐→技术方案.pdf 重导出（终验三 PDF 旧数字残留 0）；外发包 PDF/img/清单同步+zip v3 重打
- **佐证 v4（选 C 补图注）**：第 3 页 2,197 段后插斜体小字图注（1 failed=已知 flaky share_link 时序依赖/2197=当前有效规模）+材料清单同款注；重导出仍 13 页；zip v4=4.42MB

## UI 修复双件（2026-10-13 深夜，cbcc3c7+新车 44B65A35）

- **审计跃迁日志**：proactive_tick 签名判重（suppress:抑制组合/calm/fire——纯状态签名不含 tension 微变值），连续同状态不记（验收：新车 22:51 起 4 分钟 0 行 vs 旧车每分钟 1 条；tension_state.updated_at 22:57 活体跳动=心跳活着判重生效）；tension_state 加 last_signature 列（幂等 ALTER）
- **审计卡默认折叠**：摘要行恒显（按住中·今日出手 X/N·张力）+▸箭头展开刷新，次级 details 保留
- **开发者暗入口第二触发点**：footer-version（index.html 新增+__xiaoju3Version 填充+连点 7 次复用 handleDevTap+解锁变橙；B2c 关于卡触发点保留双通道）；动态 id 白名单 +3
- **部署坑实录**：本轮 taskkill 只杀 1/3 进程→旧车占 5003 回 health ok 假象→22:51 新车三进程才真起（health ok ≠ 新车已接管——部署后须查进程 StartTime！）

## 佐证材料外发包（2026-10-13）

- F:\小橘3号存证\佐证材料_发给同学_20261013.zip（4.6MB，发同学做佐证）
- 内含：格式要求 README.txt / 材料清单.txt / 13 页佐证 PDF / img 截图 11 张
- 两个说明 txt 用 GBK 编码（记事本直开防乱码）；zip 中文文件名 UTF-8 标志位

## 佐证外发包 v2（2026-10-13 续）

- README 命名示例改**双赛道**（场景 37673260 / 软件 27226694 两套编号各按对应赛道）
- 13 页佐证 PDF 逐页扫旧数字：**第 3 页「全仓 1898 项」=旧数字实锤**（当前 2197+4）——文字与 z4 截图（1898）自洽为"全旧"状态；改新需连 z4 重截，等拍板；v1.0.4=当前版本无需更新
- img 11 张视觉检查：**z5/z7 学校名入镜红线违规（中南林业科技大学书签）→已 PIL 裁左栏 250px 修复**；z1-z4/z6/demo/architecture 干净（个人书签栏低风险）；architecture 底部「1862 项」旧数字=图内文字低优先
- zip 重打包：佐证材料_发给同学_20261013.zip（裁剪版覆盖）

## 缺点位置设计原则（2026-10-13 拍板落盘）

- 正档：_dev/design_defect_positioning.md（安全观第三条，与 design_security_philosophy.md 互引）
- 核心：控制缺点位置 ≠ 消灭缺点（代价真实存在）；三层结构 Q8 定海神针（表达层✅/执行层⚠️不转嫁/稳定层❌）；十条原则 Q1-Q10；新功能六问分流（痛区/晚/静默/转嫁/稳定层→加门，不痛区/早/可见/自身/表达层→接受+声明）
- 工程锚点已映射到现役实例（审计三面/R2 .bak/儿童锁/赤狐人格/z4 图注等）

## 关系化人格演化系统设计稿（2026-10-13 拍板落盘）

- 正档：_dev/design_271_personality_evolution.md（挂 #271 下；**v2 实施稿 2026-10-14 落盘**，见顶部批 1 段）
- 核心：三层结构（底色层=狐狸五特质+PAD 基线永不变 / 关系模式层=按相处模式分级斗嘴/依赖/客气/照顾四型自动判定 / 表现层=6 行为开关用户自定）+ 相互包容引擎（记住好/包容坏，峰终同源）+ 有底线不记仇（长期负面→退化客气型，绝不冷暴力不恶意）+ 时间尺度看质量不看时长
- 三系统互补表：M1/M2=短期情绪 / relationship.db=关系值 / 本系统=关系模式（定性归簇）
- ~~待解：模式判定算法~~（v2 §三规则版已细化）/ 关键事件权重（一期留空）/ #319 接口（rel_mode 落 relationship.db 已对齐关系库=核心）/ 排期（批 2/3 等用户发话）

## 小工具面板批 1（2026-10-13 深夜，d040e3e+新车 44B65A35）

- 🧰 入口（header-actions 最前）→全屏 overlay 卡片墙三分类（📊 监控/🏠 控制/🔌 管理）；主动性监控卡首批实装（设置页段迁入：摘要+审计列表+频率调节 config 随迁+防误导说明）；其余卡片占位（批 2：终端/记忆/家电；批 3：插件 #312）
- 后端零改动（跃迁日志+双 API 复用——前车已验 0 行判重）；exe 哈希同前辆=合理（纯前端资源改动）
- 部署：绕锁 420 拷+23:24 新车三进程+health ok+_internal 前端上车确认；**面板交互目检=等用户真机**

- **批 2 已完成（本笔，不部署）**：记忆查看/家电列表卡实装——GET /api/memory/list（近 100 条+V2 五字段，降级形态）/GET /api/ha/devices（文本形态 <pre> 直显，HA 不可达=错误文案 200）；toggleToolBody 就地展开；dev_unlocked 已清 false（轻量重启验证过，设置页回默认隐藏态——footer 连点 7 次可重新解锁）

## 审计三层视图 + 历史清理报告（2026-10-13 深夜，f442aba+新车 61399174）

- **三层视图**（console.js）：层 1 日汇总（📅 日期+分类计数）/层 2 同分类连续区间（起止+持续+条数）/层 3 原始行——嵌套 details 零交互代码；分类映射八类；/api/proactive/recent 加 limit 参数（1-5000，面板传 2000 跨天聚合）
- **历史清理报告（只读未删，等拍板）**：现状 2000 行 → 按天+分类区间保留首尾 ≈ **28 行**（14 区间，省 1972 行）；明细=10-12（深夜 313/按住 760/4 组 fire+cooldown 循环）/10-13（深夜 91/按住 670）——旧车每分钟记录的证据密度全在区间首尾里可再模拟
- 部署：新车 61399174（23:38 三进程+health ok+前端上车 grep 2）
- **历史清理定论（用户拍板）：不清**——区间视图已解决可读性/143KB 成本极低/LOG_KEEP 自动淘汰/原始流水=改进前后考古样本（10-12 深夜 4 组 fire+cooldown 循环=旧车行为铁证保留）

## UI 修复批 2（2026-10-14 凌晨，d040e3e 后续 cbcc3c7 后续=本笔）

- **终端记录一步搬入+tab 栏退役**（用户拍板"一步到位不留中间态"）：🧰 面板「终端记录」卡实装（switchChatTab('terminal')+closeToolsPanel，渲染链复用）；.chat-tabs/按钮/CSS/死常量全删（对话常显；null 守卫死代码不留）；terminal-back 返回回路补齐；设置卡入管理分类（设置页统一经面板）
- **开发者模式可见性诊断**（用户真机报告"未连点却可见"）：生产 ui_pref.json **dev_unlocked=True**（B2c 验收时用户自己连点解锁+B2c 拍板"永久无重置路径"）——**诊断 A 成立非逻辑缺失**；处理等拍板：清掉（重置 false→走新 footer 连点解锁=新机制闭环演示）或保留（尊重 B2c 拍板）
- **测试时间脆弱两型修复**：跨日固定时刻（today_fire_count 按天统计）+凌晨 quiet_hours 拦 fire——动态 now+mock 抑制

## 开发者模式视觉反馈+折叠（2026-10-14 凌晨，91b2b89+新车 C70B22BC）

- **B+D+折叠三件**（拍板落地，C 图标砍）：解锁 toast 文案改 🔓；footer 版本号解锁后浅橙背景块（applyDevBadges F5 恢复链同步）；dev-switch-row 改 details/summary 折叠（默认收起）；B2c toast 文案锚随拍板更新
- **部署连带说明**：构建=HEAD 全量——tab 退役+批 2 面板卡（记忆查看/家电列表实装）全部随之上车（生产车现=全功能最新）；绕锁 420 拷+01:02 三进程+health ok+前端上车确认
- **真机验证留用户**：footer 连点 7 次（V1.0.4 底色变浅橙块+🔓 toast+设置页 details 展开）；🧰 面板全功能（主动性三层审计/记忆查看/家电列表/终端记录）

- **测试隔离修复（01:3x 实锤连环）**：dev recent_actions 被 pytest 内真跑 HA 心跳污染（测试进程心跳线程开真测试灯×3）→ChatApiTests 断言全挂；HistoryApiTestsBase 基类统一 RECENT_ACTIONS_FILE 注入 tmp 修复（Onebot 类先例对齐）；**方法论入 thinking_notes：测试真跑外部副作用=环境级隔离必备**

## Hindsight 共享记忆库（2026-10-14 凌晨，慢跑模式完成）

- **全链打通**：F 盘 venv（C 盘零占用——C 仅剩 9.7GB 的关键决策）+ hindsight-api-slim[embedded-db=pg0] + ollama/qwen2.5:1.5b + HF 镜像下载模型 216MB；服务 127.0.0.1:9077 healthy（start.bat 拉起）
- **ZCode 接入**：hindsight-zcode hook 装于 ~/.zcode/hooks/hindsight/（retain/recall/session_start）；settings.json bankId=**xiaoju3-project** apiUrl=9077——**重启 ZCode 后 hook 自动 retain/recall 生效**
- **六文档导入 6/6 OK**（retain async 抽取）；验证：并行模式命中 ✓；专利筛查/XUNandxiaoju3 细节未命中=**Hindsight 抽"结论条"不保真数字细节的行为特性**——使用建议=关键事实存独立小条目
- **报告**：F:\Hindsight\SETUP_REPORT.md（慢跑模式完整报告：五坑/常驻方案/明天继续点）
- **待明天**：①重验召回 ②ZCode 重启验 hook ③服务常驻方案拍板 ④DeepSeek 代持开始用

## Hindsight 常驻手动方案配套（2026-10-14 晨，用户选 B 三件齐）

- **桌面快捷方式已建**：C:\Users\Xun\Desktop\启动 Hindsight.lnk → F:\Hindsight\start.bat（工作目录 F:\Hindsight；WScript.Shell 经 EncodedCommand 建，绕 Git Bash 中文编码坑）
- **双击验证 PASS**：os.startfile（=双击同语义 ShellExecute open）拉起 → **35s health ok**；新进程树 cmd←父已退出，链上零 ZCode 祖先=真解耦；start.bat 本体无需改动（可选优化项确认不需要）
- **旧 ZCode 挂载树风险实锤并清除**：原 daemon 链=bash.exe(ZCode)→cmd /c start.bat→hindsight-api.exe→python×2——会话结束/后台回收即杀树风险；taskkill /T 清除后由双击实例接管
- 辅助脚本：_hindsight_shortcut.py + _hindsight_launch_verify.py（坑：PowerShell 输出 GBK，python text=True 按 UTF-8 解码炸——只炸读输出不炸产物）
- 服务现状：在线（模拟双击实例）；**桌面 cmd 窗口=服务本体，关闭即停服**；运行中再双击=端口占用报错窗（无害）

## 薄交接层 BOOT.md（2026-10-14 晨，DeepSeek 路由文档三件齐）

- **_dev/BOOT.md 新建**（303 汉字/923 字符）：定位/记忆坐标（9077+bank）/三动作用法（存查想）/关键路径/8 条基础规矩/边界声明；**exclude 已收（check-ignore 实锤零 git 暴露）**
- **PROJECT_CONTEXT.md 头部加引导**（.bak-20261014-boot 在案）：新会话先读 BOOT.md，细节再查本档或 Hindsight
- **recall 验证=细节未命中（特性第三次实锤）**：查"BOOT.md 里写了 Hindsight 地址吗"召回 23 条全泛相关零地址；BOOT.md retain 入库（59→60 条）复验仍零命中——抽取链把 9077 抽丢成骨架条（output 101 tokens）；**结论：数字/URL 细节的正确载体=文件本身（BOOT.md 粘贴给 DeepSeek），不是 Hindsight；BOOT.md 已补"已知限制"行**
- 验证脚本：_hindsight_recall_test.py / _hindsight_retain_boot.py（坑再证：Git Bash curl 传中文 JSON 必炸 body parsing，走 python urllib）
- ~~库里 boot_md 骨架条 1 条留观未删~~ **收尾（同日续）**：boot_md 骨架条已删（memory 级无 DELETE，走 DELETE /documents/boot_md 连带删 1 条，库 60→59）；BOOT.md「已知限制」行换用户版措辞（"字面事实直接阅读；Hindsight 只记语义结论查数字会落空"，.bak-20261014-wording 在案）

## #319 批 1 收官 + set_call_name 追查 + 1.0.5 Release 确认（2026-10-14 晚）

- **批 1 已推平（72765fb）**：soul_manifest.py（三档清单 default deny+SQLite 侧车跟随主库档位）+migration v2（export v2=soul_meta sha256/integrity 前检/include_extensions 开关；import=篡改拒收零落盘+导入前全目录自动备份）+验收门过（跨目录迁移行为等价五连：身份/记忆召回/关系值/称呼/ui_pref 位置）+29 锚全仓 2302→**2331+4**；**v2 尚无指令/面板接线（仅 CLI 能力），批 2 回写端点等拍板**
- **set_call_name 孤儿行 bug**：已修（users 行同步补）+影响面追查=无影响（零接线/生产 4 天零触发/tone_preference 全 None/history 零命中三重实锤）；坑库 **#29 悬空函数**（1f7cc91，库 29 条）
- **v1.0.5 Release 全闭环确认（只读）**：tag 本地+远程=6278678 ✓ / Release Latest 2026-10-14T08:08Z ✓ / 资产 xiaoju3-1.0.5-setup.exe 72,487,225B sha256 双端一致 **b1f0535c…** ✓；生产 .env：PERSONA_ENABLED=1（139 行）+CHAT_TYPING=1（140 行）均已生效（mtime 13:19 < 进程 15:39）
- 四冒烟复测清单已交用户手测（修 B+裸 JSON/persona 斗嘴/打字机分段/常规闲聊）

## 修 B v2 三修已提交+待重启验证（2026-10-14 晚）

- **e274e28 三修已推平**：修1 问句升正文（澄清反问）/修2 幻觉检测+消毒扩 action 键值形态/修3 QQ 沉默改兜底（_sanitize_qq_reply 两发送点）；+16 锚；19:27 实锤语料回放 PASS
- 测试基线账：2331+16=**2347+4**（含三修+16 锚；2346 过+#303+旧接线锚=2348 收集账，锚修后=2347 过）（#303 既有除外）；全仓后半程受环境挂死（import openai 间歇挂=AppData user-site 读争用，系统服务级）未能出终数——**重启后复跑全仓定版**
- **待用户重启电脑**（清系统服务态+失控进程 25748）→ 重启后：全仓复跑→bump 1.0.5.1→构建部署→真机重测修 B→tag+Release

## 1.0.5.1 收官（2026-10-14 深夜，不打 tag）

- **修 B v3 A+B 上车+真机验毕**：控制台三针 3/3（裸删+共现→云端诚实拒绝带能力清单/双字→云端拒绝/闲聊零变化）+**QQ 真机三连全过（私聊 3/3+群聊 3/3，用户确认）**；全仓 **2355+4**（#303 除外全绿）
- **版本策略拍板（已入 AGENTS.md 提交纪律）**：1.0.x 内部补丁不打 tag/Release；下个 Release=**2.0 里程碑**（护城河七条均值 ≥85%）
- 生产车 15a6f53f（421 拷+2 VCRUNTIME 跳过双端同版；schtasks 拉起 health ok）；坑库 31 条；Hindsight retain v1051 条目在库

## 人格演化批 4 · UI 卡收官（2026-10-15，ffb2f21 本地待推）

- **纯状态展示批落地**：设置页人格分区（D1）——persona_state 聚合+三路由（写门 Lv3=D13）+前端卡片（权限预检置灰=用户补 requirement；用户化翻译全行为层，临床/标签词锚负向锁死）；+11 锚全仓 2355→2366+4；category 列（维护单分类）+2 锚 →**2368+4**
- **坑库 #32/#33**（实施中自捕当场修）：注册期绑定函数名（settings_api 其余路由未扫→待办 #331 专扫）/竞态守卫跨模块复用；静态锚注释误触→thinking_notes 待验证假设（攒着）
- 生产车仍 15a6f53f：**UI 卡未上车**（随下次 rebuild+部署，验收清单已交用户）；待推：ffb2f21+收官 docs
