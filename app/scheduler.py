r"""常驻调度器：按点自动跑 app/crawler.py，跑完子进程自动退出，调度器继续等下一次。

用法（一般由根目录 定时任务启动.bat 启动，不需要手敲）：
    python app\scheduler.py                  # 按 config.schedule 的设定常驻
    python app\scheduler.py --time 02:30     # 每天 02:30
    python app\scheduler.py --every 6        # 每 6 小时
    python app\scheduler.py --run-now        # 启动先跑一次，再按计划等
    python app\scheduler.py --once           # 只跑一次就退出（测试用）
    python app\scheduler.py --status         # 只看下次运行时间，不跑
"""

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR) if os.path.basename(SCRIPT_DIR).lower() == "app" else SCRIPT_DIR
CONFIG_DIR = os.path.join(BASE_DIR, "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
LEGACY_CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
CRAWLER = os.path.join(SCRIPT_DIR, "crawler.py")
LOCK_PORT = 51877  # 单实例检测：重复启动会直接退出


def active_config_path():
    if os.path.isfile(CONFIG_PATH):
        return CONFIG_PATH
    if os.path.isfile(LEGACY_CONFIG_PATH):
        return LEGACY_CONFIG_PATH
    return CONFIG_PATH


def load_schedule():
    defaults = {"enabled": True, "mode": "daily", "time": "02:00", "interval_hours": 24, "run_on_start": False, "save_excel": False}
    path = active_config_path()
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
        block = cfg.get("schedule") or {}
    except Exception:
        block = {}
    merged = dict(defaults)
    merged.update({k: v for k, v in block.items() if v is not None})
    return merged


def load_map_cfg():
    defaults = {"enabled": False, "port": 8787, "snapshot": True}
    try:
        with open(active_config_path(), "r", encoding="utf-8-sig") as f:
            block = (json.load(f).get("map") or {})
    except Exception:
        block = {}
    merged = dict(defaults)
    merged.update({k: v for k, v in block.items() if v is not None})
    return merged


def start_map_server(port):
    """顺手把地图服务拉起来：手机打开 http://本机IP:端口/ 就能看飞书表。"""
    try:
        import web_server
    except Exception:
        logging.exception("地图服务模块加载失败（app/web_server.py）")
        return None
    try:
        httpd = web_server.serve(host="0.0.0.0", port=port, lan=True, blocking=False)
        logging.info("地图服务已在后台运行（端口 %d）", port)
        return httpd
    except OSError as exc:
        logging.warning("地图服务端口 %d 启动失败（可能已被占用）：%s", port, exc)
    except Exception:
        logging.exception("地图服务启动失败")
    return None


BUILD_MAP = os.path.join(SCRIPT_DIR, "build_map_html.py")


def refresh_snapshot():
    """把最新飞书表内容写回 备案项目地图.html（手机打开这个文件就有数据）。"""
    try:
        p = subprocess.run([sys.executable, BUILD_MAP], cwd=BASE_DIR, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=180)
        msg = (p.stdout or p.stderr or "").strip().splitlines()
        if p.returncode == 0 and msg:
            logging.info(msg[-1])
            return True
        logging.warning("刷新地图快照失败 rc=%s：%s", p.returncode, (p.stderr or "").strip()[:300])
    except Exception:
        logging.exception("刷新地图快照失败")
    return False


def output_dir():
    try:
        with open(active_config_path(), "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
        d = (cfg.get("export") or {}).get("output_dir") or "output"
    except Exception:
        d = "output"
    if not os.path.isabs(d):
        d = os.path.join(BASE_DIR, d)
    return d


def setup_logging(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    log_dir = os.path.join(out_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "scheduler_%s.log" % datetime.now().strftime("%Y%m%d"))
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    return log_path


def already_running():
    try:
        s = socket.create_connection(("127.0.0.1", LOCK_PORT), timeout=1)
        s.close()
        return True
    except Exception:
        return False


def take_lock():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", LOCK_PORT))
        srv.listen(1)
        return srv
    except Exception:
        return None


def parse_hhmm(text):
    try:
        hh, mm = str(text).split(":")
        return int(hh), int(mm)
    except Exception:
        return 2, 0


def next_daily(hh, mm, after=None):
    now = after or datetime.now()
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def run_task(save_excel=False, snapshot=True):
    """跑一次导出，子进程结束即释放；返回退出码与耗时。

    定时任务默认不落本地 Excel（--no-excel），只覆盖飞书在线表格；
    需要留档时把 config 的 schedule.save_excel 设为 true。
    导出成功后把飞书表内容写回 备案项目地图.html（内置快照），手机打开即最新。
    """
    started = time.time()
    cmd = [sys.executable, CRAWLER]
    if not save_excel:
        cmd.append("--no-excel")
    logging.info("---------- 开始导出：%s（%s） ----------",
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "保存 Excel" if save_excel else "仅飞书，不保存 Excel")
    try:
        proc = subprocess.run(
            cmd,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=3600,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        rc = proc.returncode
        tail = (proc.stdout or "").strip().splitlines()
        for line in tail[-12:]:
            logging.info("  %s", line)
    except subprocess.TimeoutExpired:
        rc = 9
        logging.error("导出超时（>60 分钟），已强制结束")
    except Exception:
        rc = 1
        logging.exception("启动导出进程失败")
    cost = time.time() - started
    if rc == 0:
        logging.info("---------- 导出成功，耗时 %.1fs ----------", cost)
        if snapshot:
            refresh_snapshot()
        logging.info("---------- 等待下次 ----------")
    else:
        logging.error("---------- 导出失败 rc=%s，耗时 %.1fs ----------", rc, cost)
    return rc


def plan_line(mode, hh, mm, interval_hours):
    if mode == "interval":
        return "每 %.1f 小时一次" % float(interval_hours)
    return "每天 %02d:%02d" % (hh, mm)


def main():
    parser = argparse.ArgumentParser(description="青鸾导出常驻调度器")
    parser.add_argument("--time", default="", help="每天几点跑，如 02:30")
    parser.add_argument("--every", type=float, default=0, help="每隔几小时跑一次，如 6")
    parser.add_argument("--run-now", action="store_true", help="启动后先立刻跑一次")
    parser.add_argument("--save-excel", action="store_true", help="定时跑也保存本地 Excel（默认不保存，只更新飞书）")
    parser.add_argument("--map-port", type=int, default=0, help="地图服务端口，默认读 config.map.port")
    parser.add_argument("--no-map", action="store_true", help="不启动地图服务（默认就不启动，除非 config.map.enabled=true）")
    parser.add_argument("--no-snapshot", action="store_true", help="导出后不刷新 备案项目地图.html 的内置快照")
    parser.add_argument("--once", action="store_true", help="只跑一次然后退出（测试用）")
    parser.add_argument("--status", action="store_true", help="只打印计划，不跑")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    cfg = load_schedule()
    mode = "interval" if (args.every or str(cfg.get("mode", "daily")).lower() == "interval") else "daily"
    interval_hours = float(args.every or cfg.get("interval_hours") or 24)
    hh, mm = parse_hhmm(args.time or cfg.get("time") or "02:00")
    save_excel = bool(cfg.get("save_excel")) or bool(args.save_excel)

    out_dir = output_dir()
    log_path = setup_logging(out_dir)
    logging.info("调度器启动，日志：%s", log_path)
    logging.info("计划：%s（时区本地）；本地 Excel：%s", plan_line(mode, hh, mm, interval_hours),
                 "保存" if save_excel else "不保存（只更新飞书）")

    map_cfg = load_map_cfg()
    map_port = args.map_port or int(map_cfg.get("port") or 8787)
    snapshot = bool(map_cfg.get("snapshot", True)) and not args.no_snapshot

    if args.status:
        nxt = datetime.now() + timedelta(hours=interval_hours) if mode == "interval" else next_daily(hh, mm)
        logging.info("下次运行：%s", nxt.strftime("%Y-%m-%d %H:%M"))
        return 0

    if args.once:
        return run_task(save_excel, snapshot)

    lock = take_lock()
    if lock is None:
        logging.error("已有调度器在运行（端口 %d 被占用），本次退出", LOCK_PORT)
        return 2

    if not args.no_map and map_cfg.get("enabled"):
        start_map_server(map_port)

    if args.run_now or cfg.get("run_on_start"):
        run_task(save_excel, snapshot)

    anchor = datetime.now()
    while True:
        if mode == "interval":
            nxt = anchor + timedelta(hours=interval_hours)
        else:
            nxt = next_daily(hh, mm)
        logging.info("下次运行：%s", nxt.strftime("%Y-%m-%d %H:%M"))
        while True:
            left = (nxt - datetime.now()).total_seconds()
            if left <= 0:
                break
            time.sleep(min(30, left))
        run_task(save_excel, snapshot)
        anchor = datetime.now()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logging.info("收到 Ctrl+C，调度器退出")
        sys.exit(0)
