---
name: xianyu-jd-arbitrage
description: |
  闲鱼·京东代发自动化：京东「只搜不点详情」取价（内置节流与熔断）、品牌官网取无水印产品图、
  闲鱼网页端批量上架（CDP 可信点击绕 isTrusted）、发布后体检（是否被无忧卖锁定 / 文案是否生效）。
  发布价规则：闲鱼价 = 京东价 − 200；文案固定「京东官方直发 / 优惠 200 / 公司礼品卡折价套现 /
  非质量问题不退不换 / 质量问题走京东官方售后」，且不承诺开具发票。
  何时调用：用户要把京东/官网商品搬去闲鱼卖、问「京东价多少顺便上架」、要做代发/无货源上架、
  要批量发布闲鱼商品、要测京东风控节流、要判断闲鱼宝贝是否被无忧卖锁住时。
  trigger 信号：闲鱼、上架、代发、无货源、京东取价、京东直发、无忧卖、isTrusted、发布没反应、
  苹果/华为/相机/镜头上架、闲鱼改不了文案、闲鱼下架不生效。
  不适用于：闲鱼标题 SEO（用 xianyu-title-seo）、图片精修/主图设计（用 xianyu-product-images）、
  违禁词检测（用 xianyu-prohibited-checker）、抖音/小红书内容发布。
---

# 闲鱼·京东代发自动化

把「京东取价 → 官网取图 → 闲鱼上架 → 发布体检」串成一条可重复执行的流水线。
所有浏览器操作都复用**用户自己已登录的 Chrome**（通过本仓库的 Xianyu Bridge 扩展），不新建浏览器、不碰 Cookie。

## 前置检查（每次任务开始先跑）

```bash
python scripts/doctor.py
```

必须全部 OK 才能继续：
- `websockets OK` / `Pillow OK`
- `bridge server: up`（没起就跑 `python scripts/bridge_server.py`）
- `extension: connected`
- `set_match: ok` ← 这条最关键，失败说明加载的是没打补丁的旧扩展

## 六条硬规则（违反必踩坑）

1. **发布类目固定 `其他闲置`**
   > 手机类目发布后会被自动纳入「无忧卖」，之后文案改不动、下架/删除点了不生效。
   > 实测对照：同账号同文案，手机类目被锁死，其他闲置可正常编辑。服务费两者相同（1.6%）。

2. **绝不打开京东商品详情页**（`item.jd.com` / `item.m.jd.com`）
   > 详情页是封禁主因：连续抓 11–13 个即封 60 分钟，解封后只够再抓 1 个。
   > 只用搜索页 `search.jd.com` 取「标题 + 价格 + 是否自营」。

3. **京东搜索返回 0 条 = 软封信号，立即终止本轮**
   > 不要重试。静置 ≥2 小时后单条测试，恢复正常（30 条）再继续。

4. **图片一律用品牌官网**，不用京东主图
   > 京东自营主图普遍带「双11促销条 + JD.COM 水印 + 促销价」，搬去闲鱼会价格打架、判搬运。

5. **发布按钮必须用 CDP 可信点击**
   > 闲鱼校验 `event.isTrusted`，`element.click()` 无效。用 `xyclient.py` 的 `click_trusted()`。

6. **发布后 60 秒内必须体检**
   > `python scripts/postcheck.py <item_id>`：确认「文案已生效 / 无无忧卖标记 / 下架按钮可用」。
   > 一旦发现被无忧卖锁定：**立即停止后续同类发布**，不要反复重试（只增加异常操作记录）。

## 定价规则

```
闲鱼标价 = 京东价 − 200
实际到手 = 京东价 − 200 − 京东价 × 1.6%（鱼小铺服务费，按到售价计）
```

**价格口径坑**：京东搜索页显示的多是「券后到手价」，比详情页 `jdPrice` 低几百
（实测 iPhone 18 Pro 512G：11699 vs 11999）。只用搜索价定价时：
- 要么在文案里注明「以京东页面实际显示为准」；
- 要么加 300 元安全垫再减 200，避免倒挂亏损。

## 文案规则（直接照抄，改动前看 references/listing-copy.md）

必备五段：价格对比、为什么便宜（礼品卡折价）、发货方式（京东官方直发）、
售后（非质量问题不退不换 / 质量问题走京东官方售后）、交易方式（只走平台）。

**绝对不要写**：
- 「可开发票 / 提供发票 / 原封带票」—— 代发场景兑现不了，且已被用户明确要求删除；
- 「全新正品保证赔偿」等无法自证的承诺；
- 微信/QQ/手机号等站外联系方式（直接违规）；
- 其他平台的商品链接。

## 标准流程

### Step 1 取价（京东搜索页，不点详情）

```bash
python scripts/jd_search.py --scope scope.jsonc --max-kw 3
# 输出 data/search_<关键词>.json，qualified 字段已过滤：自营 + 价格 ≥ 门槛 + 排除定金/分期
```

熔断逻辑：任一关键词返回 0 条 → 立刻结束整轮并写 `data/search_summary.json`。
节流：默认 45 秒/关键词，单轮 ≤6 个。**不要调小**。

### Step 2 取图（品牌官网）

```bash
# 苹果：先列出可用图片名
python scripts/images.py apple --list-page https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro
# 下载（可多个 name）
python scripts/images.py apple --item-dir items/100317829557 \
  --names iphone-18-pro-max-finish-select-silver-202609
```

非苹果品牌：用 `--urls` 传入官网图片直链（脚本会转白底 JPG）。
华为/相机/镜头的图源补充方法见 `references/pitfalls.md` 规则 7。

### Step 3 生成文案与队列

```bash
python scripts/listings.py --products products.json
# 产出 items/<id>/desc.txt + queue.json（price = jd_price - 200）
```

### Step 4 上架

```bash
python scripts/publish.py --products products.json --id 100317829557 --dry-run   # 只填表
python scripts/publish.py --products products.json --id 100317829557            # 真发
```

必须走 `publish.py`，它会：填描述 → 填价格 → 上传图 → 选「其他闲置」→ 选「包邮」→ 可信点击发布。

### Step 5 体检（不可跳过）

```bash
python scripts/postcheck.py <item_id> [...]
```

判据：
- `copy_ok: true` ← 文案已生效（含「【售后】」且不含「发票」）
- `wuyoumai_marker: false`
- `action_buttons` 含「下架」「删除」

任一条不符 → 停止本轮，按硬规则 6 处理。

## 命令速查

| 脚本 | 用途 |
|---|---|
| `doctor.py` | 环境自检 |
| `bridge_server.py` | 起本地 WebSocket 桥（常驻） |
| `jd_search.py` | 京东只搜取价 + 熔断 |
| `images.py` | 官网图下载 → 白底 JPG |
| `listings.py` | 文案/价格/队列生成 |
| `publish.py` | 闲鱼填表 + 可信点击发布 |
| `postcheck.py` | 发布后体检 |

## 失败处理

| 现象 | 原因 | 处理 |
|---|---|---|
| `set_match: UNSUPPORTED` | 加载了旧扩展 | 删旧扩展，重新加载 `extension/`，点一次「重新加载」 |
| `extension: disconnected` | 扩展没连上桥 | 确认 `bridge_server.py` 在跑；`chrome://extensions` 里点重新加载 |
| 京东搜索 0 条 | 软封 | 停 ≥2 小时，单条重测 |
| 京东详情页跳 `limit.html` | 详情页封禁 | 本流程不该打开详情页；若出现立即停止 |
| 发布点了没反应 | isTrusted 校验 | 必须用 `click_trusted`，不能用 JS click |
| 发布后改文案不生效 | 被无忧卖锁定 | 停止重试；走 APP/客服解锁 |
| 弹窗里按钮点不中 | `scrollIntoView` 导致 rect 变 (0,0) | 把目标按钮 `position:fixed` 钉住再点 |

## 参考文档

- `references/pitfalls.md` — 全部实测踩坑台账（含时间线与证据）
- `references/listing-copy.md` — 文案模板、合规红线、定价口径
- `references/risk-control.md` — 京东风控实测与恢复策略
