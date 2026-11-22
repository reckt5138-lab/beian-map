# 配置说明（config/）

本目录所有**真实值**文件都不会进入 Git：`credentials.json`、`config.json`（业务值）、`deploy.json`（部署凭证）都已在 `.gitignore` 里。
仓库里只保留 `*.example.json` 模板。

## 文件清单

| 文件 | 是否入库 | 作用 |
| --- | --- | --- |
| `config.example.json` | ✅ | 业务配置模板（采集参数、导出参数、publish 段） |
| `config.json` | ❌ | 你的真实业务配置，首次部署时从 example 复制 |
| `credentials.example.json` | ✅ | 账号配置模板 |
| `credentials.json` | ❌ | 真实青鸾账号密码（或改用环境变量） |
| `public_fields.example.json` | ✅ | **公开数据白名单**（决定哪些字段能上网） |
| `public_fields.json` | ❌ | 想改白名单时复制模板再改 |
| `deploy.json` | ❌ | 一键部署用的 GitHub owner/repo/token（可选 CF 三项） |

## 读取优先级

环境变量 > `config/credentials.json` > `config/config.json` > 代码内安全默认值。

支持的環境变量：

| 变量 | 作用 |
| --- | --- |
| `JUFA_USERNAME` / `JUFA_PASSWORD` | 青鸾账号（云端 Actions 用 Secrets 注入） |
| `JUFA_BASE_URL` | 覆盖青鸾地址（默认 `https://c.jbufa.com`） |
| `GITHUB_OWNER` / `GITHUB_REPO` | 覆盖 publish 段 |
| `GITHUB_TOKEN` / `GH_TOKEN` | 一键更新、手动刷新时用的 GitHub 凭证 |

## 关键配置项

`crawl.*`：采集参数。`page_size` 分页大小、`max_pages` 分页上限、`retry` 重试次数、`timeout` 单请求超时、`request_interval` 请求间隔（太小会被限流）。
`export.*`：Excel 输出（`file_prefix` 文件名前缀、`keep_days` 保留天数、`checkin_columns` 签到列数、`use_field_template` 是否用字段模板，改成 `false` 会导致列顺序变化，谨慎）。
`publish.*`：仓库地址，决定网页去哪里读 `data.json`。
`feishu.*`：**V2.1 已不使用**，保留仅为兼容旧配置，`enabled` 默认 `false`。

## 改公开字段白名单

1. 复制 `public_fields.example.json` 为 `public_fields.json`
2. 修改 `projects_keep`（项目里允许公开的字段）和 `columns_keep`（表格里允许公开的列名，必须是真实表头里的中文列名）
3. 运行 `python -m app.main selftest` 确认自检通过
4. 运行 `python -m app.main publish` 重新生成 `data.json` 与网页

**默认原则：不确定是否敏感，就不要加进白名单。** 客户姓名、联系人、电话、客户地址、金额、报价、签到记录、内部备注、业务员与部门一律不公开。
