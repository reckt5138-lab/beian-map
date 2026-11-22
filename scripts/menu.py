"""统一菜单：青鸾地图.bat 调这里，只做菜单与调度，不写业务逻辑。

各菜单项分别调用 scripts/ 下对应的实现（或 app.main 的子命令），
这样「一个入口、多个实现」——BAT 只有一行，业务仍在各自模块里。
"""

import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MENU = """
╔══════════════════════════════════════════════╗
║        青鸾备案项目地图 V3.0                 ║
╠══════════════════════════════════════════════╣
║  1  首次配置 / 部署                          ║
║  2  一键更新代码并部署                       ║
║  3  手动刷新云端数据                         ║
║  4  本地抓取（只写完整 JSON）                ║
║  5  本地预览地图（HTTP 服务）                ║
║  6  项目诊断                                 ║
║  0  退出                                     ║
╚══════════════════════════════════════════════╝
"""

ACTIONS = {
    "1": ("首次配置 / 部署", ["scripts/first_setup.py"]),
    "2": ("一键更新代码并部署", ["scripts/deploy_update.py"]),
    "3": ("手动刷新云端数据", ["scripts/refresh.py"]),
    "4": ("本地抓取（只写完整 JSON）", ["-m", "app.main", "crawl"]),
    "5": ("本地预览地图（HTTP 服务）", ["scripts/local_server.py"]),
    "6": ("项目诊断", ["-m", "app.main", "diagnose"]),
}


def python_exe():
    """优先用项目虚拟环境里的解释器；没有就用当前解释器。"""
    for rel in (os.path.join(".venv", "Scripts", "python.exe"),
                os.path.join("venv", "Scripts", "python.exe")):
        p = os.path.join(BASE, rel)
        if os.path.isfile(p):
            return p
    return sys.executable


def run(args):
    cmd = [python_exe()] + args
    print("\n>>> 运行：" + " ".join(cmd) + "\n")
    try:
        return subprocess.call(cmd, cwd=BASE)
    except KeyboardInterrupt:
        print("\n已取消。")
        return 130
    except FileNotFoundError:
        print("✗ 找不到 Python。请先安装 Python 3.12+ 并勾选加入 PATH。")
        return 1


def main():
    while True:
        print(MENU)
        try:
            choice = input("请输入编号后回车：").strip()
        except EOFError:                     # 被管道/脚本调用时没有交互输入
            print("\n没有检测到交互输入，已退出。请在窗口中双击「青鸾地图.bat」使用。")
            return 0
        if choice in ("0", "q", "Q", ""):
            print("已退出。")
            return 0
        if choice not in ACTIONS:
            print("✗ 无效编号，请输入 0-6。")
            continue
        name, args = ACTIONS[choice]
        print("\n== %s ==" % name)
        code = run(args)
        print("\n完成，退出码 %d。" % code)
        if code != 0:
            print("（失败时请看上方输出，或选 6 做项目诊断）")
        try:
            input("\n按回车返回菜单...")
        except EOFError:
            return code


if __name__ == "__main__":
    sys.exit(main())
