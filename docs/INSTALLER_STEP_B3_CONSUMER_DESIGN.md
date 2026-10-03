# 安装器步 B3 消费端设计：首装引导消费 installer_report.txt

> 状态：设计稿（2026-10-03），**未动代码**。上游：xiaoju3.iss `[Code]` 段已落（eea634e），
> `DeinitializeSetup()` 每次安装会话覆写报告。本步 = 应用侧**唯一新增消费点**，只读展示。
> 总方案 `docs/INSTALLER_PLAN.md`（步 B）；首装引导层见 `docs/INSTALLER_STEP_A_DESIGN.md` / `INSTALLER_STEP_A4_DESIGN.md`。

## 0. 一句话

安装器写入的「硬件分档建议 + 三组件安装意向」报告，首装引导浮层弹出时读取并在 UI
展示（徽标 + 建议文案）——**只读展示，不写任何配置、不替用户做任何决定**；报告缺失
（便携 exe / python 直跑 / 老版本升级）时行为与现状零差异。

## 1. 报告侧事实（xiaoju3.iss:140-152，本步不改安装器）

- **位置**：`{app}\xiaoju3_data\installer_report.txt`。frozen 下 `paths.py` 数据根 =
  exe 所在目录，即与 `.env`、`.first_run_skipped` **同目录**（= `dirname(ENV_FILE)`，
  first_run.py 已有同构常量 SKIP_FLAG_FILE）；非 frozen 直跑 = 项目根 `xiaoju3_data/`。
- **内容**（5 行，CRLF）：
  ```
  2026/10/03 23:15:42            ← GetDateTimeString，安装会话时间戳
  硬件自检建议: 推荐完整版（…）     ← 仅安装期建议，真档位归 hardware_profiler
  ollama=1|0
  napcat=1|0
  ha=1|0
  ```
- **覆写语义**：`SaveStringToFile(..., Append=False)`，每次安装会话（完成、取消、升级
  覆盖）都整体覆写 → 报告恒等于"最近一次安装会话"的用户意向。`{app}\xiaoju3_data` 由
  `[Dirs]` 保证存在，装完未首启也写入成功。
- **生命周期**：只服务首装浮层；之后留在盘上作诊断痕迹，卸载默认保留
  （`[UninstallDelete]` 留空）。
- **⚠ 编码实锤坑**：Inno 6 `SaveStringToFile` 的 S 参是 **AnsiString** → 中文按系统
  ANSI 代码页落盘（中文 Windows = GBK/cp936）。Python 端 utf-8 严格读会
  UnicodeDecodeError。三布尔行纯 ASCII 恒可解析，只有文案行可能损。

## 2. 应用侧设计

### 2.1 first_run.py 新增（后端唯一改动点）

```python
INSTALLER_REPORT_FILE = os.path.join(os.path.dirname(ENV_FILE),
                                     "installer_report.txt")   # 与 SKIP_FLAG_FILE 同构

def parse_installer_report(text):   # 纯函数，可测
    """→ {"installed_at": str|None, "tier_hint": str|None,
          "intents": {"ollama": True|False|None, "napcat": …, "ha": …}}"""
```

- 行解析规则：先按两类规则归类——`硬件自检建议: ` 前缀行取 `tier_hint`；
  `^(ollama|napcat|ha)=(1|0)$` 严格取布尔（值既非 1 也非 0 → None=未知，UI 不展示）；
  归类剩余的**首个非空行**才作为 `installed_at`（理由：避免残缺报告丢时间戳行时
  把 `ollama=1` 误吞为时间戳）；其余行忽略。解析异常不外抛，逐项降级为 None。
- `read_installer_report() -> dict`：文件不存在 / OSError / 解析异常 →
  `{"available": False}`；成功 → `{"available": True, **parsed}`。**绝不抛**。
- 读文件编码回退：utf-8 → 失败退 gbk → 再失败 `errors="replace"`（§1 编码坑）。

### 2.2 dashboard 新路由（1 条）

`GET /api/first_run/installer_report` → `{"code": 200, "data": {…}}`；延迟导入
first_run（依赖面零变化锚，与既有四路由一致）。**不并入 probes**：探针是运行态、
带网络超时（最慢 5s），报告是安装期意向、读盘即时——关注点分离，各自独立失败。

### 2.3 前端（index.html + console.js，最小增量）

- `initFirstRun()` 的 `first_run=true` 分支：probes 请求旁**并行** fetch 报告接口，
  报告请求自带 `.catch(() => null)`——报告失败绝不拖垮探针展示；
  `showFirstRun(probes)` 签名不动，新增 `renderInstallerReport(data)` 独立渲染函数。
- 展示块：浮层卡片内新增 `<div id="first-run-install-hints" hidden>`（默认隐藏 =
  非安装形态零视觉变化锚），内容一律 `textContent`（与探针行同纪律，不拼 HTML）：
  - 有 True 意向 → 徽标行：「安装时勾选：本地 Ollama / QQ(NapCat) / HA 心跳」（只列 True 项）；
  - `tier_hint` 非空 → 灰字行：「安装器建议：{tier_hint}（真实档位以本机复测为准）」；
  - `installed_at` 非空 → 并入灰字行首：「安装于 …」；
  - `available=False` → 块整体保持 hidden。
- **铁律**：只读展示。不预填表单、不写 .env、不预勾自启、不因意向跳过任何探针；
  真实档位仍归 hardware_profiler 复测（单一事实源），DEVICE_TIER 不碰。

## 3. 明确不做（本步边界）

- 不把意向写进 `.env`（save_env_file 39 键白名单不动）；不改 `is_first_run` 判定；
- 报告消费不阻塞、不延慢浮层弹出（并行 fetch、独立降级）；
- 卸载「彻底删除」复选仍归 B3b 安装器侧（`CurUninstallStepChanged` + `DelTree`），
  本步不碰 iss。

## 4. 测试计划（对齐 tests/test_first_run.py 惯例）

| 层 | 用例 |
|---|---|
| parse 纯函数 | 全量 5 行报告 / 缺行 / 垃圾行混入 / 空串 / 值非 01 → None / 时间戳行不误吞 |
| read | 文件缺失 → available False；monkeypatch 常量指 tmp_path 写 **GBK 字节**（含中文文案）→ 解析成功且徽标项正确；utf-8 字节同样通过 |
| 路由 | Flask test client GET → 200 结构锚；报告缺失 → `{"available": False}` |
| 前端源码锁定（字符串扫描锚） | `fetch('/api/first_run/installer_report')` 恰一次；`id="first-run-install-hints"` 存在且默认 hidden；`renderInstallerReport(` 存在；零触碰锚沿用（轮询 / minimize / localStorage 断言不动） |

## 5. 验收（本步完成的定义）

1. python 直跑（无报告文件）：浮层 DOM 与现状一致（hints 块保持 hidden），存量 1588 全绿；
2. 造一份 GBK 报告进 `xiaoju3_data/` → 浮层出现意向徽标 + 建议灰字行；
3. 新增用例全绿。

## 6. 顺带发现的安装器侧降级缺陷（不属本步，记入 B3b 演练清单评估是否修）

| # | 现象 | 与设计稿的偏差 |
|---|---|---|
| 1 | WMI 全挂时 RamGbInt=0 → 分档落「推荐轻量版」，DiskGb 显示「约 0 GB」 | INSTALLER_STEP_B_DESIGN §4 要求降级为「无法预判，程序内将自动复测」，现实现未达 |
| 2 | 半路取消安装也写报告（意向=当时默认勾选） | 语义可接受（记录"最近一次会话"），演练确认即可 |

修法备忘（若 B3b 认领 #1）：InitializeSetup 探测失败分支置
`Tier := '无法预判（程序首次运行将自动复测）'`，DiskGb<1 同样降级文案。

## 7. 对 B3b 真机装卸演练清单的增量（本步落地后追加验证链）

装（勾 ollama+napcat）→ 首启浮层出现对应徽标与建议文案 → 跳过/完成两路均正常 →
升级覆盖安装改勾 ha → 报告被覆写为新意向（浮层仅首装弹，升级后不再弹属预期）→
卸载 → installer_report.txt 连同数据目录默认保留。
