; 小橘3号 · Inno Setup 安装器（安装器方案步 B2/B3a，详见 docs/INSTALLER_STEP_B_DESIGN.md）
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
Source: "dist\xiaoju3.exe"; DestDir: "{app}"; Flags: ignoreversion
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
Name: "custom"; Description: "自定义选择（三项均可跳过，后续在程序内配置）"

[Components]
Name: "ollama"; Description: "计划使用本地 Ollama（推荐完整版路线，需自行安装 Ollama 与模型）"; Types: custom
Name: "napcat"; Description: "计划接入 QQ（NapCat / LLOneBot，仓库内 setup_napcat.bat 可一键装配）"; Types: custom
Name: "ha"; Description: "计划接入 Home Assistant 主动服务心跳（需另配 HA_URL/HA_TOKEN）"; Types: custom

[UninstallDelete]
; 故意留空——卸载默认保留用户数据（数据目录由程序首启生成，卸载不清）：
;   配置与日志目录 / 身份记忆目录 / 工作区 / 灵魂备份目录
; 「彻底删除」可选项归后续步（卸载向导复选 + 删除树）。

[Code]
var
  SelfCheckPageID: Integer;
  TierHintText: String;

function YesNoStr(B: Boolean): String;
begin
  if B then Result := '1' else Result := '0';
end;

function WmiFirstValue(const WmiClass, WmiProp: String): String;
var
  Locator, Service, ResultSet: Variant;
begin
  Result := '';
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root' + chr(92) + 'cimv2');
    ResultSet := Service.ExecQuery('SELECT ' + WmiProp + ' FROM ' + WmiClass);
    if ResultSet.Count > 0 then
      Result := ResultSet.ItemIndex(0).Properties[WmiProp].Value;
  except
    Result := '';
  end;
end;

function InitializeSetup(): Boolean;
var
  RamKb, GpuName, Tier: String;
  RamGbInt, DiskGb: Int64;
  Dedicated: String;
  Body: String;
  SelfCheckPage: TOutputMsgWizardPage;
begin
  Result := True;   { 返回 False 将中止安装（本流程恒继续） }
  { 硬件自检（WMI；任一查询失败降级"无法预判"，不阻塞安装） }
  RamKb := WmiFirstValue('Win32_OperatingSystem', 'TotalVisibleMemorySize');
  GpuName := WmiFirstValue('Win32_VideoController', 'Name');
  Dedicated := '0';
  if (Pos('NVIDIA', GpuName) > 0) or (Pos('Radeon', GpuName) > 0) or
     (Pos('GTX', GpuName) > 0) or (Pos('RX ', GpuName) > 0) then
    Dedicated := '1';
  RamGbInt := 0;
  try
    RamGbInt := StrToInt64(Trim(RamKb)) div 1048576;   { KB -> GB }
  except
    RamGbInt := 0;
  end;
  DiskGb := StrToInt64(WmiFirstValue('Win32_LogicalDisk', 'FreeSpace')) div 1073741824;

  { 分档仅为安装期建议；真档位由程序内 hardware_profiler 首启复测 }
  if (RamGbInt >= 16) and (Dedicated = '1') and (DiskGb >= 20) then
    Tier := '推荐完整版（本地优先：可安装 Ollama + 本地模型）'
  else if RamGbInt < 8 then
    Tier := '推荐轻量版（云端优先：跳过本地模型，直接使用云端）'
  else
    Tier := '推荐完整版（本地模型响应可能较慢，可按需安装 Ollama）';
  TierHintText := Tier;

  Body := '内存：' + IntToStr(RamGbInt) + ' GB' + #13#10 +
          '显卡：' + GpuName + #13#10 +
          '安装目标盘可用空间：约 ' + IntToStr(DiskGb) + ' GB' + #13#10 +
          '安装形态建议：' + Tier + #13#10 +
          '（仅用于推荐安装形态；程序首次运行会自动复测真实档位）';
  SelfCheckPage := CreateOutputMsgPage(wpInfoBefore,
    '硬件自检', '检测结果仅用于推荐安装形态', Body);
  SelfCheckPageID := SelfCheckPage.ID;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then
    WizardSelectComponents('napcat');   { 默认不勾：ollama/ha 可选项，napcat 保持默认勾选 }
end;

procedure DeinitializeSetup();
var
  Report: String;
begin
  { 记录用户组件意向（装完或取消都记录）；文件在数据目录，卸载默认保留 }
  Report := GetDateTimeString('yyyy/mm/dd hh:nn:ss', '-', ':') + #13#10 +
    '硬件自检建议: ' + TierHintText + #13#10 +
    'ollama=' + YesNoStr(WizardIsComponentSelected('ollama')) + #13#10 +
    'napcat=' + YesNoStr(WizardIsComponentSelected('napcat')) + #13#10 +
    'ha=' + YesNoStr(WizardIsComponentSelected('ha')) + #13#10;
  SaveStringToFile(ExpandConstant('{app}' + chr(92) + 'xiaoju3_data' + chr(92) + 'installer_report.txt'),
                   Report, False);
end;
