r"""地图数据服务：把飞书表格实时变成手机能打开的网页 + JSON。

页面本身 100% 是静态 HTML/JS（所有渲染、地图、交互都在浏览器里跑），
这里只做两件事：
    1. 把 备案项目地图.html 发出去；
    2. 用自建应用身份读飞书表格，吐 /projects.json（默认缓存 90 秒）。

用法：
    python app\web_server.py                 # 0.0.0.0:8787，手机同网段可直接访问
    python app\web_server.py --port 9000
    python app\web_server.py --host 127.0.0.1 --no-lan
"""

import argparse
import json
import os
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import sheet_to_projects as src

BASE_DIR = src.BASE_DIR
HTML_FILE = os.path.join(BASE_DIR, "备案项目地图.html")
CACHE_SECONDS = 90

_cache = {"at": 0.0, "body": b"", "err": None}
_lock = threading.Lock()


def payload_json(force=False):
    with _lock:
        now = time.time()
        if not force and _cache["body"] and now - _cache["at"] < CACHE_SECONDS:
            return _cache["body"], _cache["err"]
        try:
            body = json.dumps(src.build_payload(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            _cache.update(at=now, body=body, err=None)
        except Exception as exc:
            _cache.update(at=now, err=str(exc))
            body = json.dumps({"error": str(exc), "projects": [], "count": 0}, ensure_ascii=False).encode("utf-8")
        return body, _cache["err"]


class Handler(BaseHTTPRequestHandler):
    server_version = "BeianMap/1.0"

    def log_message(self, fmt, *args):
        sys.stdout.write("%s  %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path in ("/projects.json", "/api/projects", "/data/projects.json"):
                force = "refresh=1" in (urlparse(self.path).query or "")
                body, err = payload_json(force)
                extra = {"X-Data-Error": err} if err else None
                self._send(200, body, "application/json; charset=utf-8", extra)
                return
            if path in ("/", "/index.html", "/map", "/map.html"):
                if not os.path.isfile(HTML_FILE):
                    self._send(404, "找不到 备案项目地图.html".encode("utf-8"), "text/plain; charset=utf-8")
                    return
                with open(HTML_FILE, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
                return
            if path == "/health":
                body = json.dumps({"ok": True, "time": time.strftime("%Y-%m-%d %H:%M:%S")}).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
                return
            self._send(404, b"not found", "text/plain; charset=utf-8")
        except Exception:
            self._send(500, traceback.format_exc().encode("utf-8"), "text/plain; charset=utf-8")


def lan_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("223.5.5.5", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            ips.append(ip)
    except Exception:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    return ips


def serve(host="0.0.0.0", port=8787, lan=True, blocking=True):
    src.load_conf()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print("地图服务已启动：%s:%d" % (host, port))
    print("  本机：http://127.0.0.1:%d/" % port)
    if lan:
        for ip in lan_ips():
            print("  手机：http://%s:%d/  （同一网络/公网可达时）" % (ip, port))
    print("  数据接口：/projects.json （读飞书表格，缓存 %ds）" % CACHE_SECONDS)
    if not blocking:
        t = threading.Thread(target=httpd.serve_forever, name="map-http", daemon=True)
        t.start()
        return httpd
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return httpd


def main():
    ap = argparse.ArgumentParser(description="备案项目地图数据服务")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--no-lan", action="store_true", help="只监听本机，不打印局域网地址")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    serve(args.host, args.port, lan=not args.no_lan)


if __name__ == "__main__":
    main()
