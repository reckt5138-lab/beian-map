r"""data.json → data.enc（AES-256-GCM 密文），给公开仓库用。

为什么加密：网页要放在公网（GitHub Pages / Pages）才能"随时打开"，仓库又是公开的，
明文 data.json 等于把 18 条客户信息摊在互联网上。加密后仓库里看到的是密文，
页面用构建时写进去的密钥解密——顺手扒仓库、搜索引擎都拿不到明文。

代价（必须知道）：密钥在页面里，谁打开那个网页都能解密，所以这是"防顺手翻"，
不是真正的保密。要真正控权，得用私有仓库 + 带鉴权的 Cloudflare Pages/Worker。

    python app\encrypt_data.py                       # data.json → data.enc
    python app\encrypt_data.py --key <base64>        # 临时指定密钥
"""

import argparse
import base64
import json
import os
import secrets
import sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "config", "config.json")
KEY_PATH = os.path.join(BASE, "config", "data_key.txt")


def read_key():
    try:
        with open(KEY_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def ensure_key(create=True):
    """密钥：config\\data_key.txt 优先，其次 config.json 的 publish.data_key。"""
    key = read_key()
    if key:
        return key
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            key = ((json.load(f).get("publish") or {}).get("data_key") or "").strip()
    except Exception:
        key = ""
    if key:
        return key
    if not create:
        raise SystemExit("没有密钥：先跑一次 python app\\encrypt_data.py，或手动放 config\\data_key.txt")
    key = base64.b64encode(secrets.token_bytes(32)).decode()
    with open(KEY_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(key + "\n")
    print("已生成新密钥：config\\data_key.txt（别提交、别外发；丢了就得重新加密 + 重新构建页面）")
    return key


def encrypt(payload_obj, key_b64):
    raw = json.dumps(payload_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    key = base64.b64decode(key_b64)
    if len(key) != 32:
        raise SystemExit("密钥必须是 32 字节（base64 编码 44 个字符）")
    iv = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(iv, raw, None)
    return {
        "alg": "AES-GCM",
        "v": 1,
        "iv": base64.b64encode(iv).decode(),
        "ct": base64.b64encode(ct).decode(),
        "updated": payload_obj.get("updated") or "",
        "count": payload_obj.get("count") or 0,
        "generated_at": payload_obj.get("generated_at") or "",
    }


def main():
    ap = argparse.ArgumentParser(description="把 data.json 加密成 data.enc")
    ap.add_argument("--in", dest="src", default=os.path.join(BASE, "data.json"))
    ap.add_argument("--out", dest="dst", default=os.path.join(BASE, "data.enc"))
    ap.add_argument("--key", default="", help="base64 密钥；默认读 config\\data_key.txt")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    with open(args.src, "r", encoding="utf-8-sig") as f:
        payload = json.load(f)
    if not payload.get("projects"):
        raise SystemExit("data.json 里没有 projects，先跑 crawl_to_data.py")

    key = args.key.strip() or ensure_key()
    env = encrypt(payload, key)
    with open(args.dst, "w", encoding="utf-8", newline="\n") as f:
        json.dump(env, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print("已加密：%s（%d 条 / %d 字节密文 / 密钥指纹 %s…）"
          % (args.dst, payload.get("count", 0), os.path.getsize(args.dst), key[:6]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
