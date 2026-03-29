"""Clef snapshot — 备份 score.abc + 写入步骤日志（一条命令完成两件事）。"""
import argparse
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _next_version(history_dir: str) -> int:
    """扫描 history/score_v*.abc 获取下一版本号。"""
    if not os.path.isdir(history_dir):
        return 1
    max_ver = 0
    for fname in os.listdir(history_dir):
        m = re.match(r"score_v(\d+)", fname)
        if m:
            max_ver = max(max_ver, int(m.group(1)))
    return max_ver + 1


def _task_name(workdir: str) -> str:
    """从 plan.json 读取 title 作为任务名，不存在则用 untitled。"""
    plan_path = os.path.join(workdir, "plan.json")
    if os.path.isfile(plan_path):
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                plan = json.load(f)
            return plan.get("title", "untitled")
        except (json.JSONDecodeError, OSError):
            pass
    return "untitled"


def _log_dir(workdir: str) -> str:
    """获取或创建当日日志目录。"""
    name = _task_name(workdir)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
    dir_name = f"{name}_{timestamp}"
    log_base = os.path.join(workdir, "log", dir_name)
    os.makedirs(log_base, exist_ok=True)
    return log_base


def snapshot(step: str, status: str = "成功", output: str = "", note: str = "", workdir: str = ".clef-work") -> int:
    """备份 score.abc + 写入步骤日志。"""
    # 1. 版本备份
    score_path = os.path.join(workdir, "score.abc")
    history_dir = os.path.join(workdir, "history")
    version = 0
    if os.path.isfile(score_path):
        os.makedirs(history_dir, exist_ok=True)
        version = _next_version(history_dir)
        dest = os.path.join(history_dir, f"score_v{version}.abc")
        shutil.copy2(score_path, dest)
        print(f"Backup: score.abc -> history/score_v{version}.abc")

    # 2. 写入步骤日志
    log_base = _log_dir(workdir)
    log_path = os.path.join(log_base, f"step_{step}.md")

    title = note if note else f"Step {step}"
    log_content = f"## Step {step}: {title}\n"
    log_content += f"- 状态: {status}\n"
    if output:
        log_content += f"- 输出: {output}"
        if version > 0:
            log_content += f" (score_v{version}.abc)"
        log_content += "\n"
    log_content += f"- 问题: {'无' if status != '失败' else '见 review/validation 报告'}\n"

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(log_content)
    print(f"Log: {log_path}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="snapshot",
        description="备份 score.abc + 写入步骤日志",
    )
    parser.add_argument("--step", required=True, help="步骤编号 (如 2a)")
    parser.add_argument("--status", default="成功", choices=["成功", "有警告", "失败"])
    parser.add_argument("--output", default="", help="输出文件名")
    parser.add_argument("--note", default="", help="补充说明")
    parser.add_argument("--workdir", default=".clef-work", help="工作目录")
    args = parser.parse_args()
    return snapshot(args.step, args.status, args.output, args.note, args.workdir)


if __name__ == "__main__":
    exit(main())
