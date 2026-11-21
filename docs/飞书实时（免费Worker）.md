# 飞书数据怎么给网页（密钥不进网页）

## 先说结论

**只读密钥写进网页也跑不通**，但不是权限问题，是浏览器跨域问题：

- 飞书 `open.feishu.cn` 不返回 `Access-Control-Allow-Origin`（实测 OPTIONS 200 但没有任何 CORS 头，GET 也一样），浏览器直接 fetch 会被拦；
- 飞书官方也明确写「请勿在应用前端使用访问凭证，请在应用服务端发起请求」。

所以只要想「打开网页就是最新飞书数据」，中间必须有一个**转发**。转发放在哪里决定了密钥暴露不暴露：

| 方案 | 密钥在哪 | 手机 4G | 要不要服务器 | 数据新鲜度 |
| --- | --- | --- | --- | --- |
| A. 现在的内置快照 | 只在电脑 `config\credentials.json` | 能（打开文件即可） | 不要 | 每天导出后更新 |
| B. 电脑上开 8787 | 同上 | 不能（仅同 Wi-Fi） | 不要（自己电脑） | 90 秒 |
| C. **免费 Worker 中转**（本方案） | **只在云端变量里，网页一个字都没有** | 能 | 不要（Cloudflare 免费托管） | 60 秒 |

C 就是「只读权限 + 密钥不进网页」唯一能成立的形态：网页只认识一个 Worker 地址，Worker 里放只读应用密钥，并且应用只开只读权限。

代码已经写好：`cloud\feishu_proxy_worker.js`（单文件，直接粘）。已用本机 Node 跑过真实飞书表做逐项比对，输出与 Python 版完全一致：18 条、158 列、每条的 35 项字段、签到记录、经纬度、geo 标记全部相同，差异 0。

## 一、把应用改成只读（重要）

1. 打开飞书开发者后台 → 你的应用「青鸾项目导出」→ **权限管理**。
2. 删掉 `sheets:spreadsheet`（读写）和 `drive:drive`（云空间全量读写，最危险）。
3. 加上 `sheets:spreadsheet:readonly`（「查看、评论和导出电子表格」）。
4. 权限变更后**发布新版本**并等生效。

改完后这个应用在飞书里**只能读、不能写**，就算密钥哪天泄露，最坏也只是别人能读你这张表。

## 二、部署 Worker（约 5 分钟，全程网页点选）

1. 注册 <https://dash.cloudflare.com>（免费，邮箱即可）。
2. 左侧 **Workers & Pages** → **Create** → **Create Worker** → 名字随便（如 `jbufa`）→ Deploy。
3. 点 **Edit code**，把 `cloud\feishu_proxy_worker.js` 全选粘贴进去（覆盖默认代码）→ **Deploy**。
4. **Settings → Variables and Secrets**，加 4 个变量（类型选 Secret）：

| 变量名 | 值 |
| --- | --- |
| `FEISHU_APP_ID` | `cli_ab8ae3e157f9dc01` |
| `FEISHU_APP_SECRET` | 你 `config\credentials.json` 里的 `feishu_app_secret` |
| `SPREADSHEET_TOKEN` | `E1AcsZQ2EhT6Vgt9GiHcxmp6ncc` |
| `SHEET_ID` | `d154b6` |

可选：`ACCESS_KEY`（给接口加口令）、`ALLOW_ORIGIN`（默认 `*`）。

5. 打开 `https://<你的子域>.workers.dev/`，应返回 `{"ok":true,...}`；再开 `/projects.json`，应看到 18 条。
6. 免费额度 10 万请求/天，这个量用不到零头。

## 三、让网页用上它

在链接后面加 `?api=`，其它啥都不用改：

```
备案项目地图.html?api=https://jbufa.xxx.workers.dev
```

- 电脑：双击这个链接（或建个快捷方式）。
- 手机：把 HTML 传到手机（微信发给自己→另存），打开时带上 `?api=`，存成书签；标题下会显示「飞书实时 12:01 · 18 条」。
- 如果设了 `ACCESS_KEY`，再加 `&key=你的口令`。
- 拿不到 Worker（断网、地址写错、额度用完）会自动退回内置快照，页面照常能看。
- 想固定下来不用每次拼参数：在 HTML 里搜 `window.REMOTE_API` 那行上方，加一行 `window.REMOTE_API = 'https://jbufa.xxx.workers.dev';`（改 `app\map_template.html` 后重新 `python app\build_map_html.py`）。

## 四、跟现有链路的关系

- 每天 02:00 的导出 + 飞书写入不变，Worker 只是「读」。
- 快照照常生成：电脑关机、Worker 挂了都还有备用数据。
- 局域网 8787 照常可用，优先级：`?data=` / `?api=` → 同目录 json → 8787 → 快照。

## 五、常见问题

| 现象 | 原因 |
| --- | --- |
| `/projects.json` 返回 403 | 设了 `ACCESS_KEY` 但没带 `?key=` |
| 返回 502 + `取 token 失败` | app_id/secret 填错，或应用没发布版本 |
| 返回 502 + `读表内容失败`，code=1310213 | 应用没被加为这张表的文档应用；表格「…」→ 添加文档应用 |
| 有条目但字段少了 | 应用仍只有旧权限，重新发布版本 |
| 页面还是显示「内置快照」 | 参数没带上，或 Worker 地址 404 |
