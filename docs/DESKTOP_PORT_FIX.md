# 端口修复设计：desktop 窗口复用 5003，砍掉随机内置服务（路线 1）

> 状态：设计稿（2026-10-03），**未动代码**。根因：desktop 进程为窗口另起的随机端口内置服务（`make_server(host, 0)`）抽中 Chromium ERR_UNSAFE_PORT 黑名单端口（6697），WebView2 导航直接被浏览器内核拒绝。
> 方案：desktop 不再自起内置服务——拉起 launcher 后**轮询探测 5003 就绪**，就绪后 `create_window` 直接指向 `http://127.0.0.1:5003/console`。与"5003 一个进程承载一切"架构口径对齐，顺带拆除 desktop 内置服务与主服务双轨并存的历史包袱。

---

## 1. 就绪探测实现

- **复用 `_is_port_listening(5003)`**（纯 socket connect，无 HTTP 副作用，desktop_launcher.py 既有）。
- 新增纯函数（可离线单测，注入 check_fn/sleep）：

```python
def wait_for_dashboard_ready(timeout_s=15.0, interval_s=0.5, check_fn=None, sleep_fn=None):
    """轮询 :5003 就绪；返回 True/False。默认 0.5s 间隔、15s 上限
    （launcher→dashboard 实测约 3-5s，上限留 3 倍余量）。"""
```

- **超时后的行为**：不弹错误页、不重试死循环——`_print` 提示「主程序未就绪（15 秒超时）」后仍创建窗口，URL 同样指向 `:5003/console`（WebView2 会显示自己的连接失败页，用户点刷新/稍后服务起来即恢复）；同时窗口标题追加既有 `MAIN_NOT_RUNNING_HINT` 口径提示。理由：dashboard 起不来的场景（缺 .env 崩溃等）窗口仍是唯一 UI 出口，不能没有窗。
- 参数依据：launcher 实测 ~3-5 秒起 dashboard；15s 上限覆盖慢机；`check_fn`/`sleep_fn` 注入使测试零真实等待。

## 2. 窗口就绪前的占位：推荐「先出窗、后导航」

两案对比：

| | 阻塞等就绪再 create_window | 先出窗口占位页，就绪后导航 |
|---|---|---|
| 体验 | 双击后 3-5s 白等无反馈（慢机 15s），像"点不开" | 窗口 ~1s 即现（"正在启动主程序…"占位），起好后自动跳控制台 |
| 实现 | 串行 wait → create_window(真 URL) | create_window(`data:` 或内置占位 URL) → 后台线程 wait → `window.load_url(...)` |
| 风险 | 慢机上被用户连点/误判坏 | 需处理 wait 失败时的占位态文案（已在 §1 设计） |

**推荐后者（先出窗）**：占位页即"启动中"视觉反馈；实现用 `webview.create_window(html=占位HTML)` 起步 + 探测线程就绪后 `window.load_url("http://127.0.0.1:5003/console")`（pywebview 5+/6.x 支持 load_url 重导航）。超时分支复用同一窗口：load_url 到 :5003 让 WebView2 显示错误页 + 标题追加提示（§1）。既有 `MAIN_NOT_RUNNING_HINT`/`_on_loaded` 标题逻辑保留，判定改为探测结果。

## 3. 5003 被外部占用的口径（双击防重不破坏）

现有链**原样保留**：`ensure_backend_services()`（:5003 已监听 → 复用，`launcher_proc=None`）在前，探测在后——外部占用（别的进程恰好监听 5003，极小概率）时 `_is_port_listening` 照样"就绪"，窗口直接挂上去，行为与"复用现有进程"完全一致（ dashboard 探测对 8123 之外的占用者无感知，属可接受边界：端口即契约）。
变化点仅一处：`launcher_proc is None` 的"复用模式"下**跳过等待轮询直接就绪**（服务已在，无需等）——`wait_for_dashboard_ready` 的首轮即命中，代码自然覆盖，无需特判。
"双击防重"不受影响：第二实例的 `ensure_backend_services` 走复用分支，两窗口同挂 5003，互不干扰。

## 4. 对 spawn-self 的影响：**四进程链零变化**

砍掉的是 desktop 进程**内部线程**（内置服务），不动任何进程：spawn-self 链仍为 bootloader → desktop 角色（无标志）→ `--xj3-role=launcher` → `--xj3-role=dashboard`(:5003)。`start_backend_launcher`/`stop_backend_launcher`/`route_argv`/`freeze_support` 全部不碰。已验证的四进程冒烟结论继续有效；唯一行为差 = desktop 窗口内容源从"随机端口"变"5003"。

## 5. 对现有测试的影响（tests/test_desktop_launcher.py）

grep 实测内置服务相关 **8 条用例 + 2 个函数自测**需要处理：

| 用例/位置 | 处理 |
|---|---|
| `test_window_title_size_and_loopback_console_url`（:305） | 改写：URL 断言改 `http://127.0.0.1:5003/console`（锁定新主线） |
| `test_serve_port_forwarded_to_server`（:320） | 删除（`--serve-port` 随内置服务退役；argparse 参数一并删，改写为"serve-port 参数已退役"反向锚或直接移除） |
| `test_spawned_launcher_killed_on_window_close`（:325） | 改写：mock `wait_for_dashboard_ready`，断言关窗仍整树终止 |
| `test_reuse_mode_cleanup_still_invoked_but_noop`（:332） | 改写：复用模式下 stop_local_server 不再调用 → 断言改为 stop_backend_launcher 仍 noop |
| `test_cleanup_runs_even_if_start_raises`（:339） | 改写：起服务段不存在 → 改为 wait 探测异常不崩、窗口仍开 |
| `test_server_failure_cleans_spawned_launcher`（:362） | 改写：探测超时 False → 窗口仍创建 + 提示 + 关窗回收（新行为锁定） |
| `test_missing_webview_no_window_no_server`（:85） | 改名/改断言：无 webview → 无窗口无探测 |
| `test_start_random_port_binds_loopback`（:68，函数自测） | 删除（start_local_server 退役） |
| `stop_local_server` 函数自测相关 | 随函数一起删 |

**预估**：改写 ~5 条、删除 ~4 条、新增 ~4 条（wait_for_dashboard_ready 三态：就绪/超时/复用即就绪 + load_url 调用锚）→ 总数 **1596 → ~1596±2，只增不减目标以"净 +0~+4"口径交付**。

## 6. 砍掉内置服务的依赖清查（grep 实测）

- **生产调用点唯一**：`desktop_launcher.py:386`（main 内）——删除后 `start_local_server`/`stop_local_server` 成死代码，**连同 `--serve-port` argparse 参数一起退役**（对外契约变化：`python desktop_launcher.py --serve-port 5900` 形态退役；该参数从未被 bat/自启/exe 使用，仅 M4 期手工调试用，文档 §2.1 已标注"保留"改为"退役"）。
- `from xiaoju3_dashboard import app`（:71）**仍需保留**——first_run 探针、`main` 业务引用（`main.get_creator_name` 等）在 dashboard 进程内使用；desktop 进程 import app 的副作用（装配路由）不因砍服务而失去意义（app 对象本身是 dashboard 模块单例，import 链不产生端口）。此 import 保留不动。
- 测试之外的引用：无（grep 全仓仅上表所列）。
- 附带收益：desktop 进程少一个常驻线程与一个监听端口；`stop_local_server` 调用点（:419 finally）随之删除，关窗清理只剩整树终止，链路更短。

## 7. 分步实施（每步收尾全仓全绿、可独立提交）

| 步 | 内容 | 交付 |
|---|---|---|
| P1 | `wait_for_dashboard_ready` 纯函数 + 三态单测（就绪/超时/首轮即就绪；check_fn/sleep_fn 注入零真实等待） | desktop_launcher.py + tests +3 |
| P2 | main() 主线切换：删内置服务段（start/stop/URL 拼接/--serve-port）→ 占位 create_window + 探测线程 load_url(:5003/console) + 超时标题提示；同步改写/删除 §5 表列 8 条测试 + 新增锚 | desktop_launcher.py + tests 改写 |
| P3 | 真机验收：双击 exe → 占位窗 → 自动进控制台；关窗重开；5003 被占（先手起 python dashboard）双击 → 复用直连；故意断 launcher（改名）→ 超时提示路径；回归冒烟①②⑥ | 冒烟记录入 EXE_PACKAGING_PLAN |

依赖：P1 → P2 → P3。P2 是主体改动，回退单提交即可。
