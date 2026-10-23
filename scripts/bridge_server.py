#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地 WebSocket 桥：一端接 Chrome 扩展（role=extension），一端接本仓库脚本（role=cli）。

协议（JSON 文本帧）
  cli  -> server : {"role":"cli","method":"evaluate","params":{...}}
  server -> ext  : {"id":"<uuid>","method":"evaluate","params":{...}}
  ext  -> server : {"id":"<uuid>","result"|"error":...}
  server -> cli  : {"result":...} 或 {"error":...}

用法：python bridge_server.py [--port 9444]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid

import websockets

HOST = "localhost"
PORT = 9444
TIMEOUT = 120

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("xianyu-bridge")

extension_ws = None
pending: dict[str, asyncio.Future] = {}


async def handle_extension(ws):
    global extension_ws
    extension_ws = ws
    log.info("extension connected")
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mid = msg.get("id")
            fut = pending.pop(mid, None) if mid else None
            if fut and not fut.done():
                fut.set_result({"error": msg["error"]} if msg.get("error") else {"result": msg.get("result")})
    finally:
        if extension_ws is ws:
            extension_ws = None
        log.info("extension disconnected")


async def handle_cli(ws, first):
    if first.get("method") == "__status__":
        await ws.send(json.dumps({"result": {"extension_connected": extension_ws is not None}}))
        return
    if extension_ws is None:
        await ws.send(json.dumps({"error": "extension not connected"}))
        return

    mid = str(uuid.uuid4())
    fut = asyncio.get_running_loop().create_future()
    pending[mid] = fut
    await extension_ws.send(json.dumps(
        {"id": mid, "method": first.get("method"), "params": first.get("params", {})},
        ensure_ascii=False))
    try:
        resp = await asyncio.wait_for(fut, timeout=TIMEOUT)
    except asyncio.TimeoutError:
        pending.pop(mid, None)
        resp = {"error": "extension command timeout"}
    await ws.send(json.dumps(resp, ensure_ascii=False))


async def handler(ws):
    try:
        first = json.loads(await ws.recv())
    except Exception:
        return
    role = first.get("role")
    if role == "extension":
        await handle_extension(ws)
    elif role == "cli":
        await handle_cli(ws, first)
    else:
        await ws.send(json.dumps({"error": f"unknown role: {role}"}))


async def main(port: int):
    log.info("listening on ws://%s:%s", HOST, port)
    async with websockets.serve(handler, HOST, port, max_size=80 * 1024 * 1024):
        await asyncio.Future()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    try:
        asyncio.run(main(args.port))
    except KeyboardInterrupt:
        pass
