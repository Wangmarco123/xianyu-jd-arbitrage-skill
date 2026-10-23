#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成闲鱼标题 / 描述 / 价格，并写出发布队列。

定价：闲鱼价 = 京东价 − 200（--discount 可改）
文案：固定五段（价格对比 / 为什么便宜 / 发货 / 售后 / 交易），
      并且**不承诺开具发票**（代发场景兑现不了，已被明确要求删除）。

products.json
{
  "items": [
    {"id": "100317829557", "jd_price": 12999, "short": "iPhone18ProMax",
     "spec": "512G 银色", "title_full": "Apple/苹果 iPhone 18 Pro Max 512GB 银色 手机",
     "category": "手机", "note": "需当面签收激活"}
  ]
}

用法
  python listings.py --products products.json [--discount 200] [--items-dir items]
输出
  items/<id>/desc.txt
  queue.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

BODY = """【价格】京东官方直发，在京东官方价基础上直接优惠 {discount} 元：京东现价 ¥{jd}，本单 ¥{price}。
【为什么便宜】公司发的京东礼品卡用不完，折价套现，所以让利 {discount} 元。不是翻新机、不是问题机、不是渠道货。
【发货】京东官方直发：你拍下后我在京东自营旗舰店下单，收货地址填你的，京东物流配送，运单号同步给你，京东 App 可查全程物流。{activate}
【售后】非质量问题不退不换。质量问题请直接走京东官方售后（京东自营七天无理由/保修政策），我全程协助对接，售后结论以京东官方判定为准。
【正品】京东自营旗舰店，全新未拆封、原封未拆，可当面验机；收货请全程录像开箱。
【交易】只走闲鱼平台交易，不私下转账、不加微信、不脱离平台。
【其他】价格已经很实，谢绝还价；库存按拍下顺序，拍前先确认。

商品型号：{title_full}
京东同款在售，可自行比价。
"""


def money(x: float) -> str:
    return str(int(x)) if abs(x - int(x)) < 0.01 else ("%.2f" % x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", required=True)
    ap.add_argument("--discount", type=float, default=200)
    ap.add_argument("--items-dir", default=os.path.join(ROOT, "items"))
    ap.add_argument("--queue", default=os.path.join(ROOT, "queue.json"))
    args = ap.parse_args()

    data = json.load(open(args.products, encoding="utf-8-sig"))
    items = data.get("items", data if isinstance(data, list) else [])
    queue = []
    for it in items:
        pid = str(it["id"])
        jd = float(it["jd_price"])
        price = round(jd - args.discount, 2)
        item_dir = os.path.join(args.items_dir, pid)
        imgs = sorted(glob.glob(os.path.join(item_dir, "*.jpg")))
        os.makedirs(item_dir, exist_ok=True)

        title = ("京东直发 %s %s" % (it.get("short", ""), it.get("spec", ""))).strip()[:30]
        activate = ""
        if it.get("note"):
            activate = "\n【注意】%s" % it["note"]
        body = BODY.format(discount=int(args.discount), jd=money(jd), price=money(price),
                           activate=activate, title_full=it.get("title_full", it.get("short", "")))
        with open(os.path.join(item_dir, "desc.txt"), "w", encoding="utf-8") as f:
            f.write(title + "\n\n" + body)

        queue.append({
            "tag": "%s_%s" % (it.get("category", "item"), pid),
            "id": pid,
            "desc": os.path.join("items", pid, "desc.txt"),
            "images": [os.path.join("items", pid, os.path.basename(p)) for p in imgs],
            "price": money(price),
            "jd_price": money(jd),
            "category": "其他闲置",          # 硬规则：手机类目会被拉进无忧卖
            "item_id": it.get("item_id", ""),
        })
        print("ok", pid, "jd=%s -> price=%s imgs=%d | %s" % (money(jd), money(price), len(imgs), title))

    with open(args.queue, "w", encoding="utf-8") as f:
        json.dump({"note": "发布队列：闲鱼价 = 京东价 − %d；类目固定其他闲置" % int(args.discount),
                   "items": queue}, f, ensure_ascii=False, indent=2)
    print("queue ->", args.queue, "items:", len(queue))
    return 0


if __name__ == "__main__":
    sys.exit(main())
