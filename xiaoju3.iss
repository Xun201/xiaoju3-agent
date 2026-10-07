; 小橘3号 · Inno Setup 安装器（安装器方案步 B2/B3a/B3 修复，详见 docs/INSTALLER_STEP_B_DESIGN.md 与 docs/INSTALLER_STEP_B3_CODE_FIX_DESIGN.md）
; 铁律：
;   程序自带文件只装三件（主程序、配置模板、快速上手）——绝不打包
;   xiaoju3_data 与 agent_state 两个用户数据目录（由程序首启生成）；
;   卸载删除清单段留空 = 卸载默认保留数据；
;   版本经 ISCC 斜杠-D AppVersion 传入（build_exe.bat 从 xiaoju3.py 抓取）。
; 自启键：HKCU Run / 值名 Xiaoju3——与 autostart.py 同键同名，卸载自动清。
; 本文件为 UTF-8 带 BOM（Inno 含中文 [Code] 段的官方要求）。

#ifndef AppVersion
#define AppVersion "0.0.0-dev"
#endif

[Setup]
AppId={{7E3A1C94-5B2D-4F68-9A03-18C45E7F2B60}
AppVersion={#AppVersion}
AppName=小橘3号
DefaultDirName={localappdata}\Programs\小橘3号
PrivilegesRequired=lowest
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\xiaoju3.exe
OutputDir=dist
OutputBaseFilename=xiaoju3-{#AppVersion}-setup
DisableProgramGroupPage=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[Files]
Source: "dist\xiaoju3\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: ".env.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "QUICKSTART.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\小橘3号 · 控制台"; Filename: "{app}\xiaoju3.exe"
Name: "{autodesktop}\小橘3号 · 控制台"; Filename: "{app}\xiaoju3.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked
Name: "autostart"; Description: "开机自动启动小橘3号（可随时在任务管理器-启动中关闭）"; Flags: checkedonce

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Xiaoju3"; ValueData: """{app}\xiaoju3.exe"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\xiaoju3.exe"; Description: "立即启动小橘3号"; Flags: nowait postinstall skipifsilent

[Dirs]
Name: "{app}\xiaoju3_data"

[Types]
Name: "lite"; Description: "轻量版（默认仅 QQ 接入，云端优先）"
Name: "full"; Description: "完整版（QQ 接入 + 本地 Ollama + HA 心跳）"
Name: "custom"; Description: "自定义（三项均可跳过，逐项勾选；后续也可在程序内配置）"; Flags: iscustom

[Components]
Name: "ollama"; Description: "计划使用本地 Ollama（推荐完整版路线，需自行安装 Ollama 与模型）"; Types: full custom
Name: "napcat"; Description: "计划接入 QQ（NapCat / LLOneBot，仓库内 setup_napcat.bat 可一键装配）"; Types: lite full custom
Name: "ha"; Description: "计划接入 Home Assistant 主动服务心跳（需另配 HA_URL/HA_TOKEN）"; Types: full custom

[UninstallDelete]
; 故意留空——卸载默认保留用户数据（数据目录由程序首启生成，卸载不清）：
;   配置与日志目录 / 身份记忆目录 / 工作区 / 灵魂备份目录
; 「彻底删除」可选项归后续步（卸载向导复选 + 删除树）。

[Code]
const
  MAX_WMI_ATTEMPTS = 3;   { 同一 WMI 查询最多尝试次数（§8.1 重试预算） }

var
  SelfCheckPageID: Integer;
  TierHintText: String;
  SelfCheckBody: String;
  WizardWasCreated: Boolean;
  WmiUnavailable: Boolean;   { 全局预算闸：任一指标重试耗尽即置位，后续 WMI 查询快速失败（§8.1） }
  PurgeUserData: Boolean;   { B5 卸载数据问询结果：True=彻底删除；默认 False=保数据（问询默认焦点「否」） }

type
  TMemoryStatusEx = record
    dwLength: Cardinal;
    dwMemoryLoad: Cardinal;
    ullTotalPhys: Int64;
    ullAvailPhys: Int64;
    ullTotalPageFile: Int64;
    ullAvailPageFile: Int64;
    ullTotalVirtual: Int64;
    ullAvailVirtual: Int64;
    ullAvailExtendedVirtual: Int64;
  end;

function GlobalMemoryStatusEx(var Buffer: TMemoryStatusEx): Boolean;
external 'GlobalMemoryStatusEx@kernel32.dll stdcall';

function TotalPhysKBBackup(): Int64;
var
  M: TMemoryStatusEx;
begin
  Result := -1;
  M.dwLength := SizeOf(M);
  if GlobalMemoryStatusEx(M) then
    Result := M.ullTotalPhys div 1024;   { 字节 → KB（与 WMI TotalVisibleMemorySize 同单位） }
end;

function YesNoStr(B: Boolean): String;
begin
  if B then Result := '1' else Result := '0';
end;

function WmiFirstValue(const WmiClass, WmiProp, WmiWhere: String): String;
var
  Locator, Service, ResultSet: Variant;
  Query: String;
  Attempt: Integer;
begin
  Result := '';
  if WmiUnavailable then
    Exit;   { 预算耗尽后不再尝试任何 WMI：用户延迟优先于数据完整性；磁盘已走 GetSpaceOnDisk64 不受影响（§8.1） }
  for Attempt := 1 to MAX_WMI_ATTEMPTS do
  begin
    try
      Locator := CreateOleObject('WbemScripting.SWbemLocator');
      Service := Locator.ConnectServer('.', 'root' + chr(92) + 'cimv2');
      Query := 'SELECT ' + WmiProp + ' FROM ' + WmiClass;
      if WmiWhere <> '' then
        Query := Query + ' WHERE ' + WmiWhere;
      ResultSet := Service.ExecQuery(Query);
      if ResultSet.Count > 0 then
      begin
        Result := ResultSet.ItemIndex(0).Properties[WmiProp].Value;
        { Value 为 Null（如无介质光驱）时隐式赋 String 得空串或抛 variant
          异常——Null 不设专门分支，空串交给 WmiFirstInt 的哨兵统一拦截（§2.2） }
        Break;
      end;
    except
      Result := '';
    end;
    if Attempt < MAX_WMI_ATTEMPTS then
      Sleep(400);   { 末次失败不睡（§8.1） }
  end;
  if Result = '' then
    WmiUnavailable := True;   { MAX_WMI_ATTEMPTS 次全失败：预算闸落下，后续 WMI 查询快速失败（§8.1） }
end;

function WmiFirstInt(const WmiClass, WmiProp, WmiWhere: String): Int64;
begin
  { 哨兵 -1=查询失败或值不可解析，真 0 不受影响；降级收敛单一咽喉点，
    调用点禁止再出现裸 StrToInt64(WmiFirstValue(...)（炸点①教训，设计稿 §2.1） }
  Result := StrToInt64Def(Trim(WmiFirstValue(WmiClass, WmiProp, WmiWhere)), -1);
end;

function InitializeSetup(): Boolean;
var
  RamKb, DiskBytes, RamGb, DiskGb, DiskFree, DiskTotal: Int64;
  GpuName, Dedicated: String;
  Tier, MemText, GpuText, DiskText: String;
begin
  Result := True;   { 返回 False 将中止安装（本流程恒继续） }
  { 硬件自检（WMI 暂态不稳是常态，降级走哨兵 -1 落"无法预判"，不阻塞安装）。
    本钩子只许纯 COM 探测：禁建页、禁任何 Wizard* API（炸点③教训） }
  RamKb := WmiFirstInt('Win32_OperatingSystem', 'TotalVisibleMemorySize', '');
  if RamKb < 0 then
    RamKb := TotalPhysKBBackup();   { WMI 重试耗尽 → kernel32 备用（§8.2；record 对齐真机实测一次） }
  GpuName := WmiFirstValue('Win32_VideoController', 'Name', '');
  Dedicated := '0';
  if (Pos('NVIDIA', GpuName) > 0) or (Pos('Radeon', GpuName) > 0) or
     (Pos('GTX', GpuName) > 0) or (Pos('RX ', GpuName) > 0) then
    Dedicated := '1';
  { 磁盘：Inno 原生 GetSpaceOnDisk64（§8.2）——不经 WMI 服务，免疫安装瞬间
    WMI 未就绪；Path 传完整路径；返回 Int64 字节，False → 哨兵 -1 }
  if GetSpaceOnDisk64(ExpandConstant('{localappdata}'), DiskFree, DiskTotal) then
    DiskBytes := DiskFree
  else
    DiskBytes := -1;

  if RamKb >= 0 then
    RamGb := RamKb div 1048576   { KB -> GB }
  else
    RamGb := -1;
  if DiskBytes >= 0 then
    DiskGb := DiskBytes div 1073741824   { 字节 -> GB }
  else
    DiskGb := -1;

  { 分档仅为安装期建议；任一指标不可知即"无法预判"，不再误报轻量版（设计稿 §2.3） }
  if (RamGb < 0) or (DiskGb < 0) or (GpuName = '') then
    Tier := '无法预判（程序首次运行将自动复测）'
  else if (RamGb >= 16) and (Dedicated = '1') and (DiskGb >= 20) then
    Tier := '推荐完整版（本地优先：可安装 Ollama + 本地模型）'
  else if RamGb < 8 then
    Tier := '推荐轻量版（云端优先：跳过本地模型，直接使用云端）'
  else
    Tier := '推荐完整版（本地模型响应可能较慢，可按需安装 Ollama）';
  TierHintText := Tier;

  if RamGb < 0 then
    MemText := '内存：无法预判'
  else
    MemText := '内存：' + IntToStr(RamGb) + ' GB';
  if GpuName = '' then
    GpuText := '显卡：无法预判'
  else
    GpuText := '显卡：' + GpuName;
  if DiskGb < 0 then
    DiskText := '安装目标盘可用空间：无法预判'
  else
    DiskText := '安装目标盘可用空间：约 ' + IntToStr(DiskGb) + ' GB';

  SelfCheckBody := MemText + #13#10 +
    GpuText + #13#10 +
    DiskText + #13#10 +
    '安装形态建议：' + Tier + #13#10 +
    '（仅用于推荐安装形态；程序首次运行会自动复测真实档位）';
end;

procedure InitializeWizard();
begin
  WizardWasCreated := True;   { 旗唯一写点：向导窗体此刻已创建（设计稿 §1.1） }
  SelfCheckPageID := CreateOutputMsgPage(wpInfoBefore,
    '硬件自检', '检测结果仅用于推荐安装形态', SelfCheckBody).ID;
end;

procedure DeinitializeSetup();
var
  Report: String;
begin
  if not WizardWasCreated then
    Exit;   { 旗守卫：向导未建=无意向可记，Wizard* API 也会二次崩（炸点②教训） }
  { 记录用户组件意向（装完或取消都记录）；文件在数据目录，卸载默认保留。
    报告写入整体 try 包裹（2026-10-03 真机教训：app 常量在用户未走过选目录
    页 wpSelectDir 时才初始化，ExpandConstant 直接抛 Runtime error——异常即
    用户未达选目录页=无意向可记，静默跳过；except 内绝不调 ExpandConstant、
    不写任何东西 }
  try
    Report := GetDateTimeString('yyyy/mm/dd hh:nn:ss', '-', ':') + #13#10 +
      '硬件自检建议: ' + TierHintText + #13#10 +
      'ollama=' + YesNoStr(WizardIsComponentSelected('ollama')) + #13#10 +
      'napcat=' + YesNoStr(WizardIsComponentSelected('napcat')) + #13#10 +
      'ha=' + YesNoStr(WizardIsComponentSelected('ha')) + #13#10;
    ForceDirectories(ExpandConstant('{app}' + chr(92) + 'xiaoju3_data'));
    SaveStringToFile(ExpandConstant('{app}' + chr(92) + 'xiaoju3_data' + chr(92) + 'installer_report.txt'),
                     Report, False);
  except
    { 静默跳过：不写文件、不建目录、绝不调 ExpandConstant（那正是炸点） }
  end;
end;

function InitializeUninstall(): Boolean;
begin
  { B5 卸载数据问询（设计稿 §2.3）：MB_DEFBUTTON2 让「否」成为默认焦点——
    默认保数据铁律在 UI 层锁死；本问询只决定数据去留，恒续卸载不中止 }
  PurgeUserData := MsgBox('是否同时删除小橘3号的用户数据？' + #13#10 + #13#10 +
      '选择「否」（推荐）：数据保留在安装目录的 xiaoju3_data 与 agent_state，重装后可无缝接续。' + #13#10 +
      '选择「是」：配置、身份记忆、日志将被彻底清除，不可恢复。',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  case CurUninstallStep of
    usUninstall:
      if PurgeUserData then
      begin
        try
          { 白名单：只许这两个数据目录，禁删安装目录本体（卸载器自身仍在运行）；
            DelTree 6.7.3 签名 (Path, IsDir, DeleteFiles, DeleteSubdirsAlso): Boolean }
          DelTree(ExpandConstant('{app}') + chr(92) + 'xiaoju3_data', True, True, True);
          DelTree(ExpandConstant('{app}') + chr(92) + 'agent_state', True, True, True);
        except
          { 删除失败=静默保留（安全向）；完成页按 DirExists 实况如实提示，不谎报 }
        end;
      end;
    usPostUninstall:
      begin
        { 完成页提示（§11 遗留②）：口径读目录实况、不读旗标——半删失败态也如实报保留 }
        if (not DirExists(ExpandConstant('{app}') + chr(92) + 'xiaoju3_data')) and
           (not DirExists(ExpandConstant('{app}') + chr(92) + 'agent_state')) then
          MsgBox('用户数据已彻底删除（xiaoju3_data 与 agent_state）。', mbInformation, MB_OK)
        else
          MsgBox('用户数据保留于：' + #13#10 +
              ExpandConstant('{app}') + chr(92) + 'xiaoju3_data（配置 / 日志 / 安装报告）' + #13#10 +
              ExpandConstant('{app}') + chr(92) + 'agent_state（身份记忆）' + #13#10 + #13#10 +
              '重新安装小橘3号后可无缝接续。', mbInformation, MB_OK);
      end;
  end;
end;
