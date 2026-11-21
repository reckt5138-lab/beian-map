# 青鸾备案项目地图 V2.1 — 暂时最终版

每天在云端（GitHub Actions，全免费）自动登录青鸾系统 → 采集「备案项目」全量数据 → 校验 → **脱敏成公开字段** → 构建静态地图网页 → 发布到 GitHub Pages。电脑关机也照常更新，手机随时打开就能看。

- 网页（公开脱敏）：<https://reckt5138-lab.github.io/beian-map/>
- 本地完整地图（含 158 列全量 + Excel）：双击 `打开地图.bat` / `本地抓取出Excel.bat`
- 不写飞书、不需要服务器、不使用付费服务

> 版本：V2.1 　最后更新：2026-11-21 　详细文档：见 [`docs/`](docs/README.md)

---

## 一、你只需要记住五个双击文件

| 什么时候 | 双击哪个 | 它做什么 |
|---|---|---|
| 第一次在新电脑上用 | **首次部署.bat** | 检查环境、装依赖、收账号、验证登录、跑一次抓取、配好云端 |
| 改了代码，要更新线上 | **一键更新部署.bat** | 跑测试 → 安全检查 → 提交 → 推送 → 触发云端部署 |
| 只想立刻刷新一次数据 | **手动刷新数据.bat** | 触发云端 `daily.yml`，不碰代码 |
| 想在本机看完整数据 | **本地抓取出Excel.bat** | 真抓一次 → `output/excel/*.xlsx` + `output/data.full.json` + 本地地图 |
| 打开网页看本地地图 | **打开地图.bat** | 只监听 127.0.0.1 的本地 HTTP 服务并开浏览器 |
| 出问题了 | **诊断项目.bat** | 一键体检，报告写到 `output/logs/diagnostic_report.txt` |

全部脚本中文提示，失败会明确告诉你缺什么，不会假装成功。

## 二、数据分级（必读）

| 等级 | 内容 | 去向 |
|---|---|---|
| A 可公开 | 项目名称、类型、分类、进度、建设类型、备案/失效时间、面积量级、行政区、经纬度、坐标可信度 | 公开网页 `index.html` + `data.json` |
| B 仅内部 | 业务员、部门、项目编号、项目情况描述 | 仅本机 `output/data.full.json` / Excel |
| C 敏感 | 客户名称、联系人、手机、客户地址、合同金额、报价、跟进/签到记录 | 永不进入公开网页；本机也不进 `dist/` |

公开字段白名单在 `config/public_fields.example.json`，脱敏由 `app/security/sanitize.py` 执行；**不是**手删几个字段。

> 历史提示：早期 V2 曾把 158 列全量提交到公开仓库约 1 小时。删除文件不等于消除历史泄露，请按 `docs/10_安全说明.md` 处置（建议对该仓库做私有化或换凭证）。

## 三、目录一览

```
jbufa_project_export_v2/
├── 首次部署.bat / 一键更新部署.bat / 手动刷新数据.bat / 本地抓取出Excel.bat / 打开地图.bat / 诊断项目.bat
├── app/
│   ├── main.py              # 统一入口：python -m app.main <命令>
│   ├── core/                # 路径、配置、日志、异常
│   ├── crawler/             # 采集（当前由 app/crawler.py 提供实现）
│   ├── data/                # 原子写、校验、JSON/Excel 导出
│   ├── map/                 # 地图构建与自检
│   ├── security/            # 白名单脱敏
│   └── crawler.py 等        # 旧版实现，保持兼容（见 legacy/README.md）
├── config/                  # 配置模板与真实配置（credentials.json 不进库）
├── data/                    # coords.json 等静态数据
├── output/                  # excel / raw / logs / backups（不进库）
├── scripts/                 # Python 实现 + 少量 .bat 转发
├── tests/                   # 35 个自动化测试
├── docs/                    # 11 份中文文档 + 架构 + 审计报告
├── cloud/                   # 飞书代理 Worker（备用，不参与主流程）
└── .github/workflows/       # daily.yml（采集发布）、deploy.yml（PR 校验）
```

## 四、常用命令（不用 bat 也行）

```bat
python -m app.main crawl                     :: 真抓一次，写 output/raw + output/excel
python -m app.main build-json --source output/data.full.json
python -m app.main build-map
python -m app.main publish --source output/data.full.json   :: 脱敏 + 校验 + 构建 dist
python -m app.main validate --source data.json
python -m app.main diagnose
python -m app.main selftest
python -m unittest discover -s tests -q      :: 35 tests
```

## 五、遇到问题

先双击 `诊断项目.bat`，再按 `docs/08_故障排查.md` 对照。任何情况下都不会自动强推、覆盖远端历史或发布真实业务数据。

## 六、文档索引

[`docs/README.md`](docs/README.md) → 01 项目介绍、02 系统架构、03 功能说明、04 数据结构、05 配置说明、06 部署教程、07 日常使用、08 故障排查、09 二次开发、10 安全说明、11 版本更新记录，审计见 `docs/audit/V2.1_FINAL_REPORT.md`。
