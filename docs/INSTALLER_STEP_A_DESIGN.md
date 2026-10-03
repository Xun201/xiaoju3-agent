# 安装器步 A 设计细则：版本统一 + 首装引导层

> 状态：设计稿（2026-10-03），**未动代码**。总方案见 `docs/INSTALLER_PLAN.md` §9 步 A。
> 原则沿用 exe 步骤纪律：每子步收尾全仓测试全绿、可独立提交、非 first_run 场景行为逐字节不变。

---

## 1. 版本统一：`XIAOJU3_VERSION = "1.0.0"`

- **源头**：`xiaoju3.py` 配置区（紧跟 `MAX_MESSAGES` 风格，模块级常量，import 零副作用口径不变）：`XIAOJU3_VERSION = "1.0.0"`。
- **下发**：`/api/status` 的 `data` 增加键 `"version": XIAOJU3_VERSION`（`xiaoju3_dashboard.py` `api_status` 处理器，与 `creator` 字段同列下发——既有字段零改动，纯增量键）。`xiaoju3_dashboard.py` 顶部 `from xiaoju3 import (...)` 增补该名。
- **前端显示**：`console.js` 既有 `/api/status` 2 秒轮询（:270）取 `data.version` → 写入 `index.html:498` `<span class="header-title">` 尾部小字徽标（`小橘3号 · 控制台 v1.0.0`，CSS 弱化色，不动标题主文案——b9c4736"标题栏素颜"口径保留，徽标为新增子元素非改写）。
- **下游引用**：`build_exe.bat` 构建时以正则从 `xiaoju3.py` 抓取注入 `version_info.txt`（PyInstaller 版本资源）与 Inno `AppVersion`（步 B 接线，本步只落常量与下发）。

## 2. `.env` 写入逻辑（步 A 的安全核心）

### 2.1 位置与签名

放 `xiaoju3.py`——与只读 `_load_env_file`（:26）**同文件对称**（配置之源职责归一，其他模块无需新依赖）：

```python
ENV_WRITE_ALLOWLIST = frozenset({...})   # 见 2.2

def save_env_file(updates, path=None, backup=True):
    """写 .env（首装引导/设置变更专用）。

    - updates: dict[str, str]，仅接受白名单键（越界键静默丢弃并返回警告）；
    - path 缺省 ENV_FILE；文件不存在则创建（含 xiaoju3_data 目录 makedirs）；
    - backup=True 时先把现存文件轮换为 .env.bak（单槽：旧 bak 被覆盖）；
    - 原子落盘：写 <path>.tmp 后 os.replace（Windows 原子）；
    - 保留文件中不在 updates 里的既有键（增量合并，非全量重写）；
    - 返回 (written_keys, skipped_keys, backup_path_or_None)。
    """
```

与 `_load_env_file` 的对称性：读取端"env 优先、文件兜底"；写入端"只动文件、不碰 os.environ"（写完由下次启动或显式 `os.environ[key]=value` 生效，引导层自行决定是否热生效——默认不热改进程环境，提示重启生效，避免双源不一致）。

### 2.2 键白名单（防任意覆盖，安全边界）

`ENV_WRITE_ALLOWLIST` = 配置契约全集（与 `.env.example` 键名同步维护）：

```
DEEPSEEK_API_KEY, LOCAL_URL, LOCAL_MODEL, CLOUD_URL, CLOUD_MODEL,
CLOUD_BALANCE_URL, VISION_MODEL, VISION_KEY, VISION_API_URL,
ONEBOT_API_URL, ONEBOT_TOKEN, NAPCAT_API_URL, NAPCAT_TOKEN, NAPCAT_DIR,
HA_URL, HA_TOKEN, WEB_API_KEY, XIAOJU3_TOTP_SECRET, XIAOJU3_REGISTER_PASSWORD,
DANGER_ENTITIES, CHILD_LOCK_ENABLED, XIAOJU3_PERSONALITY, TTS_VOICE,
USER_CITY, USER_DISTRICT, XIAOJU3_HUMIDITY_THRESHOLD, DEVICE_TIER,
WORKSPACE, MAX_MESSAGES, AGENT_STATE_DIR, XIAOJU3_PEERS, XIAOJU3_WATCH, PEER_DEVICE_URL
```

规则：白名单常量与 `.env.example` 键集做**一致性测试**（两边 diff 必须为空，防漂移）；黑名单键（如 `PATH`、`PYTHON*`、任意新键）一律拒绝。**引导页 UI 只暴露其子集**（见 §3），白名单全集服务后续"设置页"复用。

### 2.3 覆盖前备份

- 位置：同目录 `xiaoju3_data/.env.bak`（单槽轮换：写前 `shutil.copy2(ENV_FILE, ENV_FILE+'.bak')`）。
- 单槽而非时间戳族的理由：`.env` 本身 gitignore，备份只为"写坏一步回退"；时间戳族会积累密钥副本，单槽最不敏感面最小。
- 首次创建（无旧文件）不产生备份。

### 2.4 并发安全

- **写者收敛为单点**：spawn-self 三进程中**只有 desktop 角色的引导/设置 UI 调用写入**；launcher/dashboard 终生不写 `.env`（职责写进函数 docstring 与模块头注）。
- **原子性**：`<path>.tmp` 写完 `os.replace`（Windows 原子替换），即使进程中途死也不留半截文件。
- **跨进程竞态残余**：desktop 角色若被双开（:5003 已监听时复用逻辑本就阻止第二实例拉服务，但窗口进程本身可双开）→ 两窗口同时提交引导的理论窗口存在；防护：写前 `os.replace` 幂等（后写者胜、内容合并基于同读快照），并在 docstring 标注"最后写入者胜"语义——引导场景一次一户一人，可接受，不加文件锁（避免引入 lock 文件清理负担）。
- **幂等**：同键同值重复提交 → 重写无害（内容不变），返回同样成功。

## 3. 首装引导 UI 与探针

### 3.1 触发与页面形态

- **判定**：`ENV_FILE` 不存在 → first_run。API `/api/first_run/status`（GET）返回 `{"first_run": true, "version": ...}`；`console.js` 启动时调一次，`first_run=true` 则在控制台壳内渲染**引导覆盖层**（全屏遮罩 + 分步卡片，复用既有 header，不新开窗口/进程）。
- 完成或跳过后 `localStorage(xiaoju3_first_run_done)` 记位 + 后端以"`ENV_FILE` 已存在"为准（单一事实源在文件，不在 localStorage）。

### 3.2 探针（`/api/first_run/probes`，GET，后端并行执行，10s 上限）

| 探针 | 复用点 | 通 | 不通提示 |
|---|---|---|---|
| Ollama | `brain` 既有 1s probe（`LOCAL_PROBE_URL`） | 🟢 完整版本地优先可用 | 🟡 给 Ollama 安装指引链接，可跳过 |
| NapCat/QQ | `xiaoju3_launcher.ensure_napcat` 的检测段（进程名扫描→6099 端口回退；只测不拉） | 🟢 QQ 链路就绪 | 🟡 提示可后装，`setup_napcat.bat` 指引 |
| Home Assistant | `HA_URL`+`HA_TOKEN` 齐才测 `/api/`（复用 ha_check 同口径） | 🟢 心跳可用 | ⚪ 可选项，未填直接灰显跳过 |
| DeepSeek | `DEEPSEEK_API_KEY` 非空即 🟢 | 🟢 云端就绪 | 🔴 高亮引导（见 3.3） |

### 3.3 DeepSeek key 引导与校验

- 文案：注册/充值官方链接 + "密钥只存本机 `xiaoju3_data\.env`，绝不上传"。
- **本地格式校验**：非空、`sk-` 前缀、长度 ≥ 30（DeepSeek key 形态；不通过标红不发）。
- **可选"测试连接"按钮**：后端调 `CLOUD_URL/models` 一次（带用户输入的 key，5s 超时）——可选不强测；失败给"仍可保存，稍后在 .env 修正"出口。
- 提交：`POST /api/first_run/complete`（JSON `{env: {...用户填的键值子集}}`）→ 后端过白名单 → `save_env_file` → 返回写入结果。**表单只暴露**：`DEEPSEEK_API_KEY`、`HA_URL`、`HA_TOKEN`、`LOCAL_URL`（默认值预填）、`USER_CITY`（可选）——其余键走 `.env.example` 手工路径。

### 3.4 写入后生效机制（定稿：方案 A 极简形态）

**问题**：引导写盘时 launcher/dashboard 已在运行、配置常量在 import 时固化——不重载则用户填完 key 一测"不生效"。

**二选一结论：选 A（重启整树），否决 B（热加载）。** 理由：热加载必须把 `xiaoju3.py` 模块级常量（`CLOUD_KEY` 等全部 import 时绑定）改为函数式访问——大面积动核心、触碰双脑/工具/心跳全部读取点，与"步 A 零风险纯增量"定位冲突；而首装场景"关窗重开"本就是用户自然动作，几秒中断无感。

**实现（零新 API、零进程管理代码）**：

1. 引导完成页文案："全部就绪！**关闭小橘3号窗口，重新打开即生效**（新进程将读取你刚填的配置）"。
2. 完成页按钮「完成并重启小橘3号」：前端调 `window.close()`——pywebview 窗口关闭即触发既有整树终止链（stop_backend_launcher，冒烟六项第⑥项已验证无孤儿）。
3. 用户重新双击 exe → 全新进程启动 → `_load_env_file` 读到新 `.env` → 配置生效。必定生效（进程级隔离），无部分生效态。
4. **边界注明**：浏览器直开 `:5003/console` 的 python 开发形态下 `window.close()` 关不掉服务——该形态使用者是开发者（懂手动 `restart_clean.bat`），引导页文案在检测到非 first_run 场景时本就不出现，可接受。

## 4. 新增测试清单（`tests/test_first_run.py` + 既有文件增补）

| # | 用例 | 归属 |
|---|---|---|
| 1 | `save_env_file` 白名单：越界键静默丢弃、返回 skipped | A2 |
| 2 | `save_env_file` 备份：旧文件 → `.env.bak` 内容等于旧内容；首建无备份 | A2 |
| 3 | `save_env_file` 幂等：同值重复写内容不变 | A2 |
| 4 | `save_env_file` 增量合并：未提及键保留原值 | A2 |
| 5 | `save_env_file` 原子性：模拟 tmp 写失败不影响旧文件（patch os.replace 抛错） | A2 |
| 6 | 白名单与 `.env.example` 键集一致（防漂移锚） | A2 |
| 7 | `/api/status` 含 `version` 键且等于 `XIAOJU3_VERSION` | A1 |
| 8 | `/api/first_run/probes`：三探针全 mock（通/不通矩阵） | A3 |
| 9 | `/api/first_run/complete`：白名单过滤 + 落盘断言（tmp 隔离区） | A4 |
| 10 | first_run 判定：`.env` 存在/不存在两态 | A4 |
| 11 | 自启键读写：mock winreg，写/删/幂等删除 | A4 |
| 12 | 非引导场景零变化锚：`ENV_FILE` 存在时 `/console` 页面与 `/api/status` 输出与现状逐字节一致 | A4 |

## 5. 子步拆分（每子步独立提交，1563 起全绿只增不减）

| 子步 | 内容 | 新增/改动文件 | 预估用例 |
|---|---|---|---|
| **A1** | 版本常量 + `/api/status` 下发 + 前端徽标 | xiaoju3.py、xiaoju3_dashboard.py、console.js、index.html + 测试#7 | +2 |
| **A2** | `save_env_file` 写入函数 + 白名单 + 备份/原子/幂等 | xiaoju3.py（对称位）+ 测试#1-6 | +6 |
| **A3** | 探针模块（复用 brain/NapCat/HA 检测）+ `/api/first_run/probes` | 新 `first_run.py`（探针编排）+ xiaoju3_dashboard 路由 + 测试#8 | +3 |
| **A4** | 引导覆盖层（console.js/index.html）+ `/api/first_run/complete` + 自启键读写 + 完成页 | console.js、index.html、xiaoju3_dashboard.py、新自启工具 + 测试#9-12 | +6 |

顺序 A1 → A2 → A3 → A4（A2 是 A4 的依赖；A1 独立可先行）。预估 A 整体 1.5–2 天。

## 6. 最高风险子步判断：**A2（写 .env）**

理由：A4 的引导 UI 交互面大但失败模式可见（页面报错即知）；A2 是**安全与持久化的根基**——白名单漏一个键就是任意配置覆盖面、备份丢了就救不回用户密钥、原子性破了会留下毒化后续所有启动的半截 `.env`。且它的失败不发生在写入瞬间（写错 → 下次启动才炸），离当前会话最远、最难察觉。缓解已内置设计：白名单一致性测试锚、单槽备份、os.replace 原子落盘、增量合并非全量重写——实施时这四条一条都不能省。
