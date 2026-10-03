# 安装器步 B3 修复设计：[Code] 段时序重构（钩子职责 + WMI 降级 + 报告时机）

> 状态：设计稿（2026-10-03），**未动 xiaoju3.iss 一行、未重编译、未重装**。按「先设计稿、后动代码」老规矩执行。
> 根因输入（已闭，见开发记忆）：B3b 真机首装三连炸——①F113 `StrToInt64(WmiFirstValue(...))` 无保护空串硬崩；②级联：InitializeSetup 失败仍调 DeinitializeSetup，F147 `WizardIsComponentSelected` 访问未创建的 WizardForm；③地雷：F129 `CreateOutputMsgPage` 写在 InitializeSetup 里。
> 本步标语：**编译通过 ≠ 真机跑得动**（B3a 的验收只做了 ISCC 编译，[Code] 从未在真机上执行过）。
> 关联文档：`INSTALLER_STEP_B_DESIGN.md` §4（降级口径）/ §6（缺陷 #1 即本次一并修掉）；`INSTALLER_STEP_B3_CONSUMER_DESIGN.md`（消费端 590e7d8，本步不改其代码）。

## 0. 一句话

把 [Code] 段从"所有事情挤在 InitializeSetup"重排为 Inno 钩子的本分工——**探测归 InitializeSetup（纯 COM、零 Wizard 依赖），建页归 InitializeWizard，收尾归 DeinitializeSetup（带 WizardWasCreated 旗守卫）**；WMI 降级收敛到单一帮助函数（哨兵 -1），报告只写"真实发生过的意向"。

## 1. 钩子职责划分（核心）

| 钩子 | 允许 | 禁止 | 本步改动 |
|---|---|---|---|
| `InitializeSetup()` | WMI 探测（纯 COM，无需窗体）、`ExpandConstant`、返回 True/False | **建页（Create*Page 族）、访问 WizardForm、任何 Wizard* API（WizardSelectComponents / WizardIsComponentSelected…）** | 保留三项 WMI 探测与分档文案计算（全部改走 WmiFirstInt，见 §2）；**移出 CreateOutputMsgPage（炸点③）**；全函数不再含任何可能抛未捕获异常的语句 |
| `InitializeWizard()` | 建页、持有 WizardForm | — | **新增本钩子**：第一行 `WizardWasCreated := True`；随后 `CreateOutputMsgPage(wpInfoBefore, ...)`（锚点与文案原样平移，视觉顺序不变）；SelfCheckPageID 存全局（沿用现状） |
| `CurPageChanged()` | Wizard* API（窗体已存在） | — | 零改动（wpWelcome 反选 ollama/ha 语义原样） |
| `DeinitializeSetup()` | 读意向写报告（**仅在旗为 True 时**） | 旗为 False 时碰任何 Wizard* API | 首行守卫：`if not WizardWasCreated then Exit;`；其余逻辑原样（时间戳 + 硬件建议 + 三意向），写盘加 ForceDirectories 前置（见 §3） |

### 1.1 WizardWasCreated 旗方案

- 声明：`var WizardWasCreated: Boolean;`（PascalScript 全局布尔零初始化 = False，无需显式初始化）。
- **唯一写点**：`InitializeWizard()` 第一行置 True。Inno 时序保证：InitializeSetup 成功返回且 Setup 进入向导阶段前必经 InitializeWizard；InitializeSetup 抛错或返回 False → InitializeWizard 永不执行 → 旗恒 False。
- **唯一读点**：`DeinitializeSetup()` 首行守卫。
- 路径矩阵：

| 会话路径 | 旗终值 | DeinitializeSetup 行为 |
|---|---|---|
| 正常装完 | True | 写报告（组件意向=完成时勾选态） |
| 向导期取消 | True | 写报告（组件意向=取消时勾选态，语义与完成一致） |
| InitializeSetup 失败/中止 | **False** | **整段跳过——不写报告、不碰 Wizard\*，第二炸点根除** |

## 2. WMI 降级策略

### 2.1 帮助函数 vs 逐点 try/except：**推荐 WmiFirstInt 帮助函数**

```pascal
function WmiFirstInt(const WmiClass, WmiProp, WmiWhere: String): Int64;
```

- 内部：调既有 WmiFirstValue（其 try/except 保留）→ `StrToInt64Def(Trim(值), -1)`；WmiFirstValue 返回空串/垃圾 → 哨兵 **-1**。
- 推荐理由：**降级收敛到单一咽喉点**。逐点 try/except 正是炸点①的产生模式——两处同型转换一处包了一处漏了；帮助函数让调用点保持声明式（`DiskGb := WmiFirstInt(...)`），未来新增探测点**不可能忘保护**。
- **取舍明示**：任务输入里"失败返回 0"的候选**不采纳**——0 会被下游当真实值渲染成"安装目标盘可用空间：约 0 GB"、并把分档推进"轻量版"，正是 §6 缺陷 #1 的两个症状；哨兵 -1 才能让 §4 的"无法预判"文案成立（见 2.3）。合法的"真 0"（盘真满了）不受影响。

### 2.2 Null 值显式处理

WMI 属性为 Null（如无介质光驱的 FreeSpace）时，PascalScript 隐式赋给 String 要么得空串、要么抛 variant 异常被 WmiFirstValue 内层 except 吃掉——**两种路径现状都收敛到 `''`，行为已安全，但属隐式**。本步显式化：该赋值语句**保留在内层 try/except 内**（现状），并在注释标注"Null → '' 由此兜底"；数值化的空串/垃圾拦截统一由 WmiFirstInt 的 StrToInt64Def 承担。即：**Null 不再做专门分支**，靠"内层兜空串 + 外层哨兵"两级显式契约覆盖。

### 2.3 降级文案（对齐 INSTALLER_STEP_B_DESIGN §4，本次一并修掉 §6 缺陷 #1）

- 哨兵 -1 的指标渲染为「**无法预判**」，**不再产出"约 0 GB"、不再落"推荐轻量版"**。
- 分档规则改写：任一关键指标为 -1 → `Tier := '无法预判（程序首次运行将自动复测）'`；三项齐全才走 16G+独显+20G / <8G / 中档三分支。
- 自检页 Body 逐行：哨兵行渲染「内存：无法预判」「显卡：无法预判」「安装目标盘可用空间：无法预判」，页脚保留"程序首次运行会自动复测真实档位"。
- 该文案经 `TierHintText` 原样流入 installer_report.txt 的「硬件自检建议: 」行（消费端照常展示，见 §4）。

### 2.4 精度增强（随本步一并做）

`Win32_LogicalDisk` 查询加 WHERE：`DriveType=3 AND DeviceID='<安装盘>'`（安装盘 = `ExtractFileDrive(ExpandConstant('{localappdata}'))`）。理由：现状 `ItemIndex(0)` 抓的是无序结果集首行，多盘机器可能取错盘；DriveType=3（固定盘）同时消灭"无介质光驱 FreeSpace=Null"这一整类输入。WmiFirstValue 增加第三参 WmiWhere 拼进 WQL（`''` = 无过滤，内存/GPU 两处传空）。

## 3. 报告写入时机

- **唯一口径：旗为 True 才写（向导真实发生过=意向真实发生过）；旗为 False 整段跳过（含时间戳行也不写，即不留半份报告）。**
  理由：报告语义="最近一次安装会话的用户意向"（消费端设计 §1）；向导没跑过就没有意向，补一份默认勾选态的报告是**伪造意向**——消费端会把假徽标亮给用户。缺文件路径本来就是消费端一等公民（`{"available": false}` → hints 块保持隐藏）。
- 成功 vs 取消的一致性：两条路径旗均为 True，报告**同一格式同一时机**（DeinitializeSetup 终局一次性写），差异只在勾选态快照取自各自终局——即"半路取消也记录当时意向"的既有语义（消费端设计 §6②）保持不变。
- 写盘健壮化：写前置 `ForceDirectories(ExpandConstant('{app}' + chr(92) + 'xiaoju3_data'))`（取消于安装阶段前的会话，[Dirs] 可能尚未落地）；`SaveStringToFile` 返回值继续忽略（失败=无报告文件，消费端自然降级，不弹错）。
- 已知痕迹取舍：取消会话会留下 `{app}\xiaoju3_data\installer_report.txt`（目录原本可能不存在）——接受：与"数据不装不删"哲学同向，且取消装=程序未装=消费端永不会读它。

## 4. 对 B3b 演练链 / 消费端（590e7d8）的影响

- **消费端零改动**：格式五行的行法不变（时间戳 / `硬件自检建议: ` 前缀行半角冒号+空格 / 三布尔 ASCII 行）、路径 `{app}\xiaoju3_data\installer_report.txt` 不变、覆写语义（Append=False）不变 → `parse_installer_report` 的前缀锚与布尔严格匹配全部兼容。
- 新增的"无报告"路径（向导未建=旗 False 不写）**本就被消费端一等公民覆盖**：文件缺失 → `{"available": false}` → 浮层 hints 块保持 hidden。
- 一处已知视觉冗余（接受，不改消费端）：降级文案「无法预判（程序首次运行将自动复测）」+ 前端固定追加的「（真实档位以本机复测为准）」在灰字行会连续出现两次"复测"字样，仅出现在 WMI 失败的罕见态。
- B3b 演练链影响：正向——首装不再崩，自检页/组件页/报告写入/浮层消费才第一次能被端到端走到；演练清单新增一态：**"模拟 InitializeSetup 失败（如临时禁 WMI 服务）→ 应零错误退出、零报告文件、无第二弹窗"**。

## 5. 编码坑回引

写路径不变：仍 `SaveStringToFile`，仍是 AnsiString→系统 ANSI 代码页（中文 Windows=GBK）落盘，仍是覆写；消费端 utf-8→gbk 回退读法（590e7d8）继续有效。本步唯一新增写盘行为是 ForceDirectories，不改变编码事实。

## 6. 新增可静态锚（tests/test_installer_script.py，新文件）

对 xiaoju3.iss 文本做字符串扫描锚（与 test_first_run 前端锚同风格；**静态锚只防回退，真机行为归 B3b 重演**，按 BUILD_BRIEF 纪律分开计数）：

1. **炸点①反向锚**：[Code] 段内 `StrToInt64(` 的出现必须且仅在 WmiFirstInt 函数体内（即禁止任何裸 `StrToInt64(WmiFirstValue` 模式）；三处探测调用点全部走 `WmiFirstInt(`。
2. **炸点③反向锚**：`InitializeSetup()` 函数体内不得出现 `CreateOutputMsgPage` / `CreateCustomPage` / `CreateInputPage` / `WizardForm` / `WizardSelectComponents` / `WizardIsComponentSelected` 任一 token。
3. **旗锚**：`WizardWasCreated: Boolean` 全局声明存在；`InitializeWizard` 内含 `WizardWasCreated := True`；`DeinitializeSetup` 内含 `if not WizardWasCreated then Exit`。
4. **钩子存在锚**：`procedure InitializeWizard();` 存在（缺失即回归）。
5. **降级文案锚**：`无法预判` 出现于分档与 Body 渲染区；`推荐轻量版` 字样**不得**再由 -1 哨兵路径触达（文本上将其从哨兵分支移除）。
6. **WHERE 锚**：`DriveType=3` 出现于磁盘 WQL。
7. **编码防回归锚**：文件字节级仍为 UTF-8 带 BOM（复用 Inno 中文 [Code] 官方要求锚）。

## 7. 实施与验收

- 实施顺序：iss 单文件手术（行级 splice，遵循 [[inno-pascalscript-pitfalls]] 十条——注释禁段名样方括号文本、UTF-8 带 BOM、PS 无 IEnumVariant 等）；随后 `tests/test_installer_script.py` 锚全绿 + 全仓 1605 不减。
- **验收只认真机口径**：重建 setup 后 B3b 重演——①双击不再弹任何 Runtime error ②自检页三行正常/或全"无法预判" ③组件页反选语义在 ④装完浮层消费报告徽标链 ⑤模拟 WMI 禁用 → 零弹窗+零报告 ⑥取消会话 → 报告=取消时意向。编译只是前置门槛，不进验收清单。
- 风险：`StrToInt64Def` 为 Inno 6 文档化支持函数（低风险，实施时以 ISCC 实际编译为前置门槛，但**不作为验收**）；wpInfoBefore 锚点平移后页面顺序视觉不变（低风险，真机核对）。
