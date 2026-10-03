# 小橘3号 · 一键发布脚本（gh CLI 路线）
# 用法：release.bat 1.0.2 [-Notes "本次更新说明"]
#   （release.bat 是一行包装器：powershell -ExecutionPolicy Bypass -File release.ps1 %*）
# 也可直接：powershell -NoProfile -ExecutionPolicy Bypass -File release.ps1 -NewVersion 1.0.2
#
# 流程：前置检查 → 确认 → 升版本号(xiaoju3.py + 2 测试锚) → build_exe.bat →
#       commit → tag v<版本> → push main+标签 → gh release create（挂双附件）
#
# 安全设计：
#   - 认证全走 gh（gh auth login 一次性浏览器授权，token 由 gh 托管——
#     脚本不出现、不存储、不传递任何 token/凭证字面）
#   - 版本号改动与推送共用一道 y 确认（确认面板列出全流程预告，防误发）
#   - 每步失败即停（$LASTEXITCODE 显式检查），失败后给出人工补救话术
#   - 不做 --force、不 rebase、不删标签、不改 git 历史
param(
    [Parameter(Mandatory = $true)][string]$NewVersion,
    [string]$Notes = ""
)
$ErrorActionPreference = 'Stop'

function Fail([string]$msg) {
    Write-Host ""
    Write-Host "❌ $msg" -ForegroundColor Red
    exit 1
}
function Step([string]$msg) { Write-Host ""; Write-Host "▶ $msg" -ForegroundColor Cyan }

# ===== 步骤 0：项目根定位（脚本位于 _dev/，项目根 = 上一级） =====
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $ProjectRoot 'xiaoju3.py'))) {
    Fail "项目根定位失败：$ProjectRoot 下没有 xiaoju3.py（脚本应位于 项目根\_dev\ 内）。"
}
Set-Location $ProjectRoot   # 脚本进程内切到项目根：git 命令与相对参数全程正确，进程退出自动还原

# ===== 步骤 1：前置检查 =====
Step "前置检查"
if (-not ($NewVersion -match '^\d+\.\d+\.\d+$')) {
    Fail "版本号格式必须为 x.y.z（如 1.0.2），收到：$NewVersion"
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Fail ("gh CLI 未安装。请先执行：winget install --id GitHub.cli -e " +
          "安装后执行：gh auth login （浏览器一次性授权，token 由 gh 托管）")
}
gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    Fail "gh 未认证。请先执行：gh auth login （浏览器授权，token 由 gh 托管，不进脚本）。"
}
if (Get-Process xiaoju3 -ErrorAction SilentlyContinue) {
    Fail "检测到 xiaoju3 进程在运行——请先关程序/安装器（防 dist 文件锁）。"
}
$gitDirty = git status --porcelain
if ($gitDirty) { Fail "git 工作树不干净——请先提交或清理：`n$gitDirty" }
git fetch origin --quiet
$remoteMain = git rev-parse origin/main
$localMain = git rev-parse main
if ($remoteMain -ne $localMain) {
    Fail "本地 main($localMain) 与 origin/main($remoteMain) 不一致——请先人工处理（落后则 pull，分叉勿动）。"
}

# ===== 步骤 2：读当前版本号 + 发布确认 =====
Step "版本号确认"
$xjRaw = Get-Content (Join-Path $ProjectRoot 'xiaoju3.py') -Raw
if (-not ($xjRaw -match 'XIAOJU3_VERSION = "([\d.]+)"')) {
    Fail "xiaoju3.py 中找不到 XIAOJU3_VERSION 定义。"
}
$OldVersion = $Matches[1]
if ([version]$NewVersion -le [version]$OldVersion) {
    Fail "目标版本 $NewVersion 必须大于当前版本 $OldVersion。"
}
Write-Host ""
Write-Host "============ 发布确认 ============" -ForegroundColor Yellow
Write-Host "当前版本：$OldVersion   →   目标版本：$NewVersion"
Write-Host "将依次执行："
Write-Host "  1) 版本号升级：xiaoju3.py 定义 + 2 个测试锚（共 3 处）"
Write-Host "  2) build_exe.bat（重建 exe + setup 双产物）"
Write-Host "  3) git commit（chore: 版本号 $OldVersion → $NewVersion）"
Write-Host "  4) git tag -a v$NewVersion"
Write-Host "  5) git push origin main + push 标签"
Write-Host "  6) gh release create v$NewVersion（挂 setup + exe 双附件）"
if ($Notes) { Write-Host "  Release 说明：$Notes" }
Write-Host "==================================="
$ans = Read-Host "确认发布？(y/n)"
if ($ans -ne 'y') { Fail "已取消（未做任何改动）。" }

# ===== 步骤 3：升版本号（定义 1 处 + 测试锚 2 处，计数校验防锚漂移） =====
Step "升版本号 $OldVersion → $NewVersion"
$edits = @(
    @{ File = (Join-Path $ProjectRoot 'xiaoju3.py');              Expect = 1 },
    @{ File = (Join-Path $ProjectRoot 'tests\test_dashboard.py'); Expect = 1 },
    @{ File = (Join-Path $ProjectRoot 'tests\test_first_run.py'); Expect = 1 }
)
foreach ($e in $edits) {
    $content = Get-Content $e.File -Raw
    $oldLit = '"' + $OldVersion + '"'
    $count = ([regex]::Matches($content, [regex]::Escape($oldLit))).Count
    if ($count -ne $e.Expect) {
        Fail "$($e.File) 中 `"$OldVersion`" 出现 $count 次（预期 $($e.Expect)）——锚可能漂移，已停，未改任何文件。"
    }
    $content = $content.Replace($oldLit, '"' + $NewVersion + '"')
    Set-Content -Path $e.File -Value $content -NoNewline -Encoding UTF8
}

# ===== 步骤 4：重建双产物 =====
Step "build_exe.bat（重建 exe + setup）"
& (Join-Path $ProjectRoot 'build_exe.bat')   # bat 内部自带 cd /d 到项目根，产物落 dist/
if ($LASTEXITCODE -ne 0) { Fail "build_exe.bat 失败——已停，未 commit（改动留在工作树，人工核查）。" }
$setup = Join-Path $ProjectRoot "dist\xiaoju3-$NewVersion-setup.exe"
if (-not (Test-Path $setup)) {
    Fail "未找到 $setup——setup 文件名未带新版本号（版本管线未生效？）。"
}
$vi = (Get-Item (Join-Path $ProjectRoot 'dist\xiaoju3.exe')).VersionInfo
if ($vi.FileVersion -ne $NewVersion) {
    Fail "exe FileVersion=$($vi.FileVersion) ≠ $NewVersion——版本管线未生效，已停。"
}
Write-Host "✅ 双产物就绪：$setup / dist\xiaoju3.exe（FileVersion=$($vi.FileVersion)）"

# ===== 步骤 5：commit =====
Step "git commit"
git add xiaoju3.py tests\test_dashboard.py tests\test_first_run.py
if ($LASTEXITCODE -ne 0) { Fail "git add 失败。" }
git commit -m "chore: 版本号 $OldVersion → $NewVersion"
if ($LASTEXITCODE -ne 0) { Fail "git commit 失败——已停（改动留在工作树，人工核查）。" }

# ===== 步骤 6：打标签 =====
Step "git tag v$NewVersion"
git tag -a "v$NewVersion" -m "小橘3号 v$NewVersion"
if ($LASTEXITCODE -ne 0) {
    Fail "打标签失败——已 commit 未 tag。请手动补救：git tag -a v$NewVersion -m '小橘3号 v$NewVersion'"
}

# ===== 步骤 7：推送 =====
Step "git push origin main + v$NewVersion"
git push origin main
if ($LASTEXITCODE -ne 0) {
    Fail "push main 被拒/失败——已停。不 force、不重试；commit 与标签在本地安全，人工核查。"
}
git push origin "v$NewVersion"
if ($LASTEXITCODE -ne 0) {
    Fail "push 标签失败——main 已推。请手动：git push origin v$NewVersion"
}

# ===== 步骤 8：gh release create（挂双附件） =====
Step "gh release create v$NewVersion"
if (-not $Notes) { $Notes = "修复与改进若干，详见 commit 历史。" }
$setupAsset = Join-Path $ProjectRoot "dist\xiaoju3-$NewVersion-setup.exe"
$exeAsset = Join-Path $ProjectRoot 'dist\xiaoju3.exe'
gh release create "v$NewVersion" `
    "$setupAsset#Windows 安装包" `
    "$exeAsset#Windows 便携版" `
    --title "小橘3号 v$NewVersion" `
    --notes $Notes
if ($LASTEXITCODE -ne 0) {
    Fail ("gh release create 失败——代码与标签已推送，Release 需手动补：" +
          "https://github.com/Xun201/xiaoju3-agent/releases/new （选 v$NewVersion，拖 dist 下两个 exe）")
}

# ===== 完成 =====
$relUrl = gh release view "v$NewVersion" --json url --jq '.url' 2>$null
Write-Host ""
Write-Host "🎉 v$NewVersion 发布完成：$relUrl" -ForegroundColor Green
