import { describe, it, expect, beforeAll, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { KEYS, exportState, importState, decodeState, mergeState, previewImport, extractPayload, buildImportURL, clearAllRecords, EXPORT_VERSION } from '../src/storage.js';

// vendor/lz-string.min.js 是給瀏覽器的傳統 script(把 LZString 放在全域);
// 這裡照同樣方式載入(當成一段 script 執行、取出 LZString),測的就是正式用的那一份。
const VENDOR = fileURLToPath(new URL('../vendor/lz-string.min.js', import.meta.url));
function loadLZ() { return new Function(readFileSync(VENDOR, 'utf8') + ';return LZString;')(); }

// 假的 localStorage(Node 沒有):驗證匯入失敗時連存下來的東西都沒動
const store = new Map();
const fakeLS = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => { store.set(k, String(v)); },
  removeItem: (k) => { store.delete(k); },
};
const snapshot = () => JSON.stringify([...store.entries()].sort());

globalThis.LZString = loadLZ();   // 模組載入時就放好(it.each 的表在收集階段就會用到)
beforeAll(() => {
  Object.defineProperty(globalThis, 'localStorage', { value: fakeLS, configurable: true, writable: true });
});
beforeEach(() => store.clear());

const sets = (f, r, t = []) => ({ favs: new Set(f), read: new Set(r), todo: new Set(t) });
const sorted = (s) => [...s].sort();

describe('匯出格式', () => {
  it('壓縮後只含 URL-safe 字元(A-Z a-z 0-9 + - $),解開是 {v, shelf, read, exportedAt}', () => {
    const when = new Date('2026-10-30T12:34:56.000Z');
    const s = exportState({ favs: new Set(['12', '7']), read: new Set(['7', '300']) }, when);
    expect(s).toMatch(/^[A-Za-z0-9+\-$]+$/);
    const o = JSON.parse(globalThis.LZString.decompressFromEncodedURIComponent(s));
    expect(o).toEqual({ v: EXPORT_VERSION, shelf: ['12', '7'], read: ['7', '300'], exportedAt: '2026-10-30T12:34:56.000Z' });
  });
  it('書架是空的也能匯出', () => {
    expect(decodeState(exportState({ favs: new Set(), read: new Set() }))).toMatchObject({ shelf: [], read: [] });
  });
});

describe('匯出再匯入', () => {
  it('匯到空的裝置 = 原狀(收藏與已讀都一樣,順序不計)', () => {
    const src = sets(['1', '2', '10', '10001'], ['2', '3']);
    const payload = exportState(src);
    const dst = sets([], []);
    const r = importState(payload, { ...dst, mode: 'merge' });
    expect(sorted(dst.favs)).toEqual(sorted(src.favs));
    expect(sorted(dst.read)).toEqual(sorted(src.read));
    expect(sorted(r.addedShelf)).toEqual(sorted(src.favs));
    expect(sorted(r.addedRead)).toEqual(sorted(src.read));
    // 也寫進了 localStorage(key 名稱不變)
    expect(JSON.parse(store.get(KEYS.FAVS)).sort()).toEqual(sorted(src.favs));
    expect(JSON.parse(store.get(KEYS.READ)).sort()).toEqual(sorted(src.read));
  });
  it('decodeState 會去重並回傳匯出時間', () => {
    const when = new Date('2026-01-02T03:04:05.000Z');
    const d = decodeState(exportState({ favs: ['5', '5', '6'], read: [] }, when));
    expect(d).toEqual({ shelf: ['5', '6'], read: [], exportedAt: '2026-01-02T03:04:05.000Z' });
  });
});

describe('合併模式(預設,聯集)', () => {
  it('兩邊都保留,重複的只算一次;回傳真正新增的編號', () => {
    const payload = exportState(sets(['1', '2'], ['2', '3']));
    const dst = sets(['2', '9'], ['3', '8']);
    const r = importState(payload, dst);   // 沒給 mode = merge
    expect(sorted(dst.favs)).toEqual(['1', '2', '9']);
    expect(sorted(dst.read)).toEqual(['2', '3', '8']);
    expect(r.addedShelf).toEqual(['1']); expect(r.addedRead).toEqual(['2']); expect(r.removedShelf).toEqual([]);
  });
  it('匯入的已讀會自動移出待閱讀(與標為已讀同一條規則)', () => {
    const payload = exportState(sets([], ['3']));
    const dst = sets([], [], ['3', '4']);
    importState(payload, dst);
    expect(sorted(dst.todo)).toEqual(['4']);
    expect(JSON.parse(store.get(KEYS.TODO))).toEqual(['4']);
  });
  it('mergeState / previewImport 是純函式:不動傳入的集合,預覽數字正確', () => {
    const cur = { favs: new Set(['1']), read: new Set(['1', '2']) }, inc = { shelf: ['1', '2', '3'], read: ['9'] };
    const next = mergeState(cur, inc, 'merge');
    expect(sorted(next.favs)).toEqual(['1', '2', '3']); expect(sorted(next.read)).toEqual(['1', '2', '9']);
    expect(sorted(cur.favs)).toEqual(['1']); expect(sorted(cur.read)).toEqual(['1', '2']);
    expect(previewImport(cur, inc, 'merge')).toEqual({ addShelf: 2, addRead: 1, removeShelf: 0, removeRead: 0, shelfTotal: 3, readTotal: 3 });
  });
});

describe('覆蓋模式', () => {
  it('以匯入的為準,原本多出來的會被移除', () => {
    const payload = exportState(sets(['1', '2'], ['2']));
    const dst = sets(['2', '9'], ['3', '8']);
    const r = importState(payload, { ...dst, mode: 'replace' });
    expect(sorted(dst.favs)).toEqual(['1', '2']);
    expect(sorted(dst.read)).toEqual(['2']);
    expect(r.addedShelf).toEqual(['1']); expect(r.removedShelf).toEqual(['9']); expect(r.addedRead).toEqual(['2']);
    expect(JSON.parse(store.get(KEYS.FAVS)).sort()).toEqual(['1', '2']);
  });
  it('previewImport 覆蓋模式會算出移除數', () => {
    const cur = { favs: new Set(['1', '2']), read: new Set(['5']) }, inc = { shelf: ['2'], read: [] };
    expect(previewImport(cur, inc, 'replace')).toEqual({ addShelf: 0, addRead: 0, removeShelf: 1, removeRead: 1, shelfTotal: 1, readTotal: 0 });
  });
});

describe('壞資料被拒絕,原資料不變', () => {
  const LZ = () => globalThis.LZString;
  const bad = () => ({
    '空字串': '',
    '隨便的文字': 'hello world',
    '不是 JSON': LZ().compressToEncodedURIComponent('not json'),
    'JSON 不是物件': LZ().compressToEncodedURIComponent('[1,2]'),
    '版本不對': LZ().compressToEncodedURIComponent(JSON.stringify({ v: 2, shelf: [], read: [] })),
    '沒有 v': LZ().compressToEncodedURIComponent(JSON.stringify({ shelf: [], read: [] })),
    'shelf 不是陣列': LZ().compressToEncodedURIComponent(JSON.stringify({ v: 1, shelf: '1,2', read: [] })),
    'read 缺少': LZ().compressToEncodedURIComponent(JSON.stringify({ v: 1, shelf: [] })),
    '編號不是字串': LZ().compressToEncodedURIComponent(JSON.stringify({ v: 1, shelf: [1, 2], read: [] })),
    '編號是空字串': LZ().compressToEncodedURIComponent(JSON.stringify({ v: 1, shelf: [''], read: [] })),
  });
  it.each(Object.entries(bad()))('%s → 丟錯、Set 與 localStorage 都沒動', (_name, payload) => {
    const dst = sets(['2', '9'], ['3'], ['4']);
    store.set(KEYS.FAVS, '["2","9"]'); store.set(KEYS.READ, '["3"]'); store.set(KEYS.TODO, '["4"]');
    const before = snapshot();
    expect(() => importState(payload, dst)).toThrow(Error);
    expect(() => importState(payload, { ...dst, mode: 'replace' })).toThrow(Error);
    expect(sorted(dst.favs)).toEqual(['2', '9']); expect(sorted(dst.read)).toEqual(['3']); expect(sorted(dst.todo)).toEqual(['4']);
    expect(snapshot()).toBe(before);
  });
  it('錯誤訊息是給讀者看的中文', () => {
    expect(() => decodeState('xx')).toThrow(/看不懂/);
    expect(() => decodeState(LZ().compressToEncodedURIComponent(JSON.stringify({ v: 7, shelf: [], read: [] })))).toThrow(/版本/);
  });
  it('lz-string 沒載入時也是丟錯、不動資料', () => {
    const saved = globalThis.LZString; globalThis.LZString = undefined;
    const dst = sets(['1'], []);
    try {
      expect(() => exportState(dst)).toThrow(/lz-string/);
      expect(() => importState('abc', dst)).toThrow(/lz-string/);
    } finally { globalThis.LZString = saved; }
    expect(sorted(dst.favs)).toEqual(['1']);
  });
});

describe('超大書架(2000 筆)', () => {
  it('壓縮後長度遠小於 JSON,仍可完整還原;字串只含 URL-safe 字元', () => {
    const nos = Array.from({ length: 2000 }, (_, i) => String(100 + i * 3));
    const src = sets(nos, nos.slice(0, 1000));
    const payload = exportState(src);
    const json = JSON.stringify({ v: 1, shelf: nos, read: nos.slice(0, 1000), exportedAt: new Date().toISOString() });
    expect(payload.length).toBeLessThan(json.length * 0.6);   // 實測約 1 萬字(JSON 約 2 萬)
    expect(payload.length).toBeLessThan(12000);
    expect(payload).toMatch(/^[A-Za-z0-9+\-$]+$/);
    const dst = sets([], []);
    importState(payload, dst);
    expect(dst.favs.size).toBe(2000); expect(dst.read.size).toBe(1000);
    expect(sorted(dst.favs)).toEqual(sorted(nos));
  });
  it('超過 2000 字的字串仍能用複製 / 連結匯入(QR 的門檻只影響畫面提示)', () => {
    const nos = Array.from({ length: 2000 }, (_, i) => String(i + 1));
    const payload = exportState(sets(nos, []));
    expect(payload.length).toBeGreaterThan(2000);
    expect(decodeState(buildImportURL(payload, 'https://yashen0512.github.io/Annyeongz/')).shelf.length).toBe(2000);
  });
});

describe('?s= 連結', () => {
  const payload = exportState(sets(['1', '2'], ['3']));
  it('buildImportURL = base?s=字串;extractPayload 能從網址、含 #f= 的網址、純字串取回', () => {
    const base = 'https://yashen0512.github.io/Annyeongz/';
    const url = buildImportURL(payload, base);
    expect(url).toBe(base + '?s=' + payload);
    expect(extractPayload(url)).toBe(payload);
    expect(extractPayload(url + '#f=%7B%22q%22%3A%22x%22%7D')).toBe(payload);
    expect(extractPayload('  ' + payload + '\n')).toBe(payload);
    expect(decodeState(url)).toMatchObject({ shelf: ['1', '2'], read: ['3'] });
  });
  it('字串裡的 + 不會被當成空白;被別的 App 百分比編碼過也能還原', () => {
    const s = 'ab+cd$ef-gh';
    expect(extractPayload('https://x/?s=' + s)).toBe(s);
    expect(extractPayload('https://x/?s=' + encodeURIComponent(s))).toBe(s);
    expect(extractPayload('https://x/?other=1&s=' + s + '&more=2')).toBe(s);
  });
});

describe('清除所有紀錄', () => {
  it('Set 清空、相關 key 全部移除,主題等其他 key 不動', () => {
    const dst = sets(['1'], ['2'], ['3']);
    [KEYS.FAVS, KEYS.READ, KEYS.TODO, KEYS.FAVS_SENT, KEYS.SHELF_TAB].forEach((k) => store.set(k, 'x'));
    store.set(KEYS.THEME, 'light');
    clearAllRecords(dst);
    expect(dst.favs.size + dst.read.size + dst.todo.size).toBe(0);
    expect([...store.keys()]).toEqual([KEYS.THEME]);
  });
});
