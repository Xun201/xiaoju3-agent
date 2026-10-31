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
