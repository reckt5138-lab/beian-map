# 初始审计（改造前状态）

版本：V2.1 审计 　最后更新：2026-11-21 　方式：只读检查 + `Copy-Item` 备份，未改动原工程 `jbufa_project_export`。

## 一、备份

- 备份目录：`output/backups/pre_v2.1_20261121`
- 范围：项目根目录下 50 个文件（含 `app/`、`config/`、`scripts/`、`docs/`、`.github/`、根 bat）
- `robocopy` 在本机不可用，改用 PowerShell `Copy-Item`

## 二、Git 状态（审计时）

| 项 | 结果 |
|---|---|
| 分支 | `main` |
| 最近提交 | `db2e415` fix: window.CLOUD 注入顺序 / `c412e05` config: index.html 指向云端 data.json / `e34d2df` init |
| 远程 | `https://github.com/reckt5138-lab/beian-map`（Public） |
| 工作区 | 有未提交修改（`.github/workflows/daily.yml`、`README.md`、`app/map_template.html`、`data.json`、`docs/*`、`index.html`、`scripts/deploy_github.py`）与未跟踪文件（`app/publish_commit.py`、`docs/Cloudflare-Pages-配置步骤.md`） |
| 与远端关系 | 远端历史已由 API 提交推进，本地已分叉 |

处置原则：不恢复、不删除用户的本地修改；本次所有改动均单独记录，推送走 API。

## 三、文件职责（现状）

| 文件 | 职责 | V2.1 处置 |
|---|---|---|
| `app/crawler.py` | 登录 + 分页 + 详情 + 158 列矩阵 + Excel | 保留（核心） |
| `app/crawl_to_data.py` | 抓取入口封装 | 保留 |
| `app/build_data_json.py` | 矩阵 → payload | 保留；新入口 `app/data/export_json.py` |
| `app/build_map_html.py` | 渲染 index.html | 保留；新入口 `app/map/build.py` |
| `app/map_payload.py` | payload 读写、坐标合并 | 保留；改为原子写 + 幂等 |
| `app/map_template.html` | 地图页面模板 | 保留并升级（状态栏/可信度/移动端） |
| `app/publish_commit.py` | Contents API 提交 | 新增 |
| `app/encrypt_data.py` | 凭证加密 | 保留（未被主流程调用） |
| `app/scheduler.py` | 本机定时 | 保留但不启用（已转云端） |
| `app/sheet_to_projects.py` | 飞书表格解析 | 保留（历史，无调用） |
| `app/web_server.py` | 本地 web 服务 | 保留；`scripts/local_server.py` 为 V2.1 入口 |
| `cloud/feishu_proxy_worker.js` | 飞书代理 Worker | 保留（备用，不参与主流程） |
| `config/config.json` | 业务配置 | 保留 + 新增模板/说明 |
| `data.json` | 网页数据 | **审计时为 158 列全量（安全风险）**，V2.1 覆盖为脱敏 13 列 |
| `docs/*`（8 份） | V2 旧文档 | 归档 `legacy/docs/` |
| 根目录 `测试运行.bat`、`一键部署.bat`、`定时任务启动.bat` | 旧入口 | 归档 `legacy/` |
| `scripts/*.bat`（7 个） | 旧调度/防火墙 | 归档 `legacy/scripts/` |

## 四、识别出的问题清单

| # | 问题 | 严重度 | 状态 |
|---|---|---|---|
| 1 | 公开仓库与 Pages 发布 158 列完整数据（客户名/电话/金额） | 严重 | V2.1 已脱敏覆盖；历史泄露待决策 |
| 2 | `data.json` 无脱敏、无白名单机制 | 严重 | 已修（sanitize + 白名单） |
| 3 | 本机 `git push` 不稳定（TLS） | 中 | 已改 Contents API |
| 4 | 无数据校验，抓取失败会覆盖好数据 | 高 | 已修（validate + 原子写 + 快照） |
| 5 | 无自动化测试 | 中 | 已建 35 项 |
| 6 | 多入口并存（3 个 bat 职责重叠） | 中 | 已归档旧入口 |
| 7 | 配置散落、无模板、无优先级 | 中 | 已统一（core/config） |
| 8 | 无文档体系 | 中 | 已补 11 份 |
| 9 | `__init__` 与子模块同名函数遮蔽、BASE_DIR 少一层 | 低 | 已修（测试排障中发现） |

## 五、结论

工程可用但不可维护、且存在真实数据泄露。V2.1 按「先安全、再结构、最后部署体验」的顺序处理，未推翻重写任何可用功能。
