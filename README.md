# 青鸾备案项目地图 V2.1 Lite

每天在云端（GitHub Actions，全免费）自动登录青鸾 → 采集备案项目 → 校验 → 脱敏 → 生成在线地图。电脑关机也照常更新。

- 在线地图（脱敏公开）：<https://reckt5138-lab.github.io/beian-map/>
- 本地完整数据（158 列 + Excel）：只在这台电脑上
- 不写飞书、不用数据库、不用服务器、无收费服务

> 版本：V2.1 Lite 　最后更新：2026-11-21

## 功能

- 青鸾登录、分页采集、项目详情、签到记录、158 列矩阵
- Excel 导出（完整数据）、JSON 导出
- Leaflet 地图：搜索、失效时间筛选、项目详情、坐标可信度、高德导航、手机端适配
- 云端每天 02:10 自动更新；支持手动触发
- 数据校验 + 原子写入 + 白名单脱敏 + 发布前自检
- 失败不覆盖：抓取异常或数据骤降时保留上一版

## 快速使用

**唯一入口：双击 `青鸾地图.bat`**，菜单选编号：

| 编号 | 功能 |
|---|---|
| 1 | 首次配置 / 部署 |
| 2 | 一键更新代码并部署 |
| 3 | 手动刷新云端数据 |
| 4 | 本地抓取并导出 Excel |
| 5 | 打开本地地图 |
| 6 | 项目诊断 |
| 0 | 退出 |

安装只需：Python 3.12+、Git；首次选菜单 1 按提示走完（含账号录入与登录验证）。

## 目录

```
jbufa_project_export_v2/
├── 青鸾地图.bat          # 唯一入口（菜单）
├── README.md / CHANGELOG.md / LICENSE / requirements.txt / .gitignore
├── app/
│   ├── main.py           # 7 命令 CLI
│   ├── crawler.py        # 采集核心（158 列）
│   ├── sheet_to_projects.py  # 矩阵解析 + 坐标（被 map_payload 调用）
│   ├── map_payload.py    # payload 构建、原子写、幂等
│   ├── build_map_html.py # 渲染页面
│   ├── map_template.html # 页面模板
│   ├── publish_commit.py # Contents API 提交
│   ├── core/ data/ map/ security/
├── config/               # config.example.json、public_fields.example.json（真实凭证不进库）
├── data/coords.json
├── scripts/              # menu / first_setup / deploy_update / refresh / local_server / maintenance
├── tests/                # 35 项
├── docs/                 # 使用说明 / 开发维护 / 部署说明 / 数据与安全 / audit
└── .github/workflows/    # daily.yml、deploy.yml
```

## 常用命令

```bat
python -m app.main crawl
python -m app.main build-json --source output/data.full.json
python -m app.main build-map
python -m app.main publish --source output/data.full.json
python -m app.main validate --source data.json
python -m app.main diagnose
python -m app.main selftest
python -m unittest discover -s tests -q
```

## 文档

| 文档 | 内容 |
|---|---|
| [docs/使用说明.md](docs/使用说明.md) | 安装、配置、打开地图、刷数据、导 Excel、日常操作、常见问题 |
| [docs/开发维护.md](docs/开发维护.md) | 架构、目录、模块职责、数据流程、改代码、加字段、测试 |
| [docs/部署说明.md](docs/部署说明.md) | GitHub/Secrets/Pages、首次部署、更新、刷新、故障排查 |
| [docs/数据与安全.md](docs/数据与安全.md) | 158 列结构、公开白名单、脱敏、凭证、Git 历史安全 |
| [docs/audit/安全与验收记录.md](docs/audit/安全与验收记录.md) | 安全清理报告、验收结果（含 NOT TESTED） |
