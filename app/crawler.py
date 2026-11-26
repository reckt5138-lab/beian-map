# -*- coding: utf-8 -*-
"""
青鸾系统（c.jbufa.com）项目列表 —— 每日凌晨全量抓取
功能：
  1. 账号密码登录（OAuth password 模式），也可直接填入浏览器里的 token / cookie
  2. 按“项目列表”接口分页拉取全部项目（多标签页合并 + 去重）
  3. 逐条调用项目详情接口，取回该项目全部字段（与网页详情页一致）
  4. 输出完整矩阵 JSON（158 列），后续由 app.main 脱敏成公开 data.json
  5. 原始 JSON 落盘，方便复核 / 二次加工

用法：
  python crawler.py --verify                      仅验证登录，打印项目总数
  python crawler.py --json-out output/data.full.json   全量抓取并输出数据
  python crawler.py --no-detail                   只抓列表字段，速度快，字段少
  python crawler.py --date 2026-11-20             指定日期标记

作者：Doubao  ·  仅用于抓取本账号有权查看的数据
"""

import argparse
import csv
import io
import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import time
import traceback
from datetime import date, datetime, timedelta

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 代码放在 app/ 下时，工程根目录是它的上一级
BASE_DIR = os.path.dirname(SCRIPT_DIR) if os.path.basename(SCRIPT_DIR).lower() == "app" else SCRIPT_DIR
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import map_payload  # noqa: E402  抓完直接写 data.json（不经过飞书）

# 代理策略：默认直连；config.network.use_proxy=true 时才走系统代理
try:
    from app.core.network import make_session
except ImportError:  # 直接以 app/ 为工作目录运行时
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "ql_network", os.path.join(BASE_DIR, "app", "core", "network.py"))
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        make_session = _mod.make_session
    except Exception:  # 兜底：退回 requests 默认（会读系统代理）
        def make_session(cfg=None):
            return requests.Session()

CONFIG_DIR = os.path.join(BASE_DIR, "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
LEGACY_CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
EXAMPLE_PATH = os.path.join(CONFIG_DIR, "config.example.json")

# 接口返回的成功码
OK_CODES = {"000", "002", "003", "004", "005", "012"}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# ---------------------------------------------------------------- 配置

DEFAULT_CONFIG = {
    "base_url": "https://c.jbufa.com",
    "login": {
        "username": "",
        "password": "",
        "client_id": "web",
        # 网页端登录接口的固定公开参数（非用户凭证），见下方 login 说明
        "client_secret": "111111",
        # 二选一：若填了 token，则跳过账号密码登录（token 会过期，仅应急用）
        "token": "",
        # 也可以直接贴登录后的整条 Cookie
        "cookie": ""
    },
    "api": {
        "token_path": "/oauth/token",
        "user_info_path": "/user/simple/info",
        "project_list_path": "/project/conditionsPage",
        "project_detail_path": "/project-info/select/one/by/{project_id}",
        "project_follow_path": "/project-follow/{project_id}",
        "project_contact_path": "/project/select/project/contact/by/{project_id}",
        "client_path": "/client/{client_id}",
        "export_field_path": "/project-info/export/record/{tab_type}",
        "export_path": "/project-info/export"
    },
    "crawl": {
        # 100 = 网页里的“全部项目”（一次返回全部分类，再按 status_filter 过滤）
        "tab_types": [100],
        # 只导出这些“项目状态”，留空 [] 表示不过滤（会把丢失/失效/非备案人报价也算进来）
        # 取值以接口为准：备案项目 / 成交；网页 Tab 文案“成交项目”会自动展开为“成交”
        "status_filter": ["备案项目", "成交"],
        "page_size": 50,
        "max_pages": 500,
        "request_interval": 0.15,
        "retry": 3,
        "timeout": 60,
        "with_detail": True,
        "with_follow": True,
        "with_client": True
    },
    "export": {
        "output_dir": "output",
        "file_prefix": "备案项目",
        "keep_days": 60,
        "use_field_template": True,
        # 与网页导出对齐：签到时间/签到记录 各展开 50 组（没有记录的留空）
        "checkin_columns": 50,
        "extra_fields": []
    }
}


def deep_merge(base, extra):
    out = dict(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


SECRETS_PATH = os.path.join(CONFIG_DIR, "credentials.json")
LEGACY_SECRETS_PATH = os.path.join(BASE_DIR, "credentials.json")


def _first_existing(*paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return paths[0]


def active_config_path():
    """config/ 下的优先；兼容旧结构（配置直接放根目录）。"""
    return _first_existing(CONFIG_PATH, LEGACY_CONFIG_PATH)


def active_secrets_path():
    return _first_existing(SECRETS_PATH, LEGACY_SECRETS_PATH)


def apply_secrets(cfg):
    """账号密码 / 应用密钥优先从环境变量、再从一个独立文件读，config.json 里可以留空。

    优先级：环境变量 > credentials.json > config.json 里已填的值。
    换设备时把 credentials.json 一起拷过去就能直接跑；没有的话设环境变量也行。
    """
    secrets = {}
    sp = active_secrets_path()
    if os.path.exists(sp):
        try:
            with open(sp, "r", encoding="utf-8-sig") as f:
                secrets = json.load(f) or {}
        except ValueError:
            print("credentials.json 不是合法 JSON，已忽略")

    env_user = os.environ.get("JUFA_USERNAME") or os.environ.get("JB_USERNAME") or ""
    env_pwd = os.environ.get("JUFA_PASSWORD") or os.environ.get("JB_PASSWORD") or ""

    login = cfg.setdefault("login", {})
    login["username"] = env_user or secrets.get("username") or login.get("username") or ""
    login["password"] = env_pwd or secrets.get("password") or login.get("password") or ""
    return cfg


def save_secrets(values):
    """把敏感值写进 credentials.json（不改 config.json）。"""
    sp = active_secrets_path()
    try:
        with open(sp, "r", encoding="utf-8-sig") as f:
            data = json.load(f) or {}
    except (OSError, ValueError):
        data = {}
    data.update(values)
    os.makedirs(os.path.dirname(sp) or ".", exist_ok=True)
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(sp, 0o600)
    except OSError:
        pass
    return sp


def load_config():
    cp = active_config_path()
    if not os.path.exists(cp):
        os.makedirs(os.path.dirname(cp) or ".", exist_ok=True)
        with open(cp, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        print("已生成配置文件：%s（账号密码可写进 credentials.json 或环境变量）" % cp)
    # utf-8-sig：兼容用记事本保存后带 BOM 的 config.json
    with open(cp, "r", encoding="utf-8-sig") as f:
        user_cfg = json.load(f)
    return apply_secrets(deep_merge(DEFAULT_CONFIG, user_cfg))


def resolve_output_dir(cfg):
    out = cfg["export"].get("output_dir") or ""
    if not out:
        out = os.path.join(BASE_DIR, "output")
    elif not os.path.isabs(out):
        # 相对路径（如默认的 output）以工程根目录为基准
        out = os.path.join(BASE_DIR, out)
    drive = os.path.splitdrive(out)[0]
    if out and drive and not os.path.exists(drive + os.sep):
        print("提示：配置的输出盘 %s 不存在，改用工程目录下的 output" % drive)
        out = os.path.join(BASE_DIR, "output")
    os.makedirs(out, exist_ok=True)
    return out

# ---------------------------------------------------------------- 日志


def setup_logging(out_dir):
    log_dir = os.path.join(out_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "crawl_%s.log" % datetime.now().strftime("%Y%m%d"))
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    return log_file

# ---------------------------------------------------------------- 异常


class ApiError(Exception):
    pass


class LoginError(ApiError):
    pass

# ---------------------------------------------------------------- HTTP 客户端


class JBufaClient(object):
    def __init__(self, cfg, session=None):
        self.cfg = cfg
        self.base = cfg["base_url"].rstrip("/")
        self.api = cfg["api"]
        self.timeout = cfg["crawl"]["timeout"]
        self.retry = cfg["crawl"]["retry"]
        self.interval = cfg["crawl"]["request_interval"]
        self.s = session or make_session(cfg)
        self.s.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Origin": self.base,
            "Referer": self.base + "/",
            "Content-Type": "application/json;charset=UTF-8",
        })
        self.token = ""
        self.token_type = "bearer"
        self.auth_mode = "concat"  # concat | space | bearer | raw
        self._last_call = 0.0

    # -- 基础
    def _url(self, path):
        if re.match(r"^https?://", path):
            return path
        return "%s/api%s" % (self.base, path if path.startswith("/") else "/" + path)

    def _throttle(self):
        gap = self.interval - (time.time() - self._last_call)
        if gap > 0:
            time.sleep(gap)
        self._last_call = time.time()

    def _auth_value(self):
        tok = self.token
        if not tok:
            return ""
        if self.auth_mode == "concat":
            return "%s%s" % (self.token_type, tok)
        if self.auth_mode == "space":
            return "%s %s" % (self.token_type, tok)
        if self.auth_mode == "bearer":
            return "Bearer %s" % tok
        return tok

    def call(self, method, path, params=None, json_body=None, data=None, allow_binary=False):
        url = self._url(path)
        last_err = None
        for attempt in range(1, self.retry + 1):
            self._throttle()
            headers = {}
            if self.token:
                headers["Authorization"] = self._auth_value()
            try:
                resp = self.s.request(method.upper(), url, params=params, json=json_body,
                                      data=data, headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                last_err = exc
                logging.warning("请求异常 %s %s（第%d次）：%s", method, path, attempt, exc)
                time.sleep(1.2 * attempt)
                continue

            if resp.status_code == 401:
                raise LoginError("登录已失效（401），请重新检查账号密码或 token")
            if resp.status_code == 420:
                raise ApiError("数据过大（420），请调小 page_size 或加筛选条件")
            if resp.status_code >= 500:
                last_err = ApiError("%s %s 服务端错误 %s" % (method, path, resp.status_code))
                time.sleep(1.5 * attempt)
                continue

            ctype = (resp.headers.get("Content-Type") or "").lower()
            if allow_binary and ("json" not in ctype):
                return {"__binary__": resp.content, "__ctype__": ctype}

            try:
                body = resp.json()
            except ValueError:
                if allow_binary:
                    return {"__binary__": resp.content, "__ctype__": ctype}
                return {"__raw__": resp.text}

            if isinstance(body, dict):
                code = str(body.get("code", body.get("errorCode", "")))
                if code in OK_CODES or code == "0":
                    return body
                if code == "010":
                    raise LoginError("登录已过期（010），请重新登录")
                msg = body.get("msg") or body.get("message") or body.get("error_description") or "未知错误"
                raise ApiError("%s %s -> code=%s msg=%s" % (method, path, code, msg))
            return body

        raise ApiError("请求失败：%s %s，最后错误：%s" % (method, path, last_err))

    # -- 登录
    def login(self):
        lg = self.cfg["login"]
        if lg.get("cookie"):
            self.s.headers["Cookie"] = lg["cookie"]
            logging.info("已使用配置中的 Cookie 登录")
        if lg.get("token"):
            self.token = lg["token"].strip()
            if self.token.lower().startswith("bearer "):
                self.auth_mode = "raw"
            logging.info("已使用配置中的 token")
            self._detect_auth_mode()
            return

        if not lg.get("username") or not lg.get("password"):
            raise LoginError(
                "请先在 config.json 的 login.username / login.password 里填好账号密码（"
                "也可以填 login.token 或 login.cookie）")

        # client_id / client_secret 是青鸾网页端登录接口的固定公开参数（浏览器 JS 里可见），
        # 不是用户凭证；真正的秘密只有 username / password，来自 credentials.json 或环境变量。
        payload = {
            "grant_type": "password",
            "username": lg["username"].strip(),
            "password": lg["password"],
            "client_id": lg.get("client_id", "web"),
            "client_secret": lg.get("client_secret", "111111"),
        }
        logging.info("正在登录：%s", lg["username"])

        body = None
        err = None
        # 前端用 query 参数发这个请求，这里两种都兼容
        for kwargs in ({"params": payload}, {"data": payload}):
            try:
                body = self.call("POST", self.api["token_path"], **kwargs)
                break
            except ApiError as exc:
                err = exc
                if "用户或密码错误" in str(exc):
                    raise LoginError("账号或密码错误：%s" % exc)
                continue
        if body is None:
            raise LoginError("登录失败：%s" % err)

        data = body.get("data") if isinstance(body.get("data"), dict) else body
        tok = data.get("access_token") or data.get("token") or data.get("accessToken")
        if not tok:
            raise LoginError("登录接口没有返回 access_token，返回内容：%s" % json.dumps(body, ensure_ascii=False)[:300])

        self.token = tok
        self.token_type = (data.get("token_type") or data.get("tokenType") or "bearer").strip() or "bearer"
        self.refresh_token = data.get("refresh_token") or ""
        logging.info("登录成功，获取到 token（长度 %d）", len(tok))
        self._detect_auth_mode()

    def _detect_auth_mode(self):
        """服务端对 Authorization 拼接方式可能有差异，用 /user/simple/info 探测一次。"""
        probe = self.api.get("user_info_path", "/user/simple/info")
        for mode in ("concat", "space", "bearer", "raw"):
            self.auth_mode = mode
            try:
                body = self.call("GET", probe)
                name = ""
                data = body.get("data")
                if isinstance(data, dict):
                    name = data.get("name") or data.get("userName") or data.get("realName") or ""
                logging.info("鉴权方式可用：%s（当前账号：%s）", mode, name or "未知")
                return mode
            except ApiError as exc:
                logging.debug("鉴权方式 %s 不可用：%s", mode, exc)
                continue
        self.auth_mode = "concat"
        logging.warning("四种 Authorization 拼接方式都探测失败，默认按 concat 发送，如报 401 请在 config.json 里改用 token 方式")
        return "concat"

    # -- 项目列表
    def list_page(self, tab_type, page_no, page_size):
        body = {
            "company": "",
            "department": "",
            "userName": "",
            "projectName": "",
            "recordTime": "",
            "expirationTime": "",
            "projectStage": "",
            "crossRegion": "",
            "signBill": "",
            "quotationStage": "",
            "stage": "",
            "projectTabType": tab_type,
            "projectTabTypeList": [],
            "projectAttribute": "",
            "startTime": "",
            "endTime": "",
            "loseReasonType": "",
            "deptIdList": [],
            "projectAddress": "",
            "projectFieldFive": "",
            "projectFieldTwelve": "",
            "projectFieldThirteen": "",
            "projectFieldFourteen": "",
            "projectFieldFifteen": "",
            "projectFieldSixteen": "",
            "sortBy": "",
            "sortType": "",
            "pageSize": page_size,
            "pageNo": page_no,
            "isFrontPage": 0,
        }
        return self.call("POST", self.api["project_list_path"], json_body=body)

    def project_detail(self, project_id):
        path = self.api["project_detail_path"].format(project_id=project_id)
        return self.call("GET", path)


# ---------------------------------------------------------------- 抓取

ID_KEYS = ("projectId", "id", "projectInfoId", "infoId")


def pick_rows(body):
    data = body.get("data")
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("data", "list", "records", "rows", "content"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
        else:
            rows = []
    else:
        rows = []
    total = body.get("total")
    if total is None and isinstance(data, dict):
        total = data.get("total")
    return rows, total


def row_key(row):
    for k in ID_KEYS:
        if row.get(k) not in (None, "", 0, "0"):
            return str(row.get(k))
    return "%s|%s" % (row.get("projectName") or "", row.get("createTime") or row.get("createdTime") or "")


# 网页 Tab 文案 与 列表接口 projectStatus 实际取值 的对应关系。
# 实测（2026-11-25）：projectStatus = 备案项目 21 / 成交 12 / 失效 3 / 丢失 2 / 非备案人报价项目 1。
# 若只按「成交项目」过滤，12 条成交项目会被全部丢掉，所以这里做别名展开。
STATUS_ALIASES = {
    "备案项目": ("备案项目", "备案"),
    "成交项目": ("成交项目", "成交"),
}


def expand_status_filter(wanted):
    values = set()
    for item in wanted or []:
        text = str(item or "").strip()
        if not text:
            continue
        values.add(text)
        values.update(STATUS_ALIASES.get(text, ()))
    return values


def filter_rows_by_status(rows, wanted):
    """按项目状态过滤；wanted 为空表示不过滤。返回 (kept, dropped_counts)。"""
    values = expand_status_filter(wanted)
    if not values:
        return list(rows), {}
    kept = []
    dropped = {}
    for row in rows:
        status = str(row.get("projectStatus") or "").strip()
        if status in values:
            kept.append(row)
        else:
            dropped[status or "(空)"] = dropped.get(status or "(空)", 0) + 1
    return kept, dropped


def crawl_list(client, cfg):
    tabs = cfg["crawl"]["tab_types"]
    page_size = int(cfg["crawl"]["page_size"])
    max_pages = int(cfg["crawl"]["max_pages"])
    collected = {}
    stats = []

    for tab in tabs:
        page = 1
        tab_rows = 0
        total = None
        while page <= max_pages:
            try:
                body = client.list_page(tab, page, page_size)
            except ApiError as exc:
                if "420" in str(exc) and page_size > 20:
                    page_size = max(20, page_size // 2)
                    logging.warning("数据量过大，page_size 降为 %d 重试", page_size)
                    continue
                logging.warning("标签 %s 第 %d 页抓取失败：%s（跳过该标签剩余页）", tab, page, exc)
                break

            rows, tot = pick_rows(body)
            if total is None:
                total = tot
            if not rows:
                break
            tab_rows += len(rows)
            for row in rows:
                key = row_key(row)
                if key in collected:
                    collected[key].update({k: v for k, v in row.items() if v not in (None, "")})
                else:
                    collected[key] = dict(row)
            logging.info("标签 %-4s 第 %3d 页：+%2d 条，累计 %d 条（接口总数 %s）",
                         tab, page, len(rows), len(collected), total)
            if total is not None and tab_rows >= int(total):
                break
            if len(rows) < page_size:
                break
            page += 1
        stats.append({"tab": tab, "rows": tab_rows, "total": total})

    rows = list(collected.values())
    wanted = cfg["crawl"].get("status_filter") or []
    if wanted:
        rows, dropped = filter_rows_by_status(rows, wanted)
        logging.info("按项目分类过滤（%s）：保留 %d 条；剔除 %d 条（%s）",
                     "、".join(wanted), len(rows), sum(dropped.values()),
                     "、".join("%s:%d" % (k, v) for k, v in sorted(dropped.items())))
    return rows, stats


def flatten_detail(obj, prefix="", out=None, depth=0):
    """把详情 JSON 拍平成 {字段: 值}，列表转成分号拼接的文本。"""
    if out is None:
        out = {}
    if depth > 6:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("id",) and prefix == "":
                continue
            flatten_detail(v, ("%s.%s" % (prefix, k)) if prefix else str(k), out, depth + 1)
    elif isinstance(obj, list):
        parts = []
        for item in obj:
            if isinstance(item, dict):
                pairs = []
                for k, v in item.items():
                    if isinstance(v, (dict, list)) or v in (None, ""):
                        continue
                    pairs.append("%s=%s" % (k, v))
                if pairs:
                    parts.append("，".join(pairs))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            elif isinstance(item, list):
                parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        out[prefix or "_list"] = "；".join(parts)
    else:
        out[prefix] = obj
    return out


def enrich_with_detail(client, cfg, rows):
    if not cfg["crawl"].get("with_detail", True):
        return rows
    out = []
    total = len(rows)
    for idx, row in enumerate(rows, 1):
        pid = None
        for k in ID_KEYS:
            if row.get(k) not in (None, "", 0, "0"):
                pid = row[k]
                break
        if pid is None:
            out.append(row)
            continue
        try:
            body = client.project_detail(pid)
        except LoginError:
            raise
        except ApiError as exc:
            logging.warning("[%d/%d] 项目 %s 详情失败：%s", idx, total, pid, exc)
            out.append(row)
            continue

        data = body.get("data") if isinstance(body.get("data"), (dict, list)) else body
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            out.append(row)
            continue

        merged = dict(row)
        flat = flatten_detail(data)
        for k, v in flat.items():
            leaf = k.split(".")[-1]
            if leaf in merged and merged[leaf] not in (None, "") and v in (None, ""):
                continue
            merged.setdefault(k, v)
            merged[leaf] = v if k.count(".") == 0 else merged.get(leaf, v)
        if cfg["crawl"].get("with_follow", True):
            attach_follow_records(client, cfg, merged, pid)
        out.append(merged)
        if idx % 20 == 0 or idx == total:
            logging.info("详情进度 %d/%d", idx, total)
    return out


def attach_follow_records(client, cfg, row, pid):
    """取签到/跟进记录：签到列只取 checkInType=1 的记录（和网页导出的规则一致）。"""
    path = cfg["api"].get("project_follow_path")
    if not path:
        return
    try:
        body = client.call("GET", path.format(project_id=pid))
    except LoginError:
        raise
    except ApiError as exc:
        logging.debug("项目 %s 跟进记录失败：%s", pid, exc)
        return

    recs = body.get("data")
    if not isinstance(recs, list):
        return
    recs = [r for r in recs if isinstance(r, dict)]
    recs.sort(key=lambda r: str(r.get("followTime") or ""), reverse=True)

    def brief(r):
        return {"time": r.get("followTime") or r.get("ct") or "",
                "record": r.get("remark") or r.get("followProgress") or "",
                "type": r.get("type") or ""}

    row["_follows"] = [brief(r) for r in recs]
    # 只有 checkInType=1 的才算“签到”，网页导出就是这么过滤的
    row["_signins"] = [brief(r) for r in recs if str(r.get("checkInType")) == "1"]

    if cfg["crawl"].get("with_client", True):
        attach_project_contact(client, cfg, row, pid)


def attach_project_contact(client, cfg, row, pid):
    """项目联系人接口一次给全：客户信息、公司性质、公司资质、挂靠、职位、公司地址。"""
    path = cfg["api"].get("project_contact_path")
    if not path:
        return
    try:
        body = client.call("GET", path.format(project_id=pid))
    except LoginError:
        raise
    except ApiError as exc:
        logging.debug("项目 %s 联系人失败：%s", pid, exc)
        return

    data = body.get("data")
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        return

    name = (data.get("clientName") or "").strip()
    company = (data.get("company") or "").strip()
    if name or company:
        row["projectCompany"] = ("%s（%s）" % (name, company)) if (name and company) else (name or company)

    # 挂靠：联系人自己挂的公司 和 项目上填的公司 不是同一家 → 是
    client_company = ""
    client_id = data.get("clientId") or data.get("mainClientId")
    if client_id:
        try:
            cl = client.call("GET", cfg["api"].get("client_path").format(client_id=client_id))
        except LoginError:
            raise
        except ApiError:
            cl = None
        cdata = (cl or {}).get("data")
        if isinstance(cdata, dict):
            comp = cdata.get("company") or {}
            if isinstance(comp, dict):
                client_company = (comp.get("name") or "").strip()

    if company:
        same = client_company and (client_company.replace(" ", "") == company.replace(" ", ""))
        row["companyTypeStr"] = "否" if same else "是"
    if not row.get("companyTypeStr"):
        row["companyTypeStr"] = "否"

    mapping = {
        "property": data.get("property"),
        "qualification": data.get("qualification"),
        "post": data.get("post"),
        "address": data.get("address"),
        "clientName": name or None,
        "company": company or None,
    }
    for key, value in mapping.items():
        if value not in (None, ""):
            row[key] = value

# ---------------------------------------------------------------- 列定义

# 常用字段的中文名（命中则用中文表头，未命中保留原始字段名，避免丢数据）
FIELD_LABELS = {
    "projectName": "项目名称", "projectId": "项目ID", "projectAddress": "项目地址",
    "userName": "业务员", "department": "部门", "deptName": "部门",
    "area": "面积", "projectCode": "项目编号", "orderTime": "预计订货时间",
    "approvalType": "审批类型", "projectDescription": "项目情况描述",
    "clientName": "客户信息", "customerName": "客户信息", "clientInfo": "客户信息",
    "productType": "产品类型", "projectType": "项目类型", "projectClassify": "项目分类",
    "isQuotation": "是否报价", "projectSource": "项目来源", "projectStage": "项目进度",
    "stage": "项目进度", "projectAttribute": "行业类型", "recordTime": "备案时间",
    "createTime": "创建时间", "updateTime": "最后更新时间",
    "filingTime": "备案时间", "contractAmount": "预计合同金额", "amount": "预计合同金额",
    "discount": "折扣信息", "discountInfo": "折扣信息", "signBill": "是否签约",
    "crossRegion": "跨区情况", "loseReason": "丢失原因", "lostReason": "丢失原因",
    "lastSignInRecord": "最后一次签到记录", "lastSignInTime": "最后一次签到时间",
    "signInCount": "项目签到次数", "noFollowDays": "未跟进天数",
    "quotationApplyCount": "申请报价次数", "companyNature": "公司性质",
    "companyQualification": "公司资质", "hostPassword": "挂靠", "position": "职位",
    "companyAddress": "公司地址", "competitor": "竞争对手",
    "contractStatus": "合同情况", "lockStatus": "锁定情况",
    "winStatus": "中标情况", "expireTime": "失效时间", "invalidTime": "失效时间",
    "dealTime": "成交时间", "projectTabTypeName": "项目分类",
    "projectStatus": "项目状态", "projectArea": "项目面积",
    "customFields": "自定义字段", "signInList": "签到记录",
}

# 没有字段配置接口时的默认顺序（也用于列排序优先级）
PREFERRED_ORDER = [
    "projectName", "projectAddress", "userName", "department", "area", "projectCode",
    "orderTime", "approvalType", "projectDescription", "clientName", "productType",
    "projectType", "isQuotation", "projectSource", "projectStage", "recordTime",
    "projectAttribute", "createTime", "contractAmount", "discount", "competitor",
    "signInCount", "noFollowDays", "quotationApplyCount", "lastSignInRecord",
    "companyNature", "companyQualification", "position", "companyAddress",
    "projectClassify", "contractStatus", "lockStatus", "winStatus", "expireTime",
    "dealTime", "projectId",
]

DATE_KEYS = ("time", "Time", "date", "Date", "timeStr")


def label_for(key):
    if key in FIELD_LABELS:
        return FIELD_LABELS[key]
    if "." in key:
        return FIELD_LABELS.get(key.split(".")[-1], key)
    return key


def sort_key(name):
    if name in PREFERRED_ORDER:
        return (0, PREFERRED_ORDER.index(name), name)
    return (1, 0, name)


CHECKIN_FIELD = "checkInRecordData"
CHECKIN_LABELS = ("签到时间", "签到记录")


def build_columns(all_rows, template=None, checkin_columns=50, extra_fields=None):
    keys = {}
    for row in all_rows:
        for k, v in row.items():
            if k.startswith("_"):
                continue
            if v is None or v == "":
                keys.setdefault(k, 0)
            else:
                keys[k] = keys.get(k, 0) + 1

    columns = []
    used = set()
    labels = set()

    def add(prop, label):
        if prop in used:
            return
        label = label or label_for(prop)
        if label in labels:
            label = "%s（%s）" % (label, prop)
        used.add(prop)
        labels.add(label)
        columns.append({"prop": prop, "label": label})

    # 有站点导出配置时，严格按它出列（和网页导出一样的 158 列），不再追加原始接口字段
    if template:
        for prop, label in template:
            if prop == CHECKIN_FIELD:
                # 这一项在网页导出里会展开成 50 组“签到时间/签到记录”
                for i in range(1, checkin_columns + 1):
                    columns.append({"prop": "checkInTime_%d" % i, "label": CHECKIN_LABELS[0]})
                    columns.append({"prop": "checkInRecord_%d" % i, "label": CHECKIN_LABELS[1]})
                continue
            # 网页导出里同一字段可能重复出现（如“项目进度”），这里照样保留
            columns.append({"prop": prop, "label": label or label_for(prop)})
        for extra in (extra_fields or []):
            if extra in keys and extra not in {c["prop"] for c in columns}:
                columns.append({"prop": extra, "label": label_for(extra)})
        return columns

    # 再按常用字段顺序补充；同名的嵌套字段跳过，避免重复列
    leaves = {k.split(".")[-1] for k in keys if "." not in k}
    for k in sorted(keys.keys(), key=sort_key):
        if k in used:
            continue
        if "." in k and k.split(".")[-1] in leaves:
            continue
        add(k, None)
    return columns


def _guess_from_row(prop, rows):
    """导出字段名可能和列表接口字段名不同（如 amountInfoText），试着找同义字段。"""
    for row in rows[:50]:
        if row.get(prop) not in (None, "", []):
            return True
    aliases = {"contractNo": "contractNoText", "amountInfoText": "amountInfo",
               "discountInfoText": "discountInfo", "checkInRecordData": "checkInRecord"}
    alias = aliases.get(prop)
    if alias:
        for row in rows[:50]:
            if row.get(alias) not in (None, "", []):
                return True
    return False


def _collect_field_pairs(node, out, depth=0):
    """从“导出字段配置”里递归找出 (字段名, 中文名) 对。"""
    if depth > 6 or not isinstance(node, (dict, list)):
        return out
    if isinstance(node, list):
        for item in node:
            _collect_field_pairs(item, out, depth + 1)
        return out

    prop = None
    for k in ("prop", "field", "fieldName", "code", "property", "key", "value"):
        v = node.get(k)
        if isinstance(v, str) and re.match(r"^[A-Za-z_][A-Za-z0-9_.]{1,60}$", v):
            prop = v
            break
    label = None
    for k in ("label", "name", "title", "alias", "labelName", "anotherName", "cnName"):
        v = node.get(k)
        if isinstance(v, str) and v and not re.match(r"^[A-Za-z_][A-Za-z0-9_.]{1,60}$", v):
            label = v
            break
    if prop and label:
        out.append((prop, label))
    for v in node.values():
        if isinstance(v, (dict, list)):
            _collect_field_pairs(v, out, depth + 1)
    return out


def load_field_template(client, cfg):
    """读取站点“导出配置”接口，拿到列名/列顺序（和网页导出的 Excel 一致）；失败返回 None。"""
    path_tpl = cfg["api"].get("export_field_path")
    if not path_tpl:
        return None
    tabs = [100] + [t for t in cfg["crawl"]["tab_types"] if t != 100]
    for tab in tabs[:3]:
        try:
            body = client.call("GET", path_tpl.format(tab_type=tab))
        except LoginError:
            raise
        except ApiError:
            continue
        data = body.get("data") if isinstance(body.get("data"), (dict, list)) else body
        groups = (data or {}).get("exportFieldList") if isinstance(data, dict) else None
        pairs = []
        for g in groups or []:
            for it in (g.get("subList") or []):
                prop = it.get("exportField") or it.get("sqlField")
                label = it.get("name") or ""
                if prop and it.get("checked") is not False:
                    pairs.append((prop, label))
        if not pairs:
            pairs = _collect_field_pairs(data, [])
        if len(pairs) >= 5:
            logging.info("已读取站点导出字段配置：%d 个字段（标签 %s）", len(pairs), tab)
            return pairs
    logging.info("未取到站点导出字段配置，按接口字段自动生成列名")
    return None


def _format_pair_list(value, value_key):
    """把 [{name:报警, contractPrice:3845}] 转成网页导出里的 “报警:3845;” 格式。"""
    if not value:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if text in ("", "[]", "null", "None"):
            return ""
        try:
            value = json.loads(text)
        except ValueError:
            return text
    if not isinstance(value, list):
        return str(value)
    parts = []
    for item in value:
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        name = item.get("name") or item.get("productType") or item.get("type") or ""
        val = item.get(value_key)
        if val in (None, ""):
            val = item.get("facePrice")
        parts.append(("%s:%s;" % (name, val)) if name else str(val))
    return "".join(parts)


def _date_only(value):
    s = str(value or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10].replace("-", "/")
    return s


def prepare_rows(rows, checkin_columns):
    """补齐网页导出里有、接口里没有的几个派生列（金额文本、折扣文本、签到明细、未跟进时间）。"""
    for row in rows:
        row.setdefault("amountInfoText", _format_pair_list(row.get("amountInfo"), "contractPrice"))
        row.setdefault("discountInfoText", _format_pair_list(row.get("discountInfo"), "discount"))
        if not row.get("companyTypeStr"):
            row["companyTypeStr"] = "否"
        if row.get("contractNo") in (None, "") and row.get("contractNoText"):
            row["contractNo"] = row.get("contractNoText")

        follows = row.get("_follows") or []
        # 网页导出里“未跟进天数”这一列实际是列表接口的 checkInTime（最近一次签到时间）
        lt = row.get("checkInTime") or row.get("deliverTime")
        if lt:
            row["noFollowDay"] = lt
        elif follows:
            row["noFollowDay"] = follows[0].get("time") or row.get("noFollowDay")

        signins = row.get("_signins")
        if signins is None:
            signins = follows
        for i in range(1, checkin_columns + 1):
            if i <= len(signins):
                row["checkInTime_%d" % i] = _date_only(signins[i - 1].get("time"))
                row["checkInRecord_%d" % i] = signins[i - 1].get("record") or ""
            else:
                row["checkInTime_%d" % i] = ""
                row["checkInRecord_%d" % i] = ""
    return rows

# ---------------------------------------------------------------- 主流程


def fmt_date(v):
    if not v:
        return ""
    s = str(v)
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10].replace("-", "/")
    return s


def save_raw(out_dir, run_date, rows_data):
    raw_dir = os.path.join(out_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    path = os.path.join(raw_dir, "projects_%s.json" % run_date)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows_data, f, ensure_ascii=False, indent=2, default=str)
    logging.info("原始数据已保存：%s（%d 条）", path, len(rows_data))
    return path


def build_matrix(columns, rows):
    """把列定义与数据组装成矩阵：rows[0] 是表头，其余每行是一条项目的值。

    columns 里每项是 {"prop": 接口字段名, "label": 中文表头}。
    """
    header = [c.get("label") or c.get("prop") for c in columns]
    body = []
    for row in rows:
        line = []
        for c in columns:
            v = row.get(c.get("prop"))
            line.append("" if v is None else v)
        body.append(line)
    return [header] + body


def run(args):
    cfg = load_config()
    out_dir = resolve_output_dir(cfg)
    log_file = setup_logging(out_dir)
    started = time.time()

    run_date = args.date or date.today().strftime("%Y-%m-%d")
    prefix = cfg["export"]["file_prefix"]

    logging.info("=" * 62)
    logging.info("青鸾项目全量导出开始：%s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logging.info("日志文件：%s", log_file)

    client = JBufaClient(cfg)
    client.login()

    template = None
    if cfg["export"].get("use_field_template", True):
        try:
            template = load_field_template(client, cfg)
        except Exception as exc:  # 字段模板只是锦上添花，失败不影响主流程
            logging.warning("读取导出字段配置失败：%s", exc)

    rows, stats = crawl_list(client, cfg)
    if not rows:
        logging.warning("没有抓到任何项目，可能筛选条件或账号权限有问题")
        return 2
    logging.info("列表去重后共 %d 个项目", len(rows))

    if args.no_detail:
        cfg["crawl"]["with_detail"] = False
        cfg["crawl"]["with_follow"] = False
    rows = enrich_with_detail(client, cfg, rows)

    checkin_columns = int(cfg["export"].get("checkin_columns", 50))
    raw_path = save_raw(out_dir, run_date, rows)
    rows = prepare_rows(rows, checkin_columns)

    columns = build_columns(rows, template, checkin_columns, cfg["export"].get("extra_fields") or [])
    raw_labels = [c["label"] for c in columns if re.match(r"^[\x00-\x7F]+$", str(c["label"]))]
    if raw_labels:
        logging.info("有 %d 列仍是接口原始字段名（如 %s），可在 FIELD_LABELS 里补中文名",
                     len(raw_labels), "、".join(raw_labels[:6]))
    meta = {
        "导出时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "导出账号": cfg["login"].get("username") or "(token)",
        "项目数量": len(rows),
        "字段数量": len(columns),
        "抓取来源": "；".join("标签%s:%s条" % (s["tab"], s["rows"]) for s in stats),
        "数据来源": cfg["base_url"] + "/#/project/index",
    }
    logging.info("本次抓取概要：%s", meta)

    matrix = build_matrix(columns, rows)
    json_out = getattr(args, "json_out", "") or ""
    if not json_out:
        print("✗ 必须指定输出文件：--json-out <路径>（例如 --json-out output/data.full.json）")
        return 1
    payload = map_payload.from_matrix(
        matrix, len(matrix[0]) if matrix else 0,
        source="青鸾 %s（抓取 %s）" % ((cfg.get("base_url") or "https://c.jbufa.com").rstrip("/"), run_date),
        updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    wrote, changed = map_payload.save(payload, json_out)

    logging.info("导出完成：%s（%d 条 / %d 列，耗时 %.1fs）", json_out, len(rows), len(columns), time.time() - started)
    print("\n✅ 抓取完成：%s" % json_out)
    print("   数据：%d 条 / %d 列" % (len(rows), len(columns)))
    print("   原始数据：%s" % raw_path)
    return 0


def main():
    parser = argparse.ArgumentParser(description="青鸾项目列表全量导出")
    parser.add_argument("--verify", action="store_true", help="只验证登录并统计项目数")
    parser.add_argument("--no-detail", action="store_true", help="只抓列表字段，不抓详情")
    parser.add_argument("--date", default="", help="日期标记，默认今天，如 2026-11-20")
    parser.add_argument("--json-out", default="", help="数据输出路径（必填），如 output/data.full.json")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    try:
        if args.verify:
            cfg = load_config()
            out_dir = resolve_output_dir(cfg)
            setup_logging(out_dir)
            client = JBufaClient(cfg)
            client.login()
            rows, _ = crawl_list(client, cfg)
            print("✅ 登录成功，当前账号可见项目：%d 个（去重后）" % len(rows))
            if rows:
                sample = rows[0]
                print("   示例项目：%s" % (sample.get("projectName") or sample.get("name") or "（无名称字段）"))
            return 0
        return run(args)
    except LoginError as exc:
        logging.error("登录失败：%s", exc)
        print("\n❌ 登录失败：%s" % exc)
        return 3
    except ApiError as exc:
        logging.error("接口异常：%s", exc)
        print("\n❌ 接口异常：%s" % exc)
        return 4
    except Exception:
        logging.error("未处理异常：\n%s", traceback.format_exc())
        print("\n❌ 运行出错，详见日志")
        return 1


if __name__ == "__main__":
    sys.exit(main())
