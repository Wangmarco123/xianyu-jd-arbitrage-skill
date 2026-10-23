# Xianyu-JD Arbitrage Skill｜闲鱼·京东代发自动化

仓库地址：https://github.com/Wangmarco123/xianyu-jd-arbitrage-skill　·　最新安装包：见 [Releases](https://github.com/Wangmarco123/xianyu-jd-arbitrage-skill/releases)

> 把「京东自营低价进货 → 闲鱼加价/减价转卖」的全流程做成可被 AI Agent 直接调用的技能包：
> **京东只搜不点详情取价 → 品牌官网取无水印图 → 闲鱼批量上架 → 发布后体检**。

发布价规则默认：**闲鱼价 = 京东价 − 200**（可配置），文案固定写明"京东官方直发 / 优惠 200 / 公司礼品卡折价套现 / 非质量问题不退不换 / 质量问题走京东官方售后"。

---

## 为什么需要这个仓库

做闲鱼代发踩了 4 个坑，每个都在这周实测过，仓库里全部固化成了规则和代码：

| 坑 | 实测结论 | 仓库里的对策 |
|---|---|---|
| 闲鱼「无忧卖」锁定 | **手机类目**发布后会被自动纳入无忧卖 → 文案改不动、下架/删除点了不生效；**其他闲置不会** | 发布一律用 `其他闲置`；发布后 60 秒跑 `postcheck.py` 体检 |
| 京东封详情页 | 连续 11–13 个详情页（间隔 8s）→ 封禁 60 分钟；解封后只够再抓 1 个 | **彻底不点详情页**，只用搜索页；`jd_search.py` 内置熔断 |
| 京东搜索也会软封 | 连续 6 次搜索全部返回 0 条 | 间隔 ≥45s、单轮 ≤6 词、**0 条即终止** |
| 京东主图不能直接用 | 自营主图带双11促销条 + `JD.COM 京东`水印 + 促销价，搬去闲鱼会价格打架/判搬运 | 图片统一从**品牌官网**取（苹果 CDN 已跑通） |

另外两个必须知道的账：
- 闲鱼**鱼小铺**服务费 **1.6%**，手机类目和其他闲置**都收**，换类目免不掉；
- 京东**搜索页价 vs 详情页价**会差几百（实测 iPhone 18 Pro 512G：11699 vs 11999），只用搜索价定价要留安全垫。

---

## 架构

```
┌─────────────┐   ws://localhost:9444   ┌──────────────────────┐
│  Python 脚本 │ ◄─────────────────────► │ bridge_server.py     │
│ （本仓库）   │                         └──────────┬───────────┘
└─────────────┘                                    │ WebSocket
                                                   ▼
                                    ┌──────────────────────────────┐
                                    │ Chrome + Xianyu Bridge 扩展   │
                                    │ （extension/ 目录，已打补丁）  │
                                    │ · 复用你已登录的京东/闲鱼会话  │
                                    │ · CDP 可信点击（绕 isTrusted）│
                                    └──────────────────────────────┘
```

**核心设计**：不新建浏览器、不接管 Cookie。扩展挂在你**日常使用的 Chrome** 上，
脚本通过 `set_match` 指令让扩展在「京东标签页」和「闲鱼标签页」之间切换，
所以京东登录态、闲鱼登录态全部复用，不需要扫码、不需要导出 Cookie。

---

## 目录结构

```
skill-xianyu-jd-arbitrage/
├── SKILL.md                  # 给 AI Agent 的指令入口（frontmatter + 工作流 + 硬规则）
├── README.md                 # 本文件
├── scope.example.jsonc       # 选品范围配置（品类/关键词/门槛价/折扣）
├── extension/                # Chrome 扩展「Xianyu Bridge」（含 set_match 补丁）
├── scripts/
│   ├── doctor.py             # 环境自检（依赖/端口/扩展连接/set_match 能力）
│   ├── bridge_server.py      # 本地 WebSocket 桥
│   ├── xyclient.py           # 桥客户端：navigate/evaluate/可信点击/截图
│   ├── jd_search.py          # 京东只搜不点详情 + 节流 + 熔断 + 价格体检
│   ├── images.py             # 官网图下载（苹果 CDN / 通用 URL 列表 → 白底 JPG）
│   ├── listings.py           # 生成标题/文案/价格与发布队列
│   ├── publish.py            # 填表 → 选包邮 → 可信点击发布 → 回读校验
│   └── postcheck.py          # 发布后体检（无忧卖 / 文案是否生效）
└── references/
    ├── pitfalls.md           # 全部实测踩坑台账（含时间线与证据）
    ├── listing-copy.md       # 文案模板、合规红线、定价口径
    └── risk-control.md       # 京东风控阈值与恢复策略
```

---

## 安装

### 1. Chrome 扩展

1. 打开 `chrome://extensions/`，右上角开启「开发者模式」
2. 点「加载已解压的扩展程序」，选择本仓库的 `extension/` 目录
3. 扩展名应为 **Xianyu Bridge**，默认连 `ws://localhost:9444`
4. 在 Chrome 里**正常登录**京东和闲鱼（脚本复用你的登录态）

> 若之前装过旧版扩展：先删掉旧版再加载本仓库的 `extension/`，并到
> `chrome://extensions/` 点一次「重新加载」，否则 Service Worker 会跑旧代码。

### 2. Python 依赖

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install websockets pillow
```

### 3. 自检

```bash
python scripts/doctor.py
```

期望输出：`websockets OK` / `bridge server: up` / `extension: connected` / `set_match: ok`。
`set_match: UNSUPPORTED` 说明加载的是**没打补丁的旧扩展**，回第 1 步重新加载。

### 4. 起桥

```bash
python scripts/bridge_server.py     # 前台常驻，或自行托管为后台服务
```

---

## 快速开始（4 步）

```bash
# 0) 复制配置并改成你的选品
cp scope.example.jsonc scope.jsonc

# 1) 京东只搜不点详情，取价（内置熔断，被软封会自己停）
python scripts/jd_search.py --scope scope.jsonc --max-kw 3

# 2) 从品牌官网取图（苹果已跑通；华为/相机见 references）
python scripts/images.py apple --item-dir items/100317829557 \
    --names iphone-18-pro-max-finish-select-silver-202609

# 3) 生成文案与价格（京东价 − 200）
python scripts/listings.py --products products.json

# 4) 上架 + 体检
python scripts/publish.py --products products.json --id 100317829557 --dry-run
python scripts/publish.py --products products.json --id 100317829557
python scripts/postcheck.py 1092343355054
```

`products.json` 形状：

```json
{
  "items": [
    {
      "id": "100317829557",
      "jd_price": 12999,
      "short": "iPhone18ProMax",
      "spec": "512G 银色",
      "title_full": "Apple/苹果 iPhone 18 Pro Max 512GB 银色 手机"
    }
  ]
}
```

---

## 硬规则（违反会直接踩坑，务必遵守）

1. **发布类目一律 `其他闲置`** —— 手机类目会被拉进无忧卖，之后既不能改文案也不能下架删除。
2. **绝不打开京东商品详情页** —— 详情页是封禁主因（1 次/小时上限）。
3. **京东搜索返回 0 条 = 软封** —— 立即停止本轮，静置 ≥2 小时后单条重测。
4. **图片用品牌官网** —— 不用京东主图（促销条/水印/促销价三重问题）。
5. **发布按钮必须 CDP 可信点击** —— JS 合成点击会被 `isTrusted` 校验静默丢弃。
6. **发布后 60 秒内体检** —— 确认文案已生效、无无忧卖标记、下架按钮真能生效。
7. **定价算 1.6% 服务费** —— 标价 −200 后，实际到手还要再扣 1.6%。

---

## 已知限制

- 只支持「你自己的已登录 Chrome」，不能用于无人值守服务器环境。
- 京东搜索页结构随改版变化，`jd_search.py` 的提取逻辑可能需要按新版调整。
- 华为 / 佳能 / 索尼 / 尼康 / 富士的官网图源需按各自站点补 selector（苹果已跑通，其余见 `references/pitfalls.md`）。
- 闲鱼「无忧卖」一旦锁定，本仓库**无法**解除，只能走 APP / 客服。

---

## 合规与免责声明

本项目只提供**自动化工具**，不提供商品、不做代购、不承担交易纠纷责任。使用者需自行确保：

- 商品来源合法、可开具或可追溯；
- 发布的描述、售后承诺与实际情况一致（本仓库模板已刻意去掉"可开发票"这类不一定能兑现的承诺）；
- 遵守闲鱼《社区公约》、京东《用户协议》及当地法律法规；
- 高频自动化访问可能触发平台风控，本仓库内置的节流/熔断值是**实测经验值**，不构成合规保证。

因使用本项目导致的封号、罚款、纠纷、损失，作者不承担责任。

---

## 上传到你自己的 GitHub 仓库（详细步骤）

### 方式 A：命令行（推荐）

```bash
cd skill-xianyu-jd-arbitrage

git init
git add .
git commit -m "feat: 闲鱼京东代发自动化 skill（扩展+脚本+实测规则）"

# 先在 GitHub 网页端 New repository（不要勾选 README/License，避免冲突）
# 然后把地址换成你自己的
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

**HTTPS 推送要 Personal Access Token**（GitHub 已不支持账号密码）：

1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. 勾 `repo` 权限，生成后复制
3. 推送时用户名填 GitHub 用户名，密码处**粘贴 token**

或改用 SSH：

```bash
ssh-keygen -t ed25519 -C "your@email.com"
# 把 ~/.ssh/id_ed25519.pub 内容贴到 GitHub → Settings → SSH and GPG keys
git remote set-url origin git@github.com:<你的用户名>/<仓库名>.git
git push -u origin main
```

### 方式 B：网页上传

1. GitHub → New repository → 建空仓库
2. 仓库页 → `Add file` → `Upload files` → 把整个目录拖进去（注意保留 `tests/` 之外的目录层级）
3. 提交

### 建议的仓库设置

| 项 | 建议 |
|---|---|
| 仓库名 | `xianyu-jd-arbitrage-skill` |
| 描述 | 闲鱼·京东代发自动化 Skill：京东只搜取价 + 官网取图 + 闲鱼上架体检 |
| Topics | `xianyu` `goofish` `jd` `agent-skill` `automation` `chrome-extension` `python` |
| License | MIT（已附 `LICENSE`，改成年份和你的名字） |
| Release | 打 `v0.1.0`，附 `extension/` 的 zip 方便别人直接下载安装 |

### 上传前必做（防止泄露账号信息）

```bash
# 确认没有任何登录态/截图/商品数据被带进仓库
cat .gitignore
git status --short
```

`.gitignore` 已排除：`.venv/`、`items/`、`data/`、`*.log`、`.browser/`、`queue.json`、
`products.json`、`xianyu-screenshot.png`、`*.png`（`extension/icons/` 除外）。

---

## 安装到 Agent 的 skills 目录

```bash
# Claude Code / DSH 等：把仓库放进 skills 根目录即可被自动发现
git clone https://github.com/Wangmarco123/xianyu-jd-arbitrage-skill.git \
  ~/.agents/skills/xianyu-jd-arbitrage
```

之后 Agent 只要看到「闲鱼上架/京东取价/代发」类需求，就会命中 `SKILL.md` 的 description 触发。

---

## License

MIT — 见 [LICENSE](LICENSE)。
