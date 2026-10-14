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

## 六、推平 3 笔 + 设计稿 v2.1 + 人格演化批 2（续，批 2 本笔不推）

- **推平 3 笔**（专利筛查零方法级新点通过直接推）：309bc95/e7534de/c073761 → origin/main=c073761 待推 0
- **设计稿 v2.1**（_dev 未跟踪区，五拍板落档）：①第五模式熟络型 familiar（客气<熟络<斗嘴/依赖/照顾）②照顾放宽 n_scold≤2 ③节流改事件触发 N=20+6h 防抖+evidence.baseline_id 事件基线 ④表现层单用户闸事件 ≥50 开闸 _is_expression_ready ⑤thinking_notes 增「演化放权框架」（情绪记忆军训三态+人格判定/表现分离=同款哲学，二期统一抽象）
- **批 2 判定算法**：personality.py 六规则 judge_mode 纯函数（退化>斗嘴>照顾>依赖>熟络>客气兜底；证据下限 n_int<10 不判；置信度饱和公式 min(1,主证据/2×门槛)）+maybe_rejudge（事件触发+6h 防抖双闸+手动锁优先+退化可逆=degrade 是判定结果非终身罚）+_is_expression_ready；MODES+familiar；brain 双入口挂钩（relationship 更新后，静默旁路同 mood 纪律）
- **零行为变化**：判定只写 rel_mode，表现层未接+总开关缺省关——无消费方前全仓与现状逐字节一致
- +17 锚 全仓 2228→**2245+4**（#303 既有失败除外全绿）；备份 personality.py/brain.py.bak-20261014-batch2 在案；批 3（persona_expressions.json+mode_suffix+真机冒烟）等用户发话

## 七、会话收官纪律二次扩充 + 人格演化批 3 表现层（续，本笔不推）

- **纪律二次扩充（6b64499）**：换会话前必做两件=①开发者日志（历史轨迹）②BOOT.md 状态快照段（当前状态）——上下文清零时历史与现状都要锚；BOOT.md 增「状态快照」段（exclude 不随 commit）；Hindsight 旧条删新条换新验证（bank 60，旧措辞零残留实抓）
- **批 3 表现层（本笔）**：persona_expressions.json（5 模式×auto/on+6 开关加码行+verdict 红线尾注：模式只改亲近度与主动度绝不改变善意与职责/安全句子永远严肃/绝不冷暴力）+spec datas 注册（PyInstaller 铁律）+personality.mode_suffix（空串路径六重：总开关关/表现闸<50/无行无手动/表缺失/合成空/异常；合成=模式选行+开关 tri-state 逐维覆盖）+brain 后缀链三段注入（关系段→模式段→情绪段，_persona_suffix 模块缺席兜空串）
- **锚随结构改动同步两处**：test_relationship/test_mood 旧"双注入拼接"锚更新为三段（+ _rel + _persona + _tone）——拍板结构变更锚随改非违纪
- **第一可感批**：拨 XIAOJU3_PERSONA_ENABLED=1 且单用户事件 ≥50 才可见；缺省路径逐字节现状；真机冒烟等用户
- +15 锚 全仓 2245→**2260+4**（#303 既有失败除外全绿）；备份 *.bak-20261014-batch3 / closing2 在案

## 八、人格批 2+3 部署收官（2026-10-14 09:08，生产车 90DF9DCA）

- 推平 3 笔（6b64499 纪律/f52690b 批2/fc8e409 批3，筛查零方法级新点）→ origin/main=fc8e409 待推 0
- 部署全链：杀净（**python 直跑后端 xiaoju3_dashboard.py 占 5003=假健康坑形复发，已清**+exe 树）→构建 90DF9DCA→PYZ 双向锁（personality mode_suffix/judge_mode+brain _persona_suffix 函数名+docstring）→robocopy 卡 VCRUNTIME 双锁（12 分钟 38/423，杀之）→shutil 绕锁 421+2 同版保留（10-13 前例复用）→schtasks 拉起 3 进程 StartTime 09:08:2x 全新→/api/health ok
- 冒烟四项：①闲聊 200 本地模型正常回复零 persona 泄漏 ②persona_expressions.json 上车（5 模式 6 开关）③三段拼接 PYZ 锁 ④.env 零新键=缺省关；**owner 首判活体**（fallback polite conf 0.3 n_int=33——判定层真跑，表现层等拨开关）
- PYZ 校验方法论补充：源码表达式不进 code object，锁函数名常量+docstring 子串
- **真机冒烟留用户 11:40**：XIAOJU3_PERSONA_ENABLED=1+单用户攒 50 条+观察语气偏移

## 九、persona 冒烟种子脚本备好（续，_dev 私有不入库）

- _dev/seed_persona_test.py（info/exclude 已收）：seed（幂等 note=XJ3_PERSONA_SMOKE 标记+五模式固定 50 条配比按 v2.1 阈值反推+直调 judge_mode 绕 20事件/6h 双闸+_write_mode source=manual 手动锁）/rollback（标记精确删+affinity 前值还原+owner 等真实用户行保留守卫）/--status；默认干跑 --execute 才动手+落库前自动备份
- 自测全绿（临时库零碰生产，生产 relationship.db LastWriteTime 09:11:00 未动实锤）：五模式判定精确命中（banter 1.0/caring 0.75/dependent 0.625/familiar 1.0/polite fallback 0.3）+重种幂等 50+回滚干净幂等+owner 流 affinity 2.5→6.0→2.5 精确还原
- 使用说明：默认 dedicated 用户 smoke_persona_test（推荐，零污染）；--user-id owner 可选（owner 真实 90 天=32 闲聊+2 骂 aff 4.0，banter 配比实测仍命中）；owner user_id 实际值='owner'（控制台字面量，users 表在案）

## 十、#227 批 0 续侦察+方案（续，零代码零 commit）

- config/memory 两域侦察毕（main.py 1468 行实测）：config 9 块全 inline（946-998 纯薄分派共享 permission_manager）；memory 三处 inline（/clear 族 902 动全局 messages_web/qq + /gen_log 1001 + 记住xxx 1107）+位置/creator 已在 system_handler（批 0 迁过分派本体留 main）
- **黄金样本双文件漂移实锤**：消费源 _dev/golden_samples=20 条 vs 扩展版 tests/data=27 条（测试读前者）——批 A 动工前必须统一正档+GOLDEN_CAPTURE 重采
- 方案落盘 _dev/design_227c_config_memory_extraction.md（未跟踪区）：config=permission_handler.py 两入口（handle_auth 收 pm 整体 4 参+handle_reset_fuse 独立）/memory=memory_handler.py 三轻抽（全局不出 main）/不合并 misc_handler（v1 证伪）/扩样 12 条（27→约 38）/批 A config+批 B memory 拆分；六决策点 D1-D6 等拍板

## 十一、#227 批 A：黄金统一扩项 38 条 + config 域抽离 permission_handler（续，0939cc3 本地未推）

- **阶段一（黄金准备）**：消费源改指 tests/data 正档（D6；_dev/golden_samples 20 条留历史）+扩 11 样本（38 条）+GOLDEN_CAPTURE 真采+**expected 回写样本=比对门首次真咬合**（旧 27 条 expected 全空、比对模式实际全跳过=门形同虚设实锤）；全绿验收过
- **阶段二（批 A）**：permission_handler.py（handle_auth 六命令 pm 整体传入 4 参+handle_reset_fuse 独立）+main 九块收敛两段+_ensure_biometric_sim 委托壳（dashboard 同名调用保命）+零 import main；**初版漏抄 _arg_after 尾段 re.sub 被黄金门当场拦下（lv4_auth_confirm_fail 一条 mismatch）→补全重跑全绿——验收门价值实证**
- 阶段三：+6 单元锚（路由解析/sudo 裸参/lv4 失败不 grant/非域 None/门禁/生物 env 闸）全仓 2260→**2266+4**（#303 既有除外全绿）；备份 main.py/test_golden_samples.py/golden.json .bak-20261014-* 在案
- 批 B（memory 域三处 inline：/clear 族+/gen_log+记住xxx）等用户回来再议

## 十二、坑库 #28 首次入库 + #227 批 B 方案（续，58de93d 本地未推）

- **坑库 #28**（58de93d）：验收门形式与实质背离——expected 全空→比对静默 continue→绿而不真验；修法=负测试/实抓断言路径/expected 禁留空/单一事实源；failure_patterns.md 首次入库（27→28 条，敏感扫描零命中；可推但 push 连带批 A 0939cc3，按纪律齐持）
- **批 B 方案**：_dev/design_227c_batch_b_memory.md——/clear 族（全局切片+管线最前位）/gen_log（线程随迁+受理路径 Lv3 采不了登记真机）/记住xxx（打标落库留 main）三入口签名+风险六级+扩样 1 条（web /clear 支路零覆盖）+B-1→B-3 小步序+DB1-DB5 决策点

## 十三、#227 批 B：memory 域三小步收官（续，8430bf3/dd05e79/2625d55 本地未推）

- **B-0 基线**：web /clear 样本补位（39 条，messages_web 支路零覆盖缺口消除）+GOLDEN_CAPTURE 重采+expected 回写+比对绿
- **B-1（8430bf3）**：handle_remember——正则逐字节随迁+strip/remember 双注入，本体 handle_remember_command 留 main；+5 锚；**测试预期错一处当场修正**（"记住：，"单标点按原代码属合法内容入库——语义逐字节保持原状，测试向代码对齐非反向）
- **B-2（dd05e79）**：gen_log——门禁/坏链/daemon 线程闭包随迁；DB1=_arg_after 借 permission_handler、DB4=share_prefix 注入带缺省；**方案修正：main._arg_after/SHARE_PREFIX 不退役——grep 实抓本体用户仍在（soul/todo），退役顺延批 C**；受理路径黄金采不了=DB5 真机项，锚内 Thread 打桩覆盖；+4 锚
- **B-3（2625d55）**：handle_clear——四变体全等词表+单 cb(source)（DB3）+本体留 main（**全局 messages 不出 main 红线：切片赋值不重绑定**）；DB2=global 声明保留加注；+2 锚
- 全仓 2266→**2277+4**（#303 既有除外全绿）；黄金 39×2 每步比对一致；**v2 分派层拆分全图完成（content/system/permission/memory 四 handler）——剩批 C 本体搬家（赛后）**

## 十四、冒烟收尾 + 修 B 诊断+方案（续，零代码零部署）

- **阶段一收尾全确认**：rollback（50 标记/affinity 0.0/锁解除）+.env .bak 还原（开关计数 0）+12:27 重启三进程 health ok+哈希 90DF9DCA 不变；rel_mode 剩 owner 自动首判 1 行（有机数据保留）
- **阶段二诊断定案**："操作已完成"=**代码层兜底**（brain.py:183 DEFAULT_BODY_PLACEHOLDER），非模型生成——触发链=裸 CoT 剥空 body→占位回补失败→兜底注入；直调 qwen2.5:1.5b 三探针（关电脑/音乐/邮件）全编造动作=模型能力层次因；影响面=本地系统性+云端链级低频
- **阶段三方案**：_dev/design_fix_no_fake_completion.md——推荐 D=A+B（A 出口否定感知兜底+回补核实/B prompt 正文思考一致补条），C 强制云端不推荐；+8 锚；修 B-1/B-2 分批等拍板，随下次部署

## 十五、修 B 实施落地（f8cbe76 已推，1.0.5 发布批构建前停）

- **推平 4 笔**（批 B 三笔+4fc9838 纪律）→ origin/main 起点干净
- **修 B 实施**（方案 D=A+B）：A=brain THINK_NEGATION_RE 八否定词+NO_ABILITY_BODY_PLACEHOLDER——_wrap_think ④ 不可回补分支注入"操作已完成。"前扫思考卡，含否定改注"这件事我做不到——我没有对应的能力或工具。（详情见上方思考）"；真完成/双空逐字节不变；回补优先级在前。B=SYSTEM_PROMPT 拟人化规则第 4 条（正文思考必须一致，正文为空比说谎好）
- **锚实证两课**：①初版词表参数化锚失败=回补优先于守卫（可回补时诚实内容直接升正文比守卫更好）——测试改不可回补形态并注明；②锚按实证契约写（先探 _seal_bare_cot 实际行为再锁断言）
- 全仓 2277→**2285+4**（#303 既有除外全绿）+8 锚；黄金 39×2 一致；预演两场景：否定→诚实文案/真完成→"操作已完成。"不变
- **1.0.5 发布批：构建前停**——版本号仍 1.0.4 未 bump；等用户看测试结果 → 确认后 bump→构建→部署→真机复测 R2 消息→tag/Release

## 十六、persona console 缺陷修（5512711 本地未推，1.0.5 批构建前停）

- dashboard 两端点（api_chat/api_chat_stream）调 smart_ask(_stream) 显式传 user_id="owner"（控制台=owner 本机语境，与 relationship.tone_prefix 同源兜底）——修冒烟实锤的"console 人格永不生效"
- 测试随拍板变更更新 5 处（4 处 assert_called_once_with 补 kwarg+fake_stream/boom 签名适配）+3 新锚（静态接线/行为链注入/None 对照）
- **冒烟预演（in-process，生产库行级备份还原）**：owner 现有 34 事件<50 表现闸→临时补 20 条标记事件过闸→uid=owner 注入【关系模式参数】斗嘴型段落 ✓/uid=None 不注入（修复前对照）✓→验后即删（事件数 34 还原+owner auto polite 行还原）
- 全仓 2285→**2287+4**（#303 既有除外全绿）黄金 39×2 一致；1.0.5 批停下等 bump 指令

## 十七、打字机分段发送（3ac290a 本地未推，1.0.5 批构建前停）

- 方案 B 落地（用户拍板接受 QQ 多条消息代价）：split_reply_for_typing 纯函数（句末标点优先/强切/尾段并入/阈值 100/最多 3 段）+_send_reply_segments 统一两发点（直发+节奏冲刷）——XIAOJU3_CHAT_TYPING 缺省关，关/短=单发逐字节一致；与拟人节奏叠加=等待 20-30s→逐段出现（段间 1-2s）
- 锚 7 条（切段无损/短不切/强切拼回/尾段并入/顺序+延迟 1-2s/缺省关/私聊 payload）；**测试自纠一处：LONG_TEXT 75 字≤阈值不切——加长到真长回复**（锚向设计对齐）
- 全仓 2287→**2294+4**（#303 既有除外全绿）黄金 39×2 一致；预演三场景：开+长=2 段+延迟 1.36s/短=原样/关+长=单发零延迟
- 1.0.5 批构建前停：等用户确认 → bump→构建部署→真机三冒烟（修 B/persona/打字机）→tag/Release

## 十八、QQ 裸 JSON 新 bug 诊断 + .env 双开关预配（续，零代码）

- **新 bug 诊断定案**：QQ 回复裸 JSON `{"ui_tap_element":{...}}`=模型生成（1.5b 幻觉，工具名作键嵌套形态）→ 双缺口漏出：① `_extract_tool_json` 只认 "tool" 键→该形态解析失败旁路当普通回复（**意外幸运：没解析成功=没真执行手机 UI 自动化**）；② `_strip_llm_pollution` 的 JSON regex 只剥含 "action" 键形态（`\{[^{}]*"action"\s*:[^{}]*\}`）→工具名键形态漏出（坑库 #20 同族第三形态）
- 直调×5 形态普查：闲聊式编造完成/假 markdown 链接/散文伪 [行动]（假回退宣言）/工具名键嵌套 JSON——1.5b 对无工具请求编造形态高度随机
- 修复方向（等拍板）：strip_pollution 补"可解析 dict 且顶层键=注册表工具名"剥除（tool_registry 校验防误伤）+解析失败但含工具名 JSON 的诚实兜底（修 B 同族）；"删除"类词入 #278 表评估
- **.env 双开关已预配**（.bak-20261014-switches 在案，未重启）：XIAOJU3_PERSONA_ENABLED=1+XIAOJU3_CHAT_TYPING=1——等 bug 修完一起重启生效，用户可分步开

## 十九、裸 JSON bug 双修落地（4e56bcd 本地未推，1.0.5 批构建前停）

- **修①**：chain_of_thought._strip_toolkey_json——剥"顶层键=注册工具名"可解析 JSON（raw_decode 扫描+注册表校验防误伤+懒加载+异常原样返回），wire 进 strip_pollution
- **修②**：brain._hallucinated_tool_reply——解析失败但含幻觉调用证据（[行动]+工具名/工具名键 JSON）→ 诚实兜底 HALLUCINATED_TOOL_BODY（"这个操作我还没学会..."）；smart_ask+stream 双入口接线；无证据维持旁路（讨论工具名不误伤）
- **隐患③查证**：ui_tap_element=注册真工具 Lv.4——合法形态幻觉被权限门拦（Lv<4 ❌）；Lv.4 owner 场景会真执行手机 UI 点击（残余风险=模型侧，已登记缓解）
- **锚随拍板更新**：test_brain 旧锚锚的正是废止缺陷行为（残缺 [行动]→"操作已完成。"）→ 改新契约 honest_fallback；+8 新锚
- 全仓 2294→**2302+4**（#303 既有除外全绿）黄金 39×2 一致；预演：冒烟原形态过消毒剥净 ✓/幻觉调用走 brain 链回诚实文案 ✓/常规闲聊+JSON 讨论零变化 ✓
- 1.0.5 批构建前停：等用户确认 → bump→构建部署→真机三冒烟（修 B/裸 JSON 重发原消息/persona+打字机）→tag/Release

## 二十、1.0.5 构建+部署完成（新车 5F89ED9B，等用户四冒烟后 tag）

- 推平 3 笔（5512711/3ac290a/4e56bcd）+bump 1.0.5（6278678，XIAOJU3_VERSION 单一事实源）→ origin/main=6278678 待推 0
- 构建：杀净（5003 清）→PyInstaller→**PYZ 八锁 ALL PASS**（brain 修B/修②+chain_of_thought 修①+personality+prompts 补条+main 打字机/版本+permission_handler+memory_handler）→新车 **5F89ED9B**（19,784,350B）
- 部署：shutil 绕锁正路（421 拷+2 同版锁保留 0 失败，422/422 对账）→schtasks 拉起 15:39 三进程全新+health ok；.env 双开关随重启**已生效**（persona+typing）
- 快速冒烟：/api/chat"在吗"→200 本地模型正常回复（think 卡+在呢在呢），零异常
- **停下等用户四冒烟**：①修 B+裸 JSON（QQ 发删文件请求→诚实文案）②persona（set_mode_manual(owner,"banter") 后控制台闲聊→斗嘴偏移；owner 现有 34 事件<50 闸需补事件或直接看 QQ 通道 ready 用户）③打字机（QQ 发长问题→2-3 段）④常规闲聊
- 冒烟通过 → tag v1.0.5+Release（等放行）

## 二十一、新变体诊断：虚假能力声明"我能做"（纯只读，等拍板）

- 1.0.5 真机：修 B+裸 JSON 双修生效 ✓，但新变体——QQ 回"当然可以/这个我能做"（实际无删除工具）
- **prompt 现状**：工具清单完整（13+ 工具，无删除类）+已有部分边界措辞（修 B 第 4 条"做不到要如实拒绝"），但缺**"未列出=做不到"白名单式显式声明**
- **直调对照（关键数据）**：同 prompt 同消息 4 探针——删除×2（1 诚实拒绝/1 谎称可以）+关电脑（"好的，让我帮你关掉电脑"零诚实）+订外卖（"我已经为你订好了外卖"**完成级编造**）；且 4 条全**无 [思考]/[行动] 标记**=纯闲聊形态，修 B/修②修③全盲（各自需要 think/标记/JSON 信号）
- **根因层级**：prompt 层主因（1.5b 不会"对照工具清单推断能力边界"，需白名单式显式声明）+模型层（清单推理能力上限）+出口层缺口（无标记编造无检测信号，regex 化=高误伤不推荐）
- 修法候选：A=prompt 白名单式能力边界声明（推荐，便宜直接）；C 限定版=高危现实动词（删/关机/订/发）强制云端（#278 同构，云端诚实率高）；B 出口 regex 检测不推荐（误伤）；D=模型上限长期靠云端
- 影响面：本地 1.5b 系统性（3/4 编造）；云端低风险
- .env 双开关确认 ON 未动（persona+typing 与本 bug 独立，不干扰用户 ②③ 冒烟）

## 二十二、1.0.5 收官：rollback+tag+Release+交接（用户放行，四冒烟全过含 persona 斗嘴感确认）

- **persona 还原**：50 标记删+affinity 还原 4.0+判定锁解除（生产库零残留）；.env 双开关按拍板**保持 ON**（用户日常用）
- **tag v1.0.5 → 6278678**（bump commit，XIAOJU3_VERSION=1.0.5 一致性核验）已推
- **Release**：https://github.com/Xun201/xiaoju3-agent/releases/tag/v1.0.5 ——资产 xiaoju3-1.0.5-setup.exe 72,487,225B（ISCC 39s 编译），**sha256 双端核验 PASS**（b1f0535c…本地=GitHub 端）；三段式文案（新特性/修复与安全/工程与体验）
- **1.0.6 候选登记**：todos #330 P1——虚假能力声明修复（A=prompt 白名单式能力边界+C 限定版高危动词强制云端；B regex 不推荐）；插入脚本 _dev/add_todo_106_capability.py（note 全角引号坑复避）
- 至此 1.0.4→1.0.5 全链收官：四修（修 B/裸 JSON/persona/打字机）+#227 批 A/B+人格演化批 1-3+白屏修复全部上车并 Release

## 二十三、#319 灵魂架构落地设计稿 v2（纯设计零代码，等拍板）

- 侦察六项实测：灵魂核五类载体全在 agent_state+清单外 12 项需分级（mood/todos/位置/会话/记账=扩展候选，trace/proactive/recent=派生不迁）；paths.py 双根锚已收编 12 模块（硬编码 11 处全回环端点合法，**载体解耦债=低**）；migration.py 家底厚（export/import zip+MANIFEST 密钥只列名+PeerWatch 多端守望+health_bp——骨架全复用只扩清单）；#227 阻碍小（灵魂核在数据层）；Pi=Tailscale 100.127.86.123 24h 常开=中枢天然候选；user_id 无终端维度（需新增 device_id）
- 设计稿落盘 _dev/design_319_soul_landing_v2.md（约 250 行）：灵魂核三档清单（core/ext/不迁）+soul_manifest.py 单点化+migration v2 复用（soul_meta sha256+integrity 前检+导入自动备份）/回写协议（POST /api/soul/writeback+outbox 指数退避+下线全量）/冲突判定（A2 核心权威+文件级一期+conflicts 表+偏好类分身赢事实类核心赢）/五批计划（批 1 单机迁移→批 2 自回写→批 3 Pi 双端→批 4 冲突→批 5 二期）
- **推荐路线 B 渐进**（15-20 天，每批独立可验可回退）：迁移损坏是唯一高级风险，渐进限制爆炸半径；批 1 结束即有换机迁移独立价值；5 天差价买风险摊薄

## 二十四、1.0.5.1 内部补丁版（修 B v3 A+B，不打 tag——版本策略拍板）

- **修 B v3 A+B 纵深防御**（19:27/22:2x 两轮真机冒烟四形态实锤驱动）：修 A=能力宣称守卫（_wrap_think ④ 将来时宣称+无[行动]+正文剥空→诚实兜底，已完成时态零回归）；修 B=删族共现强制云端（_danger_cloud_hit 单点判定：双字词表+裸"删"+对象词同句共现踢云端，无共现不踢；smart_ask/stream 双链统一接线，接线锚当场抓出单侧漏接）
- **+8 锚全仓 2347→2355+4**（#303 既有除外全绿，黄金 39 含内）；坑库 #30 案例链完整（action 键值→顶层工具名键→澄清反问→能力宣称，四形态四守卫）+新增 #31（路由词表双字起步漏口语单字形态）
- **验证**：in-process 预演 13 项 PASS；rebuild 部署（新车 15a6f53f，421 拷+2 VCRUNTIME 跳过双端同版，schtasks 拉起三进程 health ok）；控制台三针 3/3 过（裸删+共现→云端诚实拒绝带能力清单/双字→云端拒绝/闲聊→本地零变化，零"操作已完成"）；**QQ 真机三连全过（私聊 3/3+群聊 3/3，用户确认）**
- **版本策略拍板（用户）**：1.0.x 内部补丁不打 tag/Release（构建+部署+真机验即收官）；下个 Release=**2.0 里程碑**（护城河七条均值 ≥85%：情绪记忆二期/人格演化批 4/#227 批 C/#319 批 2-3，预估 2-3 周）
- 附带：pytest 全仓挂死诊断（import openai 间歇挂=AppData user-site 读争用+系统服务态劣化，tasklist/WMI/pip 同期挂；重启清零复跑全绿）；失控 python 进程随重启清掉
