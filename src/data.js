// 載入與正規化資料。
// 資料由 _build/build_site.py 在建置時注入 index.html(window.DATA),簡繁對照表注入 window.AZ_STMAP。
// 這裡只做讀取、正規化(加搜尋用的 _s)與幾個跨模組共用的資料存取小工具,不碰 DOM。

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

/** 從建置注入的全域變數載入(瀏覽器端用)。 */
export function loadData() {
  const st = (typeof window !== 'undefined' && window.AZ_STMAP) || { t: '', s: '' };
  const foldZH = makeFolder(st.t, st.s);
  const D = normalizeData((typeof window !== 'undefined' && window.DATA) || {}, foldZH);
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
