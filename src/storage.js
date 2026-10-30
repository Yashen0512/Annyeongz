// 本機儲存集中管理:所有 localStorage / sessionStorage 的 key 都定義在這裡,其他模組不得自己寫字串。
// 書架(收藏/待閱讀/已讀)只存瀏覽器本機,免登入、每台裝置各自一份;
// 要帶到另一台裝置用檔尾的 exportState / importState(壓縮字串、QR code 或 ?s= 連結)。
export const KEYS = {
  FAVS: 'annyeongz_favs',           // localStorage:收藏(❤️)的編號陣列
  READ: 'annyeongz_read',           // localStorage:已讀(✓)的編號陣列
  TODO: 'annyeongz_todo',           // localStorage:待閱讀(🔖)的編號陣列
  SHELF_TAB: 'annyeongz_shelftab',  // localStorage:書架上次停留的分頁 fav | todo | read
  FAVS_SENT: 'annyeongz_favs_sent', // localStorage:已計入公開愛心數的收藏編號(避免重複 +1)
  THEME: 'azTheme',                 // localStorage:'dark' | 'light'(預設深色)
  INTRO: 'azIntro',                 // sessionStorage:本分頁已播過開場動畫(src/intro.js 直接用字串,須同步)
  VIEW_PREFIX: 'azv_',              // sessionStorage:azv_<編號> = 同一分頁同一篇只計一次觀測
};

export const SHELF_TABS = ['fav', 'todo', 'read'];

/** 讀出存成 JSON 陣列的集合;壞掉或不存在都回空集合。 */
export function loadSet(key) {
  try { return new Set(JSON.parse(localStorage.getItem(key) || '[]')); } catch (e) { return new Set(); }
}
/** 把集合存回 localStorage(存不進去就算了,功能照常)。 */
export function saveSet(key, set) {
  try { localStorage.setItem(key, JSON.stringify([...set])); } catch (e) {}
}

/** 書架分頁:記住上次停在哪一頁,不合法就回 'fav'。 */
export function loadShelfTab() {
  try { const v = localStorage.getItem(KEYS.SHELF_TAB); if (SHELF_TABS.includes(v)) return v; } catch (e) {}
  return 'fav';
}
export function saveShelfTab(tab) {
  try { localStorage.setItem(KEYS.SHELF_TAB, tab); } catch (e) {}
}

/** 主題:預設深色(配合品牌)。 */
export function loadTheme() {
  try { return localStorage.getItem(KEYS.THEME) || 'dark'; } catch (e) { return 'dark'; }
}
export function saveTheme(t) {
  try { localStorage.setItem(KEYS.THEME, t); } catch (e) {}
}

/**
 * 觀測去重:同一分頁同一篇只算一次。第一次呼叫回 true(並記下來),之後回 false。
 * sessionStorage 不能用時也回 true(寧可多算,不要漏算)。
 */
export function firstViewThisSession(no) {
  try {
    const k = KEYS.VIEW_PREFIX + no;
    if (sessionStorage.getItem(k)) return false;
    sessionStorage.setItem(k, '1');
  } catch (e) {}
  return true;
}

// ---- 匯出 / 匯入:把書架(收藏)與已讀帶到另一台裝置(不登入、不架後端)----
// 匯出內容 { v: 1, shelf: [收藏編號...], read: [已讀編號...], todo: [待閱讀編號...](可選), exportedAt: ISO 時間 },
// todo 是後來加的可選欄位(版本仍是 1):舊字串沒有這欄照樣能匯入,且不會動到這台的待閱讀。
// 用 lz-string(vendor/lz-string.min.js,傳統 script 掛在 window.LZString)壓成只含 A-Z a-z 0-9 + - $ 的字串,
// 可以直接複製、做成 QR code,或接在網址 ?s=<字串> 後面讓另一台裝置打開時跳出匯入預覽。
export const EXPORT_VERSION = 1;
export const IMPORT_PARAM = 's';   // 網址參數名:?s=<匯出字串>

/** 取得 lz-string;沒載到(vendor 腳本失敗)就丟錯,由畫面顯示。 */
function lz() {
  const L = typeof globalThis !== 'undefined' ? globalThis.LZString : null;
  if (!L || typeof L.compressToEncodedURIComponent !== 'function') throw new Error('壓縮元件(lz-string)未載入,請重新整理再試');
  return L;
}

/**
 * 匯出:收藏 + 已讀(+ 待閱讀,有給才寫進去)→ 壓縮字串。
 * @param {{favs:Set|Iterable, read:Set|Iterable, todo?:Set|Iterable}} state
 * @param {Date} [now] 匯出時間(測試用)
 */
export function exportState({ favs, read, todo }, now = new Date()) {
  const o = { v: EXPORT_VERSION, shelf: [...new Set(favs)], read: [...new Set(read)] };
  if (todo) o.todo = [...new Set(todo)];
  o.exportedAt = now.toISOString();
  return lz().compressToEncodedURIComponent(JSON.stringify(o));
}

/** 完整匯入連結:<網址>?s=<字串>(字串本身就是 URL-safe,不再編碼)。 */
export function buildImportURL(payload, base) {
  return base + '?' + IMPORT_PARAM + '=' + payload;
}

/**
 * 從貼上的文字(或整個網址)取出匯出字串:有 ?s= / &s= 就取那一段,否則整段去頭尾空白。
 * 注意不能用 URLSearchParams,它會把字串裡的 + 當成空白。
 */
export function extractPayload(text) {
  const t = String(text == null ? '' : text).trim();
  const m = t.match(new RegExp('[?&]' + IMPORT_PARAM + '=([^&#\\s]+)'));
  if (!m) return t;
  try { return decodeURIComponent(m[1]); } catch (e) { return m[1]; }
}

/**
 * 解析並驗證匯出字串 → { shelf:[編號], read:[編號], todo:[編號] | null, exportedAt }(已去重)。
 * todo 是可選欄位:字串裡沒有就是 null(= 舊格式,匯入時不動這台的待閱讀);有的話型別一樣要對。
 * 不合法就丟 Error(訊息可直接顯示),呼叫端的資料完全不動。
 */
export function decodeState(payload) {
  const s = extractPayload(payload);
  if (!s) throw new Error('沒有內容,請先貼上匯出的字串或連結');
  const L = lz();   // 沒載入要丟它自己的錯,不能被下面吃掉
  let json = null;
  try { json = L.decompressFromEncodedURIComponent(s); } catch (e) { json = null; }
  if (!json) throw new Error('看不懂這段字串,請確認有完整複製');
  let o;
  try { o = JSON.parse(json); } catch (e) { throw new Error('看不懂這段字串,請確認有完整複製'); }
  if (!o || typeof o !== 'object' || Array.isArray(o)) throw new Error('看不懂這段字串,請確認有完整複製');
  if (o.v !== EXPORT_VERSION) throw new Error('這段字串的版本(v=' + o.v + ')不支援,請用最新版網站重新匯出');
  const list = (k) => {
    const a = o[k];
    if (!Array.isArray(a) || a.some((x) => typeof x !== 'string' || !x.trim())) throw new Error('欄位 ' + k + ' 格式不對,拒絕匯入');
    return [...new Set(a.map((x) => x.trim()))];
  };
  return { shelf: list('shelf'), read: list('read'), todo: o.todo === undefined ? null : list('todo'), exportedAt: typeof o.exportedAt === 'string' ? o.exportedAt : '' };
}

/**
 * 合併規則(純函式,回傳新的 Set,不動傳入的):
 *   merge   聯集(預設):目前的 + 匯入的
 *   replace 覆蓋:以匯入的為準
 * 待閱讀:匯入字串沒有 todo 欄(舊格式)就維持目前的;有的話照同樣規則合併 / 覆蓋。
 * 最後已讀的一律移出待閱讀(與「標為已讀」同一條規則)。current.todo 沒給就不處理待閱讀。
 */
export function mergeState(current, incoming, mode = 'merge') {
  const union = (a, b) => new Set([...a, ...b]);
  const rep = mode === 'replace';
  const next = rep
    ? { favs: new Set(incoming.shelf), read: new Set(incoming.read) }
    : { favs: union(current.favs, incoming.shelf), read: union(current.read, incoming.read) };
  if (current.todo) {
    const t = incoming.todo == null ? new Set(current.todo) : (rep ? new Set(incoming.todo) : union(current.todo, incoming.todo));
    next.read.forEach((x) => t.delete(x));
    next.todo = t;
  }
  return next;
}

/** 匯入預覽:會加入 / 移除幾筆(移除只在覆蓋模式、或已讀把待閱讀擠掉時會有),以及匯入後的總數。 */
export function previewImport(current, incoming, mode = 'merge') {
  const next = mergeState(current, incoming, mode);
  const only = (a, b) => [...a].filter((x) => !b.has(x));
  const todo0 = current.todo || new Set(), todo1 = next.todo || todo0;
  return {
    addShelf: only(next.favs, current.favs).length, addRead: only(next.read, current.read).length, addTodo: only(todo1, todo0).length,
    removeShelf: only(current.favs, next.favs).length, removeRead: only(current.read, next.read).length, removeTodo: only(todo0, todo1).length,
    shelfTotal: next.favs.size, readTotal: next.read.size, todoTotal: todo1.size,
  };
}

/**
 * 匯入:解析 payload → 依模式合併 → 就地改寫 favs / read / todo(呼叫端持有的 Set)並存回 localStorage。
 * 已讀的會自動移出待閱讀(與 toggleRead 同一條規則);todo 沒給就不碰待閱讀。
 * 解析失敗會丟 Error,此時什麼都沒改。
 * @returns {{addedShelf:string[], addedRead:string[], addedTodo:string[], removedShelf:string[], removedTodo:string[], exportedAt:string}} 這次真正新增 / 移除的編號
 */
export function importState(payload, { favs, read, todo, mode = 'merge' }) {
  const incoming = decodeState(payload);
  const cur = { favs: new Set(favs), read: new Set(read), todo: todo ? new Set(todo) : null };
  const next = mergeState(cur, incoming, mode);
  const only = (a, b) => [...a].filter((x) => !b.has(x));
  const result = {
    addedShelf: only(next.favs, cur.favs), addedRead: only(next.read, cur.read), addedTodo: todo ? only(next.todo, cur.todo) : [],
    removedShelf: only(cur.favs, next.favs), removedTodo: todo ? only(cur.todo, next.todo) : [], exportedAt: incoming.exportedAt,
  };
  favs.clear(); next.favs.forEach((x) => favs.add(x));
  read.clear(); next.read.forEach((x) => read.add(x));
  saveSet(KEYS.FAVS, favs); saveSet(KEYS.READ, read);
  if (todo && (result.addedTodo.length || result.removedTodo.length)) { todo.clear(); next.todo.forEach((x) => todo.add(x)); saveSet(KEYS.TODO, todo); }
  return result;
}

/** 清除這台裝置的所有紀錄:收藏 / 待閱讀 / 已讀 / 已計愛心 / 書架分頁。Set 就地清空,localStorage 的 key 移除。 */
export function clearAllRecords({ favs, read, todo }) {
  [favs, read, todo].forEach((s) => { if (s) s.clear(); });
  [KEYS.FAVS, KEYS.READ, KEYS.TODO, KEYS.FAVS_SENT, KEYS.SHELF_TAB].forEach((k) => { try { localStorage.removeItem(k); } catch (e) {} });
}
