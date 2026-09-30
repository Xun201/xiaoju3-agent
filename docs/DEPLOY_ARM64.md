# 小橘3号 · 香橙派（ARM64 / Python 3.8）部署指南

> 适用于 `release/arm64-py38` 分支。目标硬件：Orange Pi 3B（RK3566，ARM64，4GB 内存以上），Ubuntu 20.04 / 22.04 ARM64，系统自带 Python 3.8（**无需升级系统 Python**）。

## 1. 安装步骤

### 1.1 拉取代码

```bash
sudo apt update && sudo apt install -y git python3-venv python3-pip
git clone -b release/arm64-py38 https://github.com/Xun201/xiaoju3-agent.git
cd xiaoju3-agent
# 若仓库已克隆过，改用：git pull
```

### 1.2 一键安装（推荐）

```bash
bash install.sh
```

安装器会自动完成：

1. **环境自检**：python3 版本（3.8 即可）、git/docker（可选，缺失降级提示）；
2. **依赖安装**：检测到 Python 3.8 → 自动按 `requirements-py38.txt` 安装降级组合（playwright 1.48.0、Flask 3.0.3、requests 2.32.3、psutil 7.2.2），**不会动系统 Python**；随后安装 Chromium 内核（ARM64 构建约 150–250MB，首次较慢；失败自动切国内镜像 `npmmirror` 重试一次，仍失败不影响安装，/gen_log 会优雅降级）；
3. **配置引导**：从 `.env.example` 生成 `.env`，交互式填入 `DEEPSEEK_API_KEY`、`WEB_API_KEY`、`XIAOJU3_TOTP_SECRET`（可输 `g` 自动生成随机密钥）、`XIAOJU3_REGISTER_PASSWORD`、`HA_URL`/`HA_TOKEN`（输入不回显；`--non-interactive` 模式只生成模板待手工填写）；
4. **完整性校验**：`checksums.sha256` 校验通过才继续；
5. **启动**：主程序守护（`start.sh`，异常 2 秒自动拉起）+ 控制台（:5003）。

### 1.3 手动安装（等价于安装器行为）

```bash
python3 -m venv .venv && . .venv/bin/activate
python -m pip install -r requirements-py38.txt
python -m playwright install chromium
cp .env.example .env   # 手工填入密钥，.env 不入仓库
python main.py         # 或 bash start.sh 守护运行
```

## 2. 验证

```bash
curl http://127.0.0.1:5002/                  # 主程序内置页 → 200
curl http://127.0.0.1:5003/api/status        # 监控接口（psutil 实时数据）
curl http://127.0.0.1:5003/console           # 控制台（含桌宠，形象图 /assets/DSniang1.jpg）
python -m unittest discover                  # 全量单元测试（香橙派上同样应全绿）
```

## 3. 注意事项

- **不要升级系统 Python**：依赖降级组合（playwright 1.48.0 / Flask 3.0.3 / requests 2.32.3）已覆盖 3.8，升级系统 Python 反而可能破坏 apt 生态。
- **本地模型不在香橙派上跑**：本项目按"本地优先决策"设计，Ollama + Qwen2.5 7B 部署在算力更强的机器上（如 RTX 4060 笔记本），香橙派只负责常驻服务；`.env` 的 `LOCAL_URL` 填该机器地址（仅存本地，不入仓库）。
- **密钥只在本地**：`DEEPSEEK_API_KEY`、`HA_TOKEN` 等一律写入设备上的 `.env`（已被 `.gitignore` 与 `push.sh` 四道扫描拦截）；从旧设备迁移时用 `migration.export_bundle()` 打包记忆/身份，密钥按包内 `MANIFEST.txt` 清单手工核对迁移。
- **TF 卡与日志**：系统跑在 16GB TF 卡上时建议定期查看 `logs/`、`install_main.log` 等体积；`heartbeat` 默认 60 秒轮询，快照无变化不耗资源。
- **串口调试**（系统烧录/引导排障用）：115200 波特率，8 数据位，1 停止位，无校验无流控；40Pin 排针 8 脚(TX)→USB-TTL RXD、10 脚(RX)→USB-TTL TXD、6 脚(GND)→GND。烧录镜像用 balenaEtcher。
- **端口**：5002（主程序 QQ/网页入口）、5003（控制台）、5001（历史预留）；`stop_all.sh` 会统一释放并按密码确认。
- **QQ 接入**：需自行部署 NapCat 容器（`docker` 可选依赖）；webhook 指向 `http://<香橙派内网地址>:5002/onebot`（内网地址自行填写，本仓库不含任何 IP）。
- **权限初始化**：`.env` 配好 `XIAOJU3_TOTP_SECRET` 与 `XIAOJU3_REGISTER_PASSWORD` 后，对话中 `/register <密码>` 升 Lv.2、`/coder_auth <TOTP>` 升 Lv.3、`/lv4_auth` 双因子升 Lv.4（首次见类 Root 安全警告）。
