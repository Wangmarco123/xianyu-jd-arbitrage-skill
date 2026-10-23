#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
品牌官网取图 → 白底 JPG（闲鱼可直接上传）。

为什么不用京东主图：京东自营主图带双 11 促销条 + "JD.COM 京东" 水印 + 促销价，
搬去闲鱼会造成价格打架、并可能被判搬运/引流。

用法
  # 1) 列出某产品页可用的官方图名（苹果）
  python images.py apple --list-page https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro

  # 2) 下载指定图名到商品目录（会清空该目录已有 jpg）
  python images.py apple --item-dir items/100317829557 ^
      --names iphone-18-pro-max-finish-select-silver-202609 ^
              iphone-18-pro-model-unselect-gallery-1-202609

  # 3) 通用官网直链（华为/佳能/索尼/尼康/富士等）
  python images.py urls --item-dir items/xxx --urls https://a.jpg https://b.png

苹果图源模板
  https://store.storeimages.cdn-apple.com/4982/as-images.apple.com/is/<imageName>?wid=1200&hei=1200&fmt=jpeg&qlt=90
  imageName 从 https://www.apple.com.cn/shop/buy-<产品线> 页面的 "imageName":"..." 字段抓取。
  注意代际：老产品页（如 ipad-air）可能仍是上一代机型图，务必核对。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36")
APPLE_TMPL = ("https://store.storeimages.cdn-apple.com/4982/as-images.apple.com/is/"
              "%s?wid=1200&hei=1200&fmt=jpeg&qlt=90")


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.apple.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clear_jpgs(item_dir: str):
    os.makedirs(item_dir, exist_ok=True)
    for f in os.listdir(item_dir):
        if f.lower().endswith((".jpg", ".jpeg")):
            os.remove(os.path.join(item_dir, f))


def save_jpg(raw: bytes, path: str) -> bool:
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    if im.width > 1600:
        im = im.resize((1600, int(1600 * im.height / im.width)), Image.LANCZOS)
    im.save(path, "JPEG", quality=92)
    return True


def cmd_apple(args):
    if args.list_page:
        html = fetch(args.list_page).decode("utf-8", "ignore")
        names = sorted(set(re.findall(r'"imageName":"([^"]+)"', html)))
        gens = sorted(set(re.findall(r"(20\d{4})", " ".join(names))))
        print(json.dumps({"page": args.list_page, "generations": gens,
                          "count": len(names),
                          "names": [n for n in names if re.search(r"(finish-select|witb|gallery|hero)", n)]},
                         ensure_ascii=False, indent=2))
        return 0
    if not args.item_dir or not args.names:
        print("需要 --item-dir 和 --names")
        return 1
    clear_jpgs(args.item_dir)
    saved = 0
    for name in args.names:
        try:
            raw = fetch(APPLE_TMPL % name)
            if len(raw) < 15000:
                print("skip(small)", name)
                continue
            saved += 1
            out = os.path.join(args.item_dir, "%02d.jpg" % saved)
            save_jpg(raw, out)
            print("ok", saved, name, len(raw))
        except Exception as e:
            print("err", name, str(e)[:90])
    print("saved", saved)
    return 0 if saved else 1


def cmd_urls(args):
    if not args.item_dir or not args.urls:
        print("需要 --item-dir 和 --urls")
        return 1
    clear_jpgs(args.item_dir)
    saved = 0
    for u in args.urls:
        try:
            raw = fetch(u)
            if len(raw) < 8000:
                print("skip(small)", u[:60])
                continue
            saved += 1
            save_jpg(raw, os.path.join(args.item_dir, "%02d.jpg" % saved))
            print("ok", saved, u[:80])
        except Exception as e:
            print("err", u[:60], str(e)[:90])
    print("saved", saved)
    return 0 if saved else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("apple", help="苹果官方 CDN 图")
    a.add_argument("--list-page", help="列出该产品页可用 imageName")
    a.add_argument("--item-dir")
    a.add_argument("--names", nargs="*")
    a.set_defaults(func=cmd_apple)

    u = sub.add_parser("urls", help="通用官网图片直链")
    u.add_argument("--item-dir", required=True)
    u.add_argument("--urls", nargs="+", required=True)
    u.set_defaults(func=cmd_urls)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
