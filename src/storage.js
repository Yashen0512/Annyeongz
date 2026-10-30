// 本機儲存集中管理:所有 localStorage / sessionStorage 的 key 都定義在這裡,其他模組不得自己寫字串。
// 書架(收藏/待閱讀/已讀)只存瀏覽器本機,免登入、每台裝置各自一份。
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
