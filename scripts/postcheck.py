#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发布后体检（不可跳过）。每条发完 60 秒内跑一次。

检查
  1. copy_ok         线上描述是否是最新版：含「【售后】」、含「优惠」、不含「发票」
  2. wuyoumai_marker 是否出现「无忧卖 / 托管 / 代卖」字样
  3. action_buttons  是否有「下架 / 删除」按钮
  4. 若 copy_ok=false 且 wuyoumai_marker=true → 基本可判定被无忧卖锁死，停止继续发布

用法
  python postcheck.py <item_id> [<item_id> ...]
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from xyclient import BridgePage  # noqa: E402

WUYOU_WORDS = ("无忧卖", "托管", "代卖", "无忧")


def log(**kw):
    print(json.dumps(kw, ensure_ascii=True), flush=True)


def check(bp, iid: str) -> dict:
    bp.navigate("https://www.goofish.com/item?id=%s" % iid)
    time.sleep(5)
    t = bp.text(4000)
    has_after = "【售后】" in t
    has_invoice = "发票" in t
    has_new_price = "优惠" in t
    wuyou = any(w in t for w in WUYOU_WORDS)
    btns = bp.evaluate(
        "(() => Array.from(document.querySelectorAll('div,span,button'))"
        ".filter(n=>n.getBoundingClientRect().width>0 && /^(下架|删除|编辑)$/.test((n.innerText||'').trim()))"
        ".map(n=>(n.innerText||'').trim()))()")
    return {
        "item_id": iid,
        "copy_ok": bool(has_after and has_new_price and not has_invoice),
        "has_aftersale": has_after,
        "invoice_present": has_invoice,
        "new_price_wording": has_new_price,
        "wuyoumai_marker": wuyou,
        "action_buttons": btns,
        "verdict": ("LOCKED_BY_WUYOUMAI" if (wuyou and not has_after)
                    else ("OK" if (has_after and not has_invoice) else "COPY_NOT_APPLIED")),
    }


def main(ids):
    bp = BridgePage()
    if not bp.is_extension_connected():
        print("扩展未连接，先跑 python doctor.py")
        return 1
    bp.set_match("goofish.com")
    bad = 0
    for iid in ids:
        try:
            r = check(bp, iid)
            log(event="postcheck", **r)
            if r["verdict"] != "OK":
                bad += 1
        except Exception as e:
            log(event="err", item_id=iid, error=str(e)[:120])
            bad += 1
        time.sleep(3)
    if bad:
        print("\n有 %d 条异常。若判定 LOCKED_BY_WUYOUMAI：停止继续发布，去闲鱼 APP 找无忧卖退出/联系客服，"
              "不要在网页端反复重试。详见 references/pitfalls.md" % bad)
        return 2
    print("\n全部正常。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
