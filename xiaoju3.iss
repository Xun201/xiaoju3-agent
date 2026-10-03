; 小橘3号 · Inno Setup 安装器 v1（安装器方案步 B2，docs/INSTALLER_STEP_B_DESIGN.md §3）
; 铁律：
;   [Files] 只装程序自带文件（exe / .env.example / QUICKSTART）——绝不装
;   xiaoju3_data\、agent_state\（用户数据由程序首启生成）；
;   [UninstallDelete] 留空 = 卸载默认保留数据；
;   AppVersion 经 ISCC /DAppVersion=x.y.z 传入（build_exe.bat 从 xiaoju3.py
;   XIAOJU3_VERSION 抓取，单一事实源），缺省 dev 串防呆。
; 自启键：HKCU Run / ValueName=Xiaoju3——与 autostart.py 同键同名，
; uninsdeletevalue 卸载自动清；程序内开关写同一键，最后写入者胜。

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

[UninstallDelete]
; 故意留空——卸载默认保留用户数据：
;   {app}\xiaoju3_data\   配置（.env）与日志、表情库
;   {app}\agent_state\    身份、权限、对话与长期记忆
;   {app}\workspace\      工作区沙箱
;   {app}\backups\        灵魂备份（soul_*.zip）
; 「彻底删除」可选项归步 B3（[Code] CurUninstallStepChanged + DelTree）。
