#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
闲鱼网页端上架。整套动作都在**用户已登录的 Chrome** 里完成，不需要扫码。

流程（每条商品）
  1. 打开 https://www.goofish.com/publish
  2. 填宝贝描述（第一行 = 标题）
  3. 填价格
  4. 上传图片
  5. 选类目「其他闲置」  ← 硬规则：手机类目会被自动拉进无忧卖，之后改不了也下不掉
  6. 选「包邮」
  7. CDP 可信点击「发布」  ← 闲鱼校验 isTrusted，JS click 无效
  8. 校验是否跳到 /item?id=xxx

用法
  python publish.py --products products.json --id 100317829557 --dry-run
  python publish.py --products products.json --id 100317829557
  python publish.py --products products.json --all          # 队列里全部，自动间隔
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from xyclient import BridgePage  # noqa: E402

PUBLISH_URL = "https://www.goofish.com/publish"
CATEGORY = "其他闲置"
DESC_SEL = '[contenteditable="true"]'
PRICE_SEL = 'input[placeholder="0.00"]'
FILE_SEL = 'input[type="file"]'


def log(**kw):
    print(json.dumps(kw, ensure_ascii=True), flush=True)


JS_PICK_CATEGORY = """(target) => {
  const sels = Array.from(document.querySelectorAll('.ant-select'));
  if (!sels.length) return 'no select';
  const box = sels[0];                       // 分类是第一个下拉
  const trigger = box.querySelector('.ant-select-selector') || box;
  trigger.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
  trigger.click();
  return 'opened';
}"""

JS_CLICK_OPTION = """(target) => {
  const opts = Array.from(document.querySelectorAll('.ant-select-item-option, [role=option], .ant-select-item'));
  const hit = opts.find(n => (n.innerText||'').trim() === target);
  if (!hit) return 'option not found: ' + opts.map(o=>(o.innerText||'').trim()).join('|');
  hit.scrollIntoView({block:'center'});
  hit.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
  hit.click();
  return 'selected';
}"""

JS_PICK_SHIP = """(() => {
  const ls = Array.from(document.querySelectorAll('label.ant-radio-wrapper'));
  const hit = ls.find(n => (n.innerText||'').trim() === '包邮');
  if (!hit) return 'no 包邮';
  if (hit.className.includes('checked')) return 'already';
  hit.querySelector('input')?.click?.();
  hit.click();
  return 'set';
})()"""

JS_MARK_PUBLISH = """(() => {
  const cands = Array.from(document.querySelectorAll('div,button,span'))
      .filter(n => (n.innerText||'').trim() === '发布' && n.getBoundingClientRect().width > 0);
  if (!cands.length) return 'no 发布 button';
  const el = cands[cands.length - 1];
  const btn = el.closest('[class*=btn],button') || el;
  btn.id = 'xy_publish_btn';
  btn.setAttribute('role', 'button');
  btn.setAttribute('tabindex', '0');
  return 'marked';
})()"""


def fill_one(bp, item) -> dict:
    pid = item["id"]
    desc = item.get("desc") or os.path.join(ROOT, "items", pid, "desc.txt")
    text = open(desc, encoding="utf-8").read()
    imgs = item.get("images") or sorted(glob.glob(os.path.join(ROOT, "items", pid, "*.jpg")))
    imgs = [p if os.path.isabs(p) else os.path.join(ROOT, p) for p in imgs]
    if not imgs:
        return {"ok": False, "reason": "no images"}

    bp.navigate(PUBLISH_URL)
    time.sleep(4)
    for _ in range(15):
        if bp.evaluate("(() => !!document.querySelector('%s'))()" % DESC_SEL):
            break
        time.sleep(1)
    else:
        return {"ok": False, "reason": "发布页未加载出描述编辑器（未登录？）"}

    bp.input_content_editable(DESC_SEL, text)
    time.sleep(0.8)
    bp.input_text(PRICE_SEL, str(item["price"]))
    time.sleep(0.5)
    bp.set_file_input(FILE_SEL, imgs[:9])
    time.sleep(2.5)

    # 类目：必须其他闲置
    try:
        bp.evaluate(JS_PICK_CATEGORY + "('" + CATEGORY + "')")
        time.sleep(1.2)
        bp.evaluate(JS_CLICK_OPTION + "('" + CATEGORY + "')")
        time.sleep(1.0)
    except Exception as e:
        log(event="category_warn", id=pid, err=str(e)[:100])

    ship = bp.evaluate(JS_PICK_SHIP)
    time.sleep(0.6)

    page = bp.text(400)
    cat_ok = CATEGORY in page
    return {"ok": True, "ship": ship, "category_ok": cat_ok, "images": len(imgs[:9]),
            "page": page[:160]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", required=True)
    ap.add_argument("--id", help="只发指定商品 id")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="只填表不点发布")
    ap.add_argument("--gap", type=int, default=60, help="两条之间的秒数")
    args = ap.parse_args()

    data = json.load(open(args.products, encoding="utf-8-sig"))
    items = data.get("items", data if isinstance(data, list) else [])
    if args.id:
        items = [x for x in items if str(x["id"]) == str(args.id)]
    elif not args.all:
        print("需要 --id 或 --all")
        return 1

    bp = BridgePage()
    if not bp.is_extension_connected():
        print("扩展未连接，先跑 python doctor.py")
        return 1
    bp.set_match("goofish.com")

    results = []
    for i, item in enumerate(items):
        if i:
            time.sleep(args.gap)
        log(event="start", id=item["id"], price=item["price"])
        r = fill_one(bp, item)
        log(event="filled", id=item["id"], **r)
        if not r.get("ok"):
            results.append({"id": item["id"], "error": r.get("reason")})
            continue
        if args.dry_run:
            shot = os.path.join(ROOT, "data", "dryrun_%s.png" % item["id"])
            os.makedirs(os.path.dirname(shot), exist_ok=True)
            try:
                bp.screenshot(shot)
            except Exception:
                shot = None
            log(event="dry_run_stop", id=item["id"], screenshot=shot,
                msg="请人工确认表单（类目=其他闲置 / 包邮 / 图 6 张），确认后再跑不带 --dry-run")
            results.append({"id": item["id"], "dry_run": True, "screenshot": shot})
            continue

        mark = bp.evaluate(JS_MARK_PUBLISH)
        time.sleep(0.6)
        try:
            bp.click_trusted(selector="#xy_publish_btn")
        except Exception as e:
            log(event="click_err", id=item["id"], err=str(e)[:120])
        time.sleep(4)
        url = bp.get_url()
        if "/item?" in url and "id=" in url:
            item_id = url.split("id=")[1].split("&")[0]
            log(event="published", id=item["id"], item_id=item_id, url=url[:90])
            item["item_id"] = item_id
            results.append({"id": item["id"], "item_id": item_id})
        else:
            shot = os.path.join(ROOT, "data", "fail_%s.png" % item["id"])
            try:
                bp.screenshot(shot)
            except Exception:
                pass
            log(event="publish_failed", id=item["id"], mark=mark, url=url[:90], screenshot=shot,
                hint="常见原因：宝贝所在地未选 / 类目未选中 / 图片还在上传")
            results.append({"id": item["id"], "error": "no item url", "url": url})

    with open(args.products, "w", encoding="utf-8") as f:
        json.dump(data if isinstance(data, dict) else {"items": items}, f, ensure_ascii=False, indent=2)
    log(event="done", results=results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
