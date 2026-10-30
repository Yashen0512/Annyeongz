// 統計星圖(stats.html):統計計算與圖表設定。
// 前半是純函式(不碰 DOM、不碰 window,Vitest 直接測):每月分組、累積、排行、比例、年度已刪。
// 後半把統計結果組成 Chart.js 設定物件(也是純函式),最後 createCharts() 才真的 new Chart。
// 資料載入沿用 src/data.js(stats_page.js 負責接 DOM 事件與主題切換)。
import { personRefs } from './data.js';

/** 宇宙誕生日(首頁頁尾同一天)。 */
export const BIRTH = { y: 2023, m: 8, d: 7 };
/** 每月趨勢起點(YYYYMM)。 */
export const START_YM = 202308;

// ---------- 日期小工具 ----------

/** ck / ek(YYYYMMDDHHMM 整數)→ YYYYMM;沒有回 0。 */
export const ymOf = (ck) => (ck ? Math.floor(ck / 1e6) : 0);
/** ck → 年份;沒有回 0。 */
export const yearOf = (ck) => (ck ? Math.floor(ck / 1e8) : 0);
/** Date → YYYYMM。 */
export const ymOfDate = (d) => d.getFullYear() * 100 + (d.getMonth() + 1);
/** YYYYMM → 顯示字串 2023/08。 */
export const ymLabel = (ym) => `${Math.floor(ym / 100)}/${String(ym % 100).padStart(2, '0')}`;

/** 連續月份清單(含頭尾)。end < start 時只回 [start]。 */
export function monthRange(startYM, endYM) {
  const out = [];
  let y = Math.floor(startYM / 100), m = startYM % 100;
  for (let guard = 0; guard < 1200; guard++) {
    const ym = y * 100 + m;
    out.push(ym);
    if (ym >= endYM) break;
    if (++m > 12) { m = 1; y++; }
  }
  return out;
}

/** 從宇宙誕生到 today 的天數(台北日曆日,UTC 計算避免時區 / 夏令差)。 */
export function daysSince(birth, today) {
  const a = Date.UTC(birth.y, birth.m - 1, birth.d);
  const b = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.max(0, Math.round((b - a) / 86400000));
}

// ---------- 統計(純函式)----------

/**
 * 每月新收錄 + 累積總數。
 * @returns {{months:number[], labels:string[], counts:number[], cumulative:number[]}}
 *   起點之前就收錄的篇數會算進累積的起始值(不會憑空消失),終點之後的不計。
 */
export function monthlyCounts(articles, startYM = START_YM, endYM = startYM) {
  const months = monthRange(startYM, endYM);
  const idx = new Map(months.map((ym, i) => [ym, i]));
  const counts = months.map(() => 0);
  let before = 0;
  (articles || []).forEach((a) => {
    const ym = ymOf(a.ck);
    if (!ym) return;
    if (ym < startYM) before++;
    else if (idx.has(ym)) counts[idx.get(ym)]++;
  });
  const cumulative = [];
  let acc = before;
  counts.forEach((c) => { acc += c; cumulative.push(acc); });
  return { months, labels: months.map(ymLabel), counts, cumulative };
}

/**
 * 標籤篇數排行(只算多選分面,與首頁「熱門星系」一致)。
 * @param {object[]} articles  @param {object[]} facets  @param {{excludeDead?:boolean, top?:number}} opt
 * @returns {{tag:string, facet:string, count:number}[]} 篇數多→少,同數依標籤名(zh-Hant)
 */
export function tagRanking(articles, facets, { excludeDead = false, top = 20 } = {}) {
  const keys = (facets || []).filter((f) => f.type === 'multi').map((f) => f.key);
  const cnt = new Map();   // "facet\u0000tag" → count
  (articles || []).forEach((a) => {
    if (excludeDead && a.dead) return;
    keys.forEach((k) => ((a.tags && a.tags[k]) || []).forEach((t) => {
      const id = k + '\u0000' + t;
      cnt.set(id, (cnt.get(id) || 0) + 1);
    }));
  });
  return [...cnt].map(([id, count]) => { const [facet, tag] = id.split('\u0000'); return { tag, facet, count }; })
    .sort((x, y) => y.count - x.count || x.tag.localeCompare(y.tag, 'zh-Hant'))
    .slice(0, top);
}

/**
 * 作者篇數排行:作者與譯者都算(與首頁作者專頁的篇數一致),同一篇同一人只算一次。
 * 以 Notion 作者頁 ID 歸戶(沒有 ID 的舊資料退回用名字),顯示名用 people 目前的名字。
 * @returns {{name:string, id:string, count:number}[]} 篇數多→少,同數依名字
 */
export function authorRanking(articles, people = {}, { top = 20 } = {}) {
  const cnt = new Map();   // key(id 或 名字) → {name, id, count}
  (articles || []).forEach((a) => {
    const refs = personRefs(a);
    const seen = new Set();
    refs.authors.concat(refs.translators).forEach((r) => {
      const key = r.id || ('name:' + r.name);
      if (seen.has(key)) return;
      seen.add(key);
      const cur = cnt.get(key) || { name: (r.id && people[r.id] && people[r.id].name) || r.name, id: r.id || '', count: 0 };
      cur.count++;
      cnt.set(key, cur);
    });
  });
  return [...cnt.values()].sort((x, y) => y.count - x.count || x.name.localeCompare(y.name, 'zh-Hant')).slice(0, top);
}

/** 原文已刪篇數與比例(pct 四捨五入到小數一位)。 */
export function deadRatio(articles) {
  const total = (articles || []).length;
  const dead = (articles || []).filter((a) => a.dead).length;
  return { dead, total, pct: total ? Math.round((dead / total) * 1000) / 10 : 0 };
}

/** 作者數:作者 + 譯者去重(ID 優先,沒有 ID 用名字)。 */
export function personCount(articles) {
  const s = new Set();
  (articles || []).forEach((a) => {
    const refs = personRefs(a);
    refs.authors.concat(refs.translators).forEach((r) => s.add(r.id || ('name:' + r.name)));
  });
  return s.size;
}

/** 標籤數:多選分面裡至少被一篇用到的標籤數。 */
export function tagCount(articles, facets) {
  return tagRanking(articles, facets, { top: Infinity }).length;
}

/** 總覽數字卡的全部數字。 */
export function overview(D, today = new Date()) {
  const arts = (D && D.articles) || [];
  const dr = deadRatio(arts);
  return {
    total: arts.length, people: personCount(arts), tags: tagCount(arts, (D && D.facets) || []),
    dead: dr.dead, deadPct: dr.pct, days: daysSince(BIRTH, today),
  };
}

/**
 * 愛心 / 觀測散佈點。counts = {編號: [愛心, 觀測]}(Val Town 或備份檔格式)。
 * 原文已刪的不計(首頁也不顯示它們的計數);沒有計數的篇不畫點。
 * @returns {{x:number, y:number, no:string, name:string}[]}
 */
export function scatterPoints(articles, counts) {
  if (!counts) return [];
  const out = [];
  (articles || []).forEach((a) => {
    if (a.dead) return;
    const c = counts[a.no];
    if (!Array.isArray(c)) return;
    out.push({ x: +c[1] || 0, y: +c[0] || 0, no: a.no, name: a.name || '' });
  });
  return out;
}

/**
 * 按收錄年份分組:每年篇數與其中已刪篇數。
 * @returns {{year:number, total:number, dead:number, alive:number}[]} 年份小→大(沒有 ck 的不計)
 */
export function yearlyDead(articles) {
  const m = new Map();
  (articles || []).forEach((a) => {
    const y = yearOf(a.ck);
    if (!y) return;
    const cur = m.get(y) || { year: y, total: 0, dead: 0, alive: 0 };
    cur.total++;
    a.dead ? cur.dead++ : cur.alive++;
    m.set(y, cur);
  });
  return [...m.values()].sort((x, y) => x.year - y.year);
}

// ---------- Chart.js 設定(純函式:回傳設定物件)----------
// colors = { accent, be, he, exc, oe, purp, ink, muted, line, card, font }(stats_page.js 從 CSS 變數讀)

/** 把 #rrggbb 加透明度變 rgba();不是 hex 就原樣回。 */
export function withAlpha(hex, a) {
  const m = /^#([0-9a-f]{6})$/i.exec((hex || '').trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

function baseScale(colors, extra = {}) {
  return { grid: { color: withAlpha(colors.line, 0.6) }, ticks: { color: colors.muted }, border: { color: colors.line }, ...extra };
}
function baseOptions(colors, extra = {}) {
  return {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: colors.ink, boxWidth: 12, boxHeight: 12, usePointStyle: true } },
      tooltip: { backgroundColor: colors.card, titleColor: colors.ink, bodyColor: colors.ink, borderColor: colors.line, borderWidth: 1 },
    },
    ...extra,
  };
}

/** 每月收錄趨勢:新收錄(左軸)+ 累積總數(右軸)。 */
export function monthlyChartConfig(mc, colors) {
  return {
    type: 'line',
    data: {
      labels: mc.labels,
      datasets: [
        { label: '每月新收錄', data: mc.counts, yAxisID: 'y', borderColor: colors.accent, backgroundColor: withAlpha(colors.accent, 0.18),
          fill: true, tension: 0.25, borderWidth: 2, pointRadius: 2, pointHoverRadius: 5 },
        { label: '累積總數(右軸)', data: mc.cumulative, yAxisID: 'y1', borderColor: colors.be, backgroundColor: colors.be,
          borderDash: [6, 4], tension: 0.25, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5 },
      ],
    },
    options: baseOptions(colors, {
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: baseScale(colors, { ticks: { color: colors.muted, maxRotation: 0, autoSkip: true, maxTicksLimit: 14 } }),
        y: baseScale(colors, { position: 'left', beginAtZero: true, title: { display: true, text: '每月新收錄', color: colors.muted } }),
        y1: baseScale(colors, { position: 'right', beginAtZero: true, grid: { drawOnChartArea: false }, title: { display: true, text: '累積總數', color: colors.muted } }),
      },
    }),
  };
}

/** 排行橫條圖(標籤 / 作者共用)。 */
export function rankingChartConfig(labels, counts, colors, { color = colors.accent, onClick } = {}) {
  return {
    type: 'bar',
    data: { labels, datasets: [{ label: '篇數', data: counts, backgroundColor: withAlpha(color, 0.75), borderColor: color, borderWidth: 1, borderRadius: 4, maxBarThickness: 22 }] },
    options: baseOptions(colors, {
      indexAxis: 'y',
      onClick: onClick ? (evt, els) => { if (els && els.length) onClick(els[0].index); } : undefined,
      onHover: onClick ? (evt, els) => { if (evt.native && evt.native.target) evt.native.target.style.cursor = els.length ? 'pointer' : 'default'; } : undefined,
      plugins: { legend: { display: false }, tooltip: baseOptions(colors).plugins.tooltip },
      scales: {
        x: baseScale(colors, { beginAtZero: true, ticks: { color: colors.muted, precision: 0 } }),
        y: baseScale(colors, { grid: { display: false }, ticks: { color: colors.ink, autoSkip: false, font: { size: 12 } } }),
      },
    }),
  };
}

/** 愛心 × 觀測散佈圖:hover 顯示標題,點擊交給 onClick(點資料)。 */
export function scatterChartConfig(points, colors, { onClick } = {}) {
  return {
    type: 'scatter',
    data: { datasets: [{ label: '每點一篇', data: points, backgroundColor: withAlpha(colors.purp, 0.55), borderColor: colors.purp, borderWidth: 1, pointRadius: 4, pointHoverRadius: 7 }] },
    options: baseOptions(colors, {
      onClick: onClick ? (evt, els) => { if (els && els.length) onClick(points[els[0].index]); } : undefined,
      onHover: onClick ? (evt, els) => { if (evt.native && evt.native.target) evt.native.target.style.cursor = els.length ? 'pointer' : 'default'; } : undefined,
      plugins: {
        legend: { display: false },
        tooltip: { ...baseOptions(colors).plugins.tooltip, callbacks: {
          title: (items) => items.map((it) => `#${it.raw.no} ${it.raw.name}`),
          label: (it) => `🔭 觀測 ${it.raw.x}・❤️ 愛心 ${it.raw.y}`,
        } },
      },
      scales: {
        x: baseScale(colors, { beginAtZero: true, title: { display: true, text: '🔭 觀測數', color: colors.muted }, ticks: { color: colors.muted, precision: 0 } }),
        y: baseScale(colors, { beginAtZero: true, title: { display: true, text: '❤️ 愛心數', color: colors.muted }, ticks: { color: colors.muted, precision: 0 } }),
      },
    }),
  };
}

/** 年度收錄 vs 已刪(堆疊長條)。 */
export function yearlyChartConfig(rows, colors) {
  return {
    type: 'bar',
    data: {
      labels: rows.map((r) => String(r.year)),
      datasets: [
        { label: '仍可閱讀', data: rows.map((r) => r.alive), backgroundColor: withAlpha(colors.he, 0.75), borderColor: colors.he, borderWidth: 1, borderRadius: 4, maxBarThickness: 64 },
        { label: '原文已刪', data: rows.map((r) => r.dead), backgroundColor: withAlpha(colors.exc, 0.75), borderColor: colors.exc, borderWidth: 1, borderRadius: 4, maxBarThickness: 64 },
      ],
    },
    options: baseOptions(colors, {
      plugins: { ...baseOptions(colors).plugins, tooltip: { ...baseOptions(colors).plugins.tooltip, callbacks: {
        footer: (items) => { const r = rows[items[0].dataIndex]; return `共 ${r.total} 篇,已刪 ${r.total ? Math.round((r.dead / r.total) * 1000) / 10 : 0}%`; },
      } } },
      scales: {
        x: baseScale(colors, { stacked: true, grid: { display: false } }),
        y: baseScale(colors, { stacked: true, beginAtZero: true, ticks: { color: colors.muted, precision: 0 } }),
      },
    }),
  };
}

// ---------- 建圖 ----------

/**
 * 在六個 canvas 上畫出全部圖表。重畫(主題切換 / 切「排除已刪」)就 destroy 後再呼叫一次。
 * @param {Function} Chart        Chart.js 建構子(vendor/chart.umd.js 掛在 window.Chart)
 * @param {object} D              正規化後的資料(loadData)
 * @param {object} opt
 *   canvases   {monthly, tags, authors, scatter, yearly}:各圖的 <canvas>(缺的就跳過)
 *   colors     見上方 colors 說明
 *   counts     {編號: [愛心, 觀測]} 或 null(null 時散佈圖不畫)
 *   excludeDead  標籤排行是否排除原文已刪
 *   now        目前時間(每月趨勢終點)
 *   onAuthorClick(name, id) / onPointClick(point)
 * @returns {{charts: object[], tags: object[], authors: object[]}}
 */
export function createCharts(Chart, D, opt = {}) {
  const { canvases = {}, colors, counts = null, excludeDead = false, now = new Date(), onAuthorClick, onPointClick } = opt;
  const charts = [];
  const make = (cv, cfg) => { if (cv && cfg) charts.push(new Chart(cv, cfg)); };

  make(canvases.monthly, monthlyChartConfig(monthlyCounts(D.articles, START_YM, Math.max(START_YM, ymOfDate(now))), colors));

  const tags = tagRanking(D.articles, D.facets, { excludeDead, top: 20 });
  make(canvases.tags, rankingChartConfig(tags.map((t) => t.tag), tags.map((t) => t.count), colors));

  const authors = authorRanking(D.articles, D.people, { top: 20 });
  make(canvases.authors, rankingChartConfig(authors.map((p) => p.name), authors.map((p) => p.count), colors, {
    color: colors.be, onClick: onAuthorClick ? (i) => onAuthorClick(authors[i].name, authors[i].id) : undefined,
  }));

  if (counts) make(canvases.scatter, scatterChartConfig(scatterPoints(D.articles, counts), colors, { onClick: onPointClick }));

  make(canvases.yearly, yearlyChartConfig(yearlyDead(D.articles), colors));
  return { charts, tags, authors };
}
