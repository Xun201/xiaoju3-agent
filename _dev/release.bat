@echo off
rem 一行包装器：绕过 PowerShell 执行策略，参数原样透传给 release.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0release.ps1" %*
