// 篩選:純函式,輸入文章陣列與篩選狀態,輸出結果,不碰 DOM。
//
// 篩選狀態 f 的欄位(全部選填):
//   sel      {分面: {標籤: 'on' | 'exc'}}  標籤三態:on=包含、exc=排除、沒有=未選
//   modes    {分面: 'and'}                 區標題切成「全部」的分面(沒有 = 任一/OR)
//   author   string | null                作者/譯者專頁(目前名字或曾用名;有 lookup 時以 Notion 作者頁 ID 對應)
//   lookup   data.js makePersonLookup() 的結果(選填;沒有就只比對名字字串)
//   term     string                        搜尋字(已經過 data.js 的 foldZH 折算),比對 a._s
//   shelf    Set | null                    書架模式:只顯示集合內的編號;null = 未開書架
//   shelfTab 'fav' | 'todo' | 'read'       書架目前分頁(在「已讀」分頁時不套「隱藏已讀」)
//   hideRead boolean + readSet Set         隱藏已讀
//   hideDead boolean                       隱藏原文已刪(a.dead)
//
// 規則:同區多選 = OR(任一)、跨區 = AND、exc = 排除(有任一排除標籤就不顯示)、
//      區標題切「全部」後同區變 AND。

import { persons, personRefs } from './data.js';

/**
 * 這篇的作者 / 譯者是否就是專頁的那位:
 * 1. 顯示名字完全相同(舊資料、沒有 ID 的關聯也能用)
 * 2. 或名字 / 曾用名透過 lookup 對到的 ID,出現在這篇的 author_ids / translator_ids(改名後仍對得到)
 */
export function matchesAuthor(a, name, lookup) {
  if (!name) return true;
  if (persons(a).includes(name)) return true;
  const id = lookup && lookup.idOf(name);
  if (!id) return false;
  const refs = personRefs(a);
  return refs.authors.concat(refs.translators).some((r) => r.id === id);
}

/** 單篇是否通過篩選。 */
export function passes(a, f = {}) {
  if (f.shelf && !f.shelf.has(a.no)) return false;
  if (!(f.shelf && f.shelfTab === 'read') && f.hideRead && f.readSet && f.readSet.has(a.no)) return false;
  if (a.dead && f.hideDead) return false;
  if (f.term) { if (!(a._s || '').includes(f.term)) return false; }
  if (f.author) { if (!matchesAuthor(a, f.author, f.lookup)) return false; }
  const sel = f.sel || {}, modes = f.modes || {};
  for (const key in sel) {
    const s = sel[key];
    const inc = Object.keys(s).filter((v) => s[v] === 'on');
    const exc = Object.keys(s).filter((v) => s[v] === 'exc');
    const vals = (a.tags && a.tags[key]) || [];
    if (exc.some((v) => vals.includes(v))) return false;
    if (inc.length) {
      const ok = modes[key] === 'and' ? inc.every((v) => vals.includes(v)) : inc.some((v) => vals.includes(v));
      if (!ok) return false;
    }
  }
  return true;
}

/** 篩出所有通過的文章(保持原順序)。 */
export function filterArticles(articles, f = {}) {
  return (articles || []).filter((a) => passes(a, f));
}

/** 某位作者/譯者的所有作品(作者專頁的篇數)。 */
export function authorWorks(articles, name, lookup) {
  return (articles || []).filter((a) => matchesAuthor(a, name, lookup));
}

/**
 * 點一下標籤:未選 → 包含(on) → 排除(exc) → 取消。就地修改 sel 並回傳新狀態字串('on' | 'exc' | undefined)。
 */
export function cycleTag(sel, key, val) {
  const s = sel[key] || (sel[key] = {});
  if (!s[val]) s[val] = 'on';
  else if (s[val] === 'on') s[val] = 'exc';
  else delete s[val];
  return s[val];
}

/** 直接設成包含(熱門星系 / 點書卡標籤用)。 */
export function selectTag(sel, key, val) {
  const s = sel[key] || (sel[key] = {});
  s[val] = 'on';
}

/** 移除單一標籤條件(條件列的 ✕);該分面沒剩任何標籤就整個拿掉。 */
export function removeTag(sel, key, val) {
  if (!sel[key]) return;
  delete sel[key][val];
  if (!Object.keys(sel[key]).length) delete sel[key];
}

/** 區標題「任一 ⇄ 全部」切換;回傳切換後是否為 'and'。 */
export function toggleMode(modes, key) {
  if (modes[key] === 'and') delete modes[key]; else modes[key] = 'and';
  return modes[key] === 'and';
}

/** 清空所有標籤條件與任一/全部設定(就地)。 */
export function clearSelection(sel, modes) {
  for (const k in sel) delete sel[k];
  for (const k in modes) delete modes[k];
}

/** 目前條件列要顯示的 chips:[{key, val, exc}],依加入順序。 */
export function selectionChips(sel) {
  const out = [];
  for (const key in sel) for (const v in sel[key]) out.push({ key, val: v, exc: sel[key][v] === 'exc' });
  return out;
}
