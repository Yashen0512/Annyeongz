// 畫面產生:書卡(分批渲染)、輪播小卡、分類面板、條件列、詳情 / 公告彈窗、統計卡。
// 這裡只負責把資料變成 DOM / HTML 字串;狀態與事件的接線在 main.js。
//
// 注意:詳情與書卡的 HTML 字串裡用 inline onclick 呼叫下列全域函式(由 main.js 掛到 window):
//   toggleFav / toggleTodo / toggleRead / setShelfTab / filterByTag / filterName / openByNo /
//   closeDetail / navDetail / toggleReport / pickReason / sendReport / shelfExport / shelfImport / shelfClear / shareArticle
// 無障礙:所有可點的 span / div 都改成 <button>(鍵盤 Enter / Space 可用),狀態用 aria-pressed / aria-checked / aria-expanded 表達;
//        每個彈窗內容的第一顆是關閉鈕(aria-label="關閉"),標題 h2 帶 id="sheetTitle" 給 <dialog aria-labelledby> 用。
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
// 文章狀態八種 → 四個家族(配色與符號都按家族,不是八種顏色):完結系 done(綠 ✓)、進行系 ongoing(藍 ●)、未完 wip(金 ⏸)、斷更 hiatus(灰 ✕)
export const STMAP = { '完結': 'done', '完結+番外': 'done', '完結+後記': 'done', '連載中': 'ongoing', '不定期更新': 'ongoing', '建置中': 'ongoing', '未完': 'wip', '斷更': 'hiatus' };
export const STKEY = (s) => STMAP[s] || '';
export const STSYM = { done: '✓', ongoing: '●', wip: '⏸', hiatus: '✕' };
/** 狀態文字前的家族符號(裝飾,對輔助科技隱藏;狀態名稱本身已經說明一切)。 */
export const stSym = (s) => { const k = STKEY(s); return k ? `<span class="si" aria-hidden="true">${STSYM[k]}</span>` : ''; };
// 面板「文章狀態」(?) 的定義(站長提供)
export const STATUS_HELP = [['連載中', '持續更新中'], ['完結', '已完成'], ['未完', '原本連載但長期未更新'], ['斷更', '作者寫到一半後刪文']];

export const SHELF_META = { fav: ['❤️', '已收藏'], todo: ['🔖', '待閱讀'], read: ['✓', '已讀'] };

/** 詳情/公告視窗底部:上一篇・下一篇。 */
export function navBar(i, n, unit) {
  if (i < 0 || n < 2) return '';
  return `<div class="dnav"><button class="ctl"${i > 0 ? ' onclick="navDetail(-1)"' : ' disabled'}>‹ 上一${unit}</button>`
    + `<span class="dpos" aria-live="polite">${i + 1} / ${n}</span>`
    + `<button class="ctl"${i < n - 1 ? ' onclick="navDetail(1)"' : ' disabled'}>下一${unit} ›</button></div>`;
}

/** 書卡 / 詳情的 chip 列:文章狀態第一顆(家族色 + 符號),再來 原文已刪、文章類型、篇幅、結局。 */
export function badges(a) {
  const b = [];
  if (sg(a, '文章狀態')) b.push(`<span class="badge sb-${STKEY(sg(a, '文章狀態'))}">${stSym(sg(a, '文章狀態'))}${sg(a, '文章狀態')}</span>`);
  if (a.dead) b.push('<span class="badge dead">原文已刪</span>');
  if (sg(a, '文章類型')) b.push(`<span class="badge type">${sg(a, '文章類型')}</span>`);
  if (sg(a, '文章篇幅')) b.push(`<span class="badge">${sg(a, '文章篇幅')}</span>`);
  if (sg(a, '結局')) b.push(`<span class="badge ${endCls(sg(a, '結局'))}">${sg(a, '結局')}</span>`);
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
  const on = ctx.favs.has(a.no);
  return `<button type="button" class="t card-open">${a.name || '(無標題)'} <span class="no">#${a.no}</span>${ctx.readSet.has(a.no) ? ' <span class="readmark">✓已讀</span>' : ''}${ctx.todoSet.has(a.no) ? ' <span class="todomark" title="待閱讀" aria-label="待閱讀">🔖</span>' : ''}</button>
    <button type="button" class="fav-btn${on ? ' on' : ''}" onclick="event.stopPropagation();toggleFav('${a.no}')" title="收藏${lk ? '（' + lk + ' 人收藏）' : ''}" aria-label="收藏${lk ? '，' + lk + ' 人收藏' : ''}" aria-pressed="${on}">${on ? '❤️' : '🤍'}${lk ? `<span class="fc" aria-hidden="true">${lk}</span>` : ''}</button>
    <div class="badges">${badges(a)}</div>
    ${persona ? `<div class="persona">${persona}</div>` : ''}
    ${aliasLine(a.alias)}
    <div class="tg">${multiTags(a, ctx.facets).map((t) => `<button type="button" onclick="event.stopPropagation();filterByTag('${encodeURIComponent(t)}')" aria-label="篩選標籤：${t}">${t}</button>`).join('')}</div>`;
}

/** 主列表:把一批書卡接在 listEl 後面。整張卡滑鼠可點,鍵盤用標題 <button>(Enter / Space 的 click 會冒泡到卡片);
 *  onOpen(a, 標題按鈕) 多傳來源元素,詳情關閉後焦點才能回到原卡片。每張卡帶 data-no(跳到 #編號 / 焦點還原用)。 */
export function renderCards(listEl, hits, ctx, onOpen) {
  const frag = document.createDocumentFragment();
  hits.forEach((a) => {
    const c = document.createElement('article'); const k = STKEY(sg(a, '文章狀態'));
    c.className = 'card' + (k ? ' cst-' + k : '') + (a.dead ? ' dead' : '');
    c.dataset.no = a.no;
    c.innerHTML = cardHTML(a, ctx); c.onclick = () => onOpen(a, c.querySelector('.card-open')); frag.appendChild(c);
  });
  listEl.appendChild(frag);
}

/**
 * 分批渲染的主列表:先畫前 batch 張,捲到底前(IntersectionObserver 盯著 moreEl,提前 rootMargin 觸發)自動補下一批;
 * moreEl 裡的按鈕是沒有 IntersectionObserver 時的手動退路,文字顯示「已顯示 N / M 篇」。
 * 真正的虛擬捲動在這裡用不上:每批只在捲到時才建 DOM,再配合 CSS content-visibility:auto 讓畫面外的書卡不排版、不繪製,
 * 1486 篇全部捲完 DOM 也只是線性成長,沒有引入套件的必要。
 *   set(hits, keepShown)  換一份清單:清空重畫;keepShown = true 時維持原本已顯示的張數(夾到清單長度,至少一批),
 *                         對應原站「搜尋 / 排序 / 勾選框重繪不跳回第 1 頁」的行為;false 從第一批開始
 *   more()                手動補一批
 * @param {(slice:Array)=>void} renderBatch 畫一批(呼叫端用 renderCards)  @param {(shown:number)=>void} [onChange] 已顯示張數變了(存捲動狀態用)
 */
export function createLazyList(listEl, moreEl, { batch = 40, rootMargin = '800px 0px', renderBatch, onChange }) {
  let hits = [], shown = 0, ticking = false;
  const btn = moreEl.querySelector('button'), txt = moreEl.querySelector('.more-txt');
  const nearBottom = () => moreEl.getBoundingClientRect().top < window.innerHeight + 800;

  function update() {
    const left = hits.length - shown;
    moreEl.hidden = left <= 0;
    if (txt) txt.textContent = `已顯示 ${shown} / ${hits.length} 篇`;
    if (btn) btn.textContent = `再載入 ${Math.min(batch, Math.max(left, 0))} 篇 ↓`;
  }
  function more() {
    if (shown >= hits.length) return;
    const slice = hits.slice(shown, shown + batch);
    renderBatch(slice); shown += slice.length; update(); if (onChange) onChange(shown);
    // 一批不夠高(例如桌機多欄)讓哨兵還在畫面裡時,下一幀再補,直到看不到或沒得補
    if (!moreEl.hidden && !ticking) { ticking = true; requestAnimationFrame(() => { ticking = false; if (!moreEl.hidden && nearBottom()) more(); }); }
  }
  function set(list, keepShown) {
    hits = list || [];
    const target = keepShown ? Math.min(hits.length, Math.max(batch, shown)) : Math.min(hits.length, batch);
    listEl.innerHTML = ''; shown = 0;
    if (target) { renderBatch(hits.slice(0, target)); shown = target; }
    update(); if (onChange) onChange(shown);
  }
  /** 至少顯示到第 n 張(一次補齊,不分批):跳到 #編號、從詳情 / 分享頁 / 上一頁返回時還原已載入張數用。回傳實際顯示張數。 */
  function ensure(n) {
    const target = Math.min(hits.length, Math.max(0, n | 0));
    if (target > shown) { renderBatch(hits.slice(shown, target)); shown = target; update(); if (onChange) onChange(shown); }
    return shown;
  }
  if (btn) btn.onclick = more;
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) more(); }, { rootMargin });
    io.observe(moreEl);
  }
  return { set, more, ensure, shown: () => shown, hits: () => hits };
}

/** el 進入(或接近)視窗時執行一次 fn;不支援 IntersectionObserver 就立刻執行。輪播與熱門星系靠這個延後初始化。 */
export function whenVisible(el, fn, rootMargin = '300px 0px') {
  if (!el) return;
  if (!('IntersectionObserver' in window)) { fn(); return; }
  const io = new IntersectionObserver((es) => {
    if (!es.some((e) => e.isIntersecting)) return;
    io.disconnect(); fn();
  }, { rootMargin });
  io.observe(el);
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
  return Object.entries(SHELF_META).map(([k, [ic, lb]]) => `<button type="button" class="ctl${k === cur ? ' on' : ''}" aria-pressed="${k === cur}" onclick="setShelfTab('${k}')">${ic} ${lb} <span class="sc">${sets[k].size}</span></button>`).join('');
}

/** 左側分類面板:每個分面一個區塊(標題可收合;多選分面有「任一/全部」切換)。
 *  標題裡的收合鈕(.fh,aria-expanded)與「任一/全部」(.mode,role=switch)都是 <button>;標籤是 <button class="opt" aria-pressed>。 */
export function buildPanel(panelEl, facets, { onTag, onMode }) {
  facets.forEach((f, fi) => {
    if (!f.options.length) return;
    const box = document.createElement('div'); box.className = 'facet';
    const h = document.createElement('h3');
    const showMode = f.type === 'multi';
    const oid = 'fopts' + fi;
    const isStatus = f.key === '文章狀態';   // 標籤依家族上色 + 符號;標題旁有 (?) 說明
    const hid = 'fhelp' + fi;
    h.innerHTML = `<button type="button" class="fh" aria-expanded="true" aria-controls="${oid}">${f.key}</button><span class="rt">`
      + (isStatus ? `<button type="button" class="fhelp" aria-expanded="false" aria-controls="${hid}" aria-label="文章狀態的定義">?</button>` : ``)
      + (showMode ? `<button type="button" class="mode" role="switch" aria-checked="false" aria-label="${f.key}：全部符合" data-k="${f.key}">任一</button>` : ``)
      + `<span class="arw" aria-hidden="true">▾</span></span>`;
    const opts = document.createElement('div'); opts.className = 'opts'; opts.id = oid;
    const fh = h.querySelector('.fh');
    h.onclick = (e) => {
      if (e.target.classList.contains('mode') || e.target.classList.contains('fhelp')) return;
      const hide = opts.style.display !== 'none';
      opts.style.display = hide ? 'none' : 'flex';
      h.querySelector('.arw').textContent = hide ? '▸' : '▾';
      fh.setAttribute('aria-expanded', String(!hide));
    };
    if (showMode) { const mt = h.querySelector('.mode'); mt.onclick = (e) => { e.stopPropagation(); onMode(f.key); }; }
    let note = null;
    if (isStatus) {
      note = document.createElement('div'); note.className = 'fnote'; note.id = hid; note.hidden = true;
      note.innerHTML = STATUS_HELP.map(([k, d]) => `<div><b>${stSym(k)}${k}</b>＝${d}</div>`).join('');
      const hb = h.querySelector('.fhelp');
      hb.onclick = (e) => { e.stopPropagation(); note.hidden = !note.hidden; hb.setAttribute('aria-expanded', String(!note.hidden)); };   // 點一下顯示、再點關閉(手機沒有 hover)
    }
    f.options.forEach(([val, cnt]) => {
      const o = document.createElement('button'); o.type = 'button';
      const extra = isStatus && STKEY(val) ? 'st-' + STKEY(val) : '';
      o.className = 'opt' + (extra ? ' ' + extra : '');
      o.innerHTML = `${isStatus ? stSym(val) : ''}${val} <span class="c" aria-hidden="true">${cnt}</span>`;   // 空白:可見文字「OOC 208」才包含在 aria-label 裡(axe label-content-name-mismatch)
      o.onclick = () => onTag(f.key, val);
      o._val = val; o._key = f.key; o._cnt = cnt; o._extra = extra; opts.appendChild(o);
    });
    box.appendChild(h); if (note) box.appendChild(note); box.appendChild(opts); panelEl.appendChild(box);
  });
}

const STATE_LABEL = { on: '包含', exc: '排除' };
/** 標籤三態 → aria-pressed(未選 false / 包含 true / 排除 "mixed")與 aria-label「{標籤}，N 篇，目前：排除」。 */
export function optAria(o, state) {
  o.setAttribute('aria-pressed', state === 'on' ? 'true' : state === 'exc' ? 'mixed' : 'false');
  o.setAttribute('aria-label', `${o._val}${o._cnt != null ? '，' + o._cnt + ' 篇' : ''}，目前：${STATE_LABEL[state] || '未選'}`);
}

/** 依目前狀態替面板標籤上色(on 粉底 / exc 紅刪除線)、aria 狀態,與「任一/全部」字樣(role=switch 的 aria-checked)。 */
export function syncStyles(sel, modes) {
  // 只在真的不同時才寫 className / textContent / aria,避免幾百個標籤每次重繪都觸發樣式失效
  document.querySelectorAll('.opt').forEach((o) => {
    if (o._key === undefined) return;   // 熱門星系的標籤沒有三態
    const s = (sel[o._key] || {})[o._val]; const cls = 'opt' + (o._extra ? ' ' + o._extra : '') + (s === 'on' ? ' on' : s === 'exc' ? ' exc' : '');   // _extra = 文章狀態的家族色 class,要保留
    if (o.className !== cls) { o.className = cls; optAria(o, s); }
    else if (!o.hasAttribute('aria-pressed')) optAria(o, s);
  });
  document.querySelectorAll('.mode').forEach((m) => {
    const and = modes[m.dataset.k] === 'and'; const cls = 'mode' + (and ? ' and' : ''), txt = and ? '全部' : '任一';
    if (m.className !== cls) m.className = cls;
    if (m.textContent !== txt) m.textContent = txt;
    if (m.getAttribute('aria-checked') !== String(and)) m.setAttribute('aria-checked', String(and));
  });
}

/** 熱門星系:所有多選標籤依收錄篇數排序取前 16 個。 */
export function renderHot(wrap, facets, onPick) {
  const all = [];
  facets.forEach((f) => { if (f.type === 'multi') f.options.forEach(([v, c]) => all.push([v, c, f.key])); });
  all.sort((a, b) => b[1] - a[1]);
  wrap.innerHTML = '';
  all.slice(0, 16).forEach(([v, c, key]) => {
    const o = document.createElement('button'); o.type = 'button'; o.className = 'opt'; o.innerHTML = `${v} <span class="c" aria-hidden="true">${c}</span>`;
    o.setAttribute('aria-label', `${v}，${c} 篇`);
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
    const el = document.createElement('button'); el.type = 'button'; el.className = 'fchip'; el.innerHTML = (c.exc ? '排除 ' : '') + c.val + ' <b aria-hidden="true">✕</b>';
    el.setAttribute('aria-label', `移除條件：${c.exc ? '排除 ' : ''}${c.val}`);
    el.onclick = () => onRemove(c.key, c.val); bar.appendChild(el);
  });
  const all = document.createElement('button'); all.type = 'button'; all.className = 'fchip clr'; all.textContent = '清除全部 ✕';
  all.setAttribute('aria-label', '清除全部條件');
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
    + `<button type="button" class="ah-clear" aria-label="離開作者專頁，返回全部文章">✕ 返回全部</button></div>`
    + (links ? `<div class="ah-links">${links}</div>` : '');
  el.querySelector('.ah-clear').onclick = onClear;
}

/** 橫向輪播(星際廣播 / 新星誕生 / 軌道更新)的一排小卡;每張是 <button>(鍵盤可聚焦),onClick(x, i, 按鈕) 回傳來源元素。 */
export function renderStrip(wrap, items, { html, cls, onClick }) {
  wrap.innerHTML = '';
  items.forEach((x, i) => {
    const c = document.createElement('button'); c.type = 'button'; c.className = cls ? cls(x) : 'scard';
    c.innerHTML = html(x); c.onclick = () => onClick(x, i, c); wrap.appendChild(c);
  });
}
export const latestCardHTML = (a) => `<span class="st">${a.name || '(無標題)'}</span><span class="sm">#${a.no}${a.created ? ' · 收錄 ' + a.created : ''}</span>`;
export const statusCardHTML = (a) => `<span class="st">${a.name || '(無標題)'}</span><span class="sm">#${a.no} · ${sg(a, '文章狀態') || '—'}${a.edited ? ' · ' + a.edited : ''}</span>`;
export const annCardHTML = (x) => `<span class="st">${x.content}</span><span class="sm">${x.pin ? '📌 ' : ''}${x.date}</span>`;
export const annCardCls = (x) => 'scard ann-card' + (x.pin ? ' pin' : '');

/** 公告全文彈窗內容。 */
export function annHTML(x, i, n) {
  return `<button type="button" class="close" onclick="closeDetail()" aria-label="關閉">✕</button>
    <h2 id="sheetTitle">📻 星際廣播</h2>
    <div class="ann-meta">${x.pin ? '📌 置頂 · ' : ''}${x.date}</div>
    <div class="ann-full">${x.content}</div>` + navBar(i, n, '則');
}

/** 詳情:作者 / 譯者列(名字可點看全部 + 平台連結)。refs = [{name, id}](personRefs)。 */
export function personRow(label, refs, ctx) {
  if (!refs || !refs.length) return '';
  const inner = refs.map(({ name: nm, id }) => {
    const info = personInfo(ctx, nm, id), p = info.urls;
    const links = Object.keys(p).map((k) => `<a class="plat pp" href="${p[k]}" target="_blank" rel="noopener">${k}</a>`).join('');
    const see = `<a class="plat pp" href="#" onclick="filterName('${encodeURIComponent(nm)}');return false">看全部</a>`;
    const dead = info.dead ? '<span class="deadauth">(已刪帳號)</span>' : '';
    return `<div class="person"><button type="button" class="aname" onclick="filterName('${encodeURIComponent(nm)}')" aria-label="${nm}，看這位的全部作品">${nm}</button>${dead} ${links} ${see}</div>`;
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
    if (u.startsWith('annyeongz:')) return `<div class="lrow"><button type="button" class="plat" style="cursor:pointer;font-family:inherit" onclick="openByNo('${u.slice(10)}')">${l[0]} ↗</button></div>`;
    if (l[2]) return `<div class="lrow"><a class="plat dead" href="${u}" target="_blank" rel="noopener"><s>${l[0]}</s> ❌</a><span class="lstat">已確認失效</span>${live ? '<div class="lnote">此連結已失效,可改讀其他連結</div>' : ''}</div>`;
    return `<div class="lrow"><a class="plat" href="${u}" target="_blank" rel="noopener">${l[0]}</a><button type="button" class="lrep" onclick="toggleReport('rb${i}')" aria-expanded="false" aria-controls="rb${i}" aria-label="回報壞掉：${l[0]} 這個連結">回報壞掉</button>
      <div class="repbox" id="rb${i}">
        <div class="q" id="rbq${i}">回報這個連結的問題:</div>
        <div class="opts" role="group" aria-labelledby="rbq${i}">
          <button type="button" class="ctl" aria-pressed="false" onclick="pickReason(this)">🔗 打不開</button>
          <button type="button" class="ctl" aria-pressed="false" onclick="pickReason(this)">🗑 被刪了</button>
          <button type="button" class="ctl" aria-pressed="false" onclick="pickReason(this)">❓ 內容不符</button>
          <button type="button" class="ctl" aria-pressed="false" onclick="pickReason(this,1)">✏️ 其他</button>
        </div>
        <textarea rows="2" placeholder="請簡述問題…" aria-label="問題說明" style="display:none;width:100%;box-sizing:border-box;font-size:13px;padding:6px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);resize:vertical"></textarea>
        <div style="margin-top:6px;display:flex;align-items:center;gap:8px"><button type="button" class="ctl" onclick="sendReport('${a.no}',${i})">送出回報</button><span class="rmsg" role="status" style="font-size:13px;color:var(--muted)"></span></div>
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
    rows += `<div class="drow"><span class="dk">${f.key}</span><span class="dv">${vals.map((v) => `<button type="button" class="chip" onclick="filterByTag('${encodeURIComponent(v)}')" aria-label="篩選標籤：${v}">${v}</button>`).join('')}</span></div>`;
  });
  const fav = ctx.favs.has(a.no), todo = ctx.todoSet.has(a.no), read = ctx.readSet.has(a.no);
  return `<button type="button" class="close" onclick="closeDetail()" aria-label="關閉">✕</button>
    <h2 id="sheetTitle">${a.name || '(無標題)'} <span class="no">#${a.no}</span></h2>
    <div class="badges">${badges(a)}</div>
    <div class="detail-actions">
      <button type="button" class="ctl${fav ? ' on' : ''}" aria-pressed="${fav}" onclick="toggleFav('${a.no}')">${fav ? '❤️ 已收藏' : '🤍 收藏'}${lk ? ' · ' + lk : ''}</button>
      <button type="button" class="ctl${todo ? ' on' : ''}" aria-pressed="${todo}" onclick="toggleTodo('${a.no}')">${todo ? '🔖 待閱讀中' : '🔖 待閱讀'}</button>
      <button type="button" class="ctl${read ? ' on' : ''}" aria-pressed="${read}" onclick="toggleRead('${a.no}')">${read ? '✓ 已讀' : '標為已讀'}</button>
      <button type="button" class="ctl" onclick="shareArticle('${a.no}', this)" title="複製這篇的分享連結(貼到社群會顯示預覽卡)" aria-label="分享，複製這篇的分享連結">🔗 分享</button>
    </div>
    ${deadBar(a)}
    ${vw ? `<div class="viewline">🔭 被觀測 ${vw.toLocaleString()} 次</div>` : ''}
    ${personRow('作者', personRefs(a).authors, ctx)}
    ${personRow('譯者', personRefs(a).translators, ctx)}
    ${a.persona ? `<div class="drow"><span class="dk">人設</span><span class="dv">${a.persona.replace(/\n/g, '<br>')}</span></div>` : ''}
    ${a.alias ? `<div class="drow"><span class="dk">收錄篇名</span><span class="dv">${a.alias.replace(/\n/g, '<br>')}</span></div>` : ''}
    ${rows}
    <div class="drow"><span class="dk">閱讀連結</span><span class="dv">${linksHTML(a)}</span></div>`
    + (rel.length ? `<div class="drow"><span class="dk">類似的文</span><span class="dv related">${rel.map((x) => `<button type="button" class="relitem" onclick="openByNo('${x.no}')">${x.name || '(無標題)'}<span class="rno">#${x.no}</span></button>`).join('')}</span></div>` : '')
    + navBar(navIndex, navLen, '篇');
}

/** 穿越蟲洞後在詳情頂端短暫浮出一句,約 2 秒淡出。 */
export function wormholeToast(sheet) {
  if (!sheet) return;
  const old = sheet.querySelector('.wh-toast'); if (old) old.remove();
  const d = document.createElement('div'); d.className = 'wh-toast'; d.setAttribute('role', 'status'); d.textContent = '🌀 穿越蟲洞!隨機降落在這顆星球';
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
    + `<button type="button" class="ctl" onclick="shelfExport()" title="把書架與已讀帶到另一台裝置" aria-label="匯出，把書架與已讀帶到另一台裝置">📤 匯出</button>`
    + `<button type="button" class="ctl" onclick="shelfImport()" title="從另一台裝置匯入書架與已讀" aria-label="匯入，從另一台裝置匯入書架與已讀">📥 匯入</button>`
    + `<button type="button" class="ctl danger" onclick="shelfClear()" title="清掉這台裝置的收藏 / 待閱讀 / 已讀">🗑 清除所有紀錄</button>`
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
  const head = `<button type="button" class="close" onclick="closeDetail()" aria-label="關閉">✕</button><h2 id="sheetTitle">📤 匯出書架與已讀</h2>`;
  if (!payload) return head + `<div class="xfer"><div class="xmsg err">⚠️ ${err || '匯出失敗'}</div></div>`;
  const n = payload.length, tooLong = n > QR_MAX;
  return head + `<div class="xfer">
    <p>收藏 <b>${counts.shelf}</b> 篇、已讀 <b>${counts.read}</b> 篇、待閱讀 <b>${counts.todo}</b> 篇 → 字串 <b>${n.toLocaleString()}</b> 字。內容只有作品編號,不含任何個人資料。</p>
    <textarea id="xpOut" rows="4" readonly spellcheck="false" aria-label="匯出字串">${payload}</textarea>
    <div class="row">
      <button type="button" class="ctl pri" id="xpCopy">📋 複製字串</button>
      <button type="button" class="ctl" id="xpLink" title="另一台裝置打開這個連結就會跳出匯入預覽">🔗 複製匯入連結</button>
      <span class="xmsg" id="xpMsg" role="status"></span>
    </div>
    ${tooLong
      ? `<div class="xmsg err">字串超過 ${QR_MAX.toLocaleString()} 字,QR code 會太密、不好掃,請改用「複製字串」或「複製匯入連結」帶到另一台裝置。</div>`
      : `<div class="qrbox" id="xpQr"></div><p>用另一台裝置的相機掃描,會直接打開本站並跳出匯入預覽;或在那邊的「📥 匯入」裡按「掃描 QR」。</p>`}
    <p>在另一台裝置:打開本站 → 📚 書架 → 📥 匯入 → 貼上字串(或連結)→ 預覽 → 確認。</p>
  </div>`;
}

/** 匯入視窗。canScan = 瀏覽器支援 BarcodeDetector 才有「掃描 QR」。預覽區由 main.js 填入 #imPre。 */
export function importHTML({ canScan, prefill }) {
  return `<button type="button" class="close" onclick="closeDetail()" aria-label="關閉">✕</button><h2 id="sheetTitle">📥 匯入書架與已讀</h2>
  <div class="xfer">
    <p>貼上另一台裝置匯出的字串或匯入連結;匯入前會先顯示預覽,確認後才寫入。</p>
    <textarea id="imIn" rows="4" spellcheck="false" placeholder="貼上匯出的字串,或整個匯入連結" aria-label="匯出字串">${esc(prefill)}</textarea>
    <div class="row">
      <button type="button" class="ctl pri" id="imPreview">🔍 預覽</button>
      ${canScan ? `<button type="button" class="ctl" id="imScan">📷 掃描 QR</button>` : ''}
      <span class="xmsg" id="imMsg" role="status"></span>
    </div>
    <div class="cam" id="imCam" style="display:none"><video autoplay playsinline muted></video><button type="button" class="ctl" id="imScanStop">停止掃描</button></div>
    <div class="xpre" id="imPre" style="display:none"></div>
  </div>`;
}

/** 匯入預覽區內容:加入 / 移除幾筆 + 合併 / 覆蓋切換 + 確認鍵。st = previewImport 的結果。 */
export function importPreviewHTML(st, mode, exportedAt) {
  const when = exportedAt ? new Date(exportedAt) : null;
  const whenStr = when && !isNaN(when) ? `${when.getFullYear()}/${when.getMonth() + 1}/${when.getDate()} ${String(when.getHours()).padStart(2, '0')}:${String(when.getMinutes()).padStart(2, '0')}` : '';
  const removed = (st.removeShelf || st.removeRead || st.removeTodo)
    ? `<div class="xmsg err">${mode === 'replace' ? '覆蓋模式' : '匯入後'}會移除目前的 ${st.removeShelf} 本書架、${st.removeRead} 篇已讀、${st.removeTodo} 篇待閱讀${mode !== 'replace' ? '(標為已讀的會自動移出待閱讀)' : ''}</div>` : '';
  return `<div>將加入 <b>${st.addShelf}</b> 本書架、<b>${st.addRead}</b> 篇已讀、<b>${st.addTodo}</b> 篇待閱讀${whenStr ? `<span class="xwhen">(匯出於 ${whenStr})</span>` : ''}</div>
    <div class="xmsg">匯入後:收藏 ${st.shelfTotal} 篇、已讀 ${st.readTotal} 篇、待閱讀 ${st.todoTotal} 篇</div>
    <div class="row xmode">
      <label><input type="radio" name="imMode" value="merge"${mode !== 'replace' ? ' checked' : ''}> 合併(保留目前的,加上匯入的)</label>
      <label><input type="radio" name="imMode" value="replace"${mode === 'replace' ? ' checked' : ''}> 覆蓋(以匯入的為準)</label>
    </div>${removed}
    <div class="row"><button type="button" class="ctl pri" id="imGo">✅ 確認匯入</button><button type="button" class="ctl" onclick="closeDetail()">取消</button></div>`;
}

/** 匯入完成。r = importState 回傳值。 */
export function importDoneHTML(r, mode) {
  return `<button type="button" class="close" onclick="closeDetail()" aria-label="關閉">✕</button><h2 id="sheetTitle">📥 匯入完成</h2>
  <div class="xfer">
    <div class="xmsg ok">✅ 已${mode === 'replace' ? '覆蓋' : '合併'}:加入 ${r.addedShelf.length} 本書架、${r.addedRead.length} 篇已讀、${r.addedTodo.length} 篇待閱讀${r.removedShelf.length || r.removedTodo.length ? `,移除 ${r.removedShelf.length} 本書架、${r.removedTodo.length} 篇待閱讀` : ''}</div>
    <p>書架、已讀與待閱讀存在這台裝置的瀏覽器裡;之後兩邊各自標記,想同步再匯出一次即可。</p>
    <div class="row"><button type="button" class="ctl pri" onclick="closeDetail()">看書架</button></div>
  </div>`;
}

/** 清除所有紀錄:要輸入「清除」才能按。counts = {fav, todo, read}。 */
export const CLEAR_WORD = '清除';
export function clearHTML(counts) {
  return `<button type="button" class="close" onclick="closeDetail()" aria-label="關閉">✕</button><h2 id="sheetTitle">🗑 清除所有紀錄</h2>
  <div class="xfer">
    <p>會清掉<b>這台裝置</b>的收藏 <b>${counts.fav}</b> 篇、待閱讀 <b>${counts.todo}</b> 篇、已讀 <b>${counts.read}</b> 篇,<b>無法復原</b>。建議先「📤 匯出」留一份備份。</p>
    <input type="text" id="clIn" autocomplete="off" placeholder="輸入「${CLEAR_WORD}」兩個字以確認" aria-label="確認文字">
    <div class="row"><button type="button" class="ctl danger" id="clGo" disabled>🗑 清除所有紀錄</button><button type="button" class="ctl" onclick="closeDetail()">取消</button><span class="xmsg" id="clMsg"></span></div>
  </div>`;
}
export function clearedHTML() {
  return `<button type="button" class="close" onclick="closeDetail()" aria-label="關閉">✕</button><h2 id="sheetTitle">🗑 已清除</h2>
  <div class="xfer"><div class="xmsg ok">✅ 這台裝置的收藏 / 待閱讀 / 已讀都清掉了</div><div class="row"><button type="button" class="ctl pri" onclick="closeDetail()">關閉</button></div></div>`;
}
