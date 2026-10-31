# 开发者日志 2026-10-31

> 按提交逐条快照。生产部署：exe 0f2e1d8c（F:\XUNandxiaoju3，回滚锚 xiaoju3.exe.bak-20261031-da1 + _internal.bak-da1）。

## 1. 总纲三文档审计 v2（等队长审阅期完成，本日队长拍板通过）

- 《架构设计文档》《功能文档》《用户界面设计文档》从 2026-09-29 旧版刷新至 v2.2.1 实态：双脑口径反转（云端全权接管）、CommandBus/意图路由、上下文三桌、影子审查、部署三形态、主从多端方案 A 入档；新增能力边界查证章与业界共识对照表（Vercel parts 状态机/Copilot 指引/HITL 卡/M3 抽屉）。
- 三路查证代理（架构共识/能力边界/UI 规范）+ 移动端三文档 v2（_dev/docs/design_mobile_*.md，查证前置版）——六文档同批，队长全数拍板通过。

## 2. 桌面全自动操控立项（队长拍板，两轮）

- 一轮拍板：删除"不承诺全自动操控"绝对表述 → 分阶段演进；恋爱模拟条目保持现状。
- 二轮拍板：单步确认不得作为独立产品阶段（反人类）→ **两段式**：阶段一=技能录制回放，阶段二=沙箱内全自动执行（早期 HITL 确认卡调试、稳定后退居幕后=「豆包模式」）。
- 《桌面操控能力演进路线》（_dev/design_desktop_automation_roadmap.md）落盘：豆包工作命名澄清（=字节 2026-08 生产力产品线，桌面操控=豆包电脑版"工作任务—操作电脑(虚拟桌面)"）、三阶段定义、安全栈五条、**沙箱选型调研章**（微软 Agent Workspace/阿里 OpenSandbox 16.3k★/EdgeBox/trycua cua 31.4k★/E2B/microsandbox/Windows Sandbox/独立标准账户/CreateDesktop 全查证+三约束评价）、参考资料 26 条。

## 3. DA1 桌面技能录制回放（阶段一落地，已部署生产）

- **desktop_tools.py**（新，~650 行）：UIA 定位链录制（祖先链 ≤12 层，比裸坐标抗 DPI 漂移）+ pynput 全局钩子（回调只入队、独立 worker、job 线程 COM 自初始化）+ 技能库 agent_state/skills/（frozen 安全路径）+ 敏感硬拦截 fail-closed（标题黑名单 env 可覆盖 + UIA IsPassword + 键盘钩子前台窗口归属）+ 全量审计 JSONL。
- **tool_registry**：desktop_list_skills/desktop_run_skill/desktop_list_windows 三工具全 LV4（run=dangerous+is_action），一处登记三处生效。
- **dashboard**：/api/desktop/record/{start,stop,status} + /api/desktop/skills(+run) 五端点；**console.js** 🧰 面板"技能录制"卡（disc/play SVG 图标入 ICON_SVGS；showConfirm 回放确认）。
- **spec**：hiddenimports 18 项（含 pynput._win32 后端——动态 import 陷阱）+ mobile 三件 datas。
- **DeepSeek 秘书审查**（4 致命点全采纳）：UIA 调用超时降级、hotkey vk 直取禁 char 反推、type_text 焦点投递不挂控件、DPI 比对不过禁坐标回退、comtypes gen 目录重定向 agent_state。
- **E2E 六轮实证修复**（全数据驱动，零猜测）：job 线程漏 CoInitialize→每击必超时；Win11 记事本未保存 `*` 标题前缀→_norm_title 归一化；UIA SetFocus 不抢前台→_bring_foreground；可编辑控件后缀匹配（DocumentControl≠"Document"）；UWP 新记事本保存加速键对合成输入免疫（已知限制落档）；E2E 验收姿势改全新窗口（避免保存冲突弹窗）。
- **验收**：真机 E2E 录制 4 步→**回放 5/5 全 PASS**+敏感窗口 19 按键事件全拦 0 步落库；全仓 **2982 passed / 0 failed**（+26 新锚）；node --check 过；PYZ 18/18 模块+8 深锚；冻结烟雾（录制链在冻结环境全活）；生产部署验活（health/skills/status/mobile.html 全 200）。

## 4. MA1 移动端骨架（工作流交付，随本批部署）

- mobile.html/css/js（独立入口）+ index.html head 一行路由；真浏览器 412×915 **12/12 验收全过**（1 轮修复回归）；三张截图交付队长；桌面 DOM/console.js 零改动。
- 手机浏览器测试：http://100.114.110.94:5003/console 自动跳转 mobile.html（**已随本批在生产可用**）。

## 5. 顺修回归与坑库

- **修 fc3b68c 回归**：index.html 写死 ?v=20261030b 打穿 dashboard mtime 自动版本注入（桌面端缓存自动失效失效）——版本注入正则化：源为裸引用或 ?v= 引用一律重写为 mtime 动态版（APK file:// 静态 ?v= 保留，桌面动态版恢复）。
- 既有 3 个前端测试锚（chat_container_id_consistency 缺 xj3-link-banner 自建 id / desktop_pet 断言未兼容 ?v= / mtime 版本断言）随修全绿。
- **坑库新条目**：①Git Bash `cmd /c xxx.bat` 的 /c 会被路径转换吃掉（cmd 只打横幅即退）→ 必须 MSYS_NO_PATHCONV=1；②同名进程 taskkill /IM 通杀会误杀生产（冻结烟雾曾杀掉生产三进程）→ 冒烟/部署窗口分离，窗口内通杀才安全；③comtypes/UIA 每个新线程必须自行 CoInitialize（job 线程漏 init=UIA 必败）；④Win11 UWP 记事本标题 `*` 前缀+保存加速键免疫合成输入；⑤heredoc 写含反斜杠路径必炸（\n 被吃）——铁律再锤：一律 Edit 工具；⑥Edit 工具对"被 Bash 侧脚本改过的文件"file-state 过期会拒改——重读再改。

## 6. 合规批（队长最高红线：全生命周期法律合规，ee66ef0 已推已部署 exe afe265d9）

- **pynput=LGPLv3 按红线移除**：录制层换自研 ctypes LL 钩子（WH_MOUSE_LL/WH_KEYBOARD_LL，零第三方依赖）；DeepSeek 秘书裁决路线 A（LGPL 不在白名单+冻结包可替换机制举证困难）。工程坑四连实锤：回调对象挂 self 防 GC（临时 _HOOKPROC 被 GC=钩子触发即访问违例进程死）、64 位句柄 argtypes 纪律（GetModuleHandleW 截断=126）、ToUnicode 规范修饰键位（VK_LSHIFT 无效须同置 VK_SHIFT）、退出先 Unhook 再 WM_QUIT。
- **敏感进程黑名单实装**：is_sensitive_proc（密码管理器类默认表，env XIAOJU3_DESKTOP_PROC_BLACKLIST 可覆盖）——标题+进程+IsPassword 三层 fail-closed。
- **免责声明实装**：🧰 技能录制卡常驻免责（自动化可能存在误差/重要文件请备份/仅限本地个人辅助）+回放 showConfirm 二次确认含备份提示。
- **协议清单落档**：在包库 uiautomation=Apache-2.0/comtypes=MIT（本地 LICENSE.txt 原文核）/pyautogui=BSD/psutil=BSD-3——零强传染；调研过的沙箱方案协议全标注（EdgeBox=GPL-3.0 ⛔ 规避）。
- **路线图新增 §九《法律与合规风险规避》**：队长五条红线逐条落实表（协议/隐私 PIPL/素材版权/爬虫 robots/防滥用）。
- 验收：真机 E2E 复跑回放 5/5+敏感 19 拦截+Shift 大写探针 PASS；全仓 2984 全绿；PYZ 13/13+**pynput 零残留**；生产部署 exe afe265d9 验活（三进程 StartTime 全新+desktop 端点+mobile.html 200）。

## 7. MA2 移动端 API 接线（计划模式拍板后落地，已部署生产 exe 70efff7e）

- **计划模式流程**：两路侦察（后端 SSE 契约/console.js 可镜像面+mobile 骨架空壳点）→ 计划含队长五问逐条 → 拍板后执行。
- **mobile.js 网络层重写**（~560 行，全部带 console.js@ee66ef0 溯源注释+同步清单 _dev/mobile_sync_checklist.md）：①探活自愈 15s 周期（probeBase 镜像，MA2 只探当前 base）②历史加载 50 条淡入③流式对话 fetch+ReadableStream（帧 pump/think 乐观卡骨架→逐行→done 折叠/answer 流式/看门狗 30-90-190s/legacy /api/chat 回退/富文本 renderRich+表格横滑）④事件总线 EventSource（bus_reply 气泡+collab_msg HITL 卡）⑤**HITL=老板手机审批面**（选项纵排全宽≥44px+自定义输入→POST /api/collab/send body.text 契约→写回 TASK_BUS [老板拍板]）。
- **E2E 真链路五断言链全过**（IAB 412×915 视口+dev 后端 5077 真云端）：历史 50 条渲染/流式全链（含修"乐观卡僵尸"bug：done 后不移除=留'正在思考…'）/HITL 渲染+点同意→TASK_BUS 实落 [老板拍板]（含修 text 契约错发 message）/失联横幅出现+恢复自动消失/桌面 console.js+index.html 零 diff。截图 3 张 _dev/shots_ma2/。
- **秘书复审两项落地**：①钩子存活看门狗（录制会话每 10s 自检句柄+线程，失效自动停录+hook_lost 如实上报）+入队 SimpleQueue.put_nowait 非阻塞（异常计数 dropped）②**技能文件脱敏 schema v2**：窗口标题明文禁令——落盘只存 proc+title_hash(sha256[:12])，回放两段式定位（进程名候选→哈希锁定，同进程多窗口精确匹配），v1 legacy 兼容；审计与回执零明文标题。
- **排障实录**：HITL 测试三轮定位（页内探针→hub 日志→py-spy）——真因链=双 dev 服务同占 5077（taskkill /FI 失败残留）+端点字段 data.items 非 messages（测试解析错）+send 契约 body.text；hub 本体零 bug（插桩实证后全撤，collab_hub 零 diff）。
- 验收：全仓 2988 全绿；PYZ 新锚（watchdog/hash）全在+mobile 三件 datas 在包；生产验活（StartTime 全新+mobile.js 200+record/status 新字段 dropped/hook_alive 在线）。

## 8. 红线加固+排雷+MA3/MA4 批（7a0d14a 已推已部署；APK v2.3.0-ma3 交付）

- **双端网络核心唯一实现**（排雷红线）：xj3_network_core.js（probeBase/chatStream/看门狗/帧解析，零 DOM）；console.js+mobile.js 全部换核；契约测试锚随迁（9 个测试文件级迁移）。坑：多段 rep 脚本中断=内存假象二犯（铁律三锤：逐段落盘）。
- **红线 A2 离线草稿箱**：断网→localStorage 队列→探活恢复自动补发（E2E 实测全链）；横幅带队列数。
- **红线 A3 崩溃自愈**：错误红条+crash.html+MainActivity onRenderProcessGone→recreate()（RenderProcessGoneDetail=android.webkit 顶层类——嵌套写法三连编译失败的根因，秘书裁决）。
- **B5 ES 退避重连双端**：2s→30s+抖动；文档级绑定防重复挂载。
- **MA3**：/api/stt/transcribe（edge-tts 合成语音实测全字一致）+/api/attach_upload（doc_ingest 解析链）+麦克风录音态/附件按钮接活。
- **MA4**：抽屉四面板全活（待办 done/reopen/快捷 chips 直发/连接设置 BASE 持久化/关于版本）。
- **APK 复仇之战**：www→mobile 入口+assets/public 白名单入库（惨案根源根除）+RECORD_AUDIO+构建成功；模拟器挂账（AEHD 驱动需管理员安装，logic 级 E2E 已全过）。
- **紧急修复**：B4 首脚本中断致 spec/dashboard 编辑丢失→生产 desktop 引用 404 的 core.js——补齐+重建+重部署（dc7c7f04），core.js 200+页面注入实证。
- 坑库：多段脚本内存假象（二犯）/heredoc 反斜杠（三犯）/双 dev 服务占 5077/gitignore 无斜杠锚/gradle mergeAssets 不追 www 手改（须直填 assets/public）。

## 9. APK 版本号紧急修复（队长真机实锤，d163c09 已推）

- **事故**：v2.3.0-ma3 APK 只改了文件名，工程内部版本标识未动——真机安装界面显示 2.2.1->2.2.1，覆盖安装被系统视为同版（缓存/覆盖语义全部失真）。
- **修复**：android/app/build.gradle defaultConfig versionCode 2→3（覆盖安装严格递增）+versionName "2.3.0-ma3"；aapt dump badging 实证 `versionCode='3' versionName='2.3.0-ma3'`。
- **坑库**：APK 改版必须同步动 build.gradle 版本三件套（versionCode 递增+versionName），文件名只是皮肤。
- **交付**：桌面「小橘手机端_2.3.0修复版.apk」+dist/phone/xiaoju3-phone-v2.3.0-ma3.apk 同步（3.6MB，入口=mobile/crash.html/core.js 全在包）。

## 10. 会话终态（上下文 93.2% 移交）

- **双轨交付完毕**：MA3 全活（五断言链）+维特根斯坦灵魂重铸+红线加固+中继 v2 方案
- **APK**：v2.3.0-ma3（versionCode=3，零外链，CSS 内联，错误钩子，诊断条三击，崩溃接管）→ 桌面+dist/phone 双交付
- **生产 exe**：dc7c7f04 三进程全新（回滚锚 .bak-20261031-da1）
- **维特根斯坦铁律**：prompts.py 双注入+AGENTS.md 灵魂原则章+positioning 章节
- **中继 v2 方案**：信令=Python aiohttp WS+E2EE=PyNaCl+降级链=P2P→30s→中继+成本 38-68 元/月
- **移交**：APK 真机验证（队长）/AEHD 驱动安装（管理员）/MA4 体验补齐/RS1-RS4 拍板/生产重启（灵魂上线）

---

## 深夜二段：RS1 信令闭环+双端握手+E2EE 落笔+移动端降级（f461bb2 已推，全仓 2988+5 复验 142s）

- **RS1 车站调度室**（_dev/relay/，git 外）：server.py（aiohttp WS+注册路由表+主动 Ping 15s 摘座+同账号广播）四需求独立验收员 9302 重放 pass；client_mock.py 四步闭环实拍（loop_proof.png）
- **双端握手（队长拍板冲刺件）✅**：python-zeroconf 0.152.0 实装，mDNS `_xiaoju._tcp.local.`，两独立进程经信令服务器握手成功（发现→注册→招手→接受→hello 互达，三方日志合图 lan_handshake.png）
- **E2EE 定稿落笔**：队长确认 v2.1 提案→主文档四条改毕（KEM-DEM：sealed box 封会话密钥+XChaCha20-Poly1305-IETF 数据面），独立审读逐项过+残留扫描零混写
- **设计文档双新章**：《多终端形态分级与自适应路由》+《设备能力分级与渐进增强（Graceful Degradation）协议》（L0-L3 矩阵+capabilities 契约+统一接口红线），各过独立审读
- **移动端能力降级上线（f461bb2）**：setConnState 唯一落点+body data-caps（l2/l0）+4 处 data-needs-server 门控+聊天/草稿箱永存；versionCode 4/2.3.1-cap；验证=node --check+静态断言+412×915 两态黑盒复验
- **销账**：dist 旧 v2.2.1 包删（git 零追踪证+哈希核对）；TASK_BUS 两备注→todos #11(P2)/#12(P3)
- **拍板记录**：E2EE 确认 ✅／MA4=D 暂缓／LAN 选型=python-zeroconf+capacitor-zeroconf 锁 3.0.0（4.0.0=Cap 7 勿装）+浏览器 JS 无组播走二维码兜底
- **交付包**：桌面「小橘RS1交付_20261031」（4 截图+README）

## 深夜三段：P0 白屏排障根治（bf4b6a8 已推，全仓 2988+5 复验 152s）

- **事故**：v2.3.1-cap 真机白屏 net::ERR_CONNECTION_REFUSED@http://localhost/（电脑/后端均在线）
- **根因（行级实锤）**：MainActivity.java:25（7a0d14a 崩溃接管块）用裸 WebViewClient 整体替换桥 client，拆掉 BridgeWebViewClient.shouldInterceptRequest→WebViewLocalServer（Capacitor 本地资产拦截唯一入口）→主文档请求直落网络栈→手机本机 80 拒连。源码注释自评"影响极小"系误判；好包同带此雷只是未触发二次导航
- **洗清**：配置层（无 server.url/包内 config 与好包逐字一致）+资产层（解包五项：入口完整/无跳转替换/无 query 毒化）+data-caps 前端（纯 CSS/DOM 属性，回归审查双证排除）
- **修复**：RenderGoneClient extends BridgeWebViewClient 仅覆写 onRenderProcessGone+bridge.setWebViewClient 正门装回（资产拦截/外链/onPageStarted 全链保留）
- **顺手排雷**：android_app/www 同步当前真源（87163B→88759B，防 npx cap sync 旧内容盖回）
- **交付**：v2.3.2-fixcap（versionCode 5，3,832,843B）dist/phone+桌面双位置；坏包留证 .broken-20261031
- **验收**：六道门自验（8 资产 md5 全等）+独立验收五条 PASS+Chrome 本地打开非白（亮度 245.99/非白像素 99.92%）
- **🔴 新坑入档**：裸 setWebViewClient 替换=拆 Capacitor 资产拦截唯一入口，任何二次导航（进程恢复/recreate/crash 重试/reload）必白屏——APK 侧加 WebViewClient 只能继承 BridgeWebViewClient 且走 bridge.setWebViewClient 正门
- **战报失实自纠**：工作流结论"桌面副本已交"实际 copy 退出码 1，主会话人工补齐并如实报备
