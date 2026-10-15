# 开发者日志 20261015（日期快照式，按提交逐条）

## 一、深夜批收尾（接 10-14 会话）

- **深夜思考批落两处**：thinking_notes +3（密码本/落子无悔+拍视频/幸存者偏差）+概念仿生·手性两增强（抄规则不抄外观/#319 不可镜像判据）；#319 设计稿新增「§十 灵魂物流框架」六条（京东类比三视角/快递员令牌+审计+回滚/**冲突判定=重放非选谁赢**/迁移粒度=派半个人/并发=复制+睡眠对账/outbox 满=信号检测）——批 2-4 语义基准；roadmap_2.0.md 落盘（2.0 总图：四块+12 决策点全带推荐项，均值账 66.9%→88.6%）；thinking_notes 三笔推平（e4ff6e0/4f493cc）
- **1.0.5.1 收官（不打 tag）**：changelog（10-14 档二十四节）+PROJECT_CONTEXT #228+BOOT/STATE 快照+AGENTS.md 提交纪律增**版本策略**（1.0.x 内部补丁不打 tag/Release；2.0=里程碑 Release）+Hindsight retain v1051_closing（复验命中）——收官 docs e126554 推平

## 二、人格演化批 4 · UI 卡落地（今日主线，ffb2f21）

- **设计稿先行**：design_271_batch4_ui_card.md 草案→用户审后放行（D13=写门 Lv3；**用户新增 requirement=前端渲染前权限预检，未达 Lv3 置灰+提示不渲染可点 UI**）
- **实施**（7 文件 +436 行）：后端=personality.persona_state 纯读聚合（模式/六开关/就绪闸/相处次数，异常静默）+settings_api 三路由（GET state 自带 level；POST switch/manual_mode 写门恰 Lv3）；前端=index.html persona-card 容器+CSS+console.js 翻译表（五模式行为描述主文案/六开关三态界面文案/"跟着感觉走"=auto）+loadPersonaCard/renderPersonaCard/postPersona+**权限预检置灰**
- **实施中自捕两坑当场修**：①路由注册期绑定函数名=测试 patch 失效+可能误碰真库 → 模块晚绑定（成坑库 **#32**，范围标注=settings_api 其余路由未扫，已开待办 **#331** 单独专扫）；②persona 卡复用 settingsFetchSeq 竞态守卫会挤掉设置列表渲染 → 独立 personaFetchSeq（成坑库 **#33**）
- **锚 +11**（聚合 4/路由 4/前端 3，含翻译红线负向断言+出界铁律锁：人格函数体禁现三态阶梯/checkpoint/autonomous/report）；全仓 2355→**2366+4**（#303 既有除外全绿，黄金 39 含内）
- 静态锚扫描含注释误触一事 → 按拍板记 thinking_notes「待验证假设」攒着（不升级为坑，再犯一起定规矩）
- 拍板台账：D1=设置页人格分区/D2=A 只放斗嘴触发（触发层留后续批）/D3=A+B 结构留好词表不激活/D13=写门 Lv3

## 二.5、待办分类「维护单」+ UI 设想登记（用户拍板）

- todos 表新增 **category 列**（幂等补列两处 init+锚 ×2，''=普通待办）；**「维护单」分类定义=独立可做/不阻塞主线/修完就了事的小活**，#331（settings_api 路由绑定专扫）归入为首例；UI 先按现有样式暂不特殊处理
- **#332**（新，P3）待办面板小票式交互改造（外观层，2.0 冲刺三块完成后启动）：小票样式翻找/完成动画=撕掉+说明+淡出/撕掉进回收站 7 天后真删/远期面板方块化自由缩放移动

## 二.8、批 4 真机验收 + 两 bug 修复 + 部署（用户验收全过）

- **首轮验收两 bug 未过**（截图实锤）：①滚动卡死——persona-card 放 pane 直下=滚动容器外（关于条目同款 bug 复犯）；②点击后卡片消失+误报 Lv.3——POST 响应无 level 字段滑进置灰分支
- **修复**（ba8bca1，+3 锚强化 2）：容器移进 settings-list 滚动容器内+摘出-放回保护；POST 响应补 level+渲染 hasLevel 防御+错误路径 toast 保卡
- **部署**：rebuild → deploy_onedir.ps1 实跑撞 IO 锁 → shutil 预案扫尾（421 拷+2 VCRUNTIME 同版+零残迹审计）→ 新车 **e2e49a71** 三进程活体
- **复验全过**（用户确认）：滚动正常/点击卡片保留/三态循环+手动锁+恢复自动全生效/Lv.3 无置灰误报。**批 4 全毕（含真机）**

## 二.9、桌宠随设置族显隐 + 批 4 彻底全毕（复验过）

- **桌宠随设置族显隐**（顺手做档评估实锤：桌宠=控制台同页 DOM，desktop-pet.js 自建 .xiaoju-root）：CSS 一行 body.xiaoju3-settings-open .xiaoju-root{display:none}（复用缩球态选择器先例）+CHAT_TABS settings/keys enter 加类 leave 移类（**密钥页同族同藏**）；锚 +3（含 desktop-pet.js 零改动锁）；全仓 2371→**2374+4**
- **部署**：新车 **5e2f8ab7** 三进程活体；**复验全过**（设置进→桌宠消失/返回→恢复/密钥页同藏/滚动无回归）——**批 4 彻底全毕（含真机）**

## 二.10、情绪记忆二期全链上线（2.1/2.2/2.3 + 段落表接线，生产车 a04243dc）

- **2.1 段-记忆关联**（baead5e）：emotional_episode 补 memory_ids 列（幂等补列）+闭合时窗回填（跨库只读 memories；时区语义=memories.timestamp UTC/episode ts 本地，datetime(?, 'utc') 窗比较）；phase3 3.1 写入链打标简化为闭合窗回填（终态等价少一条写链侵入）；+2 锚
- **2.2 autonomy+disclosure**（d582797）：autonomy.py 演化放权三态阶梯通用状态机（promote N=5 未纠正升档累计 10 到顶/负面段零毕业/纠正 1 次退档 streak 清零/2 连纠直退/manual 钉档+审计流水/gate 矩阵）+disclosure.py 域实例（filter_memories 消费侧过滤/mute 任何 phase 丢/B3 7 天频次 boost 豁免/note_mention/note_correction）+mood.episode_associations 反查；+14 锚
- **2.3 注入分流+纠正入口+想听闭环**（cb15c87）：brain._inject_memory_context 分流（split_recall_rows 内容键候选表——recall 二元组无 id 适配，recall 本体零改动；普通行透传逐字节硬门+异常回退全量现状）；语气 D2/D3 行放数据围栏外（防注入铁律）；main.try_memory_disclosure_hook（F3 精确 4 短语+7 天内有提及双闸防误吞）三挂点（handle_message+api_chat+stream）；想听闭环 Q1=B 收窄版（pending_ask 24h TTL→main 层组回复零幻觉：正面展开/负面结果化守 C4）；Q2 失败审计落位；+10 锚
- **段落表接线**（d642deb）：heartbeat_loop 快照节拍顺带 flush_episodes（幂等去重）——**此前 flush 零调用方=休眠代码，不接线段永远不产生**；+1 锚
- **部署+复验**：生产车 **a04243dc**（421 拷+2 VCRUNTIME 同版跳过），段落表激活实锤（🧩 首次心跳新落表 10 段，episode_check_20261015.md）；memory_ids 空=历史回溯段时间语义（2.1 只对未来生效，非 bug）
- 2.3 真链路：触发前提=新段+关联记忆 recall 命中（段稀疏不追急，机制空转已由锚验证）；回归四连用户确认通过

## 二.11、深夜系统审计 + 自启清理闭环（用户四路拍板执行全绿）

- **自启动全景台账** startup_audit_20261015.md（四路实查 28 项五列：HKCU/HKLM Run+启动夹双级+计划任务；归属四类/建议三档；thinking_notes 沉淀复查纪律=基线+新装软件加行）
- **AMD 专项两轮修正**：首判"双驱动栈冗余"→硬件拓扑侦察（ASUS TUF A15 笔记本混合架构：780M 核显主控显示 2560×1440/4060 Laptop 独显渲染）撤回冗余定性；用户切**独显直连**后复核：4060 接管主屏实锤 → AMD 用户态 UI 层（RadeonSoftware/AMDRSServ/AMDRSrcExt/amdow ≈198MB）失去作用对象改判可关（切回混合模式需重开面板）；驱动配套服务（atieclxx/amdfendrsr/amdpmf/AmdPpkgSvc）留
- **A 档执行全绿**：RadeonSoftware 杀 ✓/AMDRSServ+amdow 需管理员（并入用户命令组）/AMDRSrcExt 自清/NI+PCManager+AMDInstallLauncher 用户管理员窗口执行全绿（8080 裸奔面消除，≈340MB 落袋）/python 32176 僵尸自清
- **B 档 6 项 ZCode 代跑全绿**：Edge AutoLaunch ×2/Chrome AutoLaunch/UC/Tabbit updater/Quark 小组件 reg delete（HKCU 用户态）+TypeEasyNotify 计划任务禁用——复验零残留
- **两处改判**：llama-server 724MB **改判 A 档**（Ollama 推理 runner 子进程：父=ollama.exe/加载 LOCAL_URL 模型 keep_alive=-1 常驻/127.0.0.1:3393 仅本机，杀它=杀本地大脑）；postgres 249MB **改判 A 档**（.pg0/instances/hindsight 实锤=Hindsight 内嵌存储引擎）
- **遗留**：:8080 现主人=NIApplicationWebServer（Multisim 捆绑 WebServer）——用户确认暂不用 Multisim，**已拍板禁用（sc stop+config disabled 两条管理员命令，恢复=sc start NIApplicationWebServer，已记台账待执行）**
- 深查副产品：/health 自检发现 python 32176 僵尸（9078 无头自启测试残例）——已随深夜清理消亡

## 二.12、纪律落地三件（两误触升级+新硬纪律）

- **会话启动纪律**（AGENTS.md 新节+BOOT 记忆系统坐标双落，b5ba058/295cd07/8e257ba）：每次工作会话第一步=Hindsight /health 自检（5s 超时）→ 不通→schtasks 拉起（命令行在案：F:\Hindsight\venv\Scripts\hindsight-api.exe --host 127.0.0.1 --port 9077）→8s 复检→两次不通立即告知用户**不静默跳过**；拉起前查残留防多实例；依据=Hindsight 手动启动无自启（Run 键/计划任务/启动夹全无侦察实锤）；**Hindsight 开机自启注册（Run 键）=待用户拍板项**
- **静态锚编写规范**（AGENTS.md 开发纪律+tests/test_settings_tab_frontend.py docstring 双落）：锚必须锚**语句形态**（正则行首/语法结构/_fn_body 函数体提取），不锚普通文本子串——批 4"心理"/C.1"零 import main"两误触实锤；误触即收窄锚形态而非删锚，重复出现升级定工具（扫描器跳过注释——C.1 已首用正则行首形态）
- **Hindsight 开机自启**：待用户拍板注册（挂账⑤）

## 二.13、1.0.5.1 补 bump 落账（e1ade3a）

- XIAOJU3_VERSION 1.0.5→1.0.5.1 此前漏 commit——深夜补账（版本策略：内部补丁不打 tag）

## 二.14、换会话收官（本节）

- 二期全链+批 C.1 已推平（origin/main=1edd816→fd3182f 深夜续）；生产车 a04243dc；基线 **2408+4**（#303 除外全绿）
- 挂账五件：①C.2/C.3 后批 C 全毕随最终 rebuild 部署+回归 ②C.3 前置 _arg_after 双副本 diff ③自启台账待确认 7 项+NI 禁用两条管理员命令 ④重启后验 6 项自启清理 ⑤Hindsight 开机自启注册（用户拍板）
- 2.0 主线剩：#227 批 C.2/C.3 → #319 批 2-3；P3 设计库三件（#332 小票/#334 折叠条/#335 启动画面）

## 三、待办与挂起

- **待办 #331**（新开，P2）：settings_api 全路由扫描注册期绑定改造（坑 #32 专扫）
- 生产车仍 15a6f53f（**UI 卡未上车**——随下次 rebuild+部署，验收清单已交用户）
- 2.0 冲刺序：批 4 触发层（D2=A 已拍板待实施）→#227 批 C→#319 批 2-3→情绪记忆二期（总图 _dev/roadmap_2.0.md）
