@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem 小橘3号 · exe 一键构建（方案 docs/EXE_PACKAGING_PLAN.md 步 4）。
rem 产物 dist\xiaoju3.exe 不入库（*.exe 已被 .gitignore 拒绝，b8507dc 口径）。
rem 前置：pip install pyinstaller；依赖已在 requirements.txt。

echo [1/3] 清理旧构建产物（build/ dist/）...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/3] PyInstaller 构建（onefile，无控制台）...
python -m PyInstaller xiaoju3.spec --noconfirm
if errorlevel 1 (
    echo [FAIL] 构建失败，请检查上方日志。
    endlocal
    exit /b 1
)

echo [3/3] 产物报告...
for %%I in (dist\xiaoju3.exe) do (
    echo 产物路径: %%~fI
    echo 产物大小: %%~zI 字节
)
echo [OK] 构建完成。
endlocal
exit /b 0
