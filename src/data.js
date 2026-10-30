// 載入與正規化資料。
// 資料由 _build/build_site.py 輸出成精簡格式的 data.json,由 src/boot.js 抓回來放到 window.DATA 再啟動 main.js;
// 簡繁對照表由建置注入 index.html 的 window.AZ_STMAP。
// 這裡做:精簡格式還原(expandData)、正規化(加搜尋用的 _s)與幾個跨模組共用的資料存取小工具,不碰 DOM。

/**
 * 把 build_site.py compact_data() 輸出的精簡格式(v=2)還原成 CLAUDE.md 記載的完整形狀;
 * 沒有 v 欄位(舊的完整格式)就原樣回傳。與 build_site.expand_data() 邏輯一致,改一邊要改另一邊。
 * 精簡鍵:n 編號、m 標題、a 作者、ai 作者 ID 索引(pids)、r 譯者、ri 譯者 ID 索引、p 人設、s 收錄篇名、
 *         l 閱讀連結、d 原文已刪、c ck、e ek、g 標籤(依 facets 順序,每格是 options 索引或原字串)。
 */
export function expandData(C) {
  if (!C || C.v !== 2) return C;
  const facets = C.facets || [];
  const pids = C.pids || Object.keys(C.people || {});
  const ids = (lst) => (lst || []).map((i) => (typeof i === 'number' && i >= 0 && i < pids.length ? pids[i] : ''));
  const dateOf = (k) => { if (!k) return ''; const s = String(k); return `${+s.slice(0, 4)}/${+s.slice(4, 6)}/${+s.slice(6, 8)}`; };
  const articles = (C.articles || []).map((o) => {
    const tags = {}, g = o.g || [];
    facets.forEach((f, i) => {
      tags[f.key] = (g[i] || []).map((v) => (typeof v === 'number' ? f.options[v][0] : v));
    });
    return {
      no: o.n, name: o.m || '', persona: o.p || '',
      author: o.a || '', author_ids: ids(o.ai), translator: o.r || '', translator_ids: ids(o.ri),
      edited: dateOf(o.e), ek: o.e || 0, created: dateOf(o.c), ck: o.c || 0,
      tags, links: o.l || [], dead: !!o.d, alias: o.s || '',
    };
  });
  const D = {};
  for (const k in C) if (k !== 'v' && k !== 'pids' && k !== 'articles') D[k] = C[k];
  D.articles = articles;
  return D;
}

/**
 * 建立簡繁折算函式:把繁體逐字對應成簡體再轉小寫,當作搜尋的統一基準
 * (輸入與資料都折算,所以簡體、繁體輸入都搜得到)。
 * @param {string} t 繁體字串  @param {string} s 同長度的簡體字串(逐字對應)
 */
export function makeFolder(t = '', s = '') {
  const map = {};
  for (let i = 0; i < t.length; i++) map[t[i]] = s[i];
  return function foldZH(str) {
    let o = '';
    for (let i = 0; i < str.length; i++) o += (map[str[i]] || str[i]);
    return o.toLowerCase();
  };
}

/** 每篇可搜尋的文字:標題、作者、譯者、人設、收錄篇名(+ 作者 / 譯者的曾用名,有才加)。 */
export function searchText(a, people) {
  let s = (a.name || '') + ' ' + (a.author || '') + ' ' + (a.translator || '') + ' ' + (a.persona || '') + ' ' + (a.alias || '');
  if (people) {
    const refs = personRefs(a);
    refs.authors.concat(refs.translators).forEach((r) => {
      const p = r.id && people[r.id];
      if (p && p.aliases && p.aliases.length) s += ' ' + p.aliases.join(' ');
    });
  }
  return s;
}

/**
 * 一篇的作者 / 譯者參照:{authors:[{name,id}], translators:[{name,id}]}。
 * name 來自 author / translator 以「、」拆開,id 來自 author_ids / translator_ids 一一對應(舊資料沒有就是空字串)。
 */
export function personRefs(a) {
  const split = (names, ids) => (names || '').split('、').map((nm, i) => ({ name: nm, id: (ids || [])[i] || '' })).filter((r) => r.name);
  return { authors: split(a.author, a.author_ids), translators: split(a.translator, a.translator_ids) };
}

/**
 * 作者查詢:people 以 Notion 作者頁 ID 為鍵 {id: {name, urls, aliases, dead}}。
 *   byId(id)        → 該作者資料或 null
 *   find(name, id)  → 先用 id,沒有(舊資料 / 只有名字的關聯)再用目前名字、曾用名找
 *   idOf(name)      → 名字或曾用名對到的 ID(作者專頁篩選用)
 */
export function makePersonLookup(people) {
  people = people || {};
  const byName = new Map(), byAlias = new Map();
  for (const id in people) {
    const p = people[id] || {};
    if (p.name && !byName.has(p.name)) byName.set(p.name, id);
    (p.aliases || []).forEach((al) => { if (al && !byAlias.has(al)) byAlias.set(al, id); });
  }
  const idOf = (name) => byName.get(name) || byAlias.get(name) || null;
  return {
    byId: (id) => (id && people[id]) || null,
    find: (name, id) => (id && people[id]) || people[idOf(name)] || null,
    idOf,
  };
}

/**
 * 正規化:就地替每篇補上 _s(折算後的搜尋字串),並把可能缺的欄位補成空陣列/物件。
 * 回傳同一個物件(方便鏈式使用)。
 */
export function normalizeData(raw, fold = (s) => s.toLowerCase()) {
  const D = raw || {};
  D.articles = D.articles || [];
  D.facets = D.facets || [];
  D.people = D.people || {};
  D.announcements = D.announcements || [];
  D.dead_authors = D.dead_authors || [];
  D.total = D.total == null ? D.articles.length : D.total;
  D.articles.forEach((a) => { a._s = fold(searchText(a, D.people)); });
  return D;
}

/** 抓 data.json(精簡格式)→ Promise<物件>;HTTP 不是 2xx 就 reject。首頁 boot.js 與統計星圖 stats_page.js 共用。 */
export function fetchData(url = 'data.json') {
  return fetch(url).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
}

/** 從全域變數載入(瀏覽器端用):window.DATA 由 boot.js / stats_page.js 抓 data.json 放進來(精簡或完整格式皆可)。 */
export function loadData() {
  const st = (typeof window !== 'undefined' && window.AZ_STMAP) || { t: '', s: '' };
  const foldZH = makeFolder(st.t, st.s);
  const D = normalizeData(expandData((typeof window !== 'undefined' && window.DATA) || {}), foldZH);
  return { D, foldZH };
}

/** 單選分面(文章類型/篇幅/結局/狀態)的值:tags[k] 的第一個,沒有就空字串。 */
export const sg = (a, k) => (a.tags && a.tags[k] && a.tags[k][0]) || '';

/** 一篇的作者 + 譯者名單(「、」分隔)。 */
export function persons(a) {
  return (a.author || '').split('、').concat((a.translator || '').split('、')).filter(Boolean);
}

/** 標籤 → 所屬多選分面(點書卡標籤可直接篩選)。 */
export function buildTag2Facet(facets) {
  const m = {};
  (facets || []).forEach((f) => { if (f.type === 'multi') f.options.forEach(([v]) => { m[v] = f.key; }); });
  return m;
}

/** 公告排序:📌 置頂排前面,其餘新→舊。 */
export function sortAnnouncements(anns) {
  return (anns || []).slice().sort((x, y) => (y.pin ? 1 : 0) - (x.pin ? 1 : 0) || (y.dk || 0) - (x.dk || 0));
}

// 閱讀連結:[名稱, 網址] 或 [名稱, 網址, 1](第三格 1 = 已失效,build_site.py 由 Notion 的 ❌ 轉出)。
// 站內互連(annyeongz:<編號>,前傳/續寫)只是跳到別篇,不算這篇的有效/失效連結。
export const isExt = (l) => !l[1].startsWith('annyeongz:');
export function liveCount(a) { return (a.links || []).filter((l) => isExt(l) && !l[2]).length; }
