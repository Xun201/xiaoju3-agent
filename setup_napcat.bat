@echo off
chcp 65001 >nul
rem ============================================================
rem  小橘3号 · NapCat 一键下载安装（setup_napcat.bat）
rem  双击运行：从 GitHub Releases 下载最新 NapCat.Shell.zip，
rem  解压到 D:\NapCat\，完成后提示启动方式。Windows 10+ 可用。
rem
rem  高级开关（环境变量，普通使用无需理会）：
rem    NAPCAT_INSTALL_DIR  覆盖安装目录（默认 D:\NapCat，勿含单引号）
rem    NAPCAT_DL_URL       覆盖下载地址（默认 GitHub 最新版 NapCat.Shell.zip）
rem ============================================================
setlocal
title 小橘3号 · NapCat 一键下载安装

set "NAPCAT_DIR=D:\NapCat"
if defined NAPCAT_INSTALL_DIR set "NAPCAT_DIR=%NAPCAT_INSTALL_DIR%"
set "DL_URL=https://github.com/NapNeko/NapCatQQ/releases/latest/download/NapCat.Shell.zip"
if defined NAPCAT_DL_URL set "DL_URL=%NAPCAT_DL_URL%"
set "ZIP_PATH=%NAPCAT_DIR%\NapCat.Shell.zip"

echo ==============================================
echo  小橘3号 · NapCat 一键下载安装
echo  安装目录：%NAPCAT_DIR%
echo  下载源：%DL_URL%
echo ==============================================
echo.

rem ---------- 已就绪检测：目录里已有 launcher 就直接提示（重复运行秒过） ----------
set "LAUNCHER="
call :find_launcher
if defined LAUNCHER goto ready

echo [1/3] 创建安装目录（若不存在）...
if not exist "%NAPCAT_DIR%" mkdir "%NAPCAT_DIR%"
if not exist "%NAPCAT_DIR%" (
    echo ❌ 无法创建目录 %NAPCAT_DIR%，请检查盘符与写入权限。
    goto end
)

echo [2/3] 正在下载 NapCat.Shell.zip（GitHub 最新版，约几十 MB，请耐心等待）...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%DL_URL%' -OutFile '%ZIP_PATH%' -UseBasicParsing -TimeoutSec 600; exit 0 } catch { if (Test-Path -LiteralPath '%ZIP_PATH%') { Remove-Item -LiteralPath '%ZIP_PATH%' -Force }; Write-Host ('下载失败: ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 goto download_failed

echo [3/3] 正在解压到 %NAPCAT_DIR% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Expand-Archive -LiteralPath '%ZIP_PATH%' -DestinationPath '%NAPCAT_DIR%' -Force; exit 0 } catch { Write-Host ('解压失败: ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 goto extract_failed

del "%ZIP_PATH%" >nul 2>&1

set "LAUNCHER="
call :find_launcher
if not defined LAUNCHER goto launcher_missing

:ready
echo.
echo ✅ NapCat 已就绪，请双击 %LAUNCHER% 启动
echo    （若 launcher.bat 启动异常，可尝试同目录的 launcher-win10.bat）
goto end

:download_failed
echo.
echo ❌ 下载失败（GitHub 访问可能受限或网络超时）。
echo    请手动下载：
echo      1. 打开 https://github.com/NapNeko/NapCatQQ/releases
echo      2. 在最新版本的 Assets 中下载 NapCat.Shell.zip
echo         （注意是 Shell 包，不是 NapCat.Win / framework 等其他包）
echo      3. 手动解压到 %NAPCAT_DIR%，解压后应能看到 launcher.bat
goto end

:extract_failed
echo.
echo ❌ 解压失败。可手动用资源管理器把 "%ZIP_PATH%" 解压到 "%NAPCAT_DIR%" 后重试。
goto end

:launcher_missing
echo.
echo ⚠️ 解压完成，但未在 %NAPCAT_DIR%（含一级子目录）找到 launcher.bat / launcher-win10.bat。
echo    请确认下载的确实是 NapCat.Shell.zip，或手动查看解压目录结构后重试。
goto end

:end
echo.
pause
exit /b

rem ---------- 子过程：定位 launcher（根目录，其次一级子目录兜底） ----------
:find_launcher
if exist "%NAPCAT_DIR%\launcher.bat" (set "LAUNCHER=%NAPCAT_DIR%\launcher.bat" & goto :eof)
if exist "%NAPCAT_DIR%\launcher-win10.bat" (set "LAUNCHER=%NAPCAT_DIR%\launcher-win10.bat" & goto :eof)
for /d %%D in ("%NAPCAT_DIR%\*") do (
    if exist "%%D\launcher.bat" set "LAUNCHER=%%D\launcher.bat"
    if exist "%%D\launcher-win10.bat" if not defined LAUNCHER set "LAUNCHER=%%D\launcher-win10.bat"
)
goto :eof
