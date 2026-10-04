# 安装器步 B5 设计稿：三项遗留收尾（组件页勾选 UI + 彻底删除复选 + 卸载完成页提示）

- 状态：**设计稿，待评审**（本轮只侦察 + 设计，未改代码、未重编译、未提交）
- 日期：2026-10-03 深夜
- 输入：§11 遗留表（docs/INSTALLER_PLAN.md:146-153，遗留①②③；遗留④ dashboard 加固不在本批）
- 查证基线：本机 Inno Setup 6.7.3（`%LOCALAPPDATA%\Programs\Inno Setup 6`）自带 ISetup.chm 与官方示例——**版本精确，全部引文出自本地解包原文**，非网页二手资料
- 落点理由：docs/ 惯例是每步一份设计稿（A/A4/B/B3/B3-code-fix/B3-consumer），B5 横跨安装页与卸载链路，独立成稿便于 §11 三行分别回链；INSTALLER_PLAN.md 保持"计划 + 验收记录"定位不动

---

## §0 结论速览

| 项 | 根因 | 主推方案 | 备选 |
|---|---|---|---|
| A 组件页 UI | 类型名叫 `custom` 但没挂 `Flags: iscustom`，Inno 判定"无自定义类型"→ 锁死手动勾改 | [Types] 定义 lite/full/custom(iscustom) 三类型，与自检页分档叙事对齐 | 现有单类型补 `Flags: iscustom`（1 行） |
| B 彻底删除 | 无卸载钩子（本来就未实现） | `InitializeUninstall` MsgBox 问询（`MB_DEFBUTTON2` 默认否）→ 全局旗标 → `usUninstall` DelTree 白名单两目录 | UninstallProgressForm 上建真复选框（需实测，见 §2.6） |
| C 完成页提示 | Inno 卸载器无完成页可自定义（非漏做） | `usPostUninstall` MsgBox，**按 DirExists 实况**二选一文案 | 进度窗 StatusLabel 常驻提示（增强候选，非本轮） |

三案共用一个全局旗标 `PurgeUserData`；C 的完成页文案不读旗标而读目录实况，杜绝"报已删实际没删"。

---

## §1 A 项：组件页勾选 UI bug

### 1.1 现状与根因

xiaoju3.iss:52-58（原文）：

```
[Types]
Name: "custom"; Description: "自定义选择（三项均可跳过，后续在程序内配置）"

[Components]
Name: "ollama"; Description: "计划使用本地 Ollama（推荐完整版路线，需自行安装 Ollama 与模型）"; Types: custom
Name: "napcat"; Description: "计划接入 QQ（NapCat / LLOneBot，仓库内 setup_napcat.bat 可一键装配）"; Types: custom
Name: "ha"; Description: "计划接入 Home Assistant 主动服务心跳（需另配 HA_URL/HA_TOKEN）"; Types: custom
```

根因（6.7.3 CHM topic_typessection.htm 原文，逐字）：

> **iscustom**：Instructs Setup that the type is a custom type. Whenever the end user manually changes the components selection during installation, Setup will set the setup type to the custom type. **Note that if you don't define a custom type, Setup will only allow the user to choose a setup type and they can no longer manually select/unselect components.** Only one type may include this flag.

即：**iscustom 是 flag 语义，与类型叫什么名字无关**。我们的类型顶着 `custom` 之名却没挂 flag，Inno 认为整个安装只有"选择类型"这一条路（且只有一个可选项），用户自然"无法逐项选择/改不了勾选态"。与 §11 遗留③"升级演练中用户未能改动勾选态"及本轮用户描述完全吻合。

官方示例佐证（Examples/Components.iss:18）：`Name: "custom"; Description: "Custom installation"; Flags: iscustom`——官方的 custom 类型必挂 flag。

### 1.2 对"去掉 types 绑定 → 复选框恒显"假设的查证结论

**不成立**。CHM topic_typessection.htm 原文：

> During compilation a set of default setup types is created **if you define components in a [Components] section but don't define types**. If you are using the default (English) messages file, these types are the same as the types in the example below.

即删掉 [Types] 段并不会得到"无下拉的纯复选框页"，而是 Inno 自动造出 full/compact/custom(iscustom) 三条默认类型（英文界面语义是"全部/精简/自定义"，与我们三个可选集成的语义错位）。且"组件不绑 types 时在默认类型下是勾是空、是否隐藏"无原文背书（需实测）。**结论：类型系统删不得，正确修法是把类型定义成我们自己的语义。**

### 1.3 方案（主推）：三类型 lite/full/custom(iscustom)

```iss
[Types]
Name: "lite"; Description: "轻量版（默认仅 QQ 接入，云端优先）"
Name: "full"; Description: "完整版（QQ 接入 + 本地 Ollama + HA 心跳）"
Name: "custom"; Description: "自定义（三项均可跳过，逐项勾选；后续也可在程序内配置）"; Flags: iscustom

[Components]
Name: "ollama"; Description: "计划使用本地 Ollama（推荐完整版路线，需自行安装 Ollama 与模型）"; Types: full custom
Name: "napcat"; Description: "计划接入 QQ（NapCat / LLOneBot，仓库内 setup_napcat.bat 可一键装配）"; Types: lite full custom
Name: "ha"; Description: "计划接入 Home Assistant 主动服务心跳（需另配 HA_URL/HA_TOKEN）"; Types: full custom
```

理由：
1. iscustom 就位 → 根因消除，用户可自由勾改（官方原文背书的手动选择解锁条件）；
2. 下拉从"只有一个条目"变成三条有意义的选项，**轻量版/完整版正好与硬件自检页的分档建议（`推荐轻量版`/`推荐完整版`，iss:184-190）形成同一套叙事**，自检页推荐什么、组件页就能一键选什么；
3. 原下拉里的安抚文案（"三项均可跳过，后续在程序内配置"）收编进 custom 类型描述，零丢失；
4. 改动面仅 [Types]/[Components] 两段 8 行，[Code] 零触碰。

配套行为（保留现状，不新增机制）：
- `CurPageChanged(wpWelcome)` 的 `WizardSelectComponents('napcat')`（iss:220-224）**保留**：首装默认 napcat 唯勾（B3b 已真机验证）；lite 类型恰好也是"仅 napcat"，双保险一致。
- 升级场景：B3b 实测注册表 `Selected Components` 恢复覆盖 hook（三意向 1/1/1），机制与类型无关，预期不变（真机验收 §5 复测）。
- `DeinitializeSetup` 三意向记录（iss:226-249）零触碰——`WizardIsComponentSelected` 读组件勾选态，不依赖类型；五行红线测试锚不动。

### 1.4 边界（不做什么）

- 不引入 `Check:` 函数、不做组件运行时动态隐藏/禁用；
- 不动 [Files]/[Tasks]/[Icons]/[Registry]/[Run]/[Dirs]；
- 不改 [Messages]（SelectComponentsDesc 等 isl 文案保持原生）；
- 不做自检分档 → 类型自动预选的联动（读 TierHintText 预选 lite/full 是个增强候选，评审若要再加，本轮不做）。

### 1.5 测试锚（新增，落 tests/test_installer_script.py 同文件新测试类）

1. `types_iscustom_exactly_once`：[Types] 段剥注释后恰含 1 处 `Flags: iscustom`（官方"Only one type may include this flag"，多写即编译错，锚防回归）；
2. `components_all_bound_custom`：ollama/napcat/ha 三行剥注释后 Types 绑定均含 `custom`（保证自定义态三项齐全可勾）；
3. 反向锚：[Types] 段不存在无 iscustom 的单类型形态——落法：段内 `Name:` 条目数 ≥ 2 且恰 1 处 iscustom（锁死"回到单类型忘 flag"的回归路）；
4. 现有锚全部不动：锚 2（InitializeSetup 禁 Wizard*）、锚 7（BOM+CRLF）、五行红线锚（DeinitializeSetup）天然兼容（A 项不碰 [Code]）。

### 1.6 真机验收

- 首装：组件页见三条类型；进入页时默认 napcat 唯勾；选"自定义"后三项可自由勾改；手改勾选后下拉跳到"自定义"（iscustom 原文行为）；
- 升级：上轮勾选恢复（B3b 口径）且**本次可改**；改完继续，installer_report 三意向行与最终勾选一致；
- 回归：卸载重装后 first_run 浮层徽标/灰字消费链路不受影响（Deinit 未动）。

需实测（不影响方案成立，纯外观）：多类型下不属于所选类型的组件行是"隐藏"还是"置灰/未勾显示"（CHM 无原文，两态皆可接受）；hook 程序化勾选是否把下拉显示切到"自定义"。

---

## §2 B 项：彻底删除复选（卸载时可选删除用户数据）

### 2.1 现状

- [UninstallDelete] 故意留空（iss:60-63）= 卸载默认保数据；B3b 卸载场景实测数据 11 项字节 + mtime 原样——**默认保数据语义是红线，本轮只加"可选删除"，绝不动默认路径**；
- [Code] 段现有四个钩子（InitializeSetup / InitializeWizard / CurPageChanged / DeinitializeSetup），**无任何卸载侧钩子**。

### 2.2 删除范围（白名单，查证完毕）

| 目录 | 内容 | 证据 |
|---|---|---|
| `{app}\xiaoju3_data` | .env（xiaoju3.py:22-26）、installer_report.txt（iss:243-244 写入）、配置与日志 | [Dirs] iss:50 显式创建；first_run.py:27/32 |
| `{app}\agent_state` | 身份记忆（long_term.db）、history_terminal.json | xiaoju3.py:229；B3b §11 实测 |

无 %APPDATA% 等安装目录外的数据落点（全仓 grep 证实）；注册表 Run 值由 `uninsdeletevalue` 自清（iss:44）。旧版根目录 `.env` 仅迁移提示场景存在（xiaoju3.py:133-143），B3b 卸载实测根目录零残留，不在白名单（边界 §2.6）。

### 2.3 方案（主推）：InitializeUninstall 问询 + usUninstall DelTree

官方背书（Examples/UninstallCodeExample1.iss，6.7.3 自带）：`InitializeUninstall(): Boolean` 内 MsgBox 问询是官方示范写法；`CurUninstallStepChanged` 的 `usUninstall`（删除开始前）与 `usPostUninstall`（删除完成后）两阶段均可执行代码。6.7.3 的 TUninstallStep 实为四值：**usAppMutexCheck / usUninstall / usPostUninstall / usDone**（topic_scriptevents.htm 原文——老资料里的 usAppDirNotify/usDeinit 已过时，别抄）。

[Code] 段新增（草案，实现轮按锚微调）：

```pascal
var
  PurgeUserData: Boolean;   { B5：卸载数据问询结果；默认 False=保数据 }

function InitializeUninstall(): Boolean;
begin
  { 默认保数据铁律：MB_DEFBUTTON2 让「否」成为默认焦点，回车直达=保留 }
  PurgeUserData := MsgBox('是否同时删除小橘3号的用户数据？' + #13#10 + #13#10 +
      '选择「否」（推荐）：数据保留在安装目录的 xiaoju3_data 与 agent_state，重装后可无缝接续。' + #13#10 +
      '选择「是」：配置、身份记忆、日志将被彻底清除，不可恢复。',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
  Result := True;   { 本问询只决定数据去留，不中止卸载 }
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  case CurUninstallStep of
    usUninstall:
      if PurgeUserData then
      begin
        try
          { 白名单：仅这两个数据目录；禁止 DelTree({app}) 本体（卸载器自身还在运行） }
          DelTree(ExpandConstant('{app}') + chr(92) + 'xiaoju3_data', True, True, True);
          DelTree(ExpandConstant('{app}') + chr(92) + 'agent_state', True, True, True);
        except
          { 删除失败=静默保留（安全向）；完成页按目录实况如实提示，不会谎报 }
        end;
      end;
    usPostUninstall:
      begin
        { 口径读实况不读旗标：两目录都不在了才算"已删"，防谎报（含半删失败态如实报保留） }
        if (not DirExists(ExpandConstant('{app}') + chr(92) + 'xiaoju3_data')) and
           (not DirExists(ExpandConstant('{app}') + chr(92) + 'agent_state')) then
          MsgBox('已按您的选择彻底删除用户数据（xiaoju3_data 与 agent_state）。', mbInformation, MB_OK)
        else
          MsgBox('用户数据已保留：' + #13#10 +
              ExpandConstant('{app}') + chr(92) + 'xiaoju3_data（配置 / 日志 / 安装报告）' + #13#10 +
              ExpandConstant('{app}') + chr(92) + 'agent_state（身份记忆）' + #13#10 + #13#10 +
              '重新安装小橘3号后可无缝接续。', mbInformation, MB_OK);
      end;
  end;
end;
```

要点与依据：
- `MB_YESNO or MB_DEFBUTTON2`（6.7.3 CHM topic_isxfunc_msgbox.htm 原文示例即 "Ask the user a Yes/No question, defaulting to No"）——**默认焦点在「否」= 默认保数据语义在 UI 层锁死**；
- `DelTree` 6.7.3 签名：`function DelTree(const Path: String; const IsDir, DeleteFiles, DeleteSubdirsAlso: Boolean): Boolean`（topic_isxfunc_deltree.htm 原文）；`(True, True, True)` = 连目录带文件带子目录全删；目录不存在时无害（返回 False）；
- 路径经 `ExpandConstant('{app}')` 展开，自定义安装路径天然正确（卸载器从卸载日志取 {app}，与安装时选的目录一致）；反斜杠沿用本 iss [Code] 段既有 chr(92) 惯例（iss:120/243-244）；
- try/except 包裹与炸点②家规对齐（卸载侧 {app} 恒已初始化，理论不炸，防御性保留）；
- 时序选择 usUninstall（删除前）而非 usPostUninstall：与官方示例"pre-uninstall tasks"注释对齐，且避开卸载中途取消的窗口期。

### 2.4 与 C 项的合流

usPostUninstall 分支即 §3 的完成页提示，二选一文案共用本钩子；B5 一并落地（同一段代码，两道验收）。

### 2.5 测试锚

1. `uninstalldelete_stays_empty`：[UninstallDelete] 段剥注释后无实质行（**默认保数据红线锚**，防未来有人往里塞 filesandordirs）；
2. `initializeuninstall_default_no`：函数体含 `MB_DEFBUTTON2` 与 `MB_YESNO`，且含 `Result := True`（默认否 + 不中止语义锁）；
3. `deltree_whitelist_only`：[Code] 段所有 `DelTree(` 调用的第一实参必须含 `xiaoju3_data` 或 `agent_state` 字样；反向锚：不存在把裸 `{app}`（不带子目录拼接）传给 DelTree 的调用；
4. `purge_gated_by_flag`：usUninstall 分支内 DelTree 调用处于 `if PurgeUserData` 之下（删除动作唯一入口）；
5. `uninstall_hooks_zero_touch`：InitializeSetup / InitializeWizard / DeinitializeSetup 函数体与 B5 前逐字节一致（零触碰锚，防实现轮顺手改坏既有逻辑；五行红线锚继续守 Deinit）。

### 2.6 边界与风险

- 不删 `{app}` 本体、不删安装器装的五件（卸载器日志自管）；两目录删净后若 {app} 变空目录，Inno 会否自动移除空 {app}：**需实测**（不影响数据语义，纯观感）；
- 旧版根目录 `.env` 不在白名单（B3b 实测零残留；若未来发现机器上有，属个案清理不进安装器）；
- `/SILENT` 卸载兼容不做——问询 MsgBox 会弹窗打断静默流；如需支持，未来可用 `UninstallSilent()`（CHM 有此函数）跳过问询默认保留，本轮记录不实现；
- 多版本叠加安装时"只有最新一次安装的脚本在卸载时运行"（topic_scriptuninstall.htm 原文）：本项目升级=全量覆盖装，卸载器脚本随最新版走，B5 代码自然生效；无 patch 流，不触发"必须复制全量 [Code]"条款；
- 备选方案（若评审坚持"真复选框 UI"）：`UninstallProgressForm`（6.7.3 全局对象，topic_scriptclasses.htm 列全属性：InnerPage/StatusLabel/CancelButton 等，继承 TSetupForm 可挂 TNewCheckBox）上动态建复选框 + MsgBox 门控等用户点完再继续。**需实测**：官方无复选示例背书，布局坐标、父容器选择、等待门三处都要真机验证。MsgBox 两键方案功能等价（勾/不勾 ↔ 是/否），主推从稳。

---

## §3 C 项：卸载完成页提示

### 3.1 现状与机制查证

- Inno 卸载器**没有向导页**，只有一张进度窗（TUninstallProgressForm）；不存在可自定义文案的"卸载完成页"，也没有 UninstallNeedRestart 之外的完成页 API（`UninstallNeedRestart(): Boolean` 仅控制"完成后是否询问重启"，topic_scriptevents.htm 原文）——§11 遗留②的"完成页提示"只能用等价承载方式落地；
- 官方等价模式：`usPostUninstall` 分支 MsgBox（UninstallCodeExample1.iss:40-44 同位置同写法，模态、必被看到）。

### 3.2 方案

§2.3 草案的 usPostUninstall 分支即本项实现：**文案按目录实况二选一**——
- 已删：「已按您的选择彻底删除用户数据（xiaoju3_data 与 agent_state）。」
- 保留：列出两目录完整路径（`ExpandConstant('{app}')` 展开真实安装位置）+「重新安装小橘3号后可无缝接续」——满足 §8 承诺的"让用户知道重装能接上"。

选 DirExists 实况而非 PurgeUserData 旗标定文案的理由：删除半途失败时旗标说"要删"而实际保留，实况口径永不谎报。

### 3.3 测试锚

1. `uspostuninstall_reality_check`：usPostUninstall 分支含 `DirExists` 两连判（实况口径锁死）；
2. 文案锚：完成消息组合串含 `xiaoju3_data`、`agent_state`、`无缝接续` 三关键词；
3. 两分支齐备锚：`已按您的选择彻底删除` 与 `用户数据已保留` 两个文案字面量各出现恰 1 次。

### 3.4 边界与真机验收

- 不做进度窗 StatusLabel 常驻提示（卸载仅数秒，用户来不及读，MsgBox 模态才是保证；列增强候选）；
- 不碰 UninstallNeedRestart（本程序无重启依赖）；
- 验收：默认路径（选否）与彻底删除（选是）各走一遍，核对文案与目录实况一致；自定义安装路径下核对展开路径正确；需实测点：usPostUninstall 弹窗时进度窗是否已关（不影响文案可读）。

---

## §4 实现轮约束（写给下轮 ZCode）

1. iss 必须 UTF-8 **带 BOM + 纯 CRLF**（锚 7 在守；历史坑：LF-only 曾碎过 bat/iss）；
2. 只动 [Types]/[Components]（A）与 [Code] 段新增两钩子一变量（B/C），其余段零触碰；
3. 每步跑全仓测试，现有 1627 全绿基础上只增不减（新增锚约 10 条）；
4. 编译验证用 build_exe.bat 五步双产物；**编译过≠真机能跑**，三项各按 §1.6/§2.3/§3.4 真机验收后才算完；
5. §11 遗留表三行状态更新、B3b 演练记录补 B5 轮，随实现轮提交（本轮不提交）。

## §5 版本与发布

B5 落地随下一版本（1.0.2 或 1.1，实现轮拍板：纯收尾建议 1.0.2）；走既有 `_dev/release.bat` 一键发版（gh CLI 路线），push 需用户明确授权。
