#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
京东「只搜不点详情」取价。详情页是封禁主因，本脚本永不打开 item 页。

特性
- 节流：默认 45 秒/关键词（实测安全）
- 熔断：任一关键词返回 0 条 → 立即终止整轮（0 条 = 软封信号）
- 价格体检：过滤定金/分期/秒杀/需签收激活的异常低价
- 只保留自营 + 价格 ≥ 门槛

用法
  python jd_search.py --scope scope.jsonc --max-kw 3
  python jd_search.py --keywords "iPhone 18" "MacBook Air"
输出
  data/search_<kw>.json   每个关键词的原始列表 + qualified
  data/search_summary.json 本轮汇总（被熔断时 stopped=true）
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from xyclient import BridgePage  # noqa: E402

DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)

EXTRACT_JS = r"""
(() => {
  const out = [], seen = new Set();
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  document.querySelectorAll('[data-sku]').forEach(el => {
    const sku = el.getAttribute('data-sku');
    if (!sku || seen.has(sku)) return;
    seen.add(sku);
    const txt = el.innerText || '';
    const t = el.querySelector('[title]');
    const title = t ? (t.getAttribute('title') || '') : clean(txt.split('\n')[0] || '');
    const m = txt.match(/[¥￥]\s*([0-9][0-9,]*(?:\.[0-9]+)?)/);
    out.push({
      sku,
      title: clean(title).slice(0, 90),
      price: m ? m[1].replace(/,/g, '') : '',
      self: /自营/.test(txt),
      presale: /预约|定金|秒杀|需签收激活/.test(txt)
    });
  });
  return JSON.stringify(out);
})()
"""


def log(**kw):
    print(json.dumps(kw, ensure_ascii=True), flush=True)


def load_scope(path: str) -> tuple[list[str], float]:
    """兼容两种写法：YAML 风格 (min_price: 9000 / keywords: [..]) 与 JSON 风格 ("min_price": 9000)。"""
    txt = open(path, encoding="utf-8-sig").read()
    txt = re.sub(r"^\s*(#|//).*$", "", txt, flags=re.M)   # 去行注释
    min_price = 9000
    m = re.search(r'"?min_price"?\s*:\s*(\d+)', txt)
    if m:
        min_price = float(m.group(1))
    kws: list[str] = []
    for q in re.findall(r'"?keywords"?\s*:\s*\[([^\]]+)\]', txt):
        kws += re.findall(r'"([^"]+)"', q)
    return kws, min_price


def price_ok(price: str, min_price: float) -> bool:
    try:
        p = float(price)
    except Exception:
        return False
    if p < min_price:
        return False
    if "." in price and p < min_price * 2:   # 分期月供形态
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default=os.path.join(ROOT, "scope.jsonc"))
    ap.add_argument("--keywords", nargs="*")
    ap.add_argument("--max-kw", type=int, default=6)
    ap.add_argument("--throttle", type=int, default=45, help="每个关键词之间的秒数，实测 45 安全")
    args = ap.parse_args()

    kws, min_price = load_scope(args.scope) if os.path.exists(args.scope) else ([], 9000)
    if args.keywords:
        kws = args.keywords
    kws = kws[: args.max_kw]
    if not kws:
        print("没有关键词：检查 scope.jsonc 或传 --keywords")
        return 1

    bp = BridgePage()
    if not bp.is_extension_connected():
        print("扩展未连接，先跑 python doctor.py")
        return 1
    bp.set_match("jd.com")

    summary, stopped = [], False
    try:
        for i, kw in enumerate(kws):
            if i:
                log(event="throttle", sleep_s=args.throttle)
                time.sleep(args.throttle)
            url = "https://search.jd.com/Search?keyword=%s&enc=utf-8" % urllib.parse.quote(kw)
            try:
                bp.navigate(url)
                time.sleep(4)
                n = bp.count("[data-sku]")
                if not n:
                    log(event="EMPTY_RESULT_SOFT_BLOCK", kw=kw,
                        action="立即停止本轮（0 条=软封），静置 ≥2 小时")
                    summary.append({"kw": kw, "total": 0, "blocked": True})
                    stopped = True
                    break
                items = json.loads(bp.evaluate(EXTRACT_JS))
            except Exception as e:
                log(event="err", kw=kw, error=str(e)[:140])
                continue

            self_items = [x for x in items if x["self"]]
            qualified = [x for x in self_items if price_ok(x["price"], min_price)]
            qualified.sort(key=lambda x: float(x["price"]))
            fname = os.path.join(DATA, "search_%s.json" % re.sub(r"[^\w]+", "_", kw))
            with open(fname, "w", encoding="utf-8") as f:
                json.dump({"keyword": kw, "total": len(items), "self": len(self_items),
                           "qualified": qualified, "all": items}, f, ensure_ascii=False, indent=2)
            summary.append({"kw": kw, "total": len(items), "self": len(self_items),
                            "qualified": len(qualified)})
            log(event="kw_ok", kw=kw, total=len(items), qualified=len(qualified),
                top=[(x["sku"], x["price"], x["title"][:24]) for x in qualified[:3]])
    finally:
        bp.set_match("goofish.com")
        with open(os.path.join(DATA, "search_summary.json"), "w", encoding="utf-8") as f:
            json.dump({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "min_price": min_price,
                       "summary": summary, "stopped": stopped}, f, ensure_ascii=False, indent=2)
        log(event="done", keywords=len(summary), stopped=stopped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
