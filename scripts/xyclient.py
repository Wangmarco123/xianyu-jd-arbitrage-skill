#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bridge 客户端：让脚本在「用户已登录的 Chrome」里执行 JS / 可信点击 / 截图。

关键点
- `set_match("jd.com")` 让扩展把目标标签页切到京东；切回闲鱼用 `set_match("goofish.com")`。
  这是本仓库扩展的补丁（原生版本只认 goofish.com）。
- 发布之类被校验 isTrusted 的按钮，必须用 `click_trusted()`（扩展内部走 chrome.debugger）。
"""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import time

import websockets.sync.client as ws_client

BRIDGE_URL = "ws://localhost:9444"
HERE = os.path.dirname(os.path.abspath(__file__))


class BridgeError(RuntimeError):
    pass


def _port_open(host="127.0.0.1", port=9444, timeout=0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_server(quiet=True) -> bool:
    """桥没起就以子进程拉起，返回是否可用。"""
    if _port_open():
        return True
    creation = 0
    if os.name == "nt":
        creation = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        subprocess.Popen([sys.executable, os.path.join(HERE, "bridge_server.py")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation)
    except Exception:
        return False
    for _ in range(20):
        time.sleep(0.3)
        if _port_open():
            return True
    return False


class BridgePage:
    def __init__(self, url: str = BRIDGE_URL, autostart: bool = True):
        self.url = url
        if autostart:
            ensure_server()

    # ---------- low level ----------
    def call(self, method: str, params: dict | None = None):
        payload = {"role": "cli", "method": method}
        if params:
            payload["params"] = params
        try:
            with ws_client.connect(self.url, max_size=80 * 1024 * 1024) as ws:
                ws.send(json.dumps(payload, ensure_ascii=False))
                raw = ws.recv(timeout=130)
        except OSError as exc:
            raise BridgeError(f"连不上 bridge server ({self.url}): {exc}") from exc
        resp = json.loads(raw)
        if resp.get("error"):
            raise BridgeError(str(resp["error"]))
        return resp.get("result")

    # ---------- status ----------
    def is_server_running(self) -> bool:
        try:
            with ws_client.connect(self.url, max_size=1024 * 1024) as ws:
                ws.send(json.dumps({"role": "cli", "method": "__status__"}))
                ws.recv(timeout=5)
            return True
        except Exception:
            return False

    def is_extension_connected(self) -> bool:
        try:
            with ws_client.connect(self.url, max_size=1024 * 1024) as ws:
                ws.send(json.dumps({"role": "cli", "method": "__status__"}))
                raw = ws.recv(timeout=5)
            return bool(json.loads(raw).get("result", {}).get("extension_connected"))
        except Exception:
            return False

    def supports_set_match(self) -> bool:
        try:
            return bool(self.call("get_match"))
        except BridgeError:
            return False

    def set_match(self, value: str) -> str:
        """切换扩展的目标标签页匹配串：goofish.com / jd.com"""
        return str(self.call("set_match", {"value": value}))

    # ---------- navigation ----------
    def navigate(self, url: str):
        return self.call("navigate", {"url": url})

    def wait_for_load(self, timeout_s: float = 60):
        return self.call("wait_for_load", {"timeout": int(timeout_s * 1000)})

    def get_url(self) -> str:
        return str(self.call("get_url") or "")

    def get_title(self) -> str:
        return str(self.call("get_title") or "")

    # ---------- dom ----------
    def evaluate(self, expression: str):
        return self.call("evaluate", {"expression": expression})

    def js(self, expression: str):
        return self.evaluate(expression)

    def text(self, limit: int = 2000) -> str:
        return str(self.evaluate(
            "(() => (document.body.innerText || '').replace(/\\s+/g,' ').slice(0,%d))()" % limit))

    def wait_for_selector(self, selector: str, timeout_s: float = 20) -> bool:
        return bool(self.call("wait_for_selector",
                              {"selector": selector, "timeout": int(timeout_s * 1000)}))

    def count(self, selector: str) -> int:
        return int(self.call("get_elements_count", {"selector": selector}) or 0)

    # ---------- input ----------
    def input_text(self, selector: str, text: str):
        return self.call("input_text", {"selector": selector, "text": text})

    def input_content_editable(self, selector: str, text: str):
        return self.call("input_content_editable", {"selector": selector, "text": text})

    def click(self, selector: str):
        return self.call("click_element", {"selector": selector})

    def click_text(self, text: str):
        return self.call("click_text", {"text": text})

    def click_trusted(self, selector: str = "", text: str = ""):
        """CDP 真实鼠标事件（isTrusted=true）。发布按钮必须用这个。"""
        return self.call("click_trusted", {"selector": selector, "text": text})

    def set_file_input(self, selector: str, files: list[str]):
        return self.call("set_file_input",
                         {"selector": selector, "files": [os.path.abspath(p) for p in files]})

    # ---------- misc ----------
    def screenshot(self, path: str) -> str:
        data_url = str(self.call("screenshot"))
        if "base64," not in data_url:
            raise BridgeError("invalid screenshot payload")
        with open(path, "wb") as f:
            f.write(base64.b64decode(data_url.split("base64,", 1)[1]))
        return path

    def get_cookies(self, domain: str = "goofish.com") -> list[dict]:
        return list(self.call("get_cookies", {"domain": domain}) or [])


if __name__ == "__main__":
    bp = BridgePage()
    print(json.dumps({
        "server": bp.is_server_running(),
        "extension": bp.is_extension_connected(),
        "set_match": bp.supports_set_match(),
        "match": bp.call("get_match") if bp.supports_set_match() else None,
        "url": bp.get_url() if bp.is_extension_connected() else None,
    }, ensure_ascii=False, indent=2))
