r"""一键部署到 GitHub（建仓库 → 推代码 → 写 Secrets → 回填云端地址 → 触发 Actions）。

用法（在项目根目录）：
    一键部署.bat                                   # 交互式：问用户名 / 仓库名 / Token
    python scripts\deploy_github.py --dry-run      # 只看要做什么，不动手
    python scripts\deploy_github.py --owner me --repo beian-map --token ghp_xxx
    python scripts\deploy_github.py --private      # 建私有仓库（本地页面就读不到 Raw 了）

也可以把参数放 config\deploy.json：
    {"owner": "你的用户名", "repo": "beian-map", "token": "ghp_xxx", "private": false}

Token 需要什么权限：classic PAT 勾 `repo` + `workflow`（要推 .github/workflows 必须有 workflow）。
脚本不会把 token 写进 .git/config，也不会打进任何提交。
"""

import argparse
import base64
import getpass
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "config", "config.json")
CRED_PATH = os.path.join(BASE, "config", "credentials.json")
DEPLOY_CFG = os.path.join(BASE, "config", "deploy.json")
API = "https://api.github.com"


# ---------------------------------------------------------------- 小工具
def log(msg=""):
    print(msg, flush=True)


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def find_git():
    for cand in ("git", r"C:\Program Files\Git\bin\git.exe", r"C:\Program Files\Git\cmd\git.exe",
                 r"C:\Program Files (x86)\Git\bin\git.exe"):
        try:
            subprocess.run([cand, "--version"], capture_output=True, check=True)
            return cand
        except Exception:
            continue
    sys.exit("找不到 git。装 Git for Windows 后重试：https://git-scm.com/download/win")


def run(cmd, cwd=None, check=True, quiet=True):
    r = subprocess.run(cmd, cwd=cwd or BASE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        log("命令失败：%s" % " ".join(str(c) for c in cmd if "@" not in str(c)))
        log((r.stdout or "").strip()[-2000:])
        log((r.stderr or "").strip()[-2000:])
        raise SystemExit(1)
    if not quiet and (r.stdout or r.stderr):
        log((r.stdout or "").strip())
        log((r.stderr or "").strip())
    return r


def api(method, path, token, body=None, ok=(200, 201, 204)):
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", "Bearer %s" % token)
    req.add_header("User-Agent", "beian-map-deploy")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"message": raw[:300]}
        if e.code in ok:
            return e.code, payload
        raise RuntimeError("GitHub API %s %s → %s %s" % (method, path, e.code, payload.get("message", "")))


# ---------------------------------------------------------------- 参数
def resolve_args(args):
    cfg = read_json(DEPLOY_CFG)
    owner = args.owner or cfg.get("owner") or os.environ.get("GITHUB_OWNER") or ""
    repo = args.repo or cfg.get("repo") or ""
    token = args.token or cfg.get("token") or os.environ.get("GITHUB_TOKEN") or ""
    private = args.private or bool(cfg.get("private"))

    if not args.dry_run:
        if not owner:
            owner = input("GitHub 用户名（owner）: ").strip()
        if not repo:
            repo = input("仓库名（不存在会自动创建）: ").strip()
        if not token:
            log("Token 生成：GitHub → Settings → Developer settings → Personal access tokens →")
            log("  Tokens (classic) → Generate new token，勾选 repo + workflow")
            token = getpass.getpass("粘贴 Token（输入不回显）: ").strip()
    return owner.strip(), repo.strip(), token.strip(), private


# ---------------------------------------------------------------- 步骤
def step_verify(owner, token):
    st, me = api("GET", "/user", token)
    log("✓ Token 有效，登录身份：%s" % me.get("login"))
    if owner and me.get("login", "").lower() != owner.lower():
        log("  注意：指定的 owner=%s 与登录账号 %s 不同，将按 owner 建仓库/推送。" % (owner, me.get("login")))
    return me


def step_repo(owner, repo, token, private):
    st, payload = api("POST", "/user/repos", token, {
        "name": repo,
        "private": bool(private),
        "auto_init": False,
        "description": "备案项目每日导出 + 零操作数据页（GitHub Actions + data.json）",
        "has_issues": False, "has_wiki": False, "has_projects": False,
    }, ok=(201, 422))
    if st == 201:
        log("✓ 仓库已创建：https://github.com/%s/%s" % (owner, repo))
    else:
        log("· 仓库已存在，继续用：https://github.com/%s/%s" % (owner, repo))


def step_push(owner, repo, token, git):
    if not os.path.isdir(os.path.join(BASE, ".git")):
        run([git, "init", "-b", "main"])
        log("✓ git 仓库已初始化")
    run([git, "branch", "-M", "main"], check=False)

    if not run([git, "config", "user.name"], check=False).stdout.strip():
        run([git, "config", "user.name", owner])
        run([git, "config", "user.email", "%s@users.noreply.github.com" % owner])

    run([git, "add", "-A"])
    status = run([git, "status", "--porcelain"]).stdout.strip()
    if status:
        n = len(status.splitlines())
        run([git, "commit", "-m", "init: 备案项目地图 v2（Actions 定时 + data.json + 本地页面）"])
        log("✓ 首次提交完成（%d 个文件变更）" % n)
    else:
        log("· 没有需要提交的改动")

    tok_url = "https://x-access-token:%s@github.com/%s/%s.git" % (token, owner, repo)
    plain = "https://github.com/%s/%s.git" % (owner, repo)
    remotes = run([git, "remote"], check=False).stdout.split()
    if "origin" in remotes:
        run([git, "remote", "set-url", "origin", tok_url])
    else:
        run([git, "remote", "add", "origin", tok_url])

    r = run([git, "push", "-u", "origin", "main"], check=False)
    if r.returncode != 0:
        log("· 远端已有提交（或网络不通），改用 GitHub API 逐个推送…")
        push_files_via_api(owner, repo, token)
    else:
        log("✓ 代码已推送：%s" % plain)
    run([git, "remote", "set-url", "origin", plain])   # 不把 token 留在 config 里


# 云端会自己生成的文件不通过 API 覆盖（否则会把当天数据/页面盖成旧版）
SKIP_FOR_API = {"data.json", "index.html", "备案项目地图.html", "projects.json",
                "config/credentials.json", "config/deploy.json"}


def push_files_via_api(owner, repo, token, branch="main"):
    """远端已有提交时，用 Contents API 逐文件推送，绕开 git 历史分叉与网络问题。"""
    import base64
    import json as _json
    try:
        import requests
    except ImportError:
        log("✗ 缺 requests，无法 API 推送：python -m pip install requests")
        return False

    git = find_git()
    files = [f for f in run([git, "ls-files"], check=False).stdout.splitlines() if f.strip()]
    api = "https://api.github.com/repos/%s/%s/contents/" % (owner, repo)
    s = requests.Session()
    s.headers.update({"Authorization": "token " + token,
                      "Accept": "application/vnd.github+json",
                      "User-Agent": "beian-map-deploy"})
    ok = failed = skipped = 0
    for f in files:
        if f in SKIP_FOR_API:
            skipped += 1
            continue
        p = os.path.join(BASE, f)
        if not os.path.isfile(p):
            continue
        with open(p, "rb") as fh:
            content = fh.read()
        try:
            r = s.get(api + f, params={"ref": branch}, timeout=30)
            sha = r.json().get("sha") if r.status_code == 200 else None
            body = {"message": "deploy: %s" % f, "branch": branch,
                    "content": base64.b64encode(content).decode()}
            if sha:
                body["sha"] = sha
            r = s.put(api + f, data=_json.dumps(body), timeout=60)
        except Exception as exc:
            log("  ✗ %s 请求失败：%s" % (f, exc))
            failed += 1
            continue
        if r.status_code in (200, 201):
            ok += 1
        else:
            log("  ✗ %s %s %s" % (f, r.status_code, r.text[:80]))
            failed += 1

    log("✓ API 推送：成功 %d 个，跳过 %d 个（data.json / index.html 由云端生成），失败 %d 个"
        % (ok, skipped, failed))
    return failed == 0


def step_secrets(owner, repo, token, cf=None):
    try:
        from nacl import encoding, public
    except ImportError:
        log("· 缺 pynacl，先装一下…")
        subprocess.run([sys.executable, "-m", "pip", "install", "pynacl", "--quiet", "--disable-pip-version-check"])
        try:
            from nacl import encoding, public
        except ImportError:
            log("✗ 自动装 pynacl 失败。请手动在仓库 Settings → Secrets → Actions 添加：")
            log("   JUFA_USERNAME / JUFA_PASSWORD")
            return False

    cred = read_json(CRED_PATH)
    conf = read_json(CONFIG_PATH)
    pairs = [
        ("JUFA_USERNAME", cred.get("username") or (conf.get("login") or {}).get("username") or ""),
        ("JUFA_PASSWORD", cred.get("password") or (conf.get("login") or {}).get("password") or ""),
    ]
    if cf:
        pairs += [("CLOUDFLARE_API_TOKEN", cf["token"]),
                  ("CLOUDFLARE_ACCOUNT_ID", cf["account"]),
                  ("CLOUDFLARE_PROJECT_NAME", cf["project"])]
    missing = [n for n, v in pairs if not v]
    if missing:
        log("✗ 缺少值，跳过这些 Secrets：%s" % ", ".join(missing))

    st, key = api("GET", "/repos/%s/%s/actions/secrets/public-key" % (owner, repo), token)
    box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder))
    n = 0
    for name, value in pairs:
        if not value:
            continue
        enc = base64.b64encode(box.encrypt(str(value).encode("utf-8"))).decode()
        api("PUT", "/repos/%s/%s/actions/secrets/%s" % (owner, repo, name), token,
            {"encrypted_value": enc, "key_id": key["key_id"]})
        n += 1
    log("✓ Actions Secrets 已写入 %d 条（值不出本机，只上传加密后的密文）" % n)
    return True


def step_publish(owner, repo, token, git):
    conf = read_json(CONFIG_PATH)
    conf["publish"] = {"github_owner": owner, "github_repo": repo, "branch": "main"}
    write_json(CONFIG_PATH, conf)
    log("✓ config/config.json 的 publish 已指向 %s/%s" % (owner, repo))

    r = subprocess.run([sys.executable, os.path.join(BASE, "app", "build_map_html.py"),
                        "--from-json", "data.json", "--out", "index.html"],
                       cwd=BASE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        log("✗ 重建 index.html 失败：%s" % (r.stderr or r.stdout)[-800:])
        return
    log("✓ index.html 已重建（云端地址已写进页面）")

    run([git, "add", "config/config.json", "config/config.example.json", "index.html"], check=False)
    if run([git, "status", "--porcelain"]).stdout.strip():
        run([git, "commit", "-m", "config: index.html 指向云端 data.json"], check=False)
        r = run([git, "push", "origin", "main"], check=False)
        if r.returncode == 0:
            log("✓ 已推送配置更新")
        else:
            log("· git 推送不通，改用 API 推 config（index.html 由云端重建，不用推）")
            push_files_via_api(owner, repo, token)
            log("✓ 配置已通过 API 更新")


def step_actions(owner, repo, token, trigger=True):
    api("PUT", "/repos/%s/%s/actions/permissions" % (owner, repo), token,
        {"enabled": True, "allowed_actions": "all"}, ok=(200, 204, 403, 404))
    api("PUT", "/repos/%s/%s/actions/permissions/workflow" % (owner, repo), token,
        {"default_workflow_permissions": "write", "can_approve_pull_request_reviews": True},
        ok=(200, 204, 403, 404))
    log("✓ Actions 已启用，默认权限设为 read/write")

    if not trigger:
        return
    for i in range(5):
        try:
            api("POST", "/repos/%s/%s/actions/workflows/daily.yml/dispatches" % (owner, repo), token,
                {"ref": "main"})
            log("✓ 已触发第一次运行（workflow 可能还有几秒才出现在列表里）")
            return
        except RuntimeError as e:
            if "404" in str(e) and i < 4:
                time.sleep(8)
                continue
            log("· 触发失败：%s" % e)
            log("  手动跑一次：https://github.com/%s/%s/actions → 备案项目地图每日更新 → Run workflow" % (owner, repo))
            return


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description="一键部署到 GitHub")
    ap.add_argument("--owner")
    ap.add_argument("--repo")
    ap.add_argument("--token")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-secrets", action="store_true")
    ap.add_argument("--no-trigger", action="store_true")
    ap.add_argument("--cf-token", default="", help="Cloudflare API Token（配了才发 Pages，免费）")
    ap.add_argument("--cf-account", default="", help="Cloudflare Account ID")
    ap.add_argument("--cf-project", default="", help="Cloudflare Pages 项目名，如 beian-map")
    args = ap.parse_args()
    cf_token, cf_account, cf_project = args.cf_token, args.cf_account, args.cf_project
    dcfg = read_json(DEPLOY_CFG)
    cf_token = cf_token or dcfg.get("cf_token") or os.environ.get("CF_API_TOKEN") or ""
    cf_account = cf_account or dcfg.get("cf_account") or ""
    cf_project = cf_project or dcfg.get("cf_project") or ""

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    owner, repo, token, private = resolve_args(args)

    log("=" * 56)
    log(" 一键部署：%s/%s（%s）" % (owner or "?", repo or "?", "私有" if private else "公开"))
    log("=" * 56)

    if args.dry_run:
        git = find_git()
        if os.path.isdir(os.path.join(BASE, ".git")):
            cnt = len(run([git, "status", "--porcelain"]).stdout.splitlines())
        else:
            cnt = 0
            for root, dirs, files in os.walk(BASE):
                dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "output", "dist")]
                cnt += len(files)
        log("· [dry-run] git: %s" % git)
        log("· [dry-run] 将创建仓库并推送约 %d 个文件" % cnt)
        log("· [dry-run] 将写入 Secrets：JUFA_USERNAME / JUFA_PASSWORD"
            + (" + CLOUDFLARE_*" if cf_token else ""))
        log("· [dry-run] 将重建 index.html 并推送，然后触发 Actions")
        return 0

    if not owner or not repo or not token:
        sys.exit("缺少 owner / repo / token")

    cf = None
    if cf_token and cf_account and cf_project:
        cf = {"token": cf_token, "account": cf_account, "project": cf_project}

    git = find_git()
    step_verify(owner, token)
    step_repo(owner, repo, token, private)
    step_push(owner, repo, token, git)
    if not args.skip_secrets:
        step_secrets(owner, repo, token, cf)
    step_publish(owner, repo, token, git)
    step_actions(owner, repo, token, trigger=not args.no_trigger)

    log()
    log("=" * 56)
    log(" 部署完成（全部免费：GitHub Actions + Cloudflare Pages）")
    log("=" * 56)
    log("仓库：https://github.com/%s/%s" % (owner, repo))
    log("Actions：https://github.com/%s/%s/actions" % (owner, repo))
    log("数据：https://raw.githubusercontent.com/%s/%s/main/data.json" % (owner, repo))
    log("本地：双击 青鸾地图.bat（菜单 5）（数据自动取云端）")
    if cf:
        log("网页（手机/电脑随时访问）：https://%s.pages.dev/" % cf["project"])
    else:
        log("手机随时访问：再配一遍 Cloudflare Pages（免费），见 docs\\部署清单.md 第 6 节")
    if private:
        log("注意：Private 仓库读不到 Raw/jsDelivr，本地页面只看内置快照；实时访问请用上面的 Pages 链接。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
