# 青鸾备案项目每日导出 · 云端版（v2）

每天在云端（GitHub Actions，全免费）自动登录「青鸾」`https://c.jbufa.com` → 抓「备案项目」→ 直接产出两份东西：

- `data.json`：网页数据（18 条 / 158 列 + 全部字段），提交回仓库
- `output\备案项目YYYY-MM-DD.xlsx`：Excel，作为 Actions 产物（Artifact）保留 30 天

**不写飞书、不需要服务器、不需要电脑开机。** 网页随时打开就能看当天数据。

---

## 两种用法，各一个脚本

| 脚本 | 在哪跑 | 干什么 |
| --- | --- | --- |
| `测试运行.bat` | 本地电脑 | 手动跑一次：抓数 → 出 Excel（自动用 Excel 打开）→ 顺带出 `data.json` 和本地 `index.html`，用来验数据对不对 |
| `一键部署.bat` | 本地电脑跑一次 | 建私有/公开仓库、推代码、写两个 Secret（`JUFA_USERNAME` / `JUFA_PASSWORD`，本机加密后上传）、开 Actions 权限、立刻触发第一次云端任务。之后就不用再管 |

云端定时（`.github\workflows\daily.yml`）每天北京时间 **02:10** 跑，也支持手动 Run workflow。

## 网页怎么看

| 方式 | 地址 | 说明 |
| --- | --- | --- |
| 手机 / 任意设备（推荐，零额外账号） | **<https://reckt5138-lab.github.io/beian-map/>** | GitHub Pages，Actions 每次跑完自动发布，免费无限流量 |
| 可选加速 | Cloudflare Pages `https://项目名.pages.dev/` | 配了三项 Secret 就自动一起发；国内访问更稳 |
| 电脑本地 | 双击 `打开地图.bat` | 起本地 HTTP 服务并打开 `index.html`；先读云端 `data.json`，拿不到退回内置快照 |

页面只读：点开任一项目能看到全部 158 列非空字段。

## 命令行（不用 bat 也行）

```bat
REM 本地测一次（出 Excel，不碰飞书）
python app\crawler.py --no-feishu --json-out data.json

REM 从已有数据重建页面
python app\build_map_html.py --from-json data.json --out index.html

REM 从 Excel 或原始 JSON 反推 data.json（离线也能用）
python app\build_data_json.py --from-xlsx output\备案项目2026-11-21.xlsx
python app\build_data_json.py --raw

REM 一键部署（首次）
python scripts\deploy_github.py --owner 你的用户名 --repo 仓库名 --token ghp_xxx
REM 想同时发布网页（Cloudflare Pages，免费）
python scripts\deploy_github.py --owner 你的用户名 --repo 仓库名 --token ghp_xxx ^
  --cf-token CF_TOKEN --cf-account ACCOUNT_ID --cf-project beian-map
```

## 数据链路

```
GitHub Actions（每天 02:10，云端，关机照跑）
   └─ crawler.py --no-feishu --json-out data.json   抓数 → Excel + data.json
   └─ build_map_html.py --from-json data.json       用当天数据重建 index.html
   └─ publish_commit.py（Contents API）             提交 data.json / index.html（没变化就跳过）
   └─ GitHub Pages 发布 dist/                        → https://reckt5138-lab.github.io/beian-map/
   └─ Cloudflare Pages（可选，配了 CF Secret 才发）
   └─ 上传 artifact（output\*.xlsx）                  → Actions 页面可下载 Excel
        ↓
你打开网页 → 页面同时读 Raw 与 jsDelivr，按 updated 取较新的一份 → 显示当天数据
```

## 目录

```
jbufa_project_export_v2/
├─ 测试运行.bat              本地：抓一次 → Excel + data.json + index.html
├─ 一键部署.bat              首次部署到 GitHub（+ 可选 Cloudflare Pages）
├─ 打开地图.bat              本地起 HTTP 服务看 index.html
├─ index.html                网页（含内置快照兜底）
├─ 备案项目地图.html           同一份页面的本地副本（可发手机看）
├─ data.json                 网页数据（Actions 每天更新）
├─ app/
│   ├─ crawler.py            主爬虫（登录 → 取数 → Excel，可选 --json-out 写 data.json）
│   ├─ map_payload.py        二维表 → data.json（幂等写，内容没变不落盘）
│   ├─ build_map_html.py     数据 → index.html（--from-json / --from-xlsx / 取飞书表）
│   ├─ build_data_json.py    离线重建 data.json（--raw / --from-xlsx / --from-json）
│   ├─ map_template.html     页面模板（改界面改这里）
│   └─ requirements.txt      requests、openpyxl
├─ .github/workflows/daily.yml  云端定时任务
├─ scripts/
│   ├─ deploy_github.py      一键部署（建仓/推送/Secrets/Pages/触发）
│   ├─ run_daily.bat         单次运行（旧入口，被 测试运行.bat 替代）
│   └─ ...
├─ config/
│   ├─ config.json           业务配置（账号密码留空）
│   └─ credentials.json      本机账号密码（不进仓库）
├─ data/coords.json          项目名 → 经纬度
├─ docs/
│   ├─ 部署清单.md            一键部署 / 手动部署 / Pages / 排错
│   ├─ 零操作改造.md          这版改了什么、怎么验证
│   └─ （飞书相关文档已归档，本版不再使用）
└─ output/
    ├─ 备案项目YYYY-MM-DD.xlsx  Excel
    ├─ raw/                  接口原始 JSON（回溯用）
    └─ logs/                 运行日志
```

## 需要准备的

1. Python 3.10+，`python -m pip install -r app\requirements.txt`（部署脚本额外需要 `pynacl`，缺了会自动装）
2. `config\credentials.json` 填青鸾账号密码（`username` / `password`）
3. GitHub Personal Access Token：classic token，勾 `repo` + `workflow`
4. （可选，建议）Cloudflare 账号：API Token（权限 Pages:Edit）+ Account ID + 项目名，用来出 `*.pages.dev` 固定网页
5. 仓库建议 **Public**：这样本地 `index.html` 能直接读 Raw/jsDelivr，不用任何中转；Secret 不会因为公开而泄露

## 不用飞书了，这些文件是历史遗留

`app/sheet_to_projects.py`、`app/scheduler.py`、`定时任务启动.bat`、`cloud/feishu_proxy_worker.js`、`docs/飞书*.md`、`docs/云端自动运行.md` 属于旧飞书路线，本版不再调用，留着只为兼容；不需要可以整目录删掉，不影响新版运行。

## 已知差异

`报价专用2` 一行的「预计合同金额 / 折扣信息」与网页导出口径不同（报价明细接口返回 500），其余行 × 158 列完全一致。
