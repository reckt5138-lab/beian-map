/**
 * 青鸾备案项目地图 · 飞书只读中转（Cloudflare Worker，免费）
 * ---------------------------------------------------------------
 * 作用：把「飞书在线表格」变成手机/电脑都能直接打开的 JSON 接口。
 *   网页里不出现任何密钥；密钥只存在这个 Worker 的变量里。
 *   应用必须是「只读」应用（权限只开 sheets:spreadsheet:readonly）。
 *
 * 部署：Cloudflare → Workers & Pages → Create Worker → 粘贴本文件 →
 *       Settings → Variables and Secrets 里加 4 个变量（见下）→ Deploy。
 *
 * 环境变量（Variables and Secrets，选 Secret 类型更稳妥）
 *   FEISHU_APP_ID       自建应用 app_id
 *   FEISHU_APP_SECRET   自建应用 app_secret（只读应用）
 *   SPREADSHEET_TOKEN   表格 token（E1Acs...）
 *   SHEET_ID            工作表 id（d154b6）
 *   ACCESS_KEY          （可选）给接口加一道口令，留空则不加
 *   ALLOW_ORIGIN        （可选）默认 *，可改成 https://你的域名
 *
 * 接口
 *   GET /            自检，返回 ok / 时间 / 条数
 *   GET /projects.json   地图数据（结构和本地 projects.json 一致，缓存 60 秒）
 *   GET /projects.json?refresh=1   跳过缓存
 */

const API_BASE = "https://open.feishu.cn";
const CACHE_SECONDS = 60;

// 表头 → 输出字段（与 app\sheet_to_projects.py 的 FIELD_MAP 完全一致）
const FIELD_MAP = {
  "项目名称": "name",
  "项目地址": "addr",
  "业务员": "owner",
  "部门": "dept",
  "面积": "area",
  "客户信息": "customer",
  "产品类型": "product",
  "项目分类": "classify",
  "项目类型": "ptype",
  "建设类型": "build",
  "项目进度": "stage",
  "预计合同金额": "amount",
  "折扣信息": "discount",
  "项目情况描述": "desc",
  "智能疏散跟进情况": "evac",
  "公司性质": "customerType",
  "公司资质": "customerQual",
  "职位": "contact",
  "公司地址": "customerAddr",
  "备案时间": "filing",
  "失效时间": "expire",
  "创建时间": "created",
  "最后一次签到时间": "lastSign",
  "项目签到次数": "signCount",
  "申请报价次数": "quoteTimes",
  "是否报价": "quoted",
  "项目来源": "source",
  "最后一次签到记录": "lastRecord",
  "项目工期": "duration",
  "垂直/非垂直": "vertical"
};

const DATE_FIELDS = ["filing", "expire", "created", "lastSign"];
const SIGN_PAIR_HEADERS = ["签到时间", "签到记录"];

const DISTRICT_CENTER = {
  "东城区": [39.928, 116.416],
  "西城区": [39.912, 116.366],
  "朝阳区": [39.948, 116.486],
  "海淀区": [39.959, 116.298],
  "丰台区": [39.858, 116.286],
  "石景山区": [39.906, 116.223],
  "通州区": [39.902, 116.658],
  "大兴区": [39.726, 116.338],
  "昌平区": [40.221, 116.231],
  "顺义区": [40.130, 116.654],
  "房山区": [39.749, 116.143],
  "门头沟区": [39.940, 116.102],
  "平谷区": [40.141, 117.121],
  "怀柔区": [40.316, 116.632],
  "密云区": [40.377, 116.843],
  "延庆区": [40.456, 115.975]
};

// 精确坐标（= data\coords.json），新增项目想精确就加一行
const COORDS = {
  "第三批央企在京老旧小区综合整治项目（标包三百三十八）（南郎家园小区 2‑11 号楼、13‑15 号楼）（一标段）工程总承包（EPC）": [39.9055, 116.478],
  "北京市朝阳区东坝车辆基地综合利用项目五期": [39.966, 116.558],
  "成都地区公寓住房统建项目": [30.643, 104.043],
  "报价专用2": [39.991, 116.315],
  "北京电源天空之境装修工程项目": [39.9924, 116.3172],
  "华文国际大厦三水一电项目": [39.907, 116.487],
  "邮储银行丰台数据中心应急照明疏散指示系统更新项目": [39.847, 116.214],
  "得熠花椒佛跳墙楼上改造项目": [39.985, 116.39],
  "星光轻社区改造": [39.793, 116.328],
  "隆瑞三优充电站建设—通州商务园": [39.918, 116.685],
  "北京城市副中心0403街区FZX-0403-6003、0403-6005、0403-6006、0403-6007、0403-6008、0403-6009、0403-6011地块": [39.903, 116.648],
  "FZX-0601-0003、FZX-0601-0006、FZX-0601-0007、FZX-0601-0011": [39.938, 116.682],
  "埃塞俄比亚比绍夫图国际机场": [8.93, 39.78],
  "乐家生活馆翻新项目": [39.781, 116.33],
  "北京市三环英和医院改造工程": [39.848, 116.332],
  "北蜂窝路5号院气灭区改造项目": [39.901, 116.326],
  "北京市朝阳区东坝车辆基地综合利用项目三期": [39.962, 116.568],
  "丰台区城乡一体化周庄子村旧村改造项目二期ZZZ-06等地块(配建“共有产权住房”)项目ZZZ-L01(东)、ZZZ-L04(东)绿隔产业用地(含经济型酒店)": [39.845, 116.295]
};

let TOKEN = { value: "", exp: 0 };
let CACHE = { at: 0, body: "" };

/* ---------- 工具 ---------- */

function cell(v) {
  if (Array.isArray(v)) {
    return v.map(x => (x && typeof x === "object" ? String(x.text ?? "") : String(x))).join("");
  }
  return v == null ? "" : String(v);
}

function normDate(s) {
  s = s == null ? "" : String(s).trim();
  if (!s) return "";
  const num = Number(s);
  if (!isNaN(num) && num > 20000 && num < 80000) {
    const d = new Date(Date.UTC(1899, 11, 30) + Math.floor(num) * 86400000);
    return d.toISOString().slice(0, 10);
  }
  const head = s.split(" ")[0].split("T")[0].replace(/[/.]/g, "-");
  const parts = head.split("-");
  if (parts.length === 3 && parts.every(p => /^\d+$/.test(p))) {
    return parts[0].padStart(4, "0") + "-" + parts[1].padStart(2, "0") + "-" + parts[2].padStart(2, "0");
  }
  return s;
}

function jitter(name) {
  const s = String(name || "");
  let h = 0;
  for (let i = 0; i < s.length; i++) h += s.charCodeAt(i) * (i + 7);
  const a = (h % 360) * 3.14159 / 180;
  const r = 0.012 + (h % 7) * 0.002;
  void a;
  return [Math.round((Math.abs(h) % 1000 / 1000) * r * 0.4 * 100000) / 100000, Math.round(r * 0.5 * 100000) / 100000];
}

function districtOf(addr) {
  const s = String(addr || "");
  for (const d in DISTRICT_CENTER) if (s.indexOf(d) >= 0) return d;
  return "";
}

function nowCST() {
  const d = new Date(Date.now() + 8 * 3600 * 1000);
  return d.toISOString().replace("T", " ").slice(0, 19);
}

/* ---------- 飞书 ---------- */

async function tenantToken(env) {
  if (TOKEN.value && TOKEN.exp > Date.now() / 1000 + 60) return TOKEN.value;
  const r = await fetch(API_BASE + "/open-apis/auth/v3/tenant_access_token/internal", {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify({ app_id: env.FEISHU_APP_ID, app_secret: env.FEISHU_APP_SECRET })
  });
  const j = await r.json();
  if (j.code !== 0) throw new Error("取 token 失败：" + JSON.stringify(j));
  TOKEN = { value: j.tenant_access_token, exp: Date.now() / 1000 + (j.expire || 7200) };
  return TOKEN.value;
}

function colLetter(n) {
  let out = "";
  while (n > 0) {
    const r = (n - 1) % 26;
    out = String.fromCharCode(65 + r) + out;
    n = Math.floor((n - 1) / 26);
  }
  return out;
}

async function readSheet(env) {
  const token = await tenantToken(env);
  const url = API_BASE + "/open-apis/sheets/v2/spreadsheets/" + env.SPREADSHEET_TOKEN;
  const meta = await (await fetch(url + "/metainfo", { headers: { Authorization: "Bearer " + token } })).json();
  if (meta.code !== 0) throw new Error("读表结构失败：" + JSON.stringify(meta));
  const sheets = (meta.data && meta.data.sheets) || [];
  const sid = env.SHEET_ID || (sheets[0] && (sheets[0].sheetId || sheets[0].sheet_id));
  const info = sheets.find(s => (s.sheetId || s.sheet_id) === sid) || {};
  const rows = Number(info.rowCount || 200);
  const cols = Number(info.columnCount || 200);
  const range = sid + "!A1:" + colLetter(cols) + rows;
  const j = await (await fetch(url + "/values/" + encodeURIComponent(range), { headers: { Authorization: "Bearer " + token } })).json();
  if (j.code !== 0) throw new Error("读表内容失败：" + JSON.stringify(j));
  return ((j.data || {}).valueRange || {}).values || [];
}

/* ---------- 映射 ---------- */

function parse(matrix) {
  if (!matrix || !matrix.length) return { projects: [], columns: 0 };
  const headers = matrix[0].map(h => cell(h).trim());
  const pos = {};
  headers.forEach((h, i) => { if (h && pos[h] === undefined) pos[h] = i; });
  const signCols = headers.map((h, i) => (h === "签到记录" ? i : -1)).filter(i => i >= 0);

  const out = [];
  for (let r = 1; r < matrix.length; r++) {
    const raw = matrix[r];
    if (!raw.some(x => cell(x).trim())) continue;
    const p = {};
    for (const label in FIELD_MAP) {
      const key = FIELD_MAP[label];
      const i = pos[label];
      p[key] = i !== undefined && i < raw.length ? cell(raw[i]).trim() : "";
    }
    const signs = [];
    for (const i of signCols) {
      if (i === 0 || i >= raw.length) continue;
      const note = cell(raw[i]).trim();
      const date = normDate(cell(raw[i - 1]));
      if (note) signs.push({ date, note });
    }
    p.signs = signs;

    const seen = {};
    const fields = [];
    for (let i = 0; i < headers.length; i++) {
      const h = headers[i];
      if (!h || SIGN_PAIR_HEADERS.indexOf(h) >= 0) continue;
      if (i >= raw.length) break;
      const v = cell(raw[i]).trim();
      if (!v) continue;
      const cnt = (seen[h] || 0) + 1;
      seen[h] = cnt;
      fields.push([cnt === 1 ? h : h + "（" + cnt + "）", v]);
    }
    p.fields = fields;
    for (const k of DATE_FIELDS) p[k] = normDate(p[k]);
    if (!p.name) continue;

    const hit = COORDS[p.name];
    if (hit && hit.length === 2 && hit[0] && hit[1]) {
      p.lat = Number(hit[0]);
      p.lng = Number(hit[1]);
      p.geo = "exact";
    } else {
      const d = districtOf(p.addr);
      if (d) {
        const base = DISTRICT_CENTER[d];
        const j = jitter(p.name);
        p.lat = Math.round((base[0] + j[0] - 0.004) * 1e6) / 1e6;
        p.lng = Math.round((base[1] + j[1] - 0.006) * 1e6) / 1e6;
        p.geo = "district";
      } else {
        p.lat = null;
        p.lng = null;
        p.geo = "none";
      }
    }
    out.push(p);
  }
  return { projects: out, columns: headers.length };
}

async function buildPayload(env) {
  const matrix = await readSheet(env);
  const { projects, columns } = parse(matrix);
  return {
    updated: nowCST(),
    source: "飞书在线表格（Worker 代理）",
    sheet: "备案项目每日导出",
    columns,
    count: projects.length,
    projects
  };
}

/* ---------- HTTP ---------- */

function cors(env) {
  return {
    "Access-Control-Allow-Origin": env.ALLOW_ORIGIN || "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
  };
}

export default {
  async fetch(request, env) {
    const u = new URL(request.url);
    const H = cors(env);
    H["Cache-Control"] = "no-store";

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: H });

    if (env.ACCESS_KEY) {
      const given = u.searchParams.get("key") || "";
      if (given !== env.ACCESS_KEY) {
        return new Response(JSON.stringify({ error: "key 不对" }), { status: 403, headers: { ...H, "Content-Type": "application/json; charset=utf-8" } });
      }
    }

    try {
      if (u.pathname === "/" || u.pathname === "/health") {
        const body = JSON.stringify({ ok: true, time: nowCST() });
        return new Response(body, { headers: { ...H, "Content-Type": "application/json; charset=utf-8" } });
      }

      if (u.pathname === "/projects.json" || u.pathname === "/api/projects") {
        const force = u.searchParams.get("refresh") === "1";
        const fresh = !force && CACHE.body && Date.now() / 1000 - CACHE.at < CACHE_SECONDS;
        if (!fresh) {
          const payload = await buildPayload(env);
          CACHE = { at: Date.now() / 1000, body: JSON.stringify(payload) };
        }
        return new Response(CACHE.body, { headers: { ...H, "Content-Type": "application/json; charset=utf-8" } });
      }

      return new Response(JSON.stringify({ error: "not found" }), { status: 404, headers: { ...H, "Content-Type": "application/json; charset=utf-8" } });
    } catch (e) {
      const body = JSON.stringify({ error: String((e && e.message) || e), projects: [], count: 0 });
      return new Response(body, { status: 502, headers: { ...H, "Content-Type": "application/json; charset=utf-8" } });
    }
  }
};
