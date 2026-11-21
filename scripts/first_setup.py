"""首次部署：环境检查 → 虚拟环境 → 依赖 → 配置 → 账号 → 登录验证 → GitHub 部署。

用法（一般由根目录「首次部署.bat」调用）：
    python scripts/first_setup.py            # 完整流程
    python scripts/first_setup.py --check    # 只做环境检查，不安装、不部署

不做的事：
- 不把账号密码写进 .bat 或普通配置文件以外的公开文件（只写 config/credentials.json，且被 .gitignore 挡住）
- 不覆盖已存在的 config/config.json（只提示差异）
- 仓库已存在时不重建，不强制推送
"""

import json
import os
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

PID = sys.executable


def log(msg):
    print(msg, flush=True)


def step(n, text):
    log("\n[%d] %s" % (n, text))


def check_python():
    v = sys.version_info
    if v < (3, 9):
        log("✗ Python 版本过低：%s，需要 3.9+（推荐 3.12）" % sys.version.split()[0])
        return False
    log("✓ Python %s（%s）" % (sys.version.split()[0], PID))
    return True


def check_network():
    try:
        import urllib.request
        urllib.request.urlopen("https://api.github.com/zen", timeout=10)
        log("✓ 网络可用（能访问 api.github.com）")
        return True
    except Exception as exc:
        log("· 无法访问 GitHub API（%s）。云端部署会失败，但本地抓取/看图仍可用。" % exc)
        return False


def ensure_venv():
    venv = os.path.join(BASE, ".venv")
    venv_py = os.path.join(venv, "Scripts", "python.exe")
    if os.path.exists(venv_py):
        log("✓ 已存在虚拟环境 .venv")
        return venv_py
    log("· 创建虚拟环境 .venv …（约 30 秒）")
    r = subprocess.run([PID, "-m", "venv", venv], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(venv_py):
        log("· 创建失败（%s），改用系统 Python 继续" % (r.stderr or "")[:300])
        return PID
    log("✓ 虚拟环境已创建")
    return venv_py


def install_deps(py):
    log("· 安装依赖（requests / openpyxl / pynacl）…")
    r = subprocess.run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"], capture_output=True, text=True)
    r = subprocess.run([py, "-m", "pip", "install", "-q", "-r",
                        os.path.join(BASE, "requirements.txt")],
                       capture_output=True, text=True, cwd=BASE)
    if r.returncode != 0:
        log("✗ 依赖安装失败：\n" + ((r.stderr or r.stdout)[-600:]))
        return False
    log("✓ 依赖安装完成")
    return True


def ensure_config():
    cfg = os.path.join(BASE, "config", "config.json")
    example = os.path.join(BASE, "config", "config.example.json")
    if os.path.exists(cfg):
        log("✓ 已存在 config/config.json（不会覆盖）")
    else:
        shutil.copy2(example, cfg)
        log("✓ 已从示例创建 config/config.json")
    return cfg


def ensure_credentials():
    path = os.path.join(BASE, "config", "credentials.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if data.get("username") and data.get("password"):
                log("✓ 已存在青鸾账号配置（不会覆盖）")
                return True
        except Exception:
            pass

    log("· 需要你的青鸾账号（只保存在 config/credentials.json，该文件已被 .gitignore 排除）")
    username = input("  青鸾账号：").strip()
    import getpass
    password = getpass.getpass("  青鸾密码（输入不回显）：").strip()
    if not username or not password:
        log("✗ 账号或密码为空，稍后可重新运行本脚本补齐")
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"username": username, "password": password}, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    log("✓ 账号已保存到 config/credentials.json")
    return True


def verify_login(py):
    log("· 验证青鸾登录…（只做一次登录请求，不抓全量）")
    r = subprocess.run([py, os.path.join(BASE, "app", "crawler.py"), "--verify"],
                       cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0:
        log("✗ 登录验证失败（退出码 %s）：\n%s" % (r.returncode, out[-500:]))
        log("  常见原因：账号密码错、青鸾站点改版、公司网络需要代理")
        return False
    log("✓ 登录验证通过")
    if out:
        log("  输出：" + out.splitlines()[-1][:200])
    return True


def write_python_path(py):
    with open(os.path.join(BASE, "python_path.txt"), "w", encoding="utf-8") as f:
        f.write(py)
    log("✓ 已写入 python_path.txt（后续 bat 都会用这个解释器）")


def check_git():
    from shutil import which
    git = which("git")
    if not git:
        for p in (r"C:\Program Files\Git\bin\git.exe", r"C:\Program Files (x86)\Git\bin\git.exe"):
            if os.path.exists(p):
                git = p
                os.environ["Path"] = os.environ.get("Path", "") + ";" + os.path.dirname(p)
                break
    log("✓ Git：%s" % (git or "未找到（会用 GitHub API 推送）"))
    return git


def run_deploy(py, git):
    log("\n接下来要把项目放到 GitHub（云端每天自动抓）。需要三样东西：")
    log("  1) GitHub 用户名（例：reckt5138-lab）")
    log("  2) 仓库名（例：beian-map，不存在会自动创建）")
    log("  3) GitHub Token（classic，勾 repo + workflow）")
    owner = input("  GitHub 用户名：").strip()
    repo = input("  仓库名：").strip() or "beian-map"
    log("  Token 生成：https://github.com/settings/tokens → Tokens (classic) → 勾 repo + workflow")
    token = input("  粘贴 Token：").strip()
    if not owner or not token:
        log("· 未填完整，跳过云端部署。之后可双击「首次部署.bat」重跑，只补这一步。")
        return 0
    cmd = [py, os.path.join(BASE, "scripts", "deploy_github.py"),
           "--owner", owner, "--repo", repo, "--token", token]
    log("\n· 开始云端部署（建仓库 / 写 Secrets / 开 Pages / 触发首次运行）…")
    r = subprocess.run(cmd, cwd=BASE)
    if r.returncode != 0:
        log("✗ 云端部署失败，退出码 %s。可对照 docs/08_故障排查.md" % r.returncode)
        return r.returncode
    log("\n✓ 首次部署完成")
    log("  网页：https://%s.github.io/%s/" % (owner, repo))
    return 0


def main():
    log("=" * 62)
    log(" 青鸾备案项目地图 V2.1 —— 首次部署")
    log("=" * 62)
    if not check_python():
        return 2

    step(1, "检查环境")
    check_network()
    check_git()

    if "--check" in sys.argv:
        log("\n· 仅检查模式，结束。")
        return 0

    step(2, "准备虚拟环境与依赖")
    py = ensure_venv()
    if not install_deps(py):
        return 3
    write_python_path(py)

    step(3, "准备配置")
    ensure_config()

    step(4, "青鸾账号")
    if not ensure_credentials():
        log("\n账号没配好，先停在本地。修好后重新双击「首次部署.bat」。")
        return 4

    step(5, "验证登录")
    if not verify_login(py):
        log("\n登录验证失败，已停止（不会继续部署）。")
        return 5

    step(6, "部署到 GitHub")
    code = run_deploy(py, check_git())
    if code == 0:
        log("\n后续日常操作：")
        log("  手动刷新数据 → 双击「手动刷新数据.bat」")
        log("  本地看地图   → 双击「打开地图.bat」")
        log("  改代码后上线 → 双击「一键更新部署.bat」")
        log("  检查问题     → 双击「诊断项目.bat」")
    return code


if __name__ == "__main__":
    sys.exit(main())
