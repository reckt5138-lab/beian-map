# CHANGELOG

## V3.0 — 2026-11-22（Cloud JSON Only 纯净版）
- 前端：唯一数据源 `./data.json`；删除 raw.githubusercontent / jsDelivr 数据读取、飞书 API 与链接、本地备用 JSON、内置快照、多源切换重试、localStorage 缓存
- 前端：加载中显示「正在读取云端数据…」且条数显示 `—`；失败显示「云端数据加载失败，请稍后刷新页面。」并清空统计/列表/标记
- 模板：`<title>` 去写死日期；删除「飞书原表 ↗」与 spreadsheet_token 暴露；详情卡改「项公开字段」
- 构建：`build_map_html.py` 只做模板拷贝（不再把数据塞进 HTML）；`app/map/build.py` 的 verify 增加旧数据源拦截
- 抓取：`crawler.py` 删除飞书同步与 Excel 导出（1696 → 约 1180 行），`--json-out` 必填
- 解析：`app/sheet_to_projects.py` → `app/matrix_parse.py`（只留矩阵解析与坐标）
- 配置：`app/core/config.py` 默认配置删除 `login.client_secret` 明文值、`feishu` 段、`schedule.save_excel`、`map.snapshot`；抓取端保留的 client_secret 是网页接口公开常量（已注释说明）；`requirements.txt` 去掉 openpyxl；`daily.yml` 删除 jsDelivr 缓存刷新步骤
- 发布：`dist/` 只含 `index.html` + `data.json`；Actions 抓数只在 runner 临时目录留完整数据
- 文档：README 精简为「项目介绍 / 在线地址 / 数据说明 / 更新时间 / 维护」；docs 四份与 audit 记录按 V3 重写
- 测试：39 项全通过（新增「不得内嵌项目数据」「拦截旧数据源」等断言）
- 未推送远程（按约束）：等人工确认后再发布

## V2.1 Lite — 2026-11-21（精简稳定版）
- 安全：config.json 删除 client_secret / feishu.app_id / app_secret；feishu.enabled=false；真实凭证仍只在本地 credentials.json
- 精简：备份与 legacy 移出项目根；废弃模块（scheduler/web_server/encrypt_data/crawl_to_data/build_data_json/feishu worker）移出；依赖收敛为单一 requirements.txt
- 入口：6 个 BAT 合并为「青鸾地图.bat」+ scripts/menu.py（菜单 1-6）
- 文档：11 份合并为 4 份（使用说明/开发维护/部署说明/数据与安全）+ audit/安全与验收记录.md
- 修复：build_map_html 解除飞书硬依赖；菜单 EOF 崩溃；诊断菜单改走 app.main diagnose
- 测试：35 项仍全绿；编译/自检/构建/诊断实测通过
- 未推送远程（按约束）：线上仍为上一版产物

## V2.1 — 2026-11-21（暂时最终版）

**安全**
- 新增白名单脱敏链（`app/security/sanitize.py` + `config/public_fields.example.json`）：158 列 → 公开 13 列
- `data.json` 覆盖为脱敏版（`redacted: true`，18 条，customer/owner/amount/contact/customerAddr 全空，signs 为 `[]`）
- `dist/` 仅含 `index.html`（62.0 KB，内置快照）与脱敏 `data.json`
- 发布前 `verify()`：文件大小、凭证/明文正则、内置快照三项自检
- 日志 SecretFilter 过滤 `ghp_` / `github_pat_` / `password=` / `cookie`

**结构**
- 新增 `app/core`、`app/data`、`app/map`、`app/main.py`（7 命令 CLI）
- `app/crawler.py`、`app/map_payload.py` 原地保留（渐进式重构）
- `app/map_payload.py` 改原子写 + 幂等比较

**质量**
- `validate`：总数/分页/重名/必需字段/日期/经纬度/异常下降（60%）阻断
- 失败保留上一版，不覆盖、不发布

**部署**
- `daily.yml` 重写：crawl → validate → publish（脱敏+构建）→ verify → Contents API 提交 → Pages（CF 可选 skip）
- `deploy.yml` 新增：PR 校验，不发布
- Actions 只上传脱敏 `dist` artifact

**脚本**
- 六个根目录中文 bat：首次部署 / 一键更新部署 / 手动刷新数据 / 本地抓取出Excel / 打开地图 / 诊断项目
- 本地服务仅 `127.0.0.1`

**文档与测试**
- 11 份中文文档 + 索引 + 架构决策 + 审计与最终报告
- 35 个测试全绿
- 旧文档/旧脚本归档 `legacy/`（附迁移说明）

**未完成**
- 真实接口在 V2.1 代码路径下的全量验证（NOT TESTED）
- Cloudflare Pages 备用站（缺 Token）
- 历史泄露处置（待负责人决定）

## V2 — 2026-11 上旬
- 去飞书，直出 JSON + Pages；Actions 每日 02:10；新增 Leaflet 地图
