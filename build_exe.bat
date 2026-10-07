@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem 小橘3号 · 一键构建双产物（安装器方案步 B2）：exe + setup 安装包。
rem 产物 dist\xiaoju3*.exe 不入库（*.exe 拒绝规则）；版本单一来源 = xiaoju3.py。
rem 前置：pip install pyinstaller pillow + Inno Setup 6（ISCC 三路探测）。

echo [1/5] 清理旧构建产物（build/ dist/ version_info.txt）...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist version_info.txt del /q version_info.txt

echo [2/5] 生成版本资源与图标（make_build_assets.py）...
set "XJ3_VER="
for /f "tokens=2 delims==" %%V in ('python make_build_assets.py ^| findstr /b "VERSION="') do set "XJ3_VER=%%V"
if not defined XJ3_VER (
    echo [FAIL] 版本抓取失败——不带版本不出包。
    endlocal
    exit /b 1
)
echo     版本 %XJ3_VER%

echo [2.5/5] playwright driver windowsHide 补丁（防冻结抓取闪黑框）...
python _dev\patch_playwright_windows_hide.py
if errorlevel 1 (
    echo [WARN] driver 补丁失败——继续构建（可能表现为抓取时闪黑框）。
)

echo [3/5] PyInstaller 构建 onedir 目录（无控制台，含版本资源与图标）...
python -m PyInstaller xiaoju3.spec --noconfirm
if errorlevel 1 (
    echo [FAIL] exe 构建失败，请检查上方日志。
    endlocal
    exit /b 1
)
if not exist dist\xiaoju3\xiaoju3.exe (
    echo [FAIL] onedir 产物缺失（dist\xiaoju3\xiaoju3.exe），请检查上方日志。
    endlocal
    exit /b 1
)

echo [4/5] exe 产物报告...
for %%I in (dist\xiaoju3\xiaoju3.exe) do (
    echo 产物路径: %%~fI
    echo 产物大小: %%~zI 字节
)

echo [5/5] 编译安装器（Inno Setup，版本 %XJ3_VER%）...
set "ISCC_EXE=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_EXE%" set "ISCC_EXE=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_EXE%" set "ISCC_EXE=C:\Program Files\Inno Setup 6\ISCC.exe"
set "ISCC_SKIP=0"
if not exist "%ISCC_EXE%" (
    echo [WARN] 未检测到 Inno Setup 6——跳过安装器构建（exe 已产出）。
    echo        安装：winget install JRSoftware.InnoSetup
    set "ISCC_SKIP=1"
)
if "%ISCC_SKIP%"=="0" call "%ISCC_EXE%" /DAppVersion=%XJ3_VER% xiaoju3.iss
if "%ISCC_SKIP%"=="0" if errorlevel 1 (echo [FAIL] 安装器编译失败，请检查上方日志。 & endlocal & exit /b 1)
for %%I in (dist\xiaoju3-*-setup.exe) do (
    echo 安装包路径: %%~fI
    echo 安装包大小: %%~zI 字节
)
echo [OK] build done (exe + setup, or exe only if Inno absent).
endlocal
exit /b 0
