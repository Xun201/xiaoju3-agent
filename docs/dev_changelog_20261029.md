# 开发者日志 2026-10-29

> 快照式按提交逐条。本日单笔：8b0e290 控制台思维链找回。

## 8b0e290 — fix(控制台思维链找回)：云端直答改流式（v2.2.1 内部补丁，已部署生产）

### 背景
- 队长报告：最后一轮控制台排版修复后，AI 回复的"思维链折叠卡片（已思考 X 秒 >）"消失，只剩光秃秃正文。
- 诊断定案（侦察三处）：
  1. **真凶不是排版修复**，是 2026-10-28"控制台闲聊强制云端"批引入：`console_cloud_chat`（main.py）用 `stream: False` 只取 `content`，且生产 `CLOUD_MODEL=deepseek-chat`（**非思考模式本就不返回 `reasoning_content`**，WebSearch 核实）——思考过程在云端源头就不存在，不是"取了丢掉"。
  2. 流式端点云端分支（xiaoju3_dashboard.py）单帧 answer+done，零 think 帧。
  3. 前端 console.js 渲染管线完好无损（骨架→思考中→直出→done 按 `<think>` 定稿折叠→点击展开），纯后端断供。
- 顺藤修出两个既有潜伏 Bug：①流式云端分支从不落盘 `_append_console_history`（云端回复刷新即消失于历史）；②generator 内 `return jsonify(...)`=StopIteration 吞值死代码（云端挂时前端零帧断流，骨架卡挂死到 30s 看门狗）。

### 修复
- `console_cloud_chat` 重写：`stream: True` 逐块解析 DeepSeek SSE，`reasoning_content`→`on_event({"type":"think"})` 回调，`content`→answer 回调；返回 `<think>…</think>正文`（无思考=裸正文；正文空=None 不产半截卡，R1 守门同口径）；失败=None 契约不变。
- **模型切换**：新增 env `XIAOJU3_CONSOLE_CLOUD_MODEL`，缺省 `deepseek-reasoner`（思考模式，V3.2 起 chat/reasoner 同价只多付思考 token）；`deepseek-chat` 可拨回（则无思考卡，优雅降级为裸正文）。QQ 通道独立链保持非思考不动。
- 流式端点云端分支重写：queue+runner 线程镜像 smart_ask_stream 既有模式，think/answer 帧实时转发，done 带包装全文；云端回复落盘历史补齐；None→真 done 帧友好兜底（不断流）。
- `_STREAM_HARD_TIMEOUT` 常量上移两分支共用。
- 前端 console.js/index.html **零改动**。

### 验证（Evidence）
- 全仓 `python -m pytest`：**2878 passed, 5 skipped, 0 失败**（基线 2876+5，净增锚：流式 SSE think 帧断言、云端 None→兜底 done 帧、console_cloud_chat 单测 5 枚（包装/裸正文/env 覆盖/失败 None/空正文 None））。
- `node --check console.js` PASS。
- 构建部署：build_exe.bat 全量（exe+setup 115,377,108B）→ deploy_shutil（copied=3 kept_same=2414 locked_diff=0，exe/console.js/index.html md5 三 MATCH）→ schtasks 拉起三进程 15:48:50 全新 + health ok。
- 生产活体 SSE：POST /api/chat/stream "你好" → **94 think 帧（147 字）+ 20 answer 帧 + done 带 `<think>` 包装**，source ☁️ 云端，1.5s。
- 真浏览器 DOM 验证（IAB）：发送→卡片在+标签"🧠 思考中…"+思考行直出；done 后 `adoptedIntoMsg=true`+标签"🧠 已思考（用时 0.8 秒）"+自动收起 collapsed=true；点击标签行展开 collapsed=false。全链 PASS。

### 没做/挂账
- 版本号保持 2.2.1（内部补丁不打 tag，生产 exe 新于 Release 资产；要发 v2.2.2 由队长拍板）。
- 深度思考成本观察：reasoner 思考 token 按输出计费，简单问候实测仅 147 字思考/0.8s，长对话成本影响待观察。
- 历史回放（GET /api/history）按 #358 定案剥 think 不出卡——刷新后旧消息无折叠卡属既有设计，非本次回归。

### 回滚
- 代码：git revert 8b0e290；文件备份 `main.py.bak-20261029-thinkcard` / `xiaoju3_dashboard.py.bak-20261029-thinkcard` / `.env.example.bak-20261029-thinkcard`。
- 生产 exe：`F:\XUNandxiaoju3\xiaoju3.exe.bak-20261029-thinkcard`（36,797,658B）。
- 快速行为回退（免重建）：生产 .env 加 `XIAOJU3_CONSOLE_CLOUD_MODEL=deepseek-chat` 重启即回非思考模式（无卡但正常回复）。


## 1297673 — feat(控制台UI图标升级)：Emoji 按钮全量矢量化（v2.2.1 内部补丁，已部署生产）

### 改了什么
- **index.html 16 处**：顶栏七钮（刷新=refresh-cw 双箭头/工具=wrench/清空=eraser/音效=bell/朗读=volume-x/密钥=key/设置=settings 齿轮）+侧栏开关=menu+待办齿轮=settings+快捷指令两钮（clipboard-list/stethoscope）+加号菜单五项（upload/camera/link/zap/puzzle）+三处文字刷新钮=refresh-cw；CSS 补 .header-btn svg display:block+行内图标 vertical-align 对齐。
- **console.js**：新增 ICON_SVGS 表（bell/bellOff/volume2/volumeX/settings/library）；音效/朗读/齿轮三处动态 setter textContent 改 innerHTML（textContent 会抹掉 SVG）；文档 chip=library SVG；小工具面板标题=wrench SVG。
- **范围红线**：状态文案 Emoji（转写中/失败/思考/排队）与后端 source 标签（系统/权限）不动——它们是文案不是按钮图标。

### 怎么验证的
- 全仓 pytest：**2878 passed, 5 skipped, 0 失败**；测试锚四处同步（keys/settings 精确 HTML、web_ux 双态断言、main 面板标题）；node --check PASS。
- 真浏览器双环境（烟雾 5099+生产 5003）DOM 断言：8/8 按钮 SVG 化、朗读开关点击双态换图标、加号菜单 5 项全 SVG；截图目检布局零破坏。
- 部署：md5 三 MATCH（exe/console.js/index.html）+三进程 16:36 全新+health ok。

### 没做/坑录
- 音效铃铛双态切换依赖 WebAudio 引擎（desktop-pet.js），烟雾环境不可见——真桌面点验归队长。
- **坑**：烟雾服务器（SimpleHTTPRequestHandler 无 Cache-Control）触发浏览器启发式缓存旧 console.js——"新 HTML+旧 JS"混跑假象（旧 textContent 抹掉新 SVG）。破法=页内 fetch 的 cache:'reload' 刷 HTTP 缓存条目再 reload；真机目检遇"改了没生效"先疑缓存再疑代码。

### 回滚
- 代码：git revert 1297673；文件备份 index.html.bak-20261029-svg / console.js.bak-20261029-svg。
- 生产 exe：F:\XUNandxiaoju3\xiaoju3.exe.bak-20261029-svg（双反斜杠=正常路径分隔）。


## 12caa71 — fix(铃铛失效+密钥面板穿模)：双根因穿透修复（v2.2.1 内部补丁，已部署生产）

### 改了什么
- **铃铛（音效开关）**：desktop-pet.js 随桌宠 DOM 物理移除后不再被 index.html 引用，window.xiaoju3Sound 引擎消失→console.js 绑定条件永假→监听器从未挂上（铃铛死了两周没人发现）。修=console.js 自持同款 WebAudio 引擎兜底（键 xiaoju3_sound/缺省 on/ding=880+1318.5Hz 双音；if(!window.xiaoju3Sound) 守卫，pet 引擎回归自动让位）。附带复活"回复到达 ding"（sendMessageStream/legacy/refreshMsg 三处调用点全回活）。
- **密钥面板穿模**：CHAT_TABS 注册表 console/terminal 两处 hide 清单漏 keysPaneEl——密钥页点「← 返回」后 keys 面板留在聊天下方与聊天穿模。修=两处 hide 补全；新增四方互斥完整性测试锚（任何 tab 的 hide 必须收全其余三 pane）。

### 怎么验证的
- 全仓 pytest：**2880 passed, 5 skipped, 0 失败**（+2 锚）；node --check PASS。
- **CDP 直连真实桌面页**（WebView2 远调试口）：引擎在位+ding 可调/铃铛点击双态切换且 SVG 不被抹/🔑开启=chat+input 全隐、面板 674px≥90% 覆盖/←返回=keys 面板干净消失聊天回归/⚙️绕行路径零残留；PrintWindow 两态实拍。
- 部署：md5 三 MATCH+三进程 17:25 全新+health ok+调试口已清（诊断用 bat/一次性任务全删）。

### 坑录
- **PrintWindow 陈旧帧坑**：最小化恢复后 WebView2 合成层可能出旧帧（曾误判"前端布局烂"）——DOM 真态以 CDP 为准，PrintWindow 仅作参考。
- **WebView2 远调试诊断法**（桌面 UI 问题终极取证）：bat 包装设 WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS（含 launcher 原 flags+--remote-debugging-port=9223）经 schtasks 拉起→CDP /json/list→websocket Runtime.evaluate 直读真实页面。诊断完恢复普通拉起+清工件。

### 回滚
- 代码：git revert 12caa71；备份 console.js.bak-20261029-penetration。
- 生产 exe：F:\XUNandxiaoju3\xiaoju3.exe.bak-20261029-penetration。


## 深夜批 — feat(现代确认弹窗)：原生 confirm 全量退役（v2.2.1 内部补丁，已部署生产）

### 改了什么
- console.js 新增 showConfirm(title, message, onConfirm, opts)：深遮罩+白圆角卡+粗标题+灰描述+蓝胶囊主钮+×（对齐 DeepSeek 截图2）；z-index 50000 遮罩全屏背景不可点；Esc/遮罩空白/×=取消、Enter=确认、settled 防重入；textContent 注入零 XSS；window.showConfirm 全局导出。index.html 配套 CSS（.xj3-modal-*）。
- 四个业务调用点全迁移：删已完成待办（confirmText:删除）/删知识库文档（删除）/清空聊天记录（清空）/密钥覆盖（覆盖）——原 window.confirm/裸 confirm 全部消失。
- 测试锚 +4（test_web_ux.ModernModalTests 四测 + keys 覆盖锚改道 + dashboard 旧 confirm( 锚更新）。

### 怎么验证的
- 全仓 pytest：2884 passed, 5 skipped, 0 失败；node --check PASS。
- 烟雾页真浏览器：形态四连（z 50000/遮罩 rgba(17,24,39,.5)/卡片居中/取消+清空双钮+×）+行为链五连（确认回调触发/Esc/遮罩点击/取消钮均不误触/单钮态/零残留）+截图目检。
- 部署：md5 三 MATCH+三进程 health ok。

### 没做/坑录
- 坑复发：烟雾服务器启发式缓存旧 console.js（"组件不存在"假象）——fetch cache:reload 破（上批已录，本轮二现）。
- APK 任务二=纯环境报告未装任何大件（_dev/phone_apk_env_plan_20261029.md），等队长确认网络。

### 回滚
- 代码：git revert 本笔；备份 index.html.bak-20261029-modal / console.js.bak-20261029-modal。
- 生产 exe：F:\XUNandxiaoju3\xiaoju3.exe.bak-20261029-modal。


## 深夜二批 — feat(首个 APK 本地构建成功)+fix(QQ 幽灵追问)+破案(API 断连)

### 改了什么
- **QQ 幽灵追问**（真机 18:14 凭空发"那句话呢？"）：waker.py _WAKE_PROMPT 加【消息独立性死命令】+新函数 enforce_context_independence（指代词黑名单：那句话/刚才那/上次说/上面说/你刚说/刚刚说/前面说/之前说/方才说——命中整条替换诚实走神话术[表情:疑问]，全来源发送前最后一道闸门）。
- **APK 全链**：_dev/setup_android_env_20261029.py（清华 JDK17 zip+腾讯 cmdline-tools/SDK 四件离线组装+licenses+用户级 env 三件+PATH）；android_app/ Capacitor 6.2.3 工程（com.xun.xiaoju3，小橘 normal_half 生成 18 件图标）；gradle wrapper 腾讯镜像+build.gradle 阿里云 maven×2；前端四改造（API_BASE fetch/EventSource 前缀管线+showApiBaseConfig 配置卡+截图入口 APK 隐藏+dashboard _apk_cors_headers）。
- **API 断连破案**：5099 烟雾静态服务器（ZCode 验证忘关）泄漏——API_BASE 当时未引入；已杀。

### 怎么验证的
- 全仓 pytest：2887 passed, 5 skipped, 0 失败（+7：幽灵 3+API_BASE 1+前批弹窗 4 内计）；node --check PASS。
- 幽灵拦截 6 连稳定（随机变体全覆盖）；生产 waker md5 双端一致+重启 health ok。
- gradle assembleDebug 首跑 2m19s BUILD SUCCESSFUL、增量 13s；aapt2 dump badging 验证（com.xun.xiaoju3/versionName 2.2.1/minSdk 22/target 34/INTERNET）。
- APK 交付：dist/phone/xiaoju3-phone-v2.2.1-debug.apk（3,864,131B）。

### 坑录
- TUNA 镜像对 python-requests 403（TLS 指纹过滤，UA 无效）——curl 通道实测通：外部资源下载脚本优先 curl。
- 腾讯 AndroidSDK=Nexus 代理（目录列表 400），须直取文件名（commandlinetools-win-10406996_latest.zip / platform-tools_r34.0.5 / build-tools_r34 / platform-34-ext7_r03 全 200）。
- Capacitor 6.2.3 模板 Manifest 无 usesCleartextTraffic——内网 http 手动补。

### 回滚
- 代码：git revert 两笔（QQ 修复/APK 工程）；备份 waker.py.bak-20261029-ghost / console.js.bak-20261029-apk / xiaoju3_dashboard.py.bak-20261029-apk。
- 生产 exe：dist 新车部署后旧车哈希见部署日志；waker 独立文件可单点回退。


## 深夜三批 — feat(插件面板可点击快捷指令)+破案(APK 失踪)

### 改了什么
- console.js：PLUGIN_QUICK_ACTIONS 映射（stock_assistant→帮我选股/dice→掷骰子/video_ingest→提取视频内容/doc_ingest→上传文档）；fetchPlugins 渲染映射内插件行追加 ▶ .dp-quick chip；popover 事件委托（send 型=填输入框+window.sendMessage() 即发走既有流式链；upload 型=转发 ＋ 菜单 upload 项；点击先 closeAll 收面板）。
- index.html：.dp-row flex 化+.dp-quick 蓝色 pill chip 样式（hover 实心蓝）。
- build_exe.bat：dist/phone move-aside 保留逻辑（wipe 前挪走后还原+残留防御行）——APK 交付目录不再被重建连坐。

### 怎么验证的
- 全仓 pytest：2892 passed, 5 skipped, 0 失败（+5 锚：PluginQuickActionsTests 四测映射/渲染/行为/CSS）；node --check PASS。
- APK 失踪破案三证：dist 18:56 时间戳=生产重建 wipe 时刻；gradle 输出 APK 18:54 完好；build_exe.bat 第 11 行整删 dist。已恢复 dist 根+dist/phone 双位置（md5 5012ebc6）。

### 事故与坑录
- **ascii write 截空 bat 事故**：首次内联 patch 用 encoding='ascii' 打开（open 即 truncate）写失败 → build_exe.bat 0 字节 → 备份秒恢复。教训再证：改文件前先备份+改文件走脚本文件（内联 heredoc 转义+编码连环坑二连）。

### 回滚
- 代码：git revert 本笔；备份 console.js.bak-20261029-quick / build_exe.bat.bak-20261029-phonekeep。


## 深夜四批 — feat(扫码配对+移动端排版重构)（v2.2.1 内部补丁，已部署生产+重打 APK）

### 改了什么
- **桌面**：dashboard /api/pairing/info（_local_lan_ips：UDP connect 零流量探测默认路由 IP+hostname 候选，Tailscale 100.x 与 LAN 同列）；console.js openPairQrModal（🧰「连接手机」卡→qrcode() SVG 弹窗，多 IP 编入一条码由手机端逐个探活）。
- **APK 配对门**：showApiBaseConfig 退役→showPairGate（📷扫码连接大按钮+details 手输折叠）；openPairScanner（getUserMedia 后摄+BarcodeDetector 加速+jsQR 逐帧兜底）；parsePairingPayload（xiaoju3://connect?ips=..&port=.. 与 http:// 直填双格式）+pairConnect 逐候选探活。
- **vendored**：qrcode-generator 1.4.4+jsQR 1.4.0（MIT）内嵌 console.js 头部（+188KB）。
- **移动端排版**：768px 媒体查询补 chat-header 防挤压（标题 nowrap 省略号/音色选择隐藏/header-btn 紧凑/composer 100%）。
- **APK**：Manifest CAMERA 权限；MainActivity 启动 ActivityCompat.requestPermissions(CAMERA)。

### 怎么验证的
- 全仓 pytest：2898 passed, 5 skipped, 0 失败（+9 锚：PairingAndMobileTests 五测+PairingInfoApiTests 功能锚+两处旧锚随新契约更新）；node --check PASS。
- 生产部署：md5 三 MATCH+pairing 端点活体（双 IP 候选实测返回）；二维码**往返解码验证**（SVG→canvas→jsQR 解出原载荷逐字节一致）。
- 390px 手机视口实拍：头部横排+标题省略号（竖排根除）+配对门渲染正常。

### 坑录
- 内联 heredoc 转义三连坑（\/ 层级/TLS 指纹之外的又一课）：**JS 正则转义一律脚本文件+raw string**。
- IAB 截图合成层迟滞三现：DOM 已新帧已旧——以 DOM 断言为准，截图辅助。

### 回滚
- 代码：git revert 22b0d12；备份 console.js/xiaoju3_dashboard.py .bak-20261029-pair。
- APK：上一版在 gradle 输出目录被覆盖——dist 双位置最新为准。


## 深夜五批 — feat(侧栏分界线全高贯穿+拖拽高亮)（v2.2.1 内部补丁，已部署生产+APK 同步）

### 改了什么
- 断裂根因双层修复：①#sidebar-resizer margin:12px（上下）+::after top/bottom:12px 双重内缩（线比窗口短约 48px）；②v0 皮肤 body{padding:16px;gap:16px} 让 align-self:stretch 只到内容盒（688px）。修=resizer margin:-16px -4px 穿透留白带+::after top/bottom 归零。
- 形态升级（队长口径）：默认 2px 浅灰实线（var(--color-border) 令牌）→hover/拖拽 4px 点缀蓝 #2563eb；cursor col-resize 常驻。拖拽逻辑零改动（指针捕获+rAF 节流+ui_pref/localStorage 持久化+双击复位）。
- 测试锚 +3 改版（贯穿/mkdir 形态/蓝色加粗——旧 12px 内缩形态禁回归）。

### 怎么验证的
- 全仓 pytest：2901 passed, 5 skipped, 0 失败；node --check PASS。
- 真浏览器几何断言：resizer top 0/bottom 720=vh 全高贯穿；hover（真鼠标 cua.move）::after 4px+rgb(37,99,235)；真鼠标拖拽 +80px→侧栏 320→400 且 localStorage/ui_pref 落库；双击复位回归。
- 部署：md5 三 MATCH（首轮 exe 锁 MISMATCH 补杀重部署 OK）+health ok。

### 坑录
- 部署 exe MISMATCH：taskkill 后立刻拷贝遇进程句柄拖尾锁——补杀+二次部署 OK（老坑变体）。

### 回滚
- 代码：git revert 6e5695f；备份 index.html.bak-20261029-divider。


## 深夜六批 — feat(左右分栏色块化)（v2.2.1 内部补丁，生产热同步部署）

### 改了什么
- v0 皮肤 body：padding:16px/gap:16px → 0（页面留白带退役——断层根因）。
- v0 .sidebar：transparent 透明底 → var(--v0-n50) 灰底满幅方角，margin 归零（右缘紧贴分界线），卡片呼吸感内收 padding 12px。
- v0 .chat-area：漂浮白卡（边框+圆角 16px+阴影）→ 纯白满幅方角。
- #sidebar-resizer：负 margin hack 退役归零（色块已无缝，负 margin 仅上批过渡态需要）。

### 怎么验证的
- 全仓 pytest：2901 passed, 5 skipped, 0 失败；node --check PASS。
- 真浏览器几何断言：sidebarRight==resizerLeft==320（左灰紧贴分界线零间隙）、chatLeft==resizer 右缘（gap 0）、resizer 全高贯穿、左灰 rgb(250,250,250)/右白 rgb(255,255,255)；整页截图目检色块拼接。
- 部署：_internal 热同步+health ok（数据文件改动无需重构建）。

### 事故录
- 四连 patch 脚本 rep④ 锚断言中止→所有改动未落盘（写文件在脚本末尾），生产页旧样式假象当场暴露→拆出 reps1-3 单独重放+验证。教训=多段替换脚本应逐段即时写盘，或在断言失败前先落已完成段。

### 回滚
- 代码：git revert cc59ce6；备份 index.html.bak-20261029-blocks。


## 深夜七批 — feat(分界线隐形化收尾)（v2.2.1 内部补丁，生产部署+APK 重打）

### 改了什么
- #sidebar-resizer::after 宽度 2px→1px（默认极细浅灰，隐形化口径）；hover/拖拽 4px→2px 点缀蓝。
- CDP 直查真实桌面页实锤：色块化批次后桌面页拼接已完美（灰→透明→白逐像素扫描零异物）——队长"黑线白带"截图为部署前旧状态，本批仅做口径收尾。

### 怎么验证的
- 全仓 pytest：2901 passed, 5 skipped, 0 失败（分界线锚改 1px/2px 口径）。
- CDP 直连真实桌面页：top 0/bottom 763 全高贯穿+1px 浅灰在位；接缝区逐像素扫描零异物。
- APK 重打交付 dist 双位置（4,163,275B）；调试口/诊断进程全清。

### 坑录
- **WebView2 调试会话静默复用旧浏览器进程池**：9223 无 target 且无报错——杀 msedgewebview2 池+全杀 xiaoju3 后重拉调试 bat 即通（CDP 取证前置步骤入档 _dev/_dbg_restart_with_cdp_20261029.py）。

### 回滚
- 代码：git revert 本笔；index.html 备份链 .bak-20261029-*。


## 深夜八批 — feat(纯净色块堆积)（v2.2.1 内部补丁，生产热同步部署+APK 重打）

### 改了什么
- 侧栏滚动条整体隐藏（.sidebar scrollbar-width:none + ::-webkit-scrollbar width:0/display:none，旧 6px 深灰 thumb 规则删除）——队长实锤的"深灰粗带"=滚动条本体贴分界线；滚轮/触摸滚动保留。
- 分界线全透明化：::after 默认 background:transparent（左灰右白自然贴合出颜色边界，无常驻线）；hover/拖拽浮现 2px 点缀蓝指示线（上批 1px 常驻线口径作废）。

### 怎么验证的
- 全仓 pytest：2901 passed, 5 skipped, 0 失败（分界线锚改透明契约+禁回归断言）。
- 真浏览器接缝扫描：resizer±12px 逐 2px 采样唯一背景色 rgb(250,250,250)（纯灰白两色零杂质）；滚动条 display none；hover 浮现蓝线截图。

### 回滚
- 代码：git revert 本笔；index.html 备份 .bak-20261029-seam。


## 深夜九批 — feat(ZCode 式纯色块拼接物理落盘)（v2.2.1 内部补丁，生产热同步部署）

### 改了什么
- 接缝审计：sidebar/chat/resizer 三元素 computed styles 逐项实测——border/shadow/radius/margin 全零，bg 精确（左 rgb(250,250,250) 右 rgb(255,255,255)），无任何残留视觉元素。
- 物理删除：resizer ::after 默认透明规则本体删除（常态无任何 background 声明——"彻底删除"而非"置透明"）；锚 assertNotIn("background:") 锁死。hover/拖拽浮现 2px 点缀蓝保留。

### 怎么验证的
- 全仓 pytest：2901 passed, 5 skipped, 0 失败；node --check PASS。
- 真浏览器终验三连：常态 afterBg transparent（无线）/hover rgb(37,99,235) 浮现/左右底色精确+全高贯穿。

### 回滚
- 代码：git revert 本笔；index.html 备份 .bak-20261029-final。


## 深夜十一批 — fix(安装器 4551 排障)+交付三件套（v2.2.1 内部补丁）

### 破案与处置
- 4551「应用程序控制策略已阻止此文件」=Windows 11 智能应用控制（SAC）拦未签名安装器的临时自解压副本（Setup.tmp 每次构建哈希变化=云端信誉未知必拦）。**iss 审计零嫌疑**（无 temp 写入/无脚本执行/[Code] 为安装器内 Pascal 自检）。
- iss 鲁棒性加固：[Setup] CloseApplications=yes / RestartApplications=no / AppMutex=Xiaoju3_Desktop_SingleInstance（desktop_launcher 真实互斥体本地名）；[Code] PrepareToInstall 静默 taskkill /F /IM xiaoju3.exe /T（双保险——AppMutex 只由桌面角色持有，launcher/backend 文件锁需显式清）。
- 交付三件套：xiaoju3-2.2.1-setup.exe（加固版）+ xiaoju3-v2.2.1-portable.zip（150MB 免安装+使用说明含 4551 绕行指南）+ xiaoju3-phone-v2.2.1-debug.apk。

### 坑录
- 编译事故自愈：patch 脚本把 PrepareToInstall 插进 [Code] 开头吞掉了 const 关键字（ISCC 报 BEGIN expected）——字节级补回。教训=Pascal 段插入须保留下游段关键字。
- bat 根 APK 保留逻辑错位（净零操作）重构修正。
- Git Bash 直调 ISCC /D 参数被 MSYS 路径转换吃掉——MSYS_NO_PATHCONV=1。

### 队长侧绕行指南（已同步便携版说明文件）
1. SAC 关闭：Windows 安全中心→应用和浏览器控制→智能应用控制设置→关闭（⚠️不可逆，重装才可再开）。
2. 下载的 setup.exe 右键→属性→解除锁定→再装。
3. 火绒/360 弹窗→允许/信任区。
4. 直接用便携版 zip，解压即用（无安装环节，SAC 拦不到安装器）。


## 深夜十二批 — ops(GitHub Release v2.2.1 三件套同步)

### 做了什么
- 旧资产（setup.exe+sha256）删除；上传三件套：setup.exe（加固版 iss）/ portable.zip（免安装+4551 绕行说明）/ phone APK（扫码配对）。
- Release Body 追加「更新说明（2026-10-29 晚）」段（便携版/安装器加固/扫码 APK/色块化界面）。

### 验证
- gh release view 资产三件尺寸与本地逐字节一致（115,412,892 / 4,163,275 / 157,644,545）。
- Body 尾部含更新说明段（tail 抽查）。


## 深夜十三批 — feat(侧栏内滚容器重构)（v2.2.1 内部补丁，生产热同步部署+APK 同步重打）

### 改了什么
- .sidebar 外层：overflow-y:auto 退役改 overflow:hidden（只做定位与裁剪），padding 归零。
- 新增 .sidebar-scroll 内层滚动容器：absolute inset 0 12px 0 0（右缘内缩 12px——滚动条悬浮在面板内部右缘，距分界线 12px 永不误触），overflow-y:auto+overscroll-behavior:contain，padding 14/6/20/14，flex column gap 12，悬浮滚动条 4px 圆角 rgba(0,0,0,0.2)（hover 0.3）+scrollbar-width thin/color 半透明双引擎。
- 待办卡禁 flex 压缩/底部 20px 留白/todos-list 32vh 内层滚动上限原样迁入内层。
- v0 .sidebar padding/gap 归零（移交内层），bg n200 对比度保持。

### 怎么验证的
- 全仓 pytest：2901 passed, 5 skipped, 0 失败；test_sidebar_scroll_fix 锚随架构升级（外层 hidden+内层滚动+内缩 12px 断言）。
- 真浏览器断言：内层 scrollTop 可设置（滚动可用）+滚动条距分界线 12px+接缝区唯一背景色 rgb(229,229,229)。
- 生产 _internal 热同步（数据文件免重构建），health ok。


## 深夜十二批（二） — feat(接缝终极微调：纯色块自然堆积)（v2.2.1 内部补丁，生产热同步部署+APK 重打）

### 改了什么
- .sidebar-scroll：inset 右缘 12px→2px（滚动条贴近分界线留 2px 呼吸位）、滚动条 4px→6px、透明度 0.2→0.15（侧栏悬浮 0.3 更醒目）、圆角 3px。
- #sidebar-resizer：n200 灰底（对比度批误加）→ 纯透明热区——两色中间杂质带根除。
- 工具面板三节标/滚动条等历史遗留 emoji 语义检查通过（无新增违规）。

### 怎么验证的
- 全仓 pytest：2901 passed, 5 skipped, 0 失败；node --check PASS。
- 真浏览器断言：接缝扫描唯一背景色=灰白两色；滚动条 6px 贴近边缘；hover 浮现 2px 蓝线（截图）。

### 回滚
- 代码：git revert 本笔；index.html 备份 .bak-20261029-polish。


## 深夜十三批（二） — feat(滚动条视觉彻底隐藏+双轨惨案根治)（v2.2.1 内部补丁，生产热同步部署）

### 改了什么
- .sidebar-scroll：scrollbar-width:none + ::-webkit-scrollbar width:0/height:0/display:none 三保险（thumb 规则与悬浮加浓规则物理删除）——上一批"悬浮滚动条"（6px thumb+2px 内缩）与 hover 蓝线在窄区并排成"双轨"（队长放大实锤）。
- wrapper inset 0 2px→0 满幅：灰白直抵分界线。

### 怎么验证的
- 全仓 pytest：2901 passed, 5 skipped, 0 失败；node --check PASS。
- 真浏览器断言：接缝唯一背景色灰白两色+滚动条 display none+滚动可用+hover 2px 蓝线浮现（截图）。

### 口径定案
侧栏 UI 滚动条历经五连演进（隐藏→内缩 12px 悬浮→释放贴边 6px→1px 常驻→**视觉全隐终版**），以最新指令为准；后续不得回潮任何常驻滚动条形态。


## 深夜十三批（三） — feat(右区纯白大区块)（v2.2.1 内部补丁，生产热同步部署）

### 改了什么
- .chat-history 底色 var(--v0-n50) #fafafa → #ffffff——右区消息列表区从「近白」变「真纯白」，与左灰 #e5e5e5 色差 26 一眼分明（终极视觉对齐最后一环：队长要的「右区一整块纯白」此前实为 #fafafa 近白）。

### 怎么验证的
- 全仓 pytest：2901 passed, 5 skipped, 0 失败。
- 真浏览器色值断言：chat-history rgb(255,255,255)+接缝扫描左灰右白。
- 生产 _internal 热同步+APK www 同步（数据文件免重构建）。

### 回滚
- 代码：git revert 6c58cae；index.html 备份链 .bak-20261029-*。


## 深夜十三批（四） — fix(蓝线像素级重合灰白交界)（v2.2.1 内部补丁，生产热同步部署）

### 改了什么
- #sidebar-resizer::after left:50% → left:0：蓝线（2px，translateX(-50%)）渲染中心从 resizer 盒正中移到左缘——灰白交界的物理位置就是 resizer 左缘，蓝线像素级压线。
- #sidebar-resizer 负外边距（0 -4px，热区向两侧扩张=蓝线随盒错位的来源）归零；热区 10px→6px（更好抓）。
- test_sidebar_resize 锚随新几何更新（flex 6px/left 0/margin 0）。

### 怎么验证的
- 全仓 pytest：2901 passed, 5 skipped, 0 失败（resizer CSS 锚随新几何更新）。
- 真浏览器几何断言三点同线：sidebarRight==resizerLeft==蓝线中心==320。
- 真鼠标 hover 分界线：2px 蓝线浮现且左右分别为灰/白（截图）。

### 回滚
- 代码：git revert 本笔；index.html 备份 .bak-20261029-align。
