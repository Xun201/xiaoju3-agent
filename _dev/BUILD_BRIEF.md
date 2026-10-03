# 小橘3号（xiaoju3-agent）重建开发规范书（全体子智能体必读）

> **第二阶段（2026-09-30）增补**：用户已解除"不新增外部依赖"限制，允许安装 Playwright 等第三方库。
> 第二阶段规则见文末 §6，与 §0–§5 冲突处以 §6 为准（安全红线 §1 仍然全部有效）。

## 0. 唯一准则与参照
- **唯一准则**：`F:\Orangepi_number3\架构设计文档.md`、`功能文档.md`、`用户界面设计文档.md`、`README.md`。行为、模块划分、状态口径（🟢 必须实现）以文档为准。
- **保真参照**：`C:\Users\Xun\.zcode\workspace\default\_source\public\xiaoju3-agent\` 是与文档逐行对应的参考实现。函数签名、提示词文案、CQ 码格式、API 返回结构等细节以它为准；**与文档冲突时以文档为准**。
- 目标目录：`F:\Orangepi_number3`（Windows，Python 3.14，Git Bash）。五个设计文档 README.md/架构设计文档.md/功能文档.md/开发日志.md/用户界面设计文档.md **不得改动**。

## 1. 安全红线（违反即返工）
1. **禁止复制**参考代码中的：内网 IP（如 `192.168.31.*`）、任何 API Key / Token / 密码、`agent_state/identity.json.bak`、`*.log`、`workspace/` 内容、`dashboard.log` 等运行数据。
2. 所有配置一律：**环境变量优先 → 中立默认值兜底**。Ollama 默认 `http://127.0.0.1:11434`；DeepSeek 默认 `https://api.deepseek.com`。
3. 新建 `.env.example` 模板（键名列表，不含真实值）。提供极简 stdlib 版 `.env` 加载器（不放 requests/dotenv）。
4. `.gitignore`（如不存在则创建）：`.env`、`agent_state/history_*.json`、`agent_state/identity.json`、`agent_state/long_term.db`、`workspace/`、`*.log`、`__pycache__/`。

## 2. 依赖白名单（停止条件）
- **允许**：Python 标准库 + 已安装的 `flask`、`flask-cors`、`psutil`、`requests`。
- **禁止**：任何 `pip install`。`playwright` 未安装——涉及它的模块必须**延迟导入 + 优雅降级**（缺库时报清晰中文提示，不得让 import 崩溃）。
- 测试**只用标准库 `unittest`**，必须离线可跑（网络/子进程一律 mock）。
- **停止条件**：若你的模块确实绕不开白名单外的新依赖，或连续 3 次报错无法解决 → 立即停止并在结果中如实汇报，不要自行绕过红线硬凑。

## 3. 统一配置契约（防止并行冲突）
配置统一定义在 **`xiaoju3.py` 顶部**（文档 §3.6 口径：配置之源），全部环境变量可覆盖；其他模块 `from xiaoju3 import ...`。xiaoju3.py 的 CLI 交互必须放在 `if __name__ == "__main__":` 内，保证 import 零副作用。键名（与文档/参考一致）：
`DEEPSEEK_API_KEY`(env)、`LOCAL_URL`、`LOCAL_MODEL`(默认 `qwen2.5:7b`)、`CLOUD_URL`、`CLOUD_MODEL`、`WORKSPACE`(默认 `<项目根>/workspace`，惰性创建)、`MAX_MESSAGES`(50)、`HA_URL`、`HA_TOKEN`、`WEB_API_KEY`、`VISION_MODEL`、`VISION_KEY`。
路径相关一律 `os.path`/`pathlib` 处理，兼容 Windows 与 Linux。

## 4. 跨模块接口契约（签名以参考实现为准，逐个核对后再动手）
- `tools.execute_tool(tool_name, args, permission_manager) -> str`；`DANGER_TOOLS = {write_file, adb_tap, adb_swipe, control_ha_device}` 需 LV3（write_file 权限），否则返回 `❌`开头的中文安全拒绝文案；文件读写以 realpath 前缀校验限制在 WORKSPACE 内；`read_file` 截断 1000 字符；10 项白名单：list_files、read_file、write_file、get_ha_devices、control_ha_device、adb_screenshot、adb_tap、adb_swipe、vision_tap_element、ui_tap_element。
- `permission.PermissionManager`：等级 Lv.1–Lv.3；权限表 LV2 += read_file/list_files，LV3 += write_file/modify_code/manage_plugins（web_search 为预留空名额）；`load_identity()` 启动读取 `agent_state/identity.json`、`save_identity()` 落盘（**不接线**到 /coder_auth，保持文档口径）；文末保留隔离区私有扩展挂载点（try-import，缺省回退默认实例）。
- `brain.ask_local(messages) / ask_cloud(messages) / smart_ask(message, history) -> (reply, source)`，来源标签 `🏠 本地` / `☁️ 云端`；每条消息先 ~1 秒探测本地 Ollama，异常热切换云端；工具 JSON 用正则提取一行 JSON → 白名单校验 → execute_tool → 结果喂回 ask_cloud 汇总（每轮最多一次工具调用；工具结果以 `❌` 开头时切断重试，防死循环）；输入含 URL → 抓正文（剔除 script/style）先总结再回答；`MAX_MESSAGES=50` 截断；`translate_emoji` 已实现但不接入回复链（文档 §5 口径）。
- `prompts.py`：系统提示词含 10 项工具协议（"只输出一行 JSON"）+ 点击优先级规则（有明确文字元素必须先 ui_tap_element，失败才 vision_tap_element）。
- `agent_state/state_manager.py`：sqlite3 `long_term.db`；memories 表；`save_memory` / `get_recent_memories` / `save_conversation`（JSON 落盘最近 50 条）。
- `main.py`（Flask，:5002）：`GET /` 内联深色聊天页；`POST /chat` 校验 `X-API-Key` 头；`POST /onebot` NapCat webhook；`handle_message`：标点清洗 → 内置指令（/help、/coder_auth、/gen_log、/send_image）→ 群聊触发词过滤（小橘/小桔/橘3号/橘三号/AI测试，@ via CQ 码）→ 双通道记忆（`agent_state/history_qq.json` / `history_web.json`，互不干扰，50 条截断）→ `brain.smart_ask`；QQ 侧取 res[0]；`/send_image` 需 LV3 且路径在 WORKSPACE 内；群聊图片消息（非 @）自动收藏表情链接（emoji_manager）。
- `xiaoju3_dashboard.py`（Flask，:5003）：`GET /` 旧版蓝色单页（含运行时长与来源标签）；`GET /console` 托管新版控制台；`/api/status` → `{code, data:{cpu, memory, temperature, timestamp}}`（psutil，温度取 sensors 失败回退 0.0）；`/api/balance` → `{balance, currency, today_usage, is_peak}`（today_usage 按文档口径恒 0.0）；`/api/chat` **直连 brain.smart_ask**（不经 handle_message、不写双通道记忆），返回含 `reply` 与 `source`。
- 前端三件套 `index.html` / `console.js` / `desktop-pet.js`：严格按《用户界面设计文档》令牌表（主色 #203170 等）与交互规范（2s 状态轮询、>80% 变红 #e0433f、60s 余额轮询、欢迎语、复制/TTS/点赞点踩本地互斥、刷新/转发 alert 占位；桌宠 IIFE 单例、250px 基准 × --pet-scale、按压形变、拖拽阈值位移平方>9、边界钳制、resize 重钳制、内联 SVG 气泡 5s 关闭、余额气泡；报错文案端口写 **5003** 不写 5005）。
- `heartbeat.py`：60 秒轮询 HA /api/states，只关注 input_boolean/light/switch/sensor/climate/media_player 六类；快照无变化跳过；变化时 ask_cloud 决策 → 提取工具 JSON → 直接执行。
- `home_tools.py`：`get_ha_devices()`（六类过滤）、`control_ha_device(entity_id, action)`（turn_on/turn_off/toggle）。
- `adb_tools.py`：subprocess 调 adb（screenshot/tap/swipe）；`android_ui_tools.py`：uiautomator dump XML → 按文本/描述定位 → 中心点点击；`vision_tools.py`：截图 → 云端视觉模型 → 坐标 → 点击（VISION_MODEL/VISION_KEY 走 env）。
- 插件（`plugins/`，`__init__.py` 由接入层负责人创建）：`help_menu`（按等级渲染菜单）、`context_manager`（compress_context：>20 条把旧消息浓缩为 ≤50 字前情提要，本地优先失败转云端）、`link_logger`（DeepSeek 分享页校验 + Playwright 抓取，**延迟导入**）、`batch_logger`（4000 字分片逐片总结 + "倒叙说书人"风格汇总）、`dev_logger`（旧版日志生成器，保留不接线）、`qq_send_image`（CQ 发图封装，保留不接线）。
- `run_link_log.py`：校验 `chat.deepseek.com/share/` 前缀 → 抓取 → 分片总结 → 倒叙成篇 → 自动编号 `dev_log_N.md` + 倒序合并 `ALL_LOGS.md`，原始文本落盘备查。
- `xiaoju3_refresh.py`：动态 6 位确认码校验 → 重算 sha256 → systemctl 重启（systemctl 调用须可 mock，核心逻辑可离线测）。
- 部署脚本：`start.sh`（守护循环，异常退出 2 秒拉起，stop.flag 安全退出）、`secure_start.sh`（sha256sum -c 校验后启动）、`stop_all.sh`（密码确认、清进程、释放 5001-5003、停 napcat/homeassistant 容器）、`start_dashboard.sh`、`restart_all.sh`、`push.sh`（四道扫描：文件名黑名单/明文 Key/git 历史 Key/可选深度扫描，命中拦截回滚）+ `manifest.txt`/`checksums.sha256` 生成方式说明。

## 5. 交付与验收
- 每个模块附带 `tests/test_<模块>.py`（unittest，离线，mock 网络/子进程/文件系统副作用用 tmp 目录）。
- 交卷前必须实际运行 `cd /f/Orangepi_number3 && python -m unittest tests.test_<你的> -v` 并如实汇报通过/失败清单。
- 汇报格式：完成的文件清单、测试结果（X passed / Y failed）、已知限制、是否触发停止条件。
- 代码注释风格与参考一致（中文、简洁）；所有文本文件 UTF-8。

---

## 6. 第二阶段增补规范（2026-09-30 迭代）

### 6.1 依赖政策变化
- **允许安装第三方库**（用户已授权），但白名单精神保留：只装任务必需的库，禁止顺手装无关依赖。
- Playwright 由专门子智能体统一安装（`pip install playwright` + `playwright install chromium`），其他子智能体**不得重复执行安装**，直接按"已可用"编码并保留优雅降级（浏览器缺失时报中文提示）。
- 测试仍以 unittest 离线为原则：网络/浏览器/子进程一律 mock；涉及真实浏览器的链路测试标记 `@unittest.skipUnless` 环境开关（如 `XIAOJU3_LIVE_TEST=1`）才运行。

### 6.2 第二阶段任务与文件所有权（并行冲突防线）
| 子任务 | 独占文件（可改） | 交付内容 |
| --- | --- | --- |
| S1 /gen_log 完整链路 | `requirements.txt`、`plugins/link_logger.py`、`plugins/dev_logger.py`、`run_link_log.py`、`tests/test_link_batch.py`、`tests/test_genlog_live.py` | 安装 playwright+chromium；真实抓取渲染链路；EPUB/文本落盘不变 |
| S2 对话核心增强 | `brain.py`、`tools.py`、`prompts.py`、`search_tools.py`(新)、`tests/test_brain.py`、`tests/test_tools.py`、`tests/test_prompts.py`、`tests/test_permission.py` | 防死循环熔断；工具汇总轮本地优先(失败转云端)；web_search 工具入白名单(11项)；[EMOJI:] 接入回复链；高危工具重复被拒计数 |
| S3 认证/迁移/家居增强 | `auth_lv4.py`(新)、`migration.py`(新)、`heartbeat.py`、`home_tools.py`、`tests/test_auth_lv4.py`、`tests/test_migration.py`、`tests/test_heartbeat.py`、`tests/test_home_tools.py` | LV4：TOTP(stdlib 实现)+可插拔因子链+类Root警告文案；设备迁移：灵魂备份 export/import + 多设备守望 peer watch；心跳决策本地优先；传感器场景规则(回家开灯/干燥加湿)；温控 set_temperature；高危实体(锁/燃气)分类 |
| S4 意图路由与新插件 | `intent_router.py`(新)、`plugins/accounting.py`(新)、`plugins/ebook_export.py`(新)、`tests/test_intent_router.py` | 自然语言意图路由(记账/导出电子书/搜索/表情等直达)；记账本(JSON 持久化)；EPUB 电子书导出(zipfile stdlib 实现) |
| S5 main.py 总接线 | `main.py`、`emoji_manager.py`、`tests/test_main.py`、`tests/test_emoji_manager.py` | /register 处理器(LV2+落盘)；/coder_auth 接 save_identity 持久化；/lv4_auth(TOTP+因子+Root警告)；意图路由接入 handle_message；前情提要压缩接线(替代纯50条截断)；长期记忆接入对话链；表情包下载+配图回复闭环；高危家居二次确认令牌流 |
| S6 仪表盘/前端 | `xiaoju3_dashboard.py`、`index.html`、`console.js`、`desktop-pet.js`、`tests/test_dashboard.py` | 控制台聊天历史持久化(/api/history + 页面加载)；桌宠翻转/边缘吸附/随机台词气泡；移动端 viewport+响应式；WebAudio 按压音效/提示音(免素材)；刷新/转发按钮实装；橘色主题 CSS 变量(皮肤系统基础) |
| S7 一键部署 | `install.sh`(新)、`tests/test_scripts.py` | 一键安装器：venv+pip install -r requirements.txt+playwright install chromium+.env 生成引导+完整性校验+启动+LV3 类Root警告提示；不碰 requirements.txt(S1 独占) |

- **人人禁改**：`xiaoju3.py` 配置区块、`.gitignore`、`.env.example`、`manifest.txt/checksums.sha256`、五份设计文档、他人所有权文件。新配置键在**自己模块内** env 读取（main.py 先例），并把键名报给主控统一补进 `.env.example`。
- **跨模块调用**：S5 是唯一接线人（import S2/S3/S4 的模块）；S3/S4 的模块必须保证 import 零副作用、函数签名稳定、可独立单测。接口先写进自己模块 docstring。
- **阶段一既有测试**：行为被路线图升级改变的（如 test_brain 的"汇总固定云端"、test_main 的"升级不落盘"、白名单 10→11 项），由对应所有权人同步修改测试并保持 discover 全绿。
- 新增运行数据一律补进 `.gitignore` 的需求报主控（如迁移包 `*.migrate.zip`、TOTP 密钥、记账本数据）。

### 6.3 第二阶段验收
- 每子任务新增代码必须有对应 unittest 且离线通过；交卷前跑 `python -m unittest discover` 全仓无回归（327+ 基线）。
- 主控终验：全量测试、双进程启动冒烟、真实 Playwright 抓取冒烟（联网环境允许时）、manifest/checksums 重算、`.env.example` 汇总更新。
- 停止条件（用户口径）：严重方向冲突，或同一问题连续 3 次报错无法解决 → 立即停下汇报。

---

## 7. 第二阶段中途增补：权限体系调整（2026-09-30，用户指令，优先级最高）

用户明确调整权限模型，**就权限相关口径覆盖 §3/§4/架构文档 §6 与功能文档 §11 的旧表**（其余文档口径不变）：

| 等级 | 定位 | 激活方式 | 能力 |
| --- | --- | --- | --- |
| Lv.1 游客 | 默认 | 无需认证 | 聊天、网页搜索（web_search 已在 Lv1） |
| Lv.2 普通用户 | 注册用户 | 密码注册（/register，注册密码走 env，不得硬编码） | 读文件、列目录、**控制普通智能家居**（灯/空调/窗帘等非危险设备）；继承 Lv.1 |
| Lv.3 代码编写者 | 开发者 | TOTP 动态密码激活（/coder_auth 升级为 TOTP 校验） | 写文件、开发日志（/gen_log 限 Lv.3+）、编写程序；继承 Lv.1/2；**执行写代码/写文件操作时需逐次 TOTP 动态密码**（设计为 /sudo <code> 开启短 TTL 操作窗口 + 凭据参数两种通道，实现方定并测试锁定） |
| Lv.4 主人级 | 无边界 | 动态密码（TOTP）+ 生物认证模拟 双因子 | 危险智能家居（煤气/门锁）、一键装卸系统组件、全部权限无边界；"主人级"身份在 identity.json 标记 owner；含撤销途径 |

### 7.1 任务归属增补
- **S8 权限重构**（S3/S4 交卷后执行；独占 `permission.py`、`tools.py` 门禁逻辑、`auth_lv4.py`（S3 交付后可扩展）、相关测试）：
  - permission.py 重建 Lv.1–Lv.4 表：继承语义（level >= required 即通过，低权限功能无需重复验证）；Lv.3 逐次 TOTP（`verify_lv3_operation(user, totp_code)` / TTL 操作窗口 API）；Lv.4 双因子经 auth_lv4 因子链；owner 标记与 grant/revoke。
  - tools.py 门禁调整：`write_file` → Lv.3 + 逐次 TOTP；`control_ha_device` → 普通实体（home_tools.is_dangerous_entity=False）需 Lv.2、危险实体（True）需 Lv.4 + 双因子；`adb_tap/adb_swipe` 维持 Lv.3；新增 `system_manage` 工具（一键装卸系统组件，**仅 Lv.4 + 双因子 + 二次确认**，subprocess 封装可 mock，白名单 11→12）；web_search 维持 Lv.1。
  - home_tools.py（S3 交付后）如需补"普通/危险"级别映射 API 由 S8 一并补齐。
  - pytest 政策：用户允许 pytest；测试继续用 unittest 风格编写（pytest 可直接执行 unittest.TestCase），如安装 pytest 仅作运行器使用。
- **S5 main.py 接线增补**：/gen_log 限 Lv.3+（Lv.2 及以下返回升级引导文案）；/register <密码> → 校验 env `XIAOJU3_REGISTER_PASSWORD` → 升 Lv.2 并落盘（等级持久化接线口径不变）；/coder_auth <TOTP> → Lv.3；/sudo <TOTP> → 开启写操作窗口；/lv4_auth → 双因子 + 类 Root 警告 + 二次确认 + owner 标记；高危设备控制走"确认令牌"流。
- **S3 进行中工作不受影响**：其 auth_lv4.py（TOTP/因子链/Root 警告）、is_dangerous_entity、set_temperature、场景规则正是本调整的基座，交付后由 S8 消费。
- 测试要求（用户指定用例，S8 必须覆盖）：Lv.2 无法写入文件；Lv.3 能写入但需正确 TOTP；Lv.2 无法控制危险设备；Lv.4 能控制危险设备且需动态密码+生物认证模拟。全程 mock/模拟数据，不连真实设备。
### 7.2 隔离区与密钥红线重申
- 不修改隔离区数据（本项目对应 agent_state/ 运行数据与 .env；测试一律 tmp 目录）；不硬编码任何密钥/IP/密码；代码风格与现有项目一致。

## 冒烟触发规则
凡改动涉及以下任一，设计稿必须列出真机冒烟项，且冒烟环境 = 交付环境：
1. 跨启动状态（localStorage / 注册表 / 文件持久化 / 缓存）
2. 容器差异（浏览器 vs WebView2 vs 不同机器）
3. 真实外部系统（QQ / HA / Ollama / NapCat / 网络）
4. 随机或时序（随机端口 / 并发 / 轮询 / 超时）
5. 进程生命周期（spawn / 关窗 / 重启 / 孤儿进程）

配套三条纪律：
- 汇报测试结果时，行为测试与静态锚分开计数——静态锚只防回退，不算行为验证
- 汇报时主动标注「哪些离线测不了」，不许用静态锚冒充行为验证
- 冒烟环境 = 交付环境（exe 的冒烟就在桌面窗口，不拿浏览器替代）

落地依据：2026-10-03 两次真机才暴露的 bug——①桌面窗口随机端口 6697 撞 Chromium 黑名单（离线全绿测不出）②跳过标记押 localStorage 但 WebView2 是 InPrivate 即焚（浏览器验过、桌面窗口失效）。

## Windows 批处理（.bat）编写规范
本项目 bat 脚本必须遵守（教训来源：build_exe.bat 与 restart_clean.bat 两次踩坑）：
1. 文件必须 CRLF 行尾，禁 LF-only——cmd 对 LF-only 的括号块/多字节解析会碎行。写完做字节级断言。
2. 含中文（UTF-8）的 bat 禁用 goto/label——cmd 的 goto/label 扫描在多字节序列里会错位跳转。一律线性 if/else。
3. 文件头不留空行 + 加 UTF-8 BOM 配 chcp 65001——chcp 后 cmd 带字节偏移重读，头部空行导致解析错位。
4. 路径带空格（如 C:\Program Files）用 call "带引号路径" 参数，别在大括号块内直接执行。

## 一键发版脚本（2026-10-03 入库：_dev/release.bat → release.ps1，gh CLI 路线）

把「升版本号 → 重建 → 提交 → 打标签 → 推送 → 建 Release 传附件」串成一条命令。前置依赖：gh CLI（`winget install --id GitHub.cli -e` 安装）+ 一次性 `gh auth login` 浏览器授权（token 由 gh 托管，脚本零凭证）。用法：`cd _dev` 后 `.\release.bat <新版本号>`（如 `.\release.bat 1.1.0`；可选 `-Notes "说明"`）。脚本流程：前置检查（gh 已装/已认证/xiaoju3 进程/git 干净/与 origin 同步）→ 版本校验（目标必须大于当前）→ y 确认 → 升版本号（xiaoju3.py 定义 + 2 测试锚，计数校验防锚漂移）→ build_exe.bat → commit → 打标签 → 推送 → 建 Release 传双附件。守卫：每步失败即停并给人工补救话术；不 force、不 rebase、不删标签、不碰 token。编码注意：release.bat 无 BOM + CRLF（全英文包装器）；release.ps1 带 BOM（中文输出）。不替代 push.sh（内容安检与本脚本互补，发版前建议先过 push.sh）。

## 开发流水账（2026-10-03 入库：xiaoju3_data/开发流水账.md + _dev/devlog_export.py）

**换对话框前**：项目根跑 `python _dev/devlog_export.py`，当日素材块（会话/工具统计/commit 时间线）输出到 stdout，粘贴进 `xiaoju3_data/开发流水账.md` 的〔素材〕区，补一两句定稿条目再收工。流水账为清单式私有文档（整目录 gitignore），叙事故事已归档至同目录 `开发日志.md`（弃用不再续写）。素材导出纪律：拷库只读、只取本项目、只导元数据不读消息正文。
