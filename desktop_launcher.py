# -*- coding: utf-8 -*-
"""小橘3号 · 离线桌面控制台壳（pywebview 原生窗口，desktop_launcher.py）。

用户口径：pywebview 离线桌面控制台——**绝对禁止加载任何外网 URL**。

【加载方案选型说明（任务给定的二选一，取方案 ①）】
  ①（本实现）webview 启动一个仅绑定 127.0.0.1 回环地址的内置线程服务
    （复用 xiaoju3_dashboard.app，端口默认随机 :0），窗口加载
    http://127.0.0.1:<port>/console。
    - 窗口本身离线打开：内置服务只听本机回环地址，不依赖、不访问外网，
      "轻量本地服务"正是任务许可的形态；
    - 保真度最高：index.html 引用的 /console/console.js 等绝对路径、
      /api/status 2s 轮询、/api/chat 聊天等既有路由原样复用——前端 fetch
      全部为相对路径（已核实 console.js），同源直达内置服务，零侵入
      （不碰 M3 正在维护的 console.js/index.html/desktop-pet.js）；
    - 相比之下方案 ②（改写 HTML 路径为相对路径后 file:// 加载）需要侵入
      M3 所有权文件，且相对 fetch('/api/...') 在 file:// 下无法工作，弃用。
  任务书中的 html=<本地 index.html 内容> 注入形态同样因此弃用：离线窗口
  无法解析页面里的 /console/console.js 等绝对路径引用，控制台会白屏。

【离线优先通信（不改任何既有链路，仅核实）】
  - 本地 Ollama 聊天 / 本地文件读取本就离线可用（brain 既有链路）；
  - 断网时 brain.smart_ask 返回 "❌ 大脑连接失败，请检查网络。..." 回复文案
    （brain.py 既有降级，前端气泡照常上屏、不白屏，已核实源码）；
  - /api/balance 请求失败回退 0.0 + 错误提示（xiaoju3_dashboard 既有口径）。

【关闭清理（防僵尸端口驻留）】
  webview.start() 阻塞至窗口关闭，返回后（finally 兜底）调用 Werkzeug
  make_server 的 shutdown() 终止内置服务线程、server_close() 释放端口；
  服务线程为 daemon，主进程异常退出时亦不悬挂。

【启动探测】
  拉起时若检测到 main.py 接入层（:5002）未运行，打印（并注入窗口标题）
  "主程序未启动，聊天功能受限" 提示——窗口仍可打开界面（状态/历史等
  仪表盘功能不受影响），QQ webhook 相关能力受限。

用法：
  python desktop_launcher.py                  # 内置服务端口随机
  python desktop_launcher.py --serve-port 5900  # 指定内置服务端口
"""
import argparse
import socket
import sys
import threading

from werkzeug.serving import make_server

from xiaoju3_dashboard import app   # 复用全部既有路由（/console、/api/*）

WINDOW_TITLE = "小橘3号 · 离线控制台"
DEFAULT_HOST = "127.0.0.1"           # 内置服务只听回环地址（离线红线）
# main.py 接入层固定端口（main.py app.run 口径），用于启动探测
MAIN_APP_PORT = 5002
MAIN_NOT_RUNNING_HINT = "⚠️ 主程序未启动，聊天功能受限（界面仍可打开）"
MISSING_WEBVIEW_HINT = (
    "未检测到 pywebview，无法打开离线桌面窗口。\n"
    "请先安装依赖后重试：pip install pywebview==6.2.1"
)


def parse_args(argv=None):
    """解析命令行参数：--serve-port <port> 指定内置服务端口（默认随机）。"""
    parser = argparse.ArgumentParser(
        description="小橘3号 · 离线桌面控制台（pywebview 壳）")
    parser.add_argument("--serve-port", type=int, default=None,
                        help="内置本地服务端口（缺省由系统随机分配）")
    return parser.parse_args(argv)


def start_local_server(port=None, host=DEFAULT_HOST):
    """启动仅绑定 host（默认 127.0.0.1 回环）的内置线程服务。

    port 为 None/0 时由系统随机分配可用端口（make_server 绑定完成后
    server.server_port 即真实端口，pywebview 据此拼 URL）；threaded=True
    支撑前端 2s 状态轮询与聊天的并发请求。服务线程为 daemon。

    返回 (server, thread)：server 含 server_port / shutdown() /
    server_close()；stop_local_server 消费同一对对象完成关闭清理。
    """
    server = make_server(host, port or 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever,
                              name="xiaoju3-console-local", daemon=True)
    thread.start()
    return server, thread


def stop_local_server(server, thread=None):
    """关闭清理：shutdown() 停 serve_forever 循环 → join 线程 →
    server_close() 释放端口（webview 窗口关闭后调用，防僵尸驻留）。

    注意 shutdown() 必须从 serve_forever 之外线程调用（本函数调用方为
    主线程/测试线程）；各步骤容错，保证清理流程走到释放端口为止。
    """
    try:
        server.shutdown()
    except Exception:
        pass
    if thread is not None:
        thread.join(timeout=5)
    try:
        server.server_close()
    except Exception:
        pass


def _is_main_running(port=MAIN_APP_PORT, timeout=1.0):
    """探测 main.py 接入层（:5002）是否在线。

    纯 socket 连接探测：不发 HTTP 请求，不触发对端路由副作用；连接成功
    即视为在线。main.py 未启动 / 端口未监听 / 超时一律返回 False。
    """
    try:
        with socket.create_connection((DEFAULT_HOST, port), timeout=timeout):
            return True
    except OSError:
        return False


def main(argv=None):
    """入口：缺 pywebview 中文提示退出；起内置服务 → 开窗口 → 关闭清理。

    返回退出码：0 正常（窗口关闭并清理完成）；1 环境不满足（缺 pywebview /
    端口不可用）。
    """
    try:
        import webview   # 延迟导入：缺库时清晰中文提示退出，不甩 traceback
    except Exception:
        print(MISSING_WEBVIEW_HINT, file=sys.stderr)
        return 1

    args = parse_args(argv)

    # 启动探测：main.py 未在线则提示"聊天功能受限"（窗口仍可打开界面）
    main_ok = _is_main_running()
    if not main_ok:
        print(MAIN_NOT_RUNNING_HINT)

    try:
        server, thread = start_local_server(args.serve_port)
    except OSError as e:
        print(f"内置本地服务启动失败（端口 {args.serve_port or '随机'}）: {e}",
              file=sys.stderr)
        return 1

    url = f"http://{DEFAULT_HOST}:{server.server_port}/console"
    window = webview.create_window(WINDOW_TITLE, url)

    def _on_loaded(*_):
        # 窗口内可见且非阻塞的提示：标题后缀（不用 alert，避免卡 GUI 线程）
        if not main_ok:
            try:
                window.evaluate_js(
                    "document.title += '（主程序未启动，聊天功能受限）'")
            except Exception:
                pass

    try:
        window.events.loaded += _on_loaded
    except Exception:
        pass   # 个别后端事件系统不可用时静默跳过（终端已有打印提示）

    try:
        webview.start()   # 阻塞至窗口关闭
    finally:
        # 关闭清理：窗口关闭（webview.start 返回）即终止内置服务线程
        stop_local_server(server, thread)
    return 0


if __name__ == "__main__":
    sys.exit(main())
