# 小橘3号 本地开发时间线总结

> 编制日期：2026-10-02。
> 依据：《开发日志.md》（12 条倒叙记录，头部注明由五篇 DeepSeek 开发对话总结而成——原始分享对话已由创建者删除，本文设计溯源以该日志的既有总结为准）、《docs/DEMO_PACK.md》（基线 43b5515，1527 项测试）、《小橘3号项目现状交接摘要.txt》、git log 实际输出。
> 状态标记沿用三份主文档口径：🟢 已实现（代码可核对）｜🟡 模块已就绪·接线中｜🔜 规划中。
> 2026-10-02 当天 33 个提交的逐笔清单见 `docs/dev_changelog_20261002.md`。

---

## 一、时间线总表（起点 → 现在）

| 日期 | 节点 | 做了什么 | 对应提交哈希 / 证据 | 状态 |
|---|---|---|---|---|
| 2026-09-23 前后 | 十三小时极限开发 | 硬件就位（Orange Pi 3B：RK3566 / 8G / 128G NVMe，iPad 改造屏，天选5 RTX 4060 外援）；双脑热切换（本地 Ollama Qwen2.5:7b 优先、云端 DeepSeek 兜底）；网页与 QQ 记忆分家（`history_web.json` / `history_qq.json`）；沙箱白黑名单（`ALLOWED_DIRS` / `DENIED_DIRS`）；Cloudflare Tunnel 5G 远程管理（替代 Tailscale）；代码推 GitHub 开源。同期发生"小犟3号"事件（JSON 死循环）与"奶奶的故事"（社会工程学试探） | `e63a8d0`（09-30 重建基线一次性收纳此前历史，逐笔哈希不可考——待核实）；《开发日志》第五/四/三章 | 🟢 |
| 随后数日 | 军师建议 + "只认 XUN"执念 | `main.py` 退化为纯路由器；`brain.py` 立状态机（THINKING/ACTING/RESPONDING）；上下文将满自写 `history_summary.md` 交接文档；`plugins/` 插件化（七个插件，含 `dev_logger.py`）。同一执念孕育四级权限（LV4 XUN 专属 / LV3 动态密码）、哈希锁、开发者日志设想 | 《开发日志》第二/一章（五篇对话之总结） | 🟢 |
| 2026-09-26/27 | 开源上传 + P1 安全底座 + P1.5 立项 + 香橙派常驻 | P1 安全链"检测→打包→恢复"：`manifest.txt`、`checksums.sha256`、`xiaoju3_refresh.py`（重算哈希锁先过六位动态验证码）；P1.5 控制台与桌宠立项（`index.html` / `console.js` / `desktop-pet.js`，手绘草图定布局）；迁移香橙派 systemd 常驻（`Restart=always`，`restart_all.sh` / `stop_all.sh`） | 《开发日志》第七/六章 | 🟢 |
| 2026-09-28 前后 | 蓝图大会师 + 分发种子 + 合规觉醒 | 竞品调研（CowAgent / YesPaPa / Xiaomi Miloco 2.0 / Platypush / Anima / Thane）；全终端联动定义（手机/电脑/电视/智能家居）；"手机 A 损坏切至其他设备"设想入册（状态外置 `agent_state/`、MQTT 节点发现、独立看门狗、Git 版本化回滚）；一键部署与 LV2/LV3 注册设计（MAA 风格向导、LV3 强警告）；素材合规红线（MAA 为 AGPL-3.0，侵权素材换 CC0，`ASSETS.md` 区分代码 MIT 与素材 CC0，创作证据归档 `docs/creation-records/`，橘色狐狸娘定为 AI 生成） | 《开发日志》第十/九/八章 | 部分🟢部分🔜 |
| 2026-09-29 | 第一次"秽土转生" | `pack_all.sh` 打包 `xiaoju3_core.tar.gz` / `xiaoju3_full_project.tar.gz`，配套 `checksums.sha256` 哈希锁（启动校验，防篡改复活） | 《开发日志》第十一章 | 🟢 |
| 2026-09-30 | 公开版 + 三文档 + 日志成文 + 重建基线入仓 | 公开包 `xiaoju3_public_for_zcode.tar.gz` 校验（与完整源码逐字节一致，少聊天记录/身份文件/长期记忆）；架构/功能/界面三份设计文档（17 个评审问题逐条核对）；开发日志成文。**git 仓库首提交（重建基线，701 测试）**；Python 3.8 双版本工程化；硬件自适应路由 `DEVICE_TIER` 三档；权限定稿重构 + 敏感配置隔离区 `xiaoju3_data/.env`；Web 端 CQ 码净化 `web_sanitize.py` | `e63a8d0`、`d1d3275`、`9eb3ccf`、`9eddada`、`e7ab8ab`；《开发日志》终章 | 🟢 |
| 2026-10-01 | 端口统一与桌宠形态迭代 | Lv.3 免 sudo 根治 + CoT 思维链全链路；`_wrap_think` 成对保证与防缓存 `?v=` 注入；七项体验优化（桌宠去白底、TTS 音色、三平台真实温度）；新增 pywebview 桌面壳与 edge-tts 依赖；架构融合 5002→5003(302)；S1-S4 搜索源降级链 + 统一启动器 `xiaoju3_launcher` / 桌面主入口 `desktop_launcher`；**5002 彻底废弃**（`main.py` 不再监听端口，全部路由宿主 `xiaoju3_dashboard.py` :5003；桌宠暂下线只留加速球，1323 测试） | `912a677`、`c6d56fa`、`e9542b5`、`235211b`、`61f4dea`、`b4b0722`、`ea20915`、`9425d69`、`213dd97`、`4f2d570` | 🟢 |
| 2026-10-02 凌晨 | 急修与自动化 | 终端记录标签页新做；加速球头像换 `normal_half.png` + 🦊 兜底；`setup_napcat.bat` 一键装配 | `a7016fd`、`5bb2ddd`、`36d06d7` | 🟢 |
| 2026-10-02 白天 | 位置隐私防守链 + 人格与接入 | 位置隐私九连（指代消解→隐私模式→硬拦截→静默期→等待窗口，`user_location.json` / `/set_location` `/clear_location` / `[LOCATION:]` 标记）；回复去重与去黑框；心跳降噪与 QQ 思考隐藏；赤狐性格四档 + 七时段时间上下文；NapCat 静默拉起 | `a25edd8`、`191e2fc`、`23c4990`、`1e25735`、`bd193f8`、`b7c5802`、`609548b`、`58dde93`、`4c49b43`、`ded2dda`、`05b3f76`、`307b55a`、`a82ee34` | 🟢 |
| 2026-10-02 午后 | 权限重构 + 指令路由 | 批次①核心门禁定稿矩阵（危险设备/ADB/发图/重启自身收进 LV4，`restart_service` 白名单 13→14，先答复后 2 秒自尽；落库时 main 暂时红灯）；批次②儿童锁 + `creator.json` 署名四落点 + 监督线程复活链（main 恢复绿灯）；`/creator` 群前缀修复；指令路由紧急修复（LLOneBot @ 纯文本形态，13 处匹配点迁移） | `575c961`、`c86e627`、`4d94771`、`6938691` | 🟢 |
| 2026-10-02 晚间 | 冲刺之夜 | `DEMO_PACK.md` 四大创新点演示包；灵魂备份 `/soul_export`(Lv.3+) //`soul_import`(Lv.4)（MANIFEST.json 强校验 + .env 快照随包，实测往返 10 文件字节一致）；多设备守望 PeerWatch 接线；心跳误判修复；`input_number` 第七类、`binary_sensor` 第八类显式列入（感知域八类齐）；桌宠回归上线 + 三份文档对齐；强制自愈入路线图；服务稳定性修复（端口探测 + 日志轮换 + `restart_clean`）。测试收官 1540 全绿 | `8260f4b`、`7b14fe2`、`c9e44fc`、`8ea0b8c`、`c24e82d`、`f2db631`、`43b5515`、`34c5259`、`b5be73a`、`7b09bea` | 🟢 |
| 待办 | 1.0 交付缺口 | exe 安装器（pyinstaller 单文件打包）；完整文档清扫（功能文档 §1 多条 🔜 已落地、架构文档 §2/§4/§5 的 5002 旧口径、界面文档 §5.1 素材 404 / §5.5 5005 文案）；回家开灯补测（需 HA 用 YAML 建 template binary_sensor + light）；桌宠透明 PNG 素材替换（当前 `DSniang1.jpg` 字节副本占位） | 交接摘要待办节 | 🔜 |

## 二、设计思想溯源：早期对话 → 本地落地

> 出处章节即五篇 DeepSeek 开发对话的既有总结（《开发日志.md》头部注明）；原始对话已删除，原文不可得，以日志记载为准。

| 设计思想 | 出处 | 本地落地 | 状态 |
|---|---|---|---|
| "只认 XUN"身份执念 | 第一章 | 四级权限矩阵 `ACTION_LEVELS`（`permission.py:67-82`，14 能力键）；TOTP（`/coder_auth` Lv.3、`/lv4_auth` Lv.4）；哈希锁；xun 子串拒名（`9eddada`）；`creator.json` 署名（`c86e627`） | 🟢 |
| 防死循环熔断（小犟3号事件） | 第四章 | `brain.py` 检测 ❌ 工具结果硬拦截切断重试；连续多次同一操作被拒剥夺工具调用权 | 🟢 |
| 童话降级模式（奶奶的故事） | 第三章 | 写入优化清单——被拒时优雅引导到安全的虚构输出（代码级落地情况待核实） | 🔜 |
| 插件化 + 状态机 + 交接文档（军师建议） | 第二章 | `plugins/` 七插件（含 `dev_logger.py`）；brain 状态机；`history_summary.md` 机制 | 🟢 |
| 双脑热切换 | 第五章 | `brain.smart_ask`（`brain.py:1635`）本地 Ollama 优先/云端兜底；`DEVICE_TIER` 三档硬件自适应（`9eb3ccf`） | 🟢 |
| 桌宠人格（大肥鱼之位 → 橘色狐狸娘） | 第六章 | `desktop-pet.js` 双版本状态机（贴边/翻转/台词/音效）；2026-10-02 回归上线（`34c5259`）；透明 PNG 素材待替换 | 🟢（素材🔜） |
| 安全链"检测→打包→恢复" | 第七章 | `manifest.txt` / `checksums.sha256` / `xiaoju3_refresh.py` / `pack_all.sh` | 🟢 |
| 分发的种子（一键部署） | 第九章 | `pack_all.sh` / `install.sh` / 公开包已落地；exe 安装器未做 | 部分🟢（exe🔜） |
| 设备自动迁移（手机 A 坏→设备 B 接班） | 第十章 | `migration.py` `export_bundle`/`import_bundle` + `PeerWatch` 守望（`8ea0b8c`）+ `/soul_export` //`soul_import`（`7b14fe2`）；自动抢班留给部署编排层 | 🟢（抢班🔜） |
| 全终端联动 / QQ 家庭入口 | 第十章 | OneBot 11 webhook 宿主 ：5003 `/onebot`（`onebot_event`，`main.py:750-815`）；儿童锁 QQ 私聊裁决闭环 | 🟢 |
| 教师—学生—裁判（先锁住再学习） | 第七章 | 未落地 | 🔜 |
| 提线木偶（多节点算力分发） | 黑话词典 | 未落地 | 🔜 |
| 全面刷新重启机制 → 强制自愈 | 第一章执念 → 路线图 | 强制自愈（Recovery Mode）入路线图 #27（`b5be73a`；前提：非对称签名 + 内置公钥 + 只读恢复通道）；近景为 `restart_service` 白名单 + 复活链（`575c961`/`c86e627`） | 🔜（近景🟢） |

## 三、四大创新点现状（对照 DEMO_PACK）

| # | 创新点 | 状态 | 关键证据 |
|---|---|---|---|
| 1 | 物理安全底线 + 软件四级权限 | 🟢 | `ACTION_LEVELS`（`permission.py:67-82`）；三档工具门禁（`tools.py:78-84`）；儿童锁全链（`main.py:183-258`）；物理开关绝对优先（功能文档 §8.0） |
| 2 | 设备自动迁移 / 灵魂备份 | 🟢 | `/soul_export` //`soul_import` 已落地（`7b14fe2`）；PeerWatch 已接线（`8ea0b8c`）；HTTP API 与控制台入口未实现（🔜） |
| 3 | 本地优先双脑 + 完整设备接管链 | 🟢 | `smart_ask` 双脑 + 14 项工具白名单（`brain.py:146-153`）+ ADB/HA/文件三类执行臂同一门禁 |
| 4 | QQ 家庭入口 + 桌宠人格 | 🟢 | `/onebot` webhook；桌宠 2026-10-02 回归上线；透明 PNG 素材待替换（🔜） |

## 四、7 天冲刺进度对照（2026-10-03 ～ 10-09 计划）

| 日程 | 计划项 | 实际 | 状态 |
|---|---|---|---|
| 10-03 | help 修复 + DEMO_PACK | help 修复与 `DEMO_PACK.md` 均已于 10-02 完成（`8260f4b`） | ✅ 提前 |
| 10-04 | 设备自动迁移最小可用版 | `/soul_export` //`soul_import` 已于 10-02 落地（`7b14fe2`） | ✅ 提前 |
| 10-05 | 多设备守望最小版 | PeerWatch 已于 10-02 接线（`8ea0b8c`） | ✅ 提前 |
| 10-06 | 主动服务心跳真实场景 | 感知域八类已齐（`c24e82d`/`f2db631`/`43b5515`）；场景规则②（湿度→模拟加湿器）已生产验证；规则①回家开灯待 HA 实测 | 🟡 |
| 10-07 | 桌宠完整形态 | 已于 10-02 回归上线（`34c5259`，三能力零补缺）；透明 PNG 素材待替换 | 🟢（素材🔜） |
| 10-08 | 权限批次③文档清扫 + 三文档对齐 | 三文档对齐 23 处已随 `34c5259` 完成；遗留清扫未完（见待办） | 🟡 |
| 10-09 | exe 安装器 + 全量回归 + 打包 | 未开始 | 🔜 |

## 五、关键架构决策（截至 2026-10-02 深夜）

- 5002 彻底废弃：`main.py` 不再监听端口，全部路由宿主 `xiaoju3_dashboard.py` :5003（`4f2d570`）。
- QQ webhook 地址：`http://127.0.0.1:5003/onebot`。
- 敏感配置隔离区：真实 `.env` 在 `xiaoju3_data/.env`（gitignore，`9eddada`）。
- 心跳感知域八类（`input_number`、`binary_sensor` 显式列入，`f2db631`/`43b5515`）。
- `restart_clean.bat` / `restart_clean.sh` 为唯一推荐重启入口（`7b09bea`）。
- 强制自愈（Recovery Mode）入远期路线图 #27，前提：非对称签名 + 内置公钥 + 只读恢复通道（`b5be73a`）。
