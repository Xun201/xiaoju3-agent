# 开发者日志 2026-10-27（发版收尾日 → 2.1.1 解冻）

## 晨批：v2.1.0 Release 补发 + 系统盘点（两笔，本会话）

- **Release 补发**：v2.1.0 网页 Release 此前未建——gh CLI 直建（标题"v2.1.0 里程碑发布"，正文=CHANGELOG 2.1.0 全段提炼，资产 xiaoju3-2.1.0-setup.exe 81,676,405B uploaded，SHA256 6e01b307… 如实标注构建快照含 tag c27f659 后同日语音收官提交）。
- **架构三思想调研**（PD 分离/投机采样/递归切块）入 _dev/thinking_notes.md，含出处勘误（vLLM 非 DeepSeek 项目；PD 正典=DistServe OSDI'24）。

## 午批：#358 历史污染根治 + #359 中文标点递归切块（e74ea8e 已推，生产车 06d4579f）

### 病灶复盘（真机日志+历史文件实锤，与队长初判不同）
队长真机"你好"收到设备日志解读——三层水源：
1. **主凶=设备操作注入**：dashboard /api/chat 与 /api/chat/stream **每轮**调 main._inject_recent_actions（docstring 旧说"不经 dashboard 链"过时）——昨晚控灯 turn_on×5 每轮进上下文，r1 把闲聊当设备操作延续解读。
2. **历史 think 自激**：assistant 回复带完整 <think> 原文落盘（50 条里 25 条），思考里复读"设备操作记录"，逐轮自我强化。
3. 附件注入块 user 侧实测未落盘（防御性剥离保留为防线）。

### 修法四刀
①main 注入加新鲜度窗：TTL 先定 24h→**真浏览器复验抓到隔夜仍注（21:27 记录 10.5h 后照注）→收紧 6h+最多最近 2 条**（指代消解只看最近操作）+包装文案明确"背景参考非当前问题"；②brain._build_messages 剥历史 assistant <think> 块（孤立开头剥到末尾+剥空占位）；③同点剥历史 user 已消费附件注入块恢复纯原话；④dashboard._read_console_history 读出即清洗（文件保留原文，回放同步净化）。

### doc_ingest._chunks 递归切块（2.1.1 解冻首任务）
纯滑窗硬截断→中文分隔符递归降级（\n\n→。→！→？→空格→字符，LangChain RecursiveCharacterTextSplitter 同构）+keep_separator 保句界+贪心合并回 500+借位 overlap 按余量封顶。

### 顺手修两颗
- _embed_backfill_thread 同根雷补刀：sqlite3.connect(_db()) 把 Connection 当路径（266b28a 只修了 once 分支——"同根 bug 一起修"纪律补课）。
- 插件测试注册表隔离：doc_ingest 插件测试卸载+白名单快照还原（既有顺序依赖问题，全仓字母序恰好掩盖，交叉跑实锤）。

### 验证
全仓 **2593+4 全绿**（+13 锚：历史清洗 4+递归切块 6+过期不注入 1+注入上限 1+另改注入契约用例）；真浏览器：'你好'零设备日志零小说串戏（对比修复前 863 字日志解读）、历史回放 50 条 0 think/0 注入块。**诚实挂账**：r1 1.5b 对裸"你好"仍会答非所问（"建议联网获取时效性信息"）——本地小模型闲聊质量=模型能力边界非污染，云端闲聊正常；插件 unload_all 是否注销 ext_* 工具有白名单快照兜底未逐项验证。

### 回滚
main.py/brain.py/xiaoju3_dashboard.py .bak-20261027-strip；doc_ingest.py .bak-20261027（无——改动可由 git revert e74ea8e 回滚）；生产旧 exe .oldA2 机制在案。

## 晚批：#354 切片 a——QQ 赛博生命体 qq_lifemate 文字唤醒闭环（0611e4d 已推）

- **VISION_KEY 确认（任务 1）**：生产 xiaoju3_data/.env 两段 VISION 配置（旧 qwen 占位+新 GLM 真值），加载器逐行覆盖=GLM 生效；vision_ask_image 实测 GLM-4V 通（桌宠图答"穿狐狸服装的角色"）——截图提问可测。
- **qq_lifemate 目录包**（首个目录形态插件，loader `submodule_search_locations` 首例）：独立 memory.db 五表（chat_log/facts/scene/rel/meta）+waker.py 唤醒线程三闸（静默 4h W1/quiet 23-8 跨午夜 W2/日限 5 硬帽 meta 落盘防绕帽）+QQ 人格档（P1 拍板更皮更黏自称小橘）+三工具（record_fact/scene_report/recall_fact）。
- **真机验证**：生产四插件同堂 rejected=0；唤醒生成链实锤两句话（"嘿~快到晚上了来得正好~"/接场景语境）；发送闸 owner 空如实跳过不落假账。
- **真机抓真雷**：`main.notify_master` 不存在（定义在 heartbeat.py，main 只导入 start_heartbeat）——grep 实抓修为 heartbeat 直引。
- **坑**：目录包内 import 同目录模块=显式 sys.path 插入（spec_from_file_location 包内相对导入不可赌）；测试与插件必须共享同一 sys.modules 实例。
- **唯一待办**：队长在 xiaoju3_data/.env 填 `XIAOJU3_OWNER_QQ=队长QQ号`（120 行现为空）→ 重启或 /plugin_reload 即活。
- 测试 **2613+4**（+18：三闸/装载契约/工具行为/落账跨日重置）；回滚=删生产 qq_lifemate 目录+`git revert 0611e4d`。

## 晚批③：侧栏拖宽 UI + 全局任务审查员草案（a476e0f 已推，生产车 a3016f82 三进程在线）

- **侧栏拖拽调宽**（队长指令①）：把手 `#sidebar-resizer`=flex 兄弟节点 10px 宽配对负外边距 -5px×2=**净零布局位移**（部署前后版式分毫不动）；指针捕获拖拽+rAF 节流实时改 `.sidebar` 宽，夹紧 [300, 窗宽×55%]；hover/拖拽显狐毛橙把手条+col-resize 光标；双击把手=复位。持久化双通道：桌面形态 js_api `set_layout_pref`→agent_state/ui_pref.json（跨启动真源，localStorage 关窗即焚铁律）、浏览器形态 localStorage 降级；恢复以 ui_pref.json 为真源（pywebview api 轮询 3s 上限，未就绪=浏览器静默）。≤768px 抽屉态隐藏把手+清内联宽（宽度交还 CSS）；窗口缩放重夹紧；matchMedia 缺席（node 桩环境）静默不启用。
- **后端**：QuitBridge 新增 `get_layout_pref`/`set_layout_pref`（读改写合并与 exit/dev 键互不覆盖；300-2000 合法落盘、0=删键复位、非法拒绝不污染文件）。
- **测试**：+15 锚=**全仓 2681+4 全绿**；node 运行时烟雾 `_dev/smoke_sidebar_resize_20261027.js` **26/26**（真源码提取+Proxy CSSStyleDeclaration 桩驼峰/横线归一+矩形反映内联宽）；浏览器真拖拽 UI 冒烟三连过（320→420px 实时变宽+localStorage 落盘/刷新保持 420px/双击复位 320px）。
- **坑两条**：①裸 `python -m http.server` 做 UI 冒烟=页面壳渲染但 console.js **404 全死**（index.html 引 `/console/console.js`，Flask 有 `/console/<file>`→仓库根映射，静态服务器没有）——假阳性排查绕远；正档烟雾服务器=`_dev/smoke_http_server_20261027.py`（translate_path 同款映射）。②streamcard 运行时烟雾桩无 `matchMedia`——新 IIFE 必须带环境守卫（`typeof window.matchMedia !== 'function'` 早退），否则全仓测试被连坐。
- **部署**：build_exe.bat（车 2.1.0+本批）→包内容三层验证（`_internal/console.js`/`index.html` grep+PYZ `ZlibArchiveReader`——**方法名锚在 co_names 不在 co_consts**，docstring 锚在 consts）→VCRUNTIME 双锁再现（robocopy 12min 49 文件龟爬）→`deploy_shutil.py` 绕锁正档（1505 拷+26 同版保留+locked_diff=0+exe/console.js/index.html md5 双端 MATCH）→schtasks 双通道拉起（MSYS_NO_PATHCONV=1）→三进程全新 StartTime 23:29+health ok+`/console` 新 UI 验证（`/` 是旧版占位页，真控制台在 `/console`——验错路由会虚惊）。
- **任务②（思维沉淀+架构草案）**：两概念确认在库（`_dev/thinking_notes.md:254`，2026-10-27 老板视频提炼，含 0.95^10 与独立视角两要点）；**全局任务审查员极简草案落盘 `_dev/design_global_task_reviewer.md`**：TaskLedger 会话账本+触发三则（T1 链长≥3/T2 工具族切换/T3 败后续）+一次云审（≤200字 prompt 要 JSON verdict）+规则兜底（云断不放大）+合法批量链保护+三步对抗论证（反转条件=误杀>5% 或超时>20% 降级单触发）；概念条目已加落点指针。**等老板/秘书拍板，未实施**。
- **回滚**：index.html/console.js/desktop_launcher.py 各 `.bak-20261027-sbresize`；`git revert a476e0f`；生产旧 exe 无 .old（VCRUNTIME 双锁下回滚=重新构建上一提交 a476e0f^ 并重部署，或 `git stash` 期 dist 未删时用 dist 旧包——诚实挂账：本次部署未保留旧 exe 副本，回滚依赖 git revert+重建，约 5 分钟）。
