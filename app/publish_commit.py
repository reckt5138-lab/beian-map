"""把 data.json / index.html 提交回仓库 —— 走 GitHub Contents API，不依赖 git push。

为什么不用 `git commit && git push`：Actions 里工作区常常是"脏"的（换行符规范化、
生成网页改动），`git pull --rebase --autostash` 会直接失败（cannot rebase: You have
unstaged changes）。用 API 提交没有这个问题，也天然幂等。

环境变量（Actions 自动提供）：
  GITHUB_TOKEN         secrets.GITHUB_TOKEN（contents: write）
  GITHUB_REPOSITORY    owner/repo
  GITHUB_REF_NAME      分支名，默认 main
可选：
  COMMIT_PATHS         要提交的文件，逗号分隔，默认 "data.json,index.html"

行为：
  data.json 内容没变（忽略 generated_at / updated）→ 不提交，打印"无变化"
  data.json 变了 → 提交 data.json；index.html 内容变了也一起提交
"""

import base64
import json
import os
import sys
from datetime import datetime

import requests

import map_payload  # 同目录，负责 payload 规范化与幂等比较

API_ROOT = "https://api.github.com"


def log(msg):
    print(msg, flush=True)


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    repo = os.environ.get("GITHUB_REPOSITORY") or ""
    branch = os.environ.get("GITHUB_REF_NAME") or "main"
    paths = [p.strip() for p in (os.environ.get("COMMIT_PATHS") or "data.json,index.html").split(",") if p.strip()]

    if not token or not repo:
        log("跳过提交：缺 GITHUB_TOKEN 或 GITHUB_REPOSITORY（本地跑可忽略）")
        return 0

    session = requests.Session()
    session.headers.update({
        "Authorization": "token " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "beian-map-publisher",
    })

    def remote_file(path):
        url = "%s/repos/%s/contents/%s" % (API_ROOT, repo, path)
        r = session.get(url, params={"ref": branch}, timeout=30)
        if r.status_code == 404:
            return None, None
        r.raise_for_status()
        data = r.json()
        raw = base64.b64decode(data.get("content") or "")
        return raw, data.get("sha")

    def put_file(path, content, sha, message):
        url = "%s/repos/%s/contents/%s" % (API_ROOT, repo, path)
        body = {"message": message, "branch": branch, "content": base64.b64encode(content).decode()}
        if sha:
            body["sha"] = sha
        r = session.put(url, data=json.dumps(body), timeout=60)
        if r.status_code not in (200, 201):
            log("  %s 提交失败 %s：%s" % (path, r.status_code, r.text[:200]))
            return False
        return True

    def norm_json(raw):
        try:
            return json.dumps(map_payload.core(json.loads(raw.decode("utf-8")), ), sort_keys=True, ensure_ascii=False)
        except Exception:
            return None

    local = {}
    for p in paths:
        with open(p, "rb") as f:
            local[p] = f.read()

    # 先判断 data.json 是否真的变了
    changed = True
    if "data.json" in local:
        remote_raw, _ = remote_file("data.json")
        if remote_raw:
            a, b = norm_json(local["data.json"]), norm_json(remote_raw)
            if a is not None and a == b:
                changed = False

    if not changed:
        log("数据没变化，跳过提交")
        return 0

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    ok_all = True
    for p in paths:
        sha_remote_before = None
        try:
            _, sha_remote_before = remote_file(p)
        except Exception as exc:
            log("  读取远端 %s 失败：%s" % (p, exc))
        ok = put_file(p, local[p], sha_remote_before, "data: update %s (%s)" % (stamp, p))
        log("  %s %s" % (p, "已提交" if ok else "失败"))
        ok_all = ok_all and ok

    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
