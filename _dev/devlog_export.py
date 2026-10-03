#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""devlog_export.py — 换对话框前跑一次：导出当日会话素材块。

用途：把 ZCode 会话库（db.sqlite）里"今天发生了什么"的元数据骨架导出成
markdown 片段，供 xiaoju3_data/开发流水账.md 的〔素材〕区使用。
（流水账格式与两分区说明见该文件头部。）

用法：
    python _dev/devlog_export.py [--date YYYY-MM-DD] [--db PATH]

纪律（写进行为，别绕过）：
    - 先拷 db.sqlite 副本再只读连接（绝不碰在线库与 -wal/-shm）
    - 只取本项目（git 仓库根）会话，含子代理
    - 只导出元数据骨架（会话/工具调用统计/commit 时间线），**不读 message 正文**
    - 输出到 stdout，由人粘贴进流水账素材区——脚本绝不直接改流水账文件
"""
import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime

DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".zcode", "cli", "db", "db.sqlite")
MS_DAY = 86_400_000


def project_root():
    """git 仓库根（脚本位于 _dev/ 也能正确定位）；非仓库则退回当前目录。"""
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else os.getcwd()


def day_bounds_ms(ymd):
    """本地日期 YYYY-MM-DD → [起, 止) epoch 毫秒。"""
    start = int(datetime.fromisoformat(ymd).timestamp() * 1000)
    return start, start + MS_DAY


def copy_db(src, dst):
    shutil.copy2(src, dst)
    return dst


def open_ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def sessions_for_day(con, project_dir, start_ms, end_ms):
    """当日有活动的本项目会话（含子代理），按开始时间升序。

    返回列：(id, slug, title, parent_id, time_created, time_updated)
    """
    return con.execute(
        "SELECT id, slug, title, parent_id, time_created, time_updated "
        "FROM session WHERE directory = ? AND time_created < ? AND time_updated >= ? "
        "ORDER BY time_created",
        (project_dir, end_ms, start_ms),
    ).fetchall()


def tool_stats(con, session_ids, start_ms, end_ms):
    """工具调用统计 [(tool_name, 次数)] 按次数降序；无会话/无记录返回 []。

    注意：tool_usage.started_at 按 epoch 毫秒假设——若真实库单位不符，
    统计为空属可接受降级（素材块缺工具节，不影响其余）。
    """
    if not session_ids:
        return []
    marks = ",".join("?" for _ in session_ids)
    return con.execute(
        f"SELECT tool_name, COUNT(*) AS n FROM tool_usage "
        f"WHERE session_id IN ({marks}) AND started_at >= ? AND started_at < ? "
        f"GROUP BY tool_name ORDER BY n DESC",
        (*session_ids, start_ms, end_ms),
    ).fetchall()


def git_commits(ymd, repo_root):
    """当日 commit 时间线 ['<hash> <时刻> <主题>', …]；非仓库返回 []。"""
    out = subprocess.run(
        ["git", "log", "--since", f"{ymd} 00:00", "--until", f"{ymd} 23:59:59",
         "--format=%h %ci %s"],
        capture_output=True, text=True, cwd=repo_root,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def render(ymd, sessions, stats, commits):
    """素材块 markdown。sessions 元组见 sessions_for_day；stats 见 tool_stats。"""
    lines = [f"### 〔素材〕{ymd}", ""]
    if sessions:
        lines.append("**会话**")
        for sid, slug, title, parent_id, tc, tu in sessions:
            kind = "子代理" if parent_id else "主对话"
            lines.append(f"- {kind} {slug}（{(title or '')[:40]}）")
    if stats:
        lines.append("")
        lines.append("**工具调用 TOP**")
        for name, n in stats[:8]:
            lines.append(f"- {name}: {n}")
    if commits:
        lines.append("")
        lines.append("**commit 时间线**")
        for c in commits:
            lines.append(f"- {c}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="导出当日会话素材块（开发流水账素材区用）")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                    help="YYYY-MM-DD，缺省今天")
    ap.add_argument("--db", default=DEFAULT_DB, help="db.sqlite 路径")
    args = ap.parse_args(argv)

    start_ms, end_ms = day_bounds_ms(args.date)
    tmp_db = copy_db(args.db, os.path.join(tempfile.gettempdir(),
                                           "devlog_export_copy.sqlite"))
    con = open_ro(tmp_db)
    try:
        root = project_root()
        project_dir = os.path.abspath(root)
        sessions = sessions_for_day(con, project_dir, start_ms, end_ms)
        stats = tool_stats(con, [s[0] for s in sessions], start_ms, end_ms)
    finally:
        con.close()
    commits = git_commits(args.date, root)

    print(render(args.date, sessions, stats, commits))
    return 0


if __name__ == "__main__":
    sys.exit(main())
