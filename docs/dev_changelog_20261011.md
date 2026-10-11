# 开发者日志 · 2026-10-11（上午批：#310 落库 + #307 桥接优先原则）

> 承接 dev_changelog_20261010.md（10-10 深夜收口：#299 全链+B1+清库，
> f994741/892c7aa4 终态）。

## 一、10-11 上午动作账

| 动作 | 内容 |
|---|---|
| **#310 落库**（P2） | 情感陪伴能力对齐清单（咕噜咕噜参照）：性质=能力对齐清单非新立项（70% 基础已有）；参照系四项（记忆主动提取/动态情感/人格一致性+主动性/会话摘要反馈）；缺口四子项（用户画像摘要层/主动引用链/关系叙事化/主动性实施）；**设计边界四条（用户拍板）：不贴心理标签、只做偏好事实结构化、不做情感依赖诱导、本地优先不变**；前置=#306/#305 消化完 |
| **#307 note 追加** | 「桥接优先」原则两段（参照 10-11 AI 缝合游戏视频）：①短注=边界桥接层优先于改造本体，与通用性纪律同族；②详注=视频本质（不改本体只做边界桥接：截渲染/劫持输入/重定向输出）+三条启示（小橘本身是缝合体方向没错/桥接可复用改造绑死本机/每个丹方=一个桥接层）+⚠️边界（不做炫技式缝合，复杂度膨胀=失控前兆，待办 79 行 P2 档 7 条警惕）——note 644 字 |
| 昨晚收尾参照 | f994741 推平（待推 0）+ 892c7aa4 生产车活体（#299 全链修复+B1 后端） |

## 二、待办库增量

- **#310** 落库（P2，前置=#306/#305 消化完；并入 #271 消费链不单开赛道）；
- 关联网络：#271 / #297 / #271③-T1 / #309（低本底纪律——自产摘要防自污染）；
- 库态：**79 行 = pending 68 + done 11**。

## 三、下一批队列（更新后）

#305 NapCat 幽灵进程（P2 首项）→ #306 坑库 → **#310 情感对齐** → #264 B2 前端 settings tab（主线大项）→ #304 形态 B′ 回看窗口。

## 四、#305 批次 1（F3 fire 日志 + F2 三态探测，设计稿 _dev/design_305_napcat_ghost.md）

**前置侦察（只读）**：监督链定位（launcher.main→ensure_napcat 每启动一调；E3 复用态监督 desktop_launcher.py:383 限 3 次/60s，生产日志零 respawn）+ BootMain 生命周期实锤（管道监督者非注入后自退，QQ 活它就活）+ 真机实况（今晨 9:05 重启后幽灵清零：BootMain=1 健康+cmd 10664 挂尸实证=bat 末尾 pause 结构性悬尸）+ 三病根定性（DEVNULL 零可观测/裸 QQ 探测盲区——进程名扫只认 napcat 子串而 QQ.exe 不含/QQ 9.9.33→9.9.36 自升级不稳窗口）+ 乘法链三候选如实挂起待现场取证。步骤 0：launcher-user.bat 逐行拆解（reg 查路径+5 静态 env+直呼 BootMain+两处 pause），loadNapCat.js 唯一消费 NAPCAT_MAIN_PATH 且带 __dirname 兜底→F1 复刻风险降级。

| 项 | 内容 |
|---|---|
| **F3 fire 日志落盘** | ensure_napcat fire 输出 DEVNULL→`agent_state/napcat_fire_<ts>.log`：首行探测快照（napcat_running/plain_napcat_qq/other_qq/分支/bat 路径）=下次幽灵现场自带证据；N=10 mtime 轮换（prune_napcat_fire_logs，与 LOG_KEEP 同口径）；目录=xiaoju3.AGENT_STATE_DIR 优先（frozen 路径陷阱铁律）回退 paths.DATA_ROOT/agent_state；创建失败回退 DEVNULL 零阻断；stderr 合流 STDOUT；Popen 后 Python 侧句柄即收（子进程持继承句柄续写） |
| **F2 三态探测** | 新增 `_classify_qq_processes`/`_qq_plain_running`：QQ.exe 按**可执行路径**二分（用户拍板：不按进程名）——exe 在 NapCat 目录下=NapCat Shell 副本（裸态）→只杀副本+10s 锁宽限（NAPCAT_QQ_LOCK_GRACE_SECONDS，E3 实锤强杀后锁残留秒崩）再 fire；NapCat 目录之外=用户日常 QQ **绝不动**且阻止 fire（锁占用硬拉=昨晚幽灵同型）；副本+日常并存=杀副本仍跳过；psutil 缺席/异常→([],0) 回退 legacy fire（宁放行不瞎杀）；exe 读取失败保守归 other |
| 锚 | +10：三态三分支（杀副本后 fire/日常阻止/并存跳过）+路径判定（NapCat 副本识别/日常不误判/非 QQ 名忽略）+快照首行+DEVNULL 兜底+轮换 N=10+目录缺省 agent_state |
| 测试 | 全仓 2000+4→**2010+4**；share_link=#303 既有失败 stash 对照实锤与本批零交集（改动仅 xiaoju3_launcher.py+test_napcat_launcher.py） |
| 批次 2 | F1 绕 bat 直呼 BootMain（设计稿已备：winreg+env 复刻+漂移自检回退），**等批次 1 观察 24h 后另行指令** |

### 部署与真机验证（10:19-10:32）

- **部署**：kill 三进程（单轮清杀防监督复活，轮询归零）→ build_exe.bat 全流程 → PYZ 双向锁验 4 标记全中（三态判定/napcat_fire_/宽限常量/_classify_qq_processes）→ VCRUNTIME 双锁再现（已知坑）→ **shutil 绕锁部署 412 文件（392 换装+20 同版跳过，零失败零孤儿）**→ schtasks 拉起 → **新 exe=027868FF**，3 进程+console 200。
- **F2 健康态零误伤活体验证**：新 launcher 日志（102336）明写「ℹ️ NapCat 已在运行，跳过」——健康树在跑时零 fire，napcat_fire_*.log=0（设计预期：健康态不产 fire 日志）。
- **计划外活体标本（10:05:34 幽灵事件）**：部署前 20 分钟实弹目击——cmd 23216 以 ensure_napcat 同款形态（`cmd /c launcher-user.bat` 无路径+cwd 形态）拉起第二棵完整树（BootMain 27468+QQ×4），**父进程 27300 已死、无对应 launcher 日志**（非 xiaoju3 launcher 所为——NapCat 自体重启链候选，napcat.mjs 含 29 处 restart 相关串待二期核）；两树并存实证 QQ 9.9.36 单实例锁**不拦截**第二棵树（僵尸树可长存=幽灵堆积的最终形态解释）；OneBot 3000/WebUI 6099 均被旧树 QQ 4424 持有，新树=纯重复。已 taskkill /T 整树清理（BootMain/QQ/xiaoju3 归位 1/4/3），3000 通道 200 复验。**乘法链候选③（BootMain/上级自拉）获实锤级新证据**——F2 管不住非 xiaoju3 来源的 fire，批次 2 前需先钉死 27300 真身（下一次事件抓父进程命令行）。

## 五、#264 B2a 设置 tab（9447af8，生产车 62E73BBB）

| 项 | 内容 |
|---|---|
| **改动** | ①index.html 第三 tab=设置（pane 与终端页同构，CSS 复用 first-run-field 族）②console.js switchChatTab 重构 **CHAT_TABS 注册表**（显隐/输入框/清空/进出副作用全条目声明，B2b/B2c 续条目即可；终端 15s 轮询语义逐条保留）③设置页=GET /api/settings 按 level 渲染（低档项后端已隐藏，**前端零键名硬编码**——扩白名单零前端改动）+str/int/bool/enum 分型+tier 分组+增量保存 POST {updates}（403 文案分流含儿童锁关需 Lv4+TOTP；applied/written 区分即生效 vs 需重启）+竞态守卫 |
| **锚** | +6（test_settings_tab_frontend.py：HTML 结构/注册表非 if-else/GET 契约/POST 契约/403 toast/渲染遍历零硬编码）；test_web_ux 四条字面量随注册表语义适配（意图不变）。全仓 **2010+4→2016+4** |
| **部署** | 11:02 换装（4 文件差异）→ schtasks 拉起 → console 200 + 线上 HTML 实含 tab-settings/settings-pane + /api/settings 200（747B=items 有货） |
| **✅ 用户真机验收 PASS（午）** | 五项全过：①设置 tab 出现 ②常规设置组渲染（城市/区县/TTS 声音）③管理员开关组渲染（儿童锁/生成超时/小模型/设备档位）④改「城市」保存 → toast「已保存 1 项，1 项已生效」（apply=env 即改即生效链活体）⑤权限分档生效（level<4 时 danger 组隐藏=后端过滤活体）——**B2a done**；B2b/B2c/B2d 待做（#264 库 note 已记进度） |
| **幽灵二次事件** | 部署健康检查再抓 ABNORMAL：第二棵树生于 **10:57:09**（cmd 16456/父 11504 已死/无 launcher 日志，ensure_napcat 同款形态）——与 10:05 事件同签名、间隔 ~52 分钟≈**小时级周期**（昨晚 20+ 棵≈20 小时堆积吻合）；新 launcher 11:02 启动正常 skip 零 fire（F2 无辜）；巡检脚本首战立功（genealogy 全链留证 napcat_ghost_report.txt）；已 taskkill /T 清理归位 1/4/3，3000/6099 始终归旧树。**下一步=被动等下次事件抓父进程 or 主动布 WMI 进程创建监视（拍板待定）** |

## 六、B2a 验收 PASS + B2d 拍板 + 第①批（72c2257 / a7ee449，生产车 2EC6D2FA）

- **B2a 用户真机验收 PASS（午，五项全过）**：tab 出现/常规组/管理员组/改城市保存 toast「已保存 1 项，1 项已生效」/权限分档 danger 组隐藏——B2a done（#264 库 note 已记进度，PROJECT_CONTEXT 已刷）。
- **B2d 拍板最终版**（design_264_b2d_ui_trio.md 已更新）：退出弹窗**双方法**（全部退出/仅退后端，两 radio 各自可记住）｜关于卡极简｜**窗口 X=同桌宠菜单退出统一弹窗**（行为变更：原 X 直接关窗→现先弹框，用户接受副作用）；记住选择走后端文件 agent_state/ui_pref.json（localStorage InPrivate 即焚铁律）；衍生待办 **#313 自动更新检查**（P3，关联 #279）。
- **第①批 = 桌宠右键菜单（a7ee449，#301 首落地点）**：img.contextmenu 阻止默认+自绘暖橘菜单（CSS 变量随双主题/挂 body/视口钳制/外点+ESC 关闭+防开即关竞态）；六项=缩小/设置/切换主题/关于/—/退出；**__xiaoju3Console 桥五方法**（镜像 __xiaoju3Pet 反向桥）；toggleTheme 抽取单一实现源；openAbout 极简卡；quitApp stub（真弹窗+js_api 全退链=第③批）；pointerdown 左键门（右键不进拖拽）。+4 锚全仓 **2016+4→2020+4**；about-overlay 进 dashboard id 一致性白名单。**✅ 用户真机验收 PASS（截图实证：菜单六项齐+双主题跟随变量+外点/ESC 关闭+右键不误触拖拽）=B2d① done**。
- **幽灵第三次事件（11:36:52）**：同签名（cmd 33268/父 28424 死/无 launcher 日志——当日 launcher 日志仅 4 份全对应真实启动）；巡检脚本再立功留证；已清理归位 1/4/3。三次节奏 10:05→10:57→11:36（~52/~40 分钟），周期性外部 spawner 定性不变，身份未钉死。

## 七、B2d② 验收 + 第③批双修复（1945a9a / 61f949b，生产车 23F070F2）

- **B2d②（齿轮入口）用户真机验收 PASS**。
- **第③批双修复（用户 B 方案拍板，61f949b）**：①**删 tab 栏「设置」文字按钮**（双入口收敛为 ⚙️齿轮+桌宠菜单；settings-pane 保留）+设置页顶部**「← 返回」**=switchChatTab('console')；CHAT_TABS settings 条目 btn 恒 null 空值安全，getElementById('tab-settings') 残留清理（dashboard id 一致性锚实锤兜底）②**桌宠右上角重叠根因修复**：下界钳制三处（出生位/拖拽/resize）裸读 `.chat-input-area` rect.top——settings/终端 tab 输入框 display:none rect 全零→下界归零→拖拽/重算把桌宠压到右上角遮 header（真机截图实证）；修=**getBottomLimit() helper**（rect.height>0 才作数，隐藏回退 window.innerHeight）三处 call site 全量替换，pet_desktop 尾巴 A 锚随语义更新。+2 锚全仓 **2022+4→2024+4**。
- **幽灵第五次事件（12:05:18）**：同签名（cmd 27552/父 22176）；节奏 10:05→10:57→11:36→11:51→12:05（间隔 52/40/15/14 分钟**收窄**）；**WMI 监视脚本 _dev/watch_napcat_spawn.ps1 已备未启动**（被动监听父进程命令行，等用户启动）。
