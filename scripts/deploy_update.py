"""一键更新部署（代码侧）：检查 → 测试 → 安全扫描 → 提交 → 推送 → 触发云端。

用法：
    python scripts/deploy_update.py               # 检查+测试+提交+推送+触发
    python scripts/deploy_update.py --dry-run     # 只检查，不改任何东西
    python scripts/deploy_update.py --refresh     # 没有代码改动也触发一次云端抓取
    python scripts/deploy_update.py --skip-tests  # 跳过测试（不推荐）

规则：
- 绝不 git push --force。
- 发现敏感文件（credentials.json / data.full.json / output/）被加入暂存区，直接中止。
- 测试不通过，直接中止。
- 推送失败时改用 GitHub Contents API（不覆盖 data.json / index.html）。
"""

import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "scripts"))

from app.core.paths import CONFIG_DIR  # noqa: E402

TOKEN_ENV = ("GITHUB_TOKEN", "GH_TOKEN")
FORBIDDEN_IN_GIT = ("credentials.json", "deploy.json", "data.full.json", "data.prev.json",
                    "/output/", "\\output\\", ".env")


def log(msg):
    print(msg, flush=True)


def find_git():
    from shutil import which
    exe = which("git")
    if exe:
        return exe
    for path in (r"C:\Program Files\Git\bin\git.exe", r"C:\Program Files (x86)\Git\bin\git.exe"):
        if os.path.exists(path):
            return path
    return None


def run(cmd, check=True, cwd=None):
    r = subprocess.run(cmd, cwd=cwd or BASE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError("命令失败：%s\n%s" % (" ".join(cmd), (r.stderr or r.stdout)[-800:]))
    return r


def load_deploy_conf():
    path = os.path.join(CONFIG_DIR, "deploy.json")
    conf = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig") as f:
            conf = json.load(f)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or conf.get("token") or ""
    owner = conf.get("owner") or os.environ.get("GITHUB_OWNER") or ""
    repo = conf.get("repo") or os.environ.get("GITHUB_REPO") or ""
    return {"owner": owner, "repo": repo, "token": token}


def run_tests():
    log("· 运行自动化测试…")
    r = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], check=False)
    output = (r.stderr or "") + (r.stdout or "")
    tail = "\n".join([ln for ln in output.strip().splitlines() if ln.strip()][-6:])
    if r.returncode != 0:
        log("✗ 测试未通过，已中止部署：\n" + tail)
        return False
    log("✓ 测试通过")
    return True


def safety_scan(git):
    log("· 检查是否有敏感文件被提交…")
    run([git, "add", "-A"], check=False)
    staged = run([git, "diff", "--cached", "--name-only"], check=False).stdout
    bad = [ln for ln in staged.splitlines() if any(k in ln for k in FORBIDDEN_IN_GIT)]
    if bad:
        for ln in bad:
            run([git, "reset", "HEAD", ln], check=False)
        log("✗ 检测到敏感文件，已从暂存区移除：\n  - " + "\n  - ".join(bad))
        log("  这些文件必须在 .gitignore 里，不允许进入仓库。")
        return False
    # 顺便扫一下暂存内容里有没有明文密码
    diff = run([git, "diff", "--cached"], check=False).stdout
    for needle in ('"password": "', "ghp_", "cli_"):
        if needle in diff and needle == '"password": "':
            hits = [ln for ln in diff.splitlines() if needle in ln and '""' not in ln]
            if hits:
                log("✗ 暂存内容疑似包含明文密码，已中止部署。")
                return False
    log("✓ 敏感文件检查通过")
    return True


def commit_and_push(git, message, conf):
    status = run([git, "status", "--porcelain"]).stdout.strip()
    if not status:
        log("· 没有代码改动，不产生空提交")
        return "nochange"

    changed = run([git, "diff", "--cached", "--name-only"], check=False).stdout.strip()
    if not changed:
        log("· 已暂存内容为空（可能只是未跟踪文件被忽略），不提交")
        return "nochange"

    run([git, "commit", "-m", message], check=False)
    log("✓ 已提交：" + message)
    return "committed"


def push(git, conf):
    r = run([git, "push", "origin", "HEAD:main"], check=False)
    if r.returncode == 0:
        log("✓ 已推送到 main")
        return True
    log("· git 推送失败，改用 GitHub API 推送…")
    if not (conf["owner"] and conf["repo"] and conf["token"]):
        log("✗ 没有 owner/repo/token，无法兜底推送。请在 config/deploy.json 或环境变量里配置。")
        return False
    try:
        import deploy_github as dg
    except Exception as exc:
        log("✗ 无法加载部署脚本：%s" % exc)
        return False
    ok = dg.push_files_via_api(conf["owner"], conf["repo"], conf["token"])
    return ok


def trigger(conf):
    if not (conf["owner"] and conf["repo"] and conf["token"]):
        log("· 未配置 GitHub 凭证，跳过触发云端")
        return True
    try:
        import requests
    except ImportError:
        log("· 缺少 requests，跳过触发云端")
        return True
    url = "https://api.github.com/repos/%s/%s/actions/workflows/daily.yml/dispatches" % (conf["owner"], conf["repo"])
    headers = {"Authorization": "token " + conf["token"], "Accept": "application/vnd.github+json"}
    r = requests.post(url, data=json.dumps({"ref": "main"}), headers=headers, timeout=40)
    if r.status_code in (204, 201):
        log("✓ 已触发云端抓取（https://github.com/%s/%s/actions）" % (conf["owner"], conf["repo"]))
        return True
    log("✗ 触发失败 %s：%s" % (r.status_code, r.text[:120]))
    return False


def main():
    args = set(sys.argv[1:])
    dry = "--dry-run" in args
    skip_tests = "--skip-tests" in args
    refresh = "--refresh" in args

    conf = load_deploy_conf()
    log("=" * 60)
    log(" 一键更新部署 %s" % ("（预览模式，不做修改）" if dry else ""))
    log("=" * 60)

    git = find_git()
    if not git:
        log("✗ 未找到 Git。请安装 Git for Windows，或改用 首次部署.bat 里的 API 方式。")
        return 2
    if not os.path.isdir(os.path.join(BASE, ".git")):
        log("✗ 当前目录不是 git 仓库。首次请双击「首次部署.bat」。")
        return 2

    run([git, "fetch", "origin", "main"], check=False)
    if "--continue" not in args:
        conflicted = run([git, "diff", "--name-only", "--diff-filter=U"], check=False).stdout.strip()
        if conflicted:
            log("✗ 存在未解决的合并冲突，请先手动处理后重试：\n" + conflicted)
            return 2

    if not skip_tests and not run_tests():
        return 3

    ok = safety_scan(git)
    if not ok:
        return 4

    if dry:
        log("· [预览] 将提交以下文件：")
        staged = run([git, "diff", "--cached", "--name-only"], check=False).stdout
        for ln in staged.splitlines()[:40]:
            log("  " + ln)
        log("· [预览] 不会推送、不会触发云端。")
        return 0

    result = commit_and_push(git, "chore: V2.1 更新（自动提交）", conf)
    if result == "nochange" and not refresh:
        log("· 没有改动，也没有指定 --refresh，结束。")
        return 0
    if result == "committed":
        if not push(git, conf):
            log("✗ 推送失败，更新没有生效。请检查网络或凭证后重试。")
            return 5
    if not trigger(conf):
        return 6
    log("✓ 更新部署完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
