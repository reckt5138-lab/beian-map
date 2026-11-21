"""本地看地图：起一个只监听 127.0.0.1 的 HTTP 服务并自动打开浏览器。

为什么必须起服务：浏览器在 file:// 下禁止 fetch，直接双击 index.html 读不到云端数据。
用法：python scripts/local_server.py [--port 8080] [--no-browser]
"""

import argparse
import functools
import http.server
import os
import socket
import socketserver
import sys
import threading
import webbrowser

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port(preferred):
    for port in range(preferred, preferred + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # 安静模式，避免刷屏

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(os.path.join(BASE, "index.html")):
        print("✗ 还没有 index.html，先跑一次：python -m app.main publish")
        return 2

    port = free_port(args.port)
    handler = functools.partial(Handler, directory=BASE)
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        url = "http://127.0.0.1:%d/index.html" % port
        print("本地地图已启动：%s" % url)
        print("只监听本机（127.0.0.1），局域网和手机默认访问不到；按 Ctrl+C 关闭服务。")
        if not args.no_browser:
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务已关闭。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
