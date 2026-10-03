@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem 小橘3号 · exe 一键构建（安装器方案步 B1：版本管线 + 图标；步 B2 将扩为双产物）。
rem 产物 dist\xiaoju3.exe 不入库（*.exe 已被 .gitignore 拒绝，b8507dc 口径）。
rem 前置：pip install pyinstaller pillow；版本单一来源 = xiaoju3.py XIAOJU3_VERSION。
echo [1/4] 清理旧构建产物（build/ dist/ version_info.txt）...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist version_info.txt del /q version_info.txt
echo [2/4] 生成版本资源与图标（make_build_assets.py：抓 XIAOJU3_VERSION）...
python make_build_assets.py
if errorlevel 1 (
    echo [FAIL] 版本/资产生成失败——不带版本不出包。
    endlocal
    exit /b 1
)
echo [3/4] PyInstaller 构建（onefile，无控制台，含版本资源与图标）...
python -m PyInstaller xiaoju3.spec --noconfirm
if errorlevel 1 (
    echo [FAIL] 构建失败，请检查上方日志。
    endlocal
    exit /b 1
)
echo [4/4] 产物报告...
for %%I in (dist\xiaoju3.exe) do (
    echo 产物路径: %%~fI
    echo 产物大小: %%~zI 字节
)
echo [OK] 构建完成。
endlocal
exit /b 0
