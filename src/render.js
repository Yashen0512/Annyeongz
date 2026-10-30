// 畫面產生:書卡、輪播小卡、分類面板、條件列、分頁、詳情 / 公告彈窗、統計卡。
// 這裡只負責把資料變成 DOM / HTML 字串;狀態與事件的接線在 main.js。
//
// 注意:詳情與書卡的 HTML 字串裡用 inline onclick 呼叫下列全域函式(由 main.js 掛到 window):
//   toggleFav / toggleTodo / toggleRead / setShelfTab / filterByTag / filterName / openByNo /
//   closeDetail / navDetail / toggleReport / pickReason / sendReport / shelfExport / shelfImport / shelfClear
//
// ctx(由 main.js 組好傳入)欄位:
//   facets, persons(data.js makePersonLookup:以作者頁 ID 查名字 / 平台 / 已刪帳號)、deadAuthors(Set,相容舊資料),
//   favs / readSet / todoSet(Set)、likeNum(no) 公開愛心數(0 不顯示)、viewNum(no) 觀測數
import { sg, isExt, liveCount, personRefs } from './data.js';

/** 作者資料(以 ID 為主、名字為輔)→ {urls, dead}。 */
function personInfo(ctx, name, id) {
  const p = ctx.persons ? ctx.persons.find(name, id) : null;
  return { urls: (p && p.urls) || {}, dead: !!(p && p.dead) || ctx.deadAuthors.has(name) };
}

export const endCls = (e) => ({ HE: 'he', BE: 'be', OE: 'oe' }[e] || '');
export const STMAP = { '完結': 'done', '完結+番外': 'done', '連載中': 'ongoing', '未完': 'wip', '斷更': 'hiatus', '建置中': 'building', '不定期更新': 'irregular' };
export const STKEY = (s) => STMAP[s] || '';

export const SHELF_META = { fav: ['❤️', '已收藏'], todo: ['🔖', '待閱讀'], read: ['✓', '已讀'] };

/** 詳情/公告視窗底部:上一篇・下一篇。 */
export function navBar(i, n, unit) {
  if (i < 0 || n < 2) return '';
  return `<div class="dnav"><button class="ctl"${i > 0 ? ' onclick="navDetail(-1)"' : ' disabled'}>‹ 上一${unit}</button>`
    + `<span class="dpos">${i + 1} / ${n}</span>`
    + `<button class="ctl"${i < n - 1 ? ' onclick="navDetail(1)"' : ' disabled'}>下一${unit} ›</button></div>`;
}

export function badges(a) {
  const b = [];
  if (a.dead) b.push('<span class="badge dead">原文已刪</span>');
  if (sg(a, '文章類型')) b.push(`<span class="badge type">${sg(a, '文章類型')}</span>`);
  if (sg(a, '文章篇幅')) b.push(`<span class="badge">${sg(a, '文章篇幅')}</span>`);
  if (sg(a, '結局')) b.push(`<span class="badge ${endCls(sg(a, '結局'))}">${sg(a, '結局')}</span>`);
  if (sg(a, '文章狀態')) b.push(`<span class="badge sb-${STKEY(sg(a, '文章狀態'))}">${sg(a, '文章狀態')}</span>`);
  return b.join('');
}

export function multiTags(a, facets) {
  const out = [];
  facets.forEach((f) => { if (f.type === 'multi') (a.tags[f.key] || []).forEach((v) => out.push(v)); });
  return out;
}

// 書卡上的「收錄」只留一行:第一筆(去掉》後面的原文括號)+「等 N 篇」;完整清單在詳情頁
export function aliasLine(al) {
  const L = (al || '').split('\n').map((s) => s.trim()).filter(Boolean);
  if (!L.length) return '';
  const first = L[0].replace(/(》)\s*[(（].*$/, '$1');
  return `<div class="persona alias"><span class="al-t">收錄：${first}</span>${L.length > 1 ? `<span class="al-n">等 ${L.length} 篇</span>` : ''}</div>`;
}

export function cardHTML(a, ctx) {
  const persona = (a.persona || '').replace(/\s*\n\s*/g, ' ／ ').trim();
  const lk = ctx.likeNum(a.no);
  return `<button class="fav-btn${ctx.favs.has(a.no) ? ' on' : ''}" onclick="event.stopPropagation();toggleFav('${a.no}')" title="收藏${lk ? '（' + lk + ' 人收藏）' : ''}" aria-label="收藏">${ctx.favs.has(a.no) ? '❤️' : '🤍'}${lk ? `<span class="fc">${lk}</span>` : ''}</button>
    <div class="t">${a.name || '(無標題)'} <span class="no">#${a.no}</span>${ctx.readSet.has(a.no) ? ' <span class="readmark">✓已讀</span>' : ''}${ctx.todoSet.has(a.no) ? ' <span class="todomark" title="待閱讀">🔖</span>' : ''}</div>
    <div class="badges">${badges(a)}</div>
    ${persona ? `<div class="persona">${persona}</div>` : ''}
    ${aliasLine(a.alias)}
    <div class="tg">${multiTags(a, ctx.facets).map((t) => `<span onclick="event.stopPropagation();filterByTag('${encodeURIComponent(t)}')">${t}</span>`).join('')}</div>`;
}

/** 主列表:把這一頁的書卡放進 listEl。 */
export function renderCards(listEl, hits, ctx, onOpen) {
  const frag = document.createDocumentFragment();
  hits.forEach((a) => {
    const c = document.createElement('div'); const k = STKEY(sg(a, '文章狀態'));
    c.className = 'card' + (k ? ' cst-' + k : '') + (a.dead ? ' dead' : '');
    c.innerHTML = cardHTML(a, ctx); c.onclick = () => onOpen(a); frag.appendChild(c);
  });
  listEl.appendChild(frag);
}

const EMPTY = {
  fav: '🛸 書架還是一片虛空<br><span>點書卡右上角的 🤍 把喜歡的文收藏進來</span>',
  todo: '🔖 還沒有待閱讀的文<br><span>在文章詳情按「🔖 待閱讀」先存起來</span>',
  read: '✓ 還沒有標記已讀的文<br><span>在文章詳情按「標為已讀」記錄讀過的文</span>',
};
/** 沒有結果:書架該分頁是空的用書架版文案,否則用「這片星域沒有符合條件的文」。 */
export function emptyHTML(emptyShelfTab) {
  return emptyShelfTab
    ? `<div class="empty">${EMPTY[emptyShelfTab]}</div>`
    : '<div class="empty">🔭 這片星域沒有符合條件的文<br><span>換個座標試試:放寬條件,或點上方條件標籤把它移除</span></div>';
}

/** 書架分頁列(已收藏/待閱讀/已讀 + 數量)。 */
export function shelfTabsHTML(sets, cur) {
  return Object.entries(SHELF_META).map(([k, [ic, lb]]) => `<button class="ctl${k === cur ? ' on' : ''}" onclick="setShelfTab('${k}')">${ic} ${lb} <span class="sc">${sets[k].size}</span></button>`).join('');
}

/** 左側分類面板:每個分面一個區塊(標題可收合;多選分面有「任一/全部」切換)。 */
export function buildPanel(panelEl, facets, { onTag, onMode }) {
  facets.forEach((f) => {
    if (!f.options.length) return;
    const box = document.createElement('div'); box.className = 'facet';
    const h = document.createElement('h3');
    const showMode = f.type === 'multi';
    h.innerHTML = `<span>${f.key}</span><span class="rt">` + (showMode ? `<span class="mode" data-k="${f.key}">任一</span>` : ``) + `<span class="arw">▾</span></span>`;
    const opts = document.createElement('div'); opts.className = 'opts';
    h.onclick = (e) => {
      if (e.target.classList.contains('mode')) return;
      opts.style.display = opts.style.display === 'none' ? 'flex' : 'none';
      h.querySelector('.arw').textContent = opts.style.display === 'none' ? '▸' : '▾';
    };
    if (showMode) { const mt = h.querySelector('.mode'); mt.onclick = (e) => { e.stopPropagation(); onMode(f.key); }; }
    f.options.forEach(([val, cnt]) => {
      const o = document.createElement('span'); o.className = 'opt';
      o.innerHTML = `${val}<span class="c">${cnt}</span>`;
      o.onclick = () => onTag(f.key, val);
      o._val = val; o._key = f.key; opts.appendChild(o);
    });
    box.appendChild(h); box.appendChild(opts); panelEl.appendChild(box);
  });
}

/** 依目前狀態替面板標籤上色(on 粉底 / exc 紅刪除線)與「任一/全部」字樣。 */
export function syncStyles(sel, modes) {
  document.querySelectorAll('.opt').forEach((o) => { const s = (sel[o._key] || {})[o._val]; o.className = 'opt' + (s === 'on' ? ' on' : s === 'exc' ? ' exc' : ''); });
  document.querySelectorAll('.mode').forEach((m) => { const and = modes[m.dataset.k] === 'and'; m.className = 'mode' + (and ? ' and' : ''); m.textContent = and ? '全部' : '任一'; });
}

/** 熱門星系:所有多選標籤依收錄篇數排序取前 16 個。 */
export function renderHot(wrap, facets, onPick) {
  const all = [];
  facets.forEach((f) => { if (f.type === 'multi') f.options.forEach(([v, c]) => all.push([v, c, f.key])); });
  all.sort((a, b) => b[1] - a[1]);
  wrap.innerHTML = '';
  all.slice(0, 16).forEach(([v, c, key]) => {
    const o = document.createElement('span'); o.className = 'opt'; o.innerHTML = `${v}<span class="c">${c}</span>`;
    o.onclick = () => onPick(key, v);
    wrap.appendChild(o);
  });
}

/** 目前條件列:每個條件一個 chip(可個別移除)+ 清除全部。chips = [{key,val,exc}] */
export function renderSelBar(bar, chips, { onRemove, onClearAll }) {
  bar.innerHTML = '';
  if (!chips.length) { bar.style.display = 'none'; return; }
  bar.style.display = 'flex';
  const head = document.createElement('span'); head.textContent = '目前條件:'; bar.appendChild(head);
  chips.forEach((c) => {
    const el = document.createElement('span'); el.className = 'fchip'; el.innerHTML = (c.exc ? '排除 ' : '') + c.val + ' <b>✕</b>';
    el.onclick = () => onRemove(c.key, c.val); bar.appendChild(el);
  });
  const all = document.createElement('span'); all.className = 'fchip clr'; all.textContent = '清除全部 ✕';
  all.onclick = onClearAll;
  bar.appendChild(all);
}

/** 作者專頁標頭(名字、篇數、平台連結、返回全部)。name 為 null 時隱藏。 */
export function renderAuthorHead(el, name, count, ctx, onClear) {
  if (!name) { el.style.display = 'none'; return; }
  const info = personInfo(ctx, name), p = info.urls;
  const links = Object.keys(p).map((k) => `<a class="plat" href="${p[k]}" target="_blank" rel="noopener">${k}</a>`).join('');
  el.style.display = 'block';
  const deadTag = info.dead ? '<span class="deadauth">(已刪帳號)</span>' : '';
  el.innerHTML = `<div class="ah-row"><span class="ah-name">✍️ ${name}${deadTag}</span><span class="ah-cnt">共 ${count} 篇</span>`
    + `<button class="ah-clear">✕ 返回全部</button></div>`
    + (links ? `<div class="ah-links">${links}</div>` : '');
  el.querySelector('.ah-clear').onclick = onClear;
}

/** 橫向輪播(星際廣播 / 新星誕生 / 軌道更新)的一排小卡。 */
export function renderStrip(wrap, items, { html, cls, onClick }) {
  wrap.innerHTML = '';
  items.forEach((x, i) => {
    const c = document.createElement('div'); c.className = cls ? cls(x) : 'scard';
    c.innerHTML = html(x); c.onclick = () => onClick(x, i); wrap.appendChild(c);
  });
}
export const latestCardHTML = (a) => `<div class="st">${a.name || '(無標題)'}</div><div class="sm">#${a.no}${a.created ? ' · 收錄 ' + a.created : ''}</div>`;
export const statusCardHTML = (a) => `<div class="st">${a.name || '(無標題)'}</div><div class="sm">#${a.no} · ${sg(a, '文章狀態') || '—'}${a.edited ? ' · ' + a.edited : ''}</div>`;
export const annCardHTML = (x) => `<div class="st">${x.content}</div><div class="sm">${x.pin ? '📌 ' : ''}${x.date}</div>`;
export const annCardCls = (x) => 'scard ann-card' + (x.pin ? ' pin' : '');

/** 公告全文彈窗內容。 */
export function annHTML(x, i, n) {
  return `<button class="close" onclick="closeDetail()">✕</button>
    <h2>📻 星際廣播</h2>
    <div class="ann-meta">${x.pin ? '📌 置頂 · ' : ''}${x.date}</div>
    <div class="ann-full">${x.content}</div>` + navBar(i, n, '則');
}

/** 分頁列:上一頁 / 頁碼(目前頁 ±2 + 首尾)/ 下一頁 / 輸入頁數跳轉。 */
export function renderPager(el, page, pages, gotoPage) {
  el.innerHTML = '';
  if (pages <= 1) { return; }
  const add = (label, p, cls) => {
    const b = document.createElement('span'); b.className = 'pg ' + (cls || ''); b.textContent = label;
    if (p && !(cls || '').includes('cur')) b.onclick = () => gotoPage(p); el.appendChild(b);
  };
  add('‹ 上一頁', page > 1 ? page - 1 : null, page > 1 ? '' : 'dis');
  const win = 2, nums = new Set([1, pages]);
  for (let i = page - win; i <= page + win; i++) if (i >= 1 && i <= pages) nums.add(i);
  const sorted = [...nums].sort((a, b) => a - b); let prev = 0;
  sorted.forEach((n) => { if (n - prev > 1) add('…', null, 'dots'); add(String(n), n, n === page ? 'cur' : ''); prev = n; });
  add('下一頁 ›', page < pages ? page + 1 : null, page < pages ? '' : 'dis');
  // 輸入頁數跳轉:Enter 或「前往」;超出範圍自動夾到 1~最後一頁,非數字不動作
  const jump = document.createElement('span'); jump.className = 'pg-jump';
  jump.innerHTML = `第 <input type="number" inputmode="numeric" min="1" max="${pages}" value="${page}" aria-label="輸入頁數"> / ${pages} 頁 <span class="pg">前往</span>`;
  const inp = jump.querySelector('input');
  const go = () => {
    const v = parseInt(inp.value, 10); if (isNaN(v)) { inp.value = page; return; }
    const p = Math.min(pages, Math.max(1, v)); if (p === page) { inp.value = page; return; } gotoPage(p);
  };
  inp.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); go(); } };
  inp.onfocus = () => inp.select();
  jump.querySelector('.pg').onclick = go;
  el.appendChild(jump);
}

/** 詳情:作者 / 譯者列(名字可點看全部 + 平台連結)。refs = [{name, id}](personRefs)。 */
export function personRow(label, refs, ctx) {
  if (!refs || !refs.length) return '';
  const inner = refs.map(({ name: nm, id }) => {
    const info = personInfo(ctx, nm, id), p = info.urls;
    const links = Object.keys(p).map((k) => `<a class="plat pp" href="${p[k]}" target="_blank" rel="noopener">${k}</a>`).join('');
    const see = `<a class="plat pp" href="#" onclick="filterName('${encodeURIComponent(nm)}');return false">看全部</a>`;
    const dead = info.dead ? '<span class="deadauth">(已刪帳號)</span>' : '';
    return `<div class="person"><b class="aname" onclick="filterName('${encodeURIComponent(nm)}')">${nm}</b>${dead} ${links} ${see}</div>`;
  }).join('');
  return `<div class="drow"><span class="dk">${label}</span><span class="dv">${inner}</span></div>`;
}

/** 原文已刪且沒有任何有效連結時,詳情頂端的橫幅。 */
export function deadBar(a) {
  if (!a.dead || liveCount(a)) return '';   // 仍有有效連結時不出橫幅
  const n = (a.links || []).filter(isExt).length;
  return `<div class="deadbar"><span class="ic">⚠️</span><div><b>作者已刪除原文</b>${n ? `<span>${n > 1 ? '所有連結都已失效' : '此連結已失效'}</span>` : ''}</div></div>`;
}

/** 閱讀連結清單:有效排前、失效灰掉(仍可點);每個有效連結有「回報壞掉」表單。 */
export function linksHTML(a) {
  const L = a.links || [];
  if (!L.length) return '<span style="color:var(--muted);font-size:13px">(這篇尚無連結)</span>';
  const idx = L.map((_, i) => i), live = liveCount(a) > 0;
  const order = idx.filter((i) => !L[i][2]).concat(idx.filter((i) => L[i][2]));   // 有效排前、失效排後
  const rows = order.map((i) => {
    const l = L[i], u = l[1];
    if (u.startsWith('annyeongz:')) return `<div class="lrow"><a class="plat" style="cursor:pointer" onclick="openByNo('${u.slice(10)}')">${l[0]} ↗</a></div>`;
    if (l[2]) return `<div class="lrow"><a class="plat dead" href="${u}" target="_blank" rel="noopener"><s>${l[0]}</s> ❌</a><span class="lstat">已確認失效</span>${live ? '<div class="lnote">此連結已失效,可改讀其他連結</div>' : ''}</div>`;
    return `<div class="lrow"><a class="plat" href="${u}" target="_blank" rel="noopener">${l[0]}</a><button class="lrep" onclick="toggleReport('rb${i}')">回報壞掉</button>
      <div class="repbox" id="rb${i}">
        <div class="q">回報這個連結的問題:</div>
        <div class="opts">
          <button class="ctl" onclick="pickReason(this)">🔗 打不開</button>
          <button class="ctl" onclick="pickReason(this)">🗑 被刪了</button>
          <button class="ctl" onclick="pickReason(this)">❓ 內容不符</button>
          <button class="ctl" onclick="pickReason(this,1)">✏️ 其他</button>
        </div>
        <textarea rows="2" placeholder="請簡述問題…" style="display:none;width:100%;box-sizing:border-box;font-size:13px;padding:6px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);resize:vertical"></textarea>
        <div style="margin-top:6px;display:flex;align-items:center;gap:8px"><button class="ctl" onclick="sendReport('${a.no}',${i})">送出回報</button><span class="rmsg" style="font-size:13px;color:var(--muted)"></span></div>
      </div></div>`;
  }).join('');
  return `<div class="links">${rows}</div>${a.dead && live ? '<div class="deadnote">(此篇多數內容已失效,僅部分連結仍可閱讀)</div>' : ''}`;
}

/**
 * 文章詳情彈窗內容。
 * @param a 文章  @param ctx 見檔頭
 * @param {{rel:Array, navIndex:number, navLen:number}} extra 類似的文、在上下篇清單中的位置
 */
export function detailHTML(a, ctx, { rel, navIndex, navLen }) {
  const lk = ctx.likeNum(a.no), vw = ctx.viewNum(a.no);
  let rows = '';
  ctx.facets.forEach((f) => {
    if (f.type !== 'multi') return; const vals = [...new Set(a.tags[f.key] || [])]; if (!vals.length) return;
    rows += `<div class="drow"><span class="dk">${f.key}</span><span class="dv">${vals.map((v) => `<span class="chip" onclick="filterByTag('${encodeURIComponent(v)}')">${v}</span>`).join('')}</span></div>`;
  });
  return `<button class="close" onclick="closeDetail()">✕</button>
    <h2>${a.name || '(無標題)'} <span class="no">#${a.no}</span></h2>
    <div class="badges">${badges(a)}</div>
    <div class="detail-actions">
      <button class="ctl${ctx.favs.has(a.no) ? ' on' : ''}" onclick="toggleFav('${a.no}')">${ctx.favs.has(a.no) ? '❤️ 已收藏' : '🤍 收藏'}${lk ? ' · ' + lk : ''}</button>
      <button class="ctl${ctx.todoSet.has(a.no) ? ' on' : ''}" onclick="toggleTodo('${a.no}')">${ctx.todoSet.has(a.no) ? '🔖 待閱讀中' : '🔖 待閱讀'}</button>
      <button class="ctl${ctx.readSet.has(a.no) ? ' on' : ''}" onclick="toggleRead('${a.no}')">${ctx.readSet.has(a.no) ? '✓ 已讀' : '標為已讀'}</button>
    </div>
    ${deadBar(a)}
    ${vw ? `<div class="viewline">🔭 被觀測 ${vw.toLocaleString()} 次</div>` : ''}
    ${personRow('作者', personRefs(a).authors, ctx)}
    ${personRow('譯者', personRefs(a).translators, ctx)}
    ${a.persona ? `<div class="drow"><span class="dk">人設</span><span class="dv">${a.persona.replace(/\n/g, '<br>')}</span></div>` : ''}
    ${a.alias ? `<div class="drow"><span class="dk">收錄篇名</span><span class="dv">${a.alias.replace(/\n/g, '<br>')}</span></div>` : ''}
    ${rows}
    <div class="drow"><span class="dk">閱讀連結</span><span class="dv">${linksHTML(a)}</span></div>`
    + (rel.length ? `<div class="drow"><span class="dk">類似的文</span><span class="dv related">${rel.map((x) => `<span class="relitem" onclick="openByNo('${x.no}')">${x.name || '(無標題)'}<span class="rno">#${x.no}</span></span>`).join('')}</span></div>` : '')
    + navBar(navIndex, navLen, '篇');
}

/** 穿越蟲洞後在詳情頂端短暫浮出一句,約 2 秒淡出。 */
export function wormholeToast(sheet) {
  if (!sheet) return;
  const old = sheet.querySelector('.wh-toast'); if (old) old.remove();
  const d = document.createElement('div'); d.className = 'wh-toast'; d.textContent = '🌀 穿越蟲洞!隨機降落在這顆星球';
  sheet.prepend(d); setTimeout(() => d.classList.add('out'), 1800); setTimeout(() => d.remove(), 2400);
}

/** 頁尾「星際旅人統計」卡;s 為 null 顯示建置中,live = 即時資料。 */
export function renderStats(el, s, live) {
  if (!el) return;
  if (!s) { el.innerHTML = '<div class="stats-card"><div class="stats-title">🛸 星際旅人統計</div><div style="color:var(--muted);font-size:13px">統計建置中,稍後顯示…</div></div>'; return; }
  const cells = [['今日', s.today], ['本週', s.week], ['本月', s.month], ['上月', s.lastmonth], ['今年', s.year], ['累計', s.total]];
  const badge = live ? '<span style="font-size:11px;font-weight:600;color:#22c55e;margin-left:8px;vertical-align:middle">● 即時</span>' : '';
  el.innerHTML = '<div class="stats-card"><div class="stats-title">🛸 星際旅人統計' + badge + '</div><div class="stats-grid">'
    + cells.map(([l, v]) => `<div class="stat"><div class="sl">${l}</div><div class="sv">${(v || 0).toLocaleString()}</div></div>`).join('')
    + '</div></div>';
}

// ---- 書架匯出 / 匯入 / 清除(與詳情共用 #modal / .sheet;事件在 main.js 接)----

/** 書架工具列:接在書架分頁後面的三個按鈕(inline onclick → main.js 掛到 window 的 shelfExport / shelfImport / shelfClear)。 */
export function shelfToolsHTML() {
  return `<span class="shelf-tools">`
    + `<button class="ctl" onclick="shelfExport()" title="把書架與已讀帶到另一台裝置">📤 匯出</button>`
    + `<button class="ctl" onclick="shelfImport()" title="從另一台裝置匯入書架與已讀">📥 匯入</button>`
    + `<button class="ctl danger" onclick="shelfClear()" title="清掉這台裝置的收藏 / 待閱讀 / 已讀">🗑 清除所有紀錄</button>`
    + `</span>`;
}

/** HTML 跳脫(匯入字串可能來自網址 ?s=,內容不可信)。 */
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export const QR_MAX = 2000;   // 匯出字串超過這個長度就不畫 QR code(太密不好掃),改提示用複製

/**
 * 匯出視窗。payload = 壓縮字串(null = 產生失敗,err 是原因),counts = {shelf, read}。
 * QR code 由 main.js 畫進 #xpQr(需要 window.qrcode)。
 */
export function exportHTML({ payload, err, counts }) {
  const head = `<button class="close" onclick="closeDetail()">✕</button><h2>📤 匯出書架與已讀</h2>`;
  if (!payload) return head + `<div class="xfer"><div class="xmsg err">⚠️ ${err || '匯出失敗'}</div></div>`;
  const n = payload.length, tooLong = n > QR_MAX;
  return head + `<div class="xfer">
    <p>收藏 <b>${counts.shelf}</b> 篇、已讀 <b>${counts.read}</b> 篇 → 字串 <b>${n.toLocaleString()}</b> 字。內容只有作品編號,不含任何個人資料。</p>
    <textarea id="xpOut" rows="4" readonly spellcheck="false" aria-label="匯出字串">${payload}</textarea>
    <div class="row">
      <button class="ctl pri" id="xpCopy">📋 複製字串</button>
      <button class="ctl" id="xpLink" title="另一台裝置打開這個連結就會跳出匯入預覽">🔗 複製匯入連結</button>
      <span class="xmsg" id="xpMsg"></span>
    </div>
    ${tooLong
      ? `<div class="xmsg err">字串超過 ${QR_MAX.toLocaleString()} 字,QR code 會太密、不好掃,請改用「複製字串」或「複製匯入連結」帶到另一台裝置。</div>`
      : `<div class="qrbox" id="xpQr"></div><p>用另一台裝置的相機掃描,會直接打開本站並跳出匯入預覽;或在那邊的「📥 匯入」裡按「掃描 QR」。</p>`}
    <p>在另一台裝置:打開本站 → 📚 書架 → 📥 匯入 → 貼上字串(或連結)→ 預覽 → 確認。</p>
  </div>`;
}

/** 匯入視窗。canScan = 瀏覽器支援 BarcodeDetector 才有「掃描 QR」。預覽區由 main.js 填入 #imPre。 */
export function importHTML({ canScan, prefill }) {
  return `<button class="close" onclick="closeDetail()">✕</button><h2>📥 匯入書架與已讀</h2>
  <div class="xfer">
    <p>貼上另一台裝置匯出的字串或匯入連結;匯入前會先顯示預覽,確認後才寫入。</p>
    <textarea id="imIn" rows="4" spellcheck="false" placeholder="貼上匯出的字串,或整個匯入連結" aria-label="匯出字串">${esc(prefill)}</textarea>
    <div class="row">
      <button class="ctl pri" id="imPreview">🔍 預覽</button>
      ${canScan ? `<button class="ctl" id="imScan">📷 掃描 QR</button>` : ''}
      <span class="xmsg" id="imMsg"></span>
    </div>
    <div class="cam" id="imCam" style="display:none"><video autoplay playsinline muted></video><button class="ctl" id="imScanStop">停止掃描</button></div>
    <div class="xpre" id="imPre" style="display:none"></div>
  </div>`;
}

/** 匯入預覽區內容:加入 / 移除幾筆 + 合併 / 覆蓋切換 + 確認鍵。st = previewImport 的結果。 */
export function importPreviewHTML(st, mode, exportedAt) {
  const when = exportedAt ? new Date(exportedAt) : null;
  const whenStr = when && !isNaN(when) ? `${when.getFullYear()}/${when.getMonth() + 1}/${when.getDate()} ${String(when.getHours()).padStart(2, '0')}:${String(when.getMinutes()).padStart(2, '0')}` : '';
  const removed = (st.removeShelf || st.removeRead) ? `<div class="xmsg err">覆蓋模式會移除目前的 ${st.removeShelf} 本書架、${st.removeRead} 篇已讀</div>` : '';
  return `<div>將加入 <b>${st.addShelf}</b> 本書架、<b>${st.addRead}</b> 篇已讀${whenStr ? `<span class="xwhen">(匯出於 ${whenStr})</span>` : ''}</div>
    <div class="xmsg">匯入後:收藏 ${st.shelfTotal} 篇、已讀 ${st.readTotal} 篇</div>
    <div class="row xmode">
      <label><input type="radio" name="imMode" value="merge"${mode !== 'replace' ? ' checked' : ''}> 合併(保留目前的,加上匯入的)</label>
      <label><input type="radio" name="imMode" value="replace"${mode === 'replace' ? ' checked' : ''}> 覆蓋(以匯入的為準)</label>
    </div>${removed}
    <div class="row"><button class="ctl pri" id="imGo">✅ 確認匯入</button><button class="ctl" onclick="closeDetail()">取消</button></div>`;
}

/** 匯入完成。r = importState 回傳值。 */
export function importDoneHTML(r, mode) {
  return `<button class="close" onclick="closeDetail()">✕</button><h2>📥 匯入完成</h2>
  <div class="xfer">
    <div class="xmsg ok">✅ 已${mode === 'replace' ? '覆蓋' : '合併'}:加入 ${r.addedShelf.length} 本書架、${r.addedRead.length} 篇已讀${r.removedShelf.length ? `,移除 ${r.removedShelf.length} 本書架` : ''}</div>
    <p>書架與已讀紀錄存在這台裝置的瀏覽器裡;之後兩邊各自標記,想同步再匯出一次即可。</p>
    <div class="row"><button class="ctl pri" onclick="closeDetail()">看書架</button></div>
  </div>`;
}

/** 清除所有紀錄:要輸入「清除」才能按。counts = {fav, todo, read}。 */
export const CLEAR_WORD = '清除';
export function clearHTML(counts) {
  return `<button class="close" onclick="closeDetail()">✕</button><h2>🗑 清除所有紀錄</h2>
  <div class="xfer">
    <p>會清掉<b>這台裝置</b>的收藏 <b>${counts.fav}</b> 篇、待閱讀 <b>${counts.todo}</b> 篇、已讀 <b>${counts.read}</b> 篇,<b>無法復原</b>。建議先「📤 匯出」留一份備份。</p>
    <input type="text" id="clIn" autocomplete="off" placeholder="輸入「${CLEAR_WORD}」兩個字以確認" aria-label="確認文字">
    <div class="row"><button class="ctl danger" id="clGo" disabled>🗑 清除所有紀錄</button><button class="ctl" onclick="closeDetail()">取消</button><span class="xmsg" id="clMsg"></span></div>
  </div>`;
}
export function clearedHTML() {
  return `<button class="close" onclick="closeDetail()">✕</button><h2>🗑 已清除</h2>
  <div class="xfer"><div class="xmsg ok">✅ 這台裝置的收藏 / 待閱讀 / 已讀都清掉了</div><div class="row"><button class="ctl pri" onclick="closeDetail()">關閉</button></div></div>`;
}
