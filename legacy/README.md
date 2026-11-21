# legacy 归档说明

版本：V2.1 　最后更新：2026-11-21

这里存放 V1/V2 早期使用、V2.1 主流程不再调用的文件。**只是归档，不是删除**，如需回滚可从这里复制回去。

| 归档项 | 原位置 | 为什么归档 |
|---|---|---|
| 飞书在线表格.md、飞书实时（免费Worker）.md | docs/ | 飞书链路已从主流程移除，仅供参考 |
| 云端自动运行.md、部署清单.md、零操作改造.md、取值与部署步骤.md、使用手册.md、地图与手机访问.md | docs/ | 内容已被 docs/ 下 11 份新文档覆盖 |
| Cloudflare-Pages-配置步骤.md | docs/ | 已并入 docs/06_部署教程.md（CF 为备用站，可跳过） |
| 测试运行.bat、一键部署.bat | 根目录 | 与「一键更新部署.bat」职责重叠，避免双入口冲突 |
| 定时任务启动.bat、run_daily.bat、run_scheduler.bat、refresh_data.bat | 根目录 / scripts/ | 本机定时已改为云端 GitHub Actions，本机不再常驻调度 |
| install_task.ps1、uninstall_task.ps1、install_autostart.ps1、open_firewall.bat | scripts/ | 本机计划任务/防火墙方案已废弃（不再对外开放局域网） |

仍然保留在主工程里、但属于「旧版兼容」的代码：

- `app/crawler.py`、`app/crawl_to_data.py`、`app/build_data_json.py`、`app/build_map_html.py`、`app/map_payload.py`、`app/publish_commit.py`、`app/scheduler.py`、`app/web_server.py`、`app/sheet_to_projects.py`
- `cloud/feishu_proxy_worker.js`

原因：`crawler.py` 是 158 列采集的核心实现，与 `map_payload.py` 强耦合，V2.1 采用「渐进式重构」——新代码通过 `app/core`、`app/data`、`app/map`、`app/security` 薄封装调用它，而不是把它拆散重写。`feishu_proxy_worker.js` 目前不被工作流引用，保留是因为它是唯一可用的飞书代理实现，删除后再接飞书需要重写。
