#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
环境自检。任务开始前先跑这个，全绿再往下走。
用法：python doctor.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

OK, BAD, WARN = "OK", "FAIL", "WARN"
results = []


def add(name, status, detail=""):
    results.append({"check": name, "status": status, "detail": detail})


def check_python():
    v = sys.version_info
    add("python", OK if v >= (3, 9) else BAD, f"{v.major}.{v.minor}.{v.micro}")


def check_deps():
    try:
        import websockets  # noqa: F401
        add("websockets", OK)
    except Exception:
        add("websockets", BAD, "pip install websockets")
    try:
        from PIL import Image  # noqa: F401
        add("Pillow", OK)
    except Exception:
        add("Pillow", WARN, "pip install pillow（图片转白底 JPG 需要）")


def check_extension_files():
    ext = os.path.join(os.path.dirname(HERE), "extension")
    need = ["manifest.json", "background.js", "content.js"]
    missing = [f for f in need if not os.path.exists(os.path.join(ext, f))]
    if missing:
        add("extension files", BAD, "缺少: " + ", ".join(missing))
        return
    src = open(os.path.join(ext, "background.js"), encoding="utf-8", errors="replace").read()
    patched = ('case "set_match"' in src) and ("includes(MATCH)" in src)
    add("extension patched", OK if patched else BAD,
        "含 set_match 补丁" if patched else "background.js 是原版（只有 goofish.com），请用本仓库 extension/")


def check_bridge():
    from xyclient import BridgePage
    bp = BridgePage(autostart=True)
    up = bp.is_server_running()
    add("bridge server", OK if up else BAD, "ws://localhost:9444")
    if not up:
        return
    conn = bp.is_extension_connected()
    add("extension", OK if conn else BAD,
        "已连接" if conn else "未连接：检查 Chrome 是否开着 Xianyu Bridge 扩展")
    if not conn:
        return
    if bp.supports_set_match():
        add("set_match", OK, f"当前 match={bp.call('get_match')}")
    else:
        add("set_match", BAD, "扩展不支持 set_match → 加载的是旧扩展，重新加载 extension/")


def check_chrome():
    chrome = None
    for p in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ]:
        if p and os.path.exists(p):
            chrome = p
            break
    add("chrome", OK if chrome else WARN, chrome or "未找到 Chrome（脚本需要你手动开着的 Chrome）")


def main():
    check_python()
    check_deps()
    check_extension_files()
    check_chrome()
    check_bridge()

    width = max(len(r["check"]) for r in results)
    worst = OK
    for r in results:
        print(f"{r['check']:<{width}}  {r['status']:<4}  {r['detail']}")
        if r["status"] == BAD:
            worst = BAD
    print()
    if worst == OK:
        print("全部通过，可以开工。")
        return 0
    print("有 FAIL 项，先按 detail 修复。常见原因见 references/pitfalls.md")
    return 1


if __name__ == "__main__":
    sys.exit(main())
