# 青鸾备案项目地图 V3.0

一个 HTML 页面，一个云端 JSON，一张地图。页面只从同目录 `./data.json` 读取备案项目并展示；数据由 GitHub Actions 每天自动抓取、校验、脱敏后写入。

- 在线地图：<https://reckt5138-lab.github.io/beian-map/>
- 数据来源：青鸾系统（c.jbufa.com），只采集本账号有权查看的项目
- 不写飞书、不用数据库、不用服务器、无收费服务

> 版本：V3.0（Cloud JSON Only）　最后更新：2026-11-22

## 在线地图

<https://reckt5138-lab.github.io/beian-map/>

打开即可用：Leaflet 地图、项目标记、搜索、失效时间筛选、项目详情、签到记录、高德导航、手机端适配。

## 数据说明

- 唯一数据源：站点根目录的 `data.json`（同源请求 `./data.json`）
- 只含公开白名单 13 列：项目名称、区域、地址、经纬度、备案时间、失效时间、剩余天数、产品类型、项目类型、项目进度、项目来源、签到次数、最后签到
- 客户、业务员、金额、联系人、客户地址一律置空；签到明细不公开
- 完整 158 列原始矩阵只留在 GitHub Actions 运行时的临时目录，不提交、不上传、不公开
- 页面加载失败时显示「云端数据加载失败，请稍后刷新页面。」，不会把 0 条当成真实数量

## 每日更新时间

- 每天北京时间 02:10，GitHub Actions 自动执行：抓取 → 校验 → 脱敏 → 生成 `dist/` → 发布 Pages
- 抓取失败或数据骤降时不覆盖，继续展示上一版有效数据
- 也可在仓库 Actions 页面手动点 Run workflow

## 简单维护

- 换账号：仓库 Settings → Secrets → Actions，改 `JUFA_USERNAME` / `JUFA_PASSWORD`
- 本地预览：双击 `青鸾地图.bat`，菜单 5（起 127.0.0.1 本地服务，页面读同目录 `data.json`）
- 本地抓一次：菜单 4（只写完整 JSON 到 `output/`，不导出 Excel、不碰飞书）
- 本地生成公开数据与发布目录：`python -m app.main publish --source output\data.full.json`
- 详细说明见 `docs/`

## 目录

```
beian-map-v3/
├── 青鸾地图.bat          # 唯一入口（菜单）
├── index.html            # 生成产物：地图页面（只请求 ./data.json）
├── data.json             # 生成产物：公开脱敏数据
├── dist/                 # 发布目录：只含 index.html + data.json
├── app/                  # 抓取、解析、脱敏、校验、构建
├── config/               # 配置与凭证示例（真实凭证不进库）
├── scripts/              # 菜单、初始化、部署、维护、本地服务
├── tests/                # 单元测试（39 项）
├── docs/                 # 使用与维护文档
└── .github/workflows/    # 每日自动抓取与发布
```

## 常用命令

```bat
python -m app.main crawl
python -m app.main publish --source output\data.full.json
python -m app.main validate --source data.json
python -m app.main selftest
python -m app.main diagnose
python -m unittest discover -s tests -q
```

## 文档

| 文档 | 内容 |
|---|---|
| [docs/使用说明.md](docs/使用说明.md) | 安装、配置、打开地图、抓数据、日常操作、常见问题 |
| [docs/开发维护.md](docs/开发维护.md) | 架构、目录、模块职责、数据流程、改代码、测试 |
| [docs/部署说明.md](docs/部署说明.md) | GitHub / Secrets / Pages、首次部署、更新、故障排查 |
| [docs/数据与安全.md](docs/数据与安全.md) | 矩阵结构、公开白名单、脱敏、凭证、Git 历史安全 |
| [docs/audit/安全与验收记录.md](docs/audit/安全与验收记录.md) | 安全清理与验收记录 |
