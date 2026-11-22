"""手动刷新数据：触发云端 daily.yml 并等待结果（不需要改代码）。

用法：
    python scripts/refresh.py            # 触发并等待（最多 8 分钟）
    python scripts/refresh.py --no-wait  # 只触发，不等待

优先使用 gh CLI（如已登录），否则用 GitHub API（需要 GITHUB_TOKEN / config/deploy.json）。
"""

import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from app.core.paths import CONFIG_DIR  # noqa: E402


def load_conf():
    path = os.path.join(CONFIG_DIR, "deploy.json")
    conf = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig") as f:
            conf = json.load(f)
    return {
        "owner": conf.get("owner") or os.environ.get("GITHUB_OWNER") or "",
        "repo": conf.get("repo") or os.environ.get("GITHUB_REPO") or "",
        "token": conf.get("token") or os.environ.get("GITHUB_TOKEN") or "",
    }


def have_gh():
    from shutil import which
    return which("gh") is not None


def gh_trigger(conf):
    r = subprocess.run(["gh", "workflow", "run", "daily.yml", "--ref", "main"],
                       cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def _session():
    """默认直连的 requests 会话，避开「系统代理没开 → ProxyError」。"""
    import requests
    s = requests.Session()
    try:
        sys.path.insert(0, BASE)
        from app.core.network import use_proxy
        s.trust_env = use_proxy()
    except Exception:
        s.trust_env = False
    return s


def api(conf, method, path, payload=None):
    url = "https://api.github.com/repos/%s/%s%s" % (conf["owner"], conf["repo"], path)
    headers = {"Authorization": "token " + conf["token"], "Accept": "application/vnd.github+json"}
    r = _session().request(method, url, data=json.dumps(payload) if payload else None,
                           headers=headers, timeout=40)
    return r


def latest_run(conf):
    url = "https://api.github.com/repos/%s/%s/actions/workflows/daily.yml/runs?per_page=1" % (conf["owner"], conf["repo"])
    headers = {"Authorization": "token " + conf["token"], "Accept": "application/vnd.github+json"}
    r = _session().get(url, headers=headers, timeout=40)
    if r.status_code != 200:
        return None
    runs = (r.json() or {}).get("workflow_runs") or []
    return runs[0] if runs else None


def main():
    wait = "--no-wait" not in sys.argv
    conf = load_conf()
    if not conf["owner"] or not conf["repo"]:
        print("✗ 还没配置仓库。请先双击「青鸾地图.bat（菜单 1）」，或在 config/deploy.json 填 owner / repo。")
        return 2

    print("=" * 60)
    print(" 手动刷新数据：%s/%s" % (conf["owner"], conf["repo"]))
    print("=" * 60)

    triggered = False
    if have_gh():
        ok, msg = gh_trigger(conf)
        if ok:
            print("✓ 已通过 gh 触发 workflow")
            triggered = True
        else:
            print("· gh 触发失败（%s），改用 API" % (msg[:120] or "未知原因"))
    if not triggered:
        if not conf["token"]:
            print("✗ 缺少 GitHub Token：设置环境变量 GITHUB_TOKEN，或在 config/deploy.json 里填 token")
            return 2
        r = api(conf, "POST", "/actions/workflows/daily.yml/dispatches", {"ref": "main"})
        if r.status_code not in (201, 204):
            print("✗ 触发失败 %s：%s" % (r.status_code, r.text[:160]))
            return 3
        print("✓ 已通过 API 触发 workflow")

    if not wait:
        print("· 已触发，不等待。查看：https://github.com/%s/%s/actions" % (conf["owner"], conf["repo"]))
        return 0

    print("· 等待云端执行（最多 8 分钟）…")
    for _ in range(48):
        time.sleep(10)
        run = latest_run(conf)
        if not run:
            continue
        status, conclusion = run.get("status"), run.get("conclusion")
        print("  状态：%s%s" % (status, " / " + conclusion if conclusion else ""))
        if status == "completed":
            url = run.get("html_url")
            if conclusion == "success":
                print("✓ 刷新完成：%s" % url)
                return 0
            print("✗ 云端执行失败：%s" % url)
            print("  常见原因：账号密码失效、青鸾接口改版、数据校验未通过（看日志里的 ✗ 行）")
            return 4
    print("· 等待超时，请自行打开 Actions 页面查看。")
    return 5


if __name__ == "__main__":
    sys.exit(main())
