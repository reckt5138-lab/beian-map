"""运维工具：诊断报告、备份、清理、状态检查。

用法：
    python scripts/maintenance.py diagnose      # 生成 output/logs/diagnostic_report.txt
    python scripts/maintenance.py backup        # 备份关键文件到 output/backups/
    python scripts/maintenance.py clean         # 清理 __pycache__ / 临时文件 / 过期日志
    python scripts/maintenance.py status        # 打印当前项目状态摘要
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from app.core.config import load_config, scrub  # noqa: E402
from app.core.paths import (  # noqa: E402
    CONFIG_JSON, CREDENTIALS_JSON, DATA_JSON, FULL_JSON, INDEX_HTML, LOG_DIR, OUTPUT_DIR, BACKUP_DIR,
)

REPORT_PATH = os.path.join(LOG_DIR, "diagnostic_report.txt")


def _which(cmd):
    from shutil import which
    return which(cmd)


def _version(cmd, args=("--version",)):
    exe = _which(cmd)
    if not exe:
        return None
    try:
        r = subprocess.run([exe] + list(args), capture_output=True, text=True, timeout=20)
        return (r.stdout or r.stderr).strip().splitlines()[0]
    except Exception as exc:
        return "检查失败：%s" % exc


def _file_info(path, label):
    if not os.path.exists(path):
        return "%s：不存在（%s）" % (label, path)
    size = os.path.getsize(path)
    mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
    return "%s：存在，%.1f KB，修改于 %s" % (label, size / 1024, mtime)


def collect():
    lines = []
    lines.append("青鸾备案项目地图 V2.1 诊断报告")
    lines.append("生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("项目目录：%s" % BASE)
    lines.append("")
    lines.append("一、运行环境")
    lines.append("  Python：%s（%s）" % (sys.version.split()[0], sys.executable))
    lines.append("  Git：%s" % (_version("git") or "未安装或不在 PATH（deploy 脚本可用 API 兜底推送）"))
    lines.append("  GitHub CLI（gh）：%s" % (_version("gh") or "未安装（青鸾地图.bat（菜单 3） 会用 API 代替）"))
    lines.append("  Node：%s" % (_version("node") or "未安装（仅前端调试需要）"))
    lines.append("")

    lines.append("二、配置")
    cfg = {}
    try:
        cfg = load_config()
        lines.append("  config/config.json：%s" % ("可读取" if os.path.exists(CONFIG_JSON) else "不存在，使用默认值"))
        lines.append("  base_url：%s" % cfg.get("base_url"))
        lines.append("  publish：%s" % json.dumps(cfg.get("publish") or {}, ensure_ascii=False))
        lines.append("  飞书段是否启用：%s（V2.1 主流程已不使用）" % bool((cfg.get("feishu") or {}).get("enabled")))
        if not (cfg.get("feishu") or {}).get("enabled"):
            pass
    except Exception as exc:
        lines.append("  ✗ 配置读取失败：%s" % exc)

    cred_ok = False
    if os.path.exists(CREDENTIALS_JSON):
        try:
            with open(CREDENTIALS_JSON, "r", encoding="utf-8-sig") as f:
                cred = json.load(f)
            cred_ok = bool(cred.get("username")) and bool(cred.get("password"))
        except Exception:
            cred_ok = False
    env_ok = bool(os.environ.get("JUFA_USERNAME")) and bool(os.environ.get("JUFA_PASSWORD"))
    lines.append("  青鸾账号：%s（配置文件=%s，环境变量=%s）"
                 % ("已配置" if (cred_ok or env_ok) else "未配置", "是" if cred_ok else "否", "是" if env_ok else "否"))
    lines.append("  GitHub Token（环境变量）：%s" % ("已设置（不打印）" if os.environ.get("GITHUB_TOKEN") else "未设置"))
    lines.append("")

    lines.append("三、关键文件")
    lines.append("  " + _file_info(DATA_JSON, "公开数据 data.json"))
    lines.append("  " + _file_info(FULL_JSON, "完整数据 output/data.full.json"))
    lines.append("  " + _file_info(INDEX_HTML, "网页 index.html"))
    lines.append("  " + _file_info(os.path.join(BASE, "data", "coords.json"), "坐标表 data/coords.json"))
    lines.append("  " + _file_info(os.path.join(BASE, "app", "map_template.html"), "地图模板"))
    lines.append("")

    lines.append("四、git 状态")
    if os.path.isdir(os.path.join(BASE, ".git")):
        try:
            for args, label in ((["status", "--porcelain"], "工作区"),
                                (["log", "--oneline", "-3"], "最近提交"),
                                (["remote", "-v"], "远程地址")):
                r = subprocess.run(["git"] + args, cwd=BASE, capture_output=True, text=True, timeout=20)
                out = (r.stdout or r.stderr).strip() or "（空）"
                lines.append("  %s：%s" % (label, out.replace("\n", " | ")))
        except Exception as exc:
            lines.append("  ✗ git 检查失败：%s" % exc)
    else:
        lines.append("  不是 git 仓库（青鸾地图.bat（菜单 1） 会自动初始化）")
    lines.append("")

    lines.append("五、目录权限 / 空间")
    for d in (OUTPUT_DIR, LOG_DIR, BACKUP_DIR):
        if os.path.isdir(d):
            try:
                test = os.path.join(d, ".write_test")
                with open(test, "w", encoding="utf-8") as f:
                    f.write("ok")
                os.remove(test)
                lines.append("  %s：可写" % d.replace(BASE, "."))
            except Exception as exc:
                lines.append("  %s：不可写（%s）" % (d.replace(BASE, "."), exc))
        else:
            lines.append("  %s：不存在" % d.replace(BASE, "."))
    return lines


def write_diagnostic_report():
    os.makedirs(LOG_DIR, exist_ok=True)
    lines = collect()
    text = "\n".join(lines) + "\n"
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    return REPORT_PATH


def backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    targets = [DATA_JSON, INDEX_HTML, CONFIG_JSON,
               os.path.join(BASE, "data", "coords.json")]
    saved = []
    for path in targets:
        if os.path.exists(path):
            dst = os.path.join(BACKUP_DIR, "%s.%s.bak" % (os.path.basename(path), stamp))
            shutil.copy2(path, dst)
            saved.append(dst)
    print("已备份 %d 个文件到 output/backups/" % len(saved))
    for s in saved:
        print("  " + os.path.basename(s))
    return 0


def clean():
    removed = 0
    for root, dirs, files in os.walk(BASE):
        if ".git" in root or "backups" in root:
            continue
        for d in list(dirs):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                dirs.remove(d)
                removed += 1
    log_cut = datetime.now() - timedelta(days=30)
    for name in os.listdir(LOG_DIR) if os.path.isdir(LOG_DIR) else []:
        path = os.path.join(LOG_DIR, name)
        if os.path.isfile(path) and datetime.fromtimestamp(os.path.getmtime(path)) < log_cut:
            os.remove(path)
            removed += 1
    print("清理完成：删除 %d 项（__pycache__ / 30 天前日志）" % removed)
    return 0


def status():
    try:
        cfg = load_config()
    except Exception as exc:
        print("配置读取失败：%s" % exc)
        cfg = {}
    print("项目：%s" % BASE)
    print("配置：%s" % json.dumps(scrub(cfg.get("publish") or {}), ensure_ascii=False))
    if os.path.exists(DATA_JSON):
        with open(DATA_JSON, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
        print("公开数据：%s 条 / %s 列，更新于 %s，脱敏=%s"
              % (d.get("count"), d.get("columns"), d.get("updated"), d.get("redacted")))
    else:
        print("公开数据：不存在")
    if os.path.exists(INDEX_HTML):
        print("网页：%s（%.1f KB）" % (INDEX_HTML, os.path.getsize(INDEX_HTML) / 1024))
    else:
        print("网页：不存在")
    return 0


def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "status").lower()
    if cmd == "diagnose":
        path = write_diagnostic_report()
        print("诊断报告已生成：" + path)
        with open(path, "r", encoding="utf-8") as f:
            print(f.read())
        return 0
    if cmd == "backup":
        return backup()
    if cmd == "clean":
        return clean()
    if cmd == "status":
        return status()
    print("未知命令：%s（可用：diagnose / backup / clean / status）" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main())
