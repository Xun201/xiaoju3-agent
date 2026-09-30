#!/usr/bin/env bash
# 小橘3号 · 一键部署安装器（功能文档 §10.2「一键部署」落地；开发日志 第九章「分发的种子」）
# 职责：环境自检 → 虚拟环境与依赖 → .env 配置引导 → 完整性校验 → 启动与 LV2/LV3 引导。
# 用法：
#   ./install.sh                     交互式安装（推荐）
#   ./install.sh --non-interactive   非交互安装：.env 只复制模板并提示"请手工填写"
#   ./install.sh --register <密码>   启动后经本机 /onebot 自动发一条 LV2 注册请求（失败不中断）
# 安全红线：本脚本不含任何密钥/内网 IP/真实密码；密钥输入一律 read -s 不回显。
# 幂等：重复安装安全（.venv 已存在跳过创建、pip 增量安装、.env 已存在不覆盖）。

# 不用 set -e：关键步骤逐个显式判错，失败时打印已完成步骤清单（见 fail_exit）
set -u
cd "$(dirname "$0")" || exit 1

NON_INTERACTIVE=0
REGISTER_PASSWORD=""

# ===== 参数解析 =====
while [ $# -gt 0 ]; do
    case "$1" in
        --non-interactive)
            NON_INTERACTIVE=1
            shift
            ;;
        --register)
            REGISTER_PASSWORD="${2:-}"
            if [ -z "$REGISTER_PASSWORD" ]; then
                echo "❌ --register 需要携带注册密码，例如：./install.sh --register 你的密码"
                exit 1
            fi
            shift 2
            ;;
        *)
            echo "❌ 未知参数: $1（支持 --non-interactive / --register <密码>）"
            exit 1
            ;;
    esac
done

# 无 TTY（管道/CI 等场景）强制非交互，避免交互 read 卡死（口径：--non-interactive 或无 TTY）
if [ "$NON_INTERACTIVE" -eq 0 ] && ! [ -t 0 ]; then
    NON_INTERACTIVE=1
    echo "ℹ️ 未检测到交互终端，自动切换为非交互模式。"
fi

# ===== 失败汇报：打印中文原因 + 已完成步骤清单；已启动的服务不回滚停止 =====
DONE_STEPS=""
mark_done() {
    DONE_STEPS="${DONE_STEPS}  - $1"$'\n'
}
fail_exit() {
    echo ""
    echo "❌ 安装失败：$1"
    if [ -n "$DONE_STEPS" ]; then
        echo "📋 已完成的步骤："
        printf "%s" "$DONE_STEPS"
    else
        echo "📋 尚无已完成的步骤。"
    fi
    echo "ℹ️ 已启动的服务不会自动停止；如需停止请运行 ./stop_all.sh。"
    exit 1
}

echo "=============================================="
echo "        🦊 小橘3号 · 一键部署安装器"
echo "=============================================="

# ===== [1/5] 环境自检 =====
echo "🔍 [1/5] 环境自检..."

if ! command -v python3 >/dev/null 2>&1; then
    fail_exit "未检测到 python3。请先安装 Python（功能口径要求 ≥ 3.8）后重新运行本安装器。"
fi
PYVER=$(python3 -c 'import sys; print(".".join(str(n) for n in sys.version_info[:3]))' 2>/dev/null)
if [ -z "$PYVER" ]; then
    fail_exit "python3 存在但无法获取版本号，请检查 Python 安装。"
fi
PY_MAJOR=${PYVER%%.*}
PY_MINOR=$(echo "$PYVER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 8 ]; }; then
    fail_exit "Python 版本过低（当前 $PYVER）：功能口径要求 ≥ 3.8，请升级后重试。"
fi
echo "✅ python3 就绪（版本 $PYVER）"

# git / docker 为可选依赖：缺失降级提示，不中断安装
if command -v git >/dev/null 2>&1; then
    echo "✅ git 就绪（push.sh 隐私门禁与版本管理可用）"
else
    echo "⚠️ 未检测到 git：已降级跳过（可选依赖，仅影响版本管理与上传门禁，不影响运行）。"
fi
if command -v docker >/dev/null 2>&1; then
    echo "✅ docker 就绪（NapCat / Home Assistant 容器可用）"
else
    echo "⚠️ 未检测到 docker：已降级跳过（可选依赖，仅影响 QQ 接入与家居容器，不影响主程序）。"
fi
mark_done "环境自检（python3 $PYVER）"

# ===== [2/5] 虚拟环境与依赖 =====
echo "🐍 [2/5] 准备 Python 虚拟环境与依赖..."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv || fail_exit "创建虚拟环境 .venv 失败（请确认已安装 venv 组件，如 Debian/Ubuntu 的 python3-venv）。"
    echo "✅ 已创建虚拟环境 .venv"
else
    echo "✅ 检测到已有 .venv，跳过创建（幂等安装）。"
fi
# Windows 的 venv 布局是 Scripts/，Linux/macOS 是 bin/，两者都兼容
# shellcheck disable=SC1091
if [ -f ".venv/bin/activate" ]; then
    . .venv/bin/activate || fail_exit "激活虚拟环境 .venv 失败。"
elif [ -f ".venv/Scripts/activate" ]; then
    . .venv/Scripts/activate || fail_exit "激活虚拟环境 .venv 失败。"
else
    fail_exit "未找到 .venv/bin/activate 或 .venv/Scripts/activate，虚拟环境不完整。"
fi
mark_done "虚拟环境 .venv"

echo "📦 安装第三方依赖（requirements.txt，增量安装）..."
python -m pip install -r requirements.txt \
    || fail_exit "依赖安装失败（python -m pip install -r requirements.txt）。请检查网络后重试。"
mark_done "依赖安装（requirements.txt）"

echo "🌐 安装 Playwright Chromium 浏览器内核（首次下载较慢，请耐心等待）..."
if python -m playwright install chromium; then
    mark_done "Playwright Chromium 浏览器内核"
else
    echo "⚠️ Chromium 下载失败，切换国内镜像源重试一次..."
    export PLAYWRIGHT_DOWNLOAD_HOST="https://npmmirror.com/mirrors/playwright/"
    if python -m playwright install chromium; then
        echo "✅ 镜像源重试成功，Chromium 已安装。"
        mark_done "Playwright Chromium（镜像源重试成功）"
    else
        # 不中断整体流程：浏览器缺失时 /gen_log 链接抓取会优雅降级
        echo "⚠️ Chromium 安装仍失败（不影响安装继续）。"
        echo "   影响：/gen_log 链接抓取等功能将优雅降级并给出中文提示。"
        echo "   稍后可手动重试："
        echo "     PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/ python -m playwright install chromium"
    fi
fi

# ===== [3/5] .env 配置引导 =====
echo "⚙️  [3/5] 配置引导（.env）..."

# 值写入 .env：用 python 逐行替换（对特殊字符安全，跨平台通用）
replace_env_value() {
    python3 - "$1" "$2" <<'PYEOF'
import sys
key, value = sys.argv[1], sys.argv[2]
with open(".env", "r", encoding="utf-8") as f:
    lines = f.read().splitlines()
out, found = [], False
for line in lines:
    if line.startswith(key + "="):
        out.append(key + "=" + value)
        found = True
    else:
        out.append(line)
if not found:
    out.append(key + "=" + value)
with open(".env", "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(out) + "\n")
PYEOF
}

prompt_secret() {
    # 用法：prompt_secret KEY 提示语 —— read -s 不回显；直接回车跳过，跳过项保留空值
    local key="$1" label="$2" value=""
    read -s -r -p "$label（直接回车跳过；输入不回显）: " value
    echo ""
    if [ -n "$value" ]; then
        replace_env_value "$key" "$value"
        echo "✅ 已写入 $key"
    else
        echo "ℹ️ 已跳过 $key（保留模板空值，可稍后编辑 .env 手工填写）"
    fi
}

prompt_plain() {
    # 用法：prompt_plain KEY 提示语 —— 非密钥项可回显输入；回车跳过保留空值
    local key="$1" label="$2" value=""
    read -r -p "$label（直接回车跳过）: " value
    if [ -n "$value" ]; then
        replace_env_value "$key" "$value"
        echo "✅ 已写入 $key"
    else
        echo "ℹ️ 已跳过 $key（保留模板空值，可稍后编辑 .env 手工填写）"
    fi
}

if [ -f ".env" ]; then
    echo "✅ 检测到已有 .env，跳过配置引导（绝不覆盖现有配置）。"
    mark_done "配置检查（.env 已存在，跳过引导）"
else
    if [ ! -f ".env.example" ]; then
        fail_exit "缺少 .env.example 模板，无法生成 .env。"
    fi
    cp .env.example .env || fail_exit "从 .env.example 复制生成 .env 失败。"
    echo "✅ 已从模板生成 .env"
    mark_done ".env 生成（自模板）"

    if [ "$NON_INTERACTIVE" -eq 1 ]; then
        echo "⚠️ 非交互模式：.env 已由模板生成，请手工填写以下配置后再使用："
        echo "   DEEPSEEK_API_KEY / WEB_API_KEY / XIAOJU3_TOTP_SECRET /"
        echo "   XIAOJU3_REGISTER_PASSWORD / HA_URL / HA_TOKEN"
    else
        echo "👇 逐项填写配置（均可直接回车跳过；跳过项保留空值，之后可编辑 .env 补填）"
        prompt_secret "DEEPSEEK_API_KEY" "请输入 DeepSeek API Key（云端密钥）"
        prompt_secret "WEB_API_KEY" "请输入网页控制台 API Key（WEB_API_KEY）"

        # TOTP 密钥：支持一键生成随机 Base32 密钥（验证器 App 手动录入即可绑定）
        echo "🔐 XIAOJU3_TOTP_SECRET（TOTP 动态密码密钥，Lv.3/Lv.4 授权用）"
        read -s -r -p "  输入 g 自动生成随机 Base32 密钥，或粘贴已有密钥（回车跳过）: " TOTP_INPUT
        echo ""
        if [ "$TOTP_INPUT" = "g" ] || [ "$TOTP_INPUT" = "G" ]; then
            TOTP_GENERATED=$(python3 -c 'import base64, secrets; print(base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("="))' 2>/dev/null)
            if [ -n "$TOTP_GENERATED" ]; then
                replace_env_value "XIAOJU3_TOTP_SECRET" "$TOTP_GENERATED"
                echo "✅ 已生成随机 Base32 密钥并写入 XIAOJU3_TOTP_SECRET（在验证器 App 中手动录入该密钥即可绑定）"
            else
                echo "⚠️ 密钥生成失败，已跳过（可稍后编辑 .env 手工填写）。"
            fi
        elif [ -n "$TOTP_INPUT" ]; then
            replace_env_value "XIAOJU3_TOTP_SECRET" "$TOTP_INPUT"
            echo "✅ 已写入 XIAOJU3_TOTP_SECRET"
        else
            echo "ℹ️ 已跳过 XIAOJU3_TOTP_SECRET（Lv.3/Lv.4 授权将不可用，可稍后补填）"
        fi

        prompt_secret "XIAOJU3_REGISTER_PASSWORD" "请输入 Lv.2 注册密码（/register 用）"
        prompt_plain "HA_URL" "请输入 Home Assistant 地址（HA_URL，例如 http://127.0.0.1:8123）"
        prompt_secret "HA_TOKEN" "请输入 Home Assistant 访问令牌（HA_TOKEN）"
        mark_done ".env 配置引导（交互填写）"
    fi
fi

# ===== [4/5] 完整性校验 =====
echo "🧾 [4/5] 完整性校验（checksums.sha256）..."

if [ -f "checksums.sha256" ]; then
    if sha256sum -c checksums.sha256 --quiet; then
        echo "✅ 完整性校验通过。"
    else
        echo "⚠️ 完整性校验失败：核心文件与清单哈希不一致（可能被篡改，或清单已过期）。"
        echo "   建议先运行 ./make_manifest.sh 重算清单，确认文件来源可信后再继续。"
        if [ "$NON_INTERACTIVE" -eq 1 ]; then
            fail_exit "完整性校验失败，非交互模式下拒绝继续安装。"
        fi
        read -r -p "是否了解风险并继续安装？(yes/no): " CHECKSUM_ANSWER
        if [ "$CHECKSUM_ANSWER" != "yes" ] && [ "$CHECKSUM_ANSWER" != "y" ]; then
            fail_exit "用户选择中止安装（完整性校验未通过）。"
        fi
        echo "⚠️ 已在风险告知后继续安装（仅本次）。"
    fi
    mark_done "完整性校验（checksums.sha256）"
else
    echo "ℹ️ 未发现 checksums.sha256，跳过完整性校验（可运行 ./make_manifest.sh 生成清单）。"
    mark_done "完整性校验（无清单，跳过）"
fi

# ===== [5/5] 启动与引导 =====
echo "🚀 [5/5] 启动小橘3号（主程序 + 控制台）..."

chmod +x start.sh start_dashboard.sh 2>/dev/null

# 控制台：start_dashboard.sh 自带后台化（nohup），直接调用即可
bash start_dashboard.sh > install_dashboard.log 2>&1 \
    || echo "⚠️ 控制台启动脚本执行异常，可稍后手动运行 ./start_dashboard.sh（不影响主程序）。"

# 主程序：start.sh 是前台守护循环，交给 nohup 后台运行，日志落 install_main.log
nohup bash start.sh > install_main.log 2>&1 &
sleep 2
echo "✅ 启动完成：主程序守护（日志 install_main.log）+ 控制台（日志 install_dashboard.log）"
mark_done "启动主程序与控制台"

# 功能 §10.2：可选自动发出 LV2 注册请求（仅本机 127.0.0.1 自调，失败不中断）
if [ -n "$REGISTER_PASSWORD" ]; then
    echo "📨 正在向本机发送 LV2 注册请求（/onebot 自调）..."
    sleep 3  # 等待服务就绪
    python3 - "$REGISTER_PASSWORD" <<'PYEOF'
import json
import sys
import urllib.request

password = sys.argv[1]
payload = json.dumps({
    "post_type": "message",
    "user_id": "installer",
    "raw_message": "/register " + password,
}).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:5002/onebot",
    data=payload,
    headers={"Content-Type": "application/json"},
)
try:
    urllib.request.urlopen(req, timeout=5)
    print("✅ 已自动发送 LV2 注册请求。")
except Exception as exc:  # 注册失败不影响安装
    print(f"⚠️ 注册请求发送失败（不影响安装，可稍后在对话中手动发送 /register）：{exc}")
PYEOF
fi

# ===== 安装完成引导文案 =====
echo ""
echo "=============================================="
echo "🎉 小橘3号安装完成！"
echo "=============================================="
echo "📖 访问地址："
echo "   • 网页控制台：http://127.0.0.1:5003/console"
echo "   • 内置聊天页：http://127.0.0.1:5002/（POST /chat 需 X-API-Key=WEB_API_KEY）"
echo ""
echo "📖 权限引导："
echo "   • LV2 注册：在对话中发送 /register <注册密码>（密码即 .env 的 XIAOJU3_REGISTER_PASSWORD）"
echo "   • LV3/LV4 授权需 TOTP/双因子，首次授权会看到类 Root 安全警告，请阅读风险后确认"
echo "     （Lv.3 用 /coder_auth <TOTP>；Lv.4 走双因子授权，TOTP 密钥见 .env 的 XIAOJU3_TOTP_SECRET）"
echo ""
echo "📖 常用命令："
echo "   • 重启全部：./restart_all.sh    彻底停止：./stop_all.sh"
echo "   • 清单重算：./make_manifest.sh  校验启动：./secure_start.sh"
exit 0
