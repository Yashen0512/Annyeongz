# CLAUDE.md — Annyeongz 平行宇宙

> 給 Claude(與任何接手的人)的專案說明。全站與這份文件都用**繁體中文、台灣用語**。

## 專案目的與讀者

- 這是「安員」(IVE 安俞真 × 張員瑛)同人文的**索引站**:只收錄書目資料與閱讀連結,不放原文。
  讀者用分類篩選找到想看的文之後,點閱讀連結回 Postype / Lofter / AO3 / AFF 等平台看原文。
- 讀者是台灣與華語圈的同人讀者,用手機看的人很多,所以手機版面與字級是第一順位。
- 網址:<https://yashen0512.github.io/Annyeongz/>(GitHub Pages 靜態站,沒有後端)。
- 站內用語維持原本的「星際」主題:新星誕生(最新收錄)、軌道更新(最近編輯)、熱門星系(熱門標籤)、
  平行宇宙(主列表)、穿越蟲洞(隨機)、星際廣播(公告)、星際旅人統計(人次)、被觀測(查看數)。

## 目錄結構

```
index.html                 由樣板建置出來的首頁(含注入的資料),不要手改 → 改 _build/site_template.html
data.js                    window.DATA = {...} 全部資料(建置產物,也會注入 index.html)
src/                       前端程式(ES modules,無框架)
  main.js                  組裝:狀態、DOM 事件、呼叫各模組、啟動順序
  data.js                  載入與正規化 window.DATA、簡繁折算、資料存取小工具
  filter.js                篩選(純函式,不碰 DOM)
  sort.js                  排序(純函式,六種)
  storage.js               localStorage / sessionStorage 的 key 與讀寫(集中管理)
  url.js                   篩選狀態 ⇄ 網址 #f= 參數
  render.js                書卡、輪播小卡、分類面板、條件列、分頁、詳情 / 公告彈窗、統計卡的 DOM 產生
  related.js               「類似的文」相似度(純函式)
  reactions.js             公開愛心數 / 觀測數的本機狀態與同步
  api.js                   站外服務(Val Town)的 fetch 包裝
  intro.js                 開場動畫(傳統 script,非 module;需同步執行)
styles/                    樣式,依原本的 cascade 順序切成六個檔(index.html 依序載入)
  base.css panel.css main.css modal.css responsive.css intro.css
tests/                     Vitest 單元測試(filter / sort / url)+ fixtures.js
_build/                    建置工具(Python)
  fetch_data.py            從 Notion API 抓主表 / 作者 / 公告 / 每篇連結 → CSV + article_links.json
  build_site.py            CSV → data.js + index.html(樣板注入資料與簡繁對照表),含編號重複 / 架構自檢
  site_template.html       首頁樣板(真正要改的 HTML 在這裡)
  facets_def.py            分面定義、標籤改名 / 合併規則、逐篇人工校正(單一事實來源)
  stmap.txt                簡繁對照表(兩行:繁字串 / 簡字串,逐字對應)
  article_links.json       每篇閱讀連結(fetch_data.py 產生)
  reactions_backup.json    愛心 / 觀測計數的備份({編號: [愛心, 觀測]})
sw.js                      PWA service worker(network-first;預先快取 src/ 與 styles/)
manifest.webmanifest       PWA 設定
.github/workflows/         sync.yml(手動:同步 Notion + 建置 + 部署)、static.yml(push main → 部署)、test.yml(PR → 測試)
```

## 資料檔

- **位置**:`data.js`(`window.DATA = {...};`),建置時同一份 JSON 也被注入 `index.html` 的
  `<script>/*__DATA__*/</script>`,所以首頁**不會另外請求 data.js**;`src/data.js` 的 `loadData()` 直接讀 `window.DATA`。
- **來源**:Notion 資料庫 → `_build/fetch_data.py` → CSV → `_build/build_site.py`。欄位意義以 `build_site.py` 為準。
- **頂層欄位**:

| 欄位 | 意義 |
|---|---|
| `total` | 文章總數(主列表「共 N / total 篇」) |
| `facets` | 分面清單 `[{key, type:'single'|'multi', options:[[標籤, 篇數], ...]}]`;single = 文章類型 / 文章篇幅 / 結局 / 文章狀態(每篇最多一個值),multi = 其餘(CP配對、氛圍、情感梗、背景設定、類型世界觀、題材梗、分級、形式/性質、三個合集活動面)。options 順序就是面板顯示順序 |
| `articles` | 文章陣列,**預設依編號大→小** |
| `people` | 作者 / 譯者的平台連結 `{名字: {平台: 網址}}` |
| `announcements` | 公告 `[{content, date:'2026/10/18', dk:20261018, pin:true}]` |
| `updated` | 資料庫更新時間(所有文章最新的編輯時間,頁尾「星圖更新」) |
| `synced` | 本次建置時間(頁尾「訊號同步」) |
| `dead_authors` | 已刪帳號的作者名字陣列(顯示「(已刪帳號)」) |
| `stats` | 建置時抓到的瀏覽人次 `{today, week, month, lastmonth, year, total, asof}`;可能是 null |

- **每篇文章(`articles[]`)**:

| 欄位 | 意義 |
|---|---|
| `no` | 編號(字串;10000 以上是活動系列)。排序、書架、計數都用它當 key |
| `name` | 標題 |
| `alias` | 收錄篇名(多行,以 `\n` 分隔;書卡只顯示第一筆 +「等 N 篇」,詳情顯示全部) |
| `author` / `translator` | 作者 / 譯者,多人用「、」分隔。譯文(形式/性質含「譯文」)時第一人是作者、其餘是譯者 |
| `persona` | 人設(安、員),多行 |
| `tags` | `{分面: [標籤, ...]}`,鍵與 `facets[].key` 相同;單選分面也是陣列(取第一個) |
| `links` | 閱讀連結 `[[名稱, 網址]]` 或 `[[名稱, 網址, 1]]`;第三格 1 = **該連結已失效**(Notion 連結名稱裡的 ❌)。網址 `annyeongz:<編號>` 是站內互連(前傳 / 續寫),不算有效或失效連結 |
| `dead` | **原文已刪旗標**:Notion 紅標,或超過一半的站外連結已失效。書卡淡化 + 紅左邊 +「原文已刪」徽章;不計愛心 / 觀測;穿越蟲洞不會抽到 |
| `created` / `ck` | **收錄日期**(Notion 建立時間)顯示字串 `2026/7/13` 與可排序整數 `YYYYMMDDHHMM`;「最新收錄」排序與「新星誕生」用 `ck` |
| `edited` / `ek` | **最近編輯日** 與整數;「軌道更新」用 `ek` |
| `_s` | (執行期才有)標題 + 作者 + 譯者 + 人設 + 收錄篇名經簡繁折算、小寫後的搜尋字串,由 `src/data.js` 補上 |

- **愛心數與觀測數不在資料檔裡**。它們是即時計數,存在 Val Town(`REACT_API`),格式 `{編號: [愛心, 觀測]}`,
  由 `src/reactions.js` 在開站時 GET 回來;收藏 / 取消收藏 / 打開詳情時 POST `{no, type:'like'|'unlike'|'view'}`。
  `REACT_API` 留空或讀取失敗時只是不顯示數字(愛心 / 觀測排序會退回編號大→小),書架照常。
  `_build/reactions_backup.json` 是這份計數的備份。

## 篩選邏輯(`src/filter.js`)

篩選狀態的形狀:`sel = {分面: {標籤: 'on' | 'exc'}}`、`modes = {分面: 'and'}`,加上作者、搜尋字、書架、隱藏已讀 / 原文已刪。

- **同區多選 = OR(任一)**:同一分面選多個標籤,文章有其中任一個就通過。
- **跨區 = AND**:不同分面之間是「同時」,每個有條件的分面都要通過。
- **點擊循環**:未選 → 第一次點 = 包含(`on`,粉底)→ 第二次點 = **排除**(`exc`,紅字刪除線)→ 第三次點 = 取消。
  排除是硬條件:文章只要有任一個被排除的標籤就不顯示,不管包含怎麼設。
- **區標題可切「任一 / 全部」**:多選分面的標題右邊有個 `任一` 小標,點一下變 `全部`(`modes[分面]='and'`),
  該區的包含標籤就變成 AND(全部都要有);只影響該區,其他區照舊。單選分面沒有這個切換。
- 其他疊加條件(都是 AND):搜尋字(比對 `_s`,簡繁皆可)、作者 / 譯者專頁(名字完全相同)、
  書架模式(只顯示該分頁集合內的編號)、隱藏已讀(在書架「已讀」分頁時不套用)、隱藏原文已刪。
- 熱門星系、書卡標籤、詳情標籤:點了直接設成包含(`selectTag`),不走循環。

## 排序(`src/sort.js`)

工具列的 `<select id="sort">`,預設 `old`。排序是純函式 `sortArticles(list, mode, {likeOf, viewOf, rng})`。

| 值 | 顯示 | 規則 |
|---|---|---|
| `old` | 編號 小→大 | 編號數字升冪(非數字當 -1) |
| `new` | 編號 大→小 | 編號數字降冪 |
| `latest` | 🆕 最新收錄 | `ck` 新→舊,同時間再比編號大→小 |
| `likes` | ❤️ 愛心最多 | 愛心數多→少,同數再比編號大→小 |
| `views` | 🔭 最多人觀測 | 觀測數多→少,同數再比編號大→小 |
| `random` | 🌀 穿越蟲洞 | Fisher–Yates 洗牌;傳固定 seed 的 `seededRandom(seed)` 可重現 |

- 「穿越蟲洞」在畫面上是**按鈕**而不是下拉選項:在目前篩選結果中(略過原文已刪與沒有連結的)隨機開一篇詳情,
  用的是 `pickRandom(list, rng)`。`random` 排序模式提供給程式與測試用。
- 未知的模式值退回標題 `localeCompare('zh-Hant')`(原站行為;分享網址帶了不存在的 sort 值時會走到這裡)。

## 本機儲存(`src/storage.js`,所有 key 只定義在這裡)

| key | 存在哪 | 內容 |
|---|---|---|
| `annyeongz_favs` | localStorage | 收藏(❤️)的編號 JSON 陣列 |
| `annyeongz_read` | localStorage | 已讀(✓)的編號 JSON 陣列;「隱藏已讀」就是看這個集合 |
| `annyeongz_todo` | localStorage | 待閱讀(🔖)的編號 JSON 陣列;標為已讀時自動移出 |
| `annyeongz_shelftab` | localStorage | 書架上次停留的分頁 `fav` / `todo` / `read` |
| `annyeongz_favs_sent` | localStorage | 已經計入公開愛心數的收藏編號(避免重複 +1;送出失敗會移除,下次補送) |
| `azTheme` | localStorage | `dark` / `light` |
| `azIntro` | sessionStorage | 本分頁已播過開場動畫(`src/intro.js` 是傳統 script,直接寫字串,改 key 要兩邊一起改) |
| `azv_<編號>` | sessionStorage | 同一分頁同一篇只計一次觀測 |

- 「隱藏已讀」「隱藏原文已刪」兩個勾選框本身**不記憶**(重新整理就清掉),也不會進分享網址。
- 書架完全存本機,免登入,每台裝置各自一份。

## 複製篩選連結(`src/url.js`)

- 格式:`<origin + pathname>#f=<encodeURIComponent(JSON.stringify(o))>`,`o` 只放有設定的欄位:
  - `s` 標籤三態 `{分面: {標籤: 'on'|'exc'}}`
  - `m` 任一 / 全部 `{分面: 'and'}`
  - `a` 作者 / 譯者專頁名字
  - `q` 搜尋字(原始輸入去頭尾空白)
  - `sort` 排序(預設 `old` 不寫)
- 沒有任何條件時就是純網址。範例:`#f=%7B%22s%22%3A%7B%22CP%E9%85%8D%E5%B0%8D%22%3A%7B%22%E5%AE%89%2F%E5%93%A1%22%3A%22on%22%7D%7D%7D`
- 只在**開站時**讀一次 hash(`applyShareHash`),之後改 hash 不會重新套用;hash 壞掉就當沒有。
- 複製用 `navigator.clipboard.writeText`,不支援時退回 `prompt()`。

## 深淺色主題

- `<html data-theme="dark|light">`,CSS 變數定義在 `styles/base.css`:`:root{}` 是淺色,`[data-theme="dark"]{}` 覆蓋成深色。
- 預設**深色**(配合品牌);`src/main.js` 的 `applyTheme()` 設屬性、換頂欄按鈕圖示(深色顯示 ☀️、淺色顯示 🌙)並存 `azTheme`。
- 開場動畫固定夜空,不跟主題。沒有用 `prefers-color-scheme`。

## 部署

- **GitHub Pages,沒有 build 步驟**:整個倉庫原樣上傳(`static.yml` 的 `path: '.'`),所以 `src/`、`styles/` 就是線上檔案。
  push 到 `main` 就部署;`.nojekyll` 關掉 Jekyll。
- **資料更新**走 `sync.yml`(手動觸發,或排程 08:31 / 21:01):`fetch_data.py` → `build_site.py` 產出 `index.html`、`data.js`,
  commit 回 `main` 再部署。**改 HTML 一律改 `_build/site_template.html`**,`index.html` 會被下一次同步覆蓋。
  本機沒有 Notion CSV 時,可用與 `build_site.py` 相同的三個取代(`__STMAP_T__`、`__STMAP_S__`、`/*__DATA__*/`)從樣板重產 `index.html`。
- `index.html` 裡由建置 / 部署決定的東西:注入的 `window.DATA`、`window.AZ_STMAP`(簡繁表)、`window.AZ_CONFIG`
  (`REACT_API` / `REPORT_API` / `STATS_API` 三個 Val Town 端點;`build_site.py` 的架構自檢會檢查它們還在)、GoatCounter 追蹤碼。
- 因為用 ES module,**本機要用 http 伺服器開**(`npm run serve` 或 `python3 -m http.server 8000`),直接雙擊 `index.html`(file://)不行。
- `package.json` / `tests/` / `node_modules` 只為了測試,部署用不到(`node_modules` 不進版控)。
- 改了 `src/` 或 `styles/` 的檔名,記得同步 `sw.js` 的預先快取清單並把 `CACHE` 版本號 +1。

## 測試

```bash
npm install      # 只需一次(vitest 是 devDependency)
npm test         # vitest run:tests/filter.test.js、sort.test.js、url.test.js
```

- `.github/workflows/test.yml` 在 PR 時自動跑。
- 純函式模組(filter / sort / url / related)不可 import DOM 或 `window`,這樣才能在 Node 直接測。
- 改畫面或行為前後,建議用 Playwright 把舊版與新版同時跑一遍比對 DOM 與截圖(這次拆模組就是這樣驗的)。

## 程式慣例

- **繁體中文註解**(台灣用語),檔頭先寫這個模組負責什麼。
- **不用框架、不引入大型相依套件**;前端只有原生 ES module,唯一的開發相依是 Vitest。瀏覽器端沒有 bundler、沒有 transpile。
- 純函式與 DOM 分開:`filter.js`、`sort.js`、`url.js`、`related.js` 不碰 DOM;`render.js` 只產生 DOM,狀態與事件接線都在 `main.js`。
- 詳情彈窗與書卡的 HTML 字串用 inline `onclick` 呼叫 `toggleFav`、`filterByTag`、`navDetail` 等函式,
  這些函式在 `main.js` 結尾用 `Object.assign(window, {...})` 掛到全域;新增這類函式要一起掛上去。
- 本機儲存的 key 只能從 `storage.js` 的 `KEYS` 拿。
- `index.html` 的文案、emoji、全形標點(「：」「（）」)是刻意的,不要「順手」改成半形。
- 原站的幾個既有行為是刻意保留的,改之前先確認:搜尋 / 排序 / 勾選框觸發重繪時**不會跳回第 1 頁**(只會夾到最後一頁);
  分面標籤三態循環是 包含 → 排除 → 取消;穿越蟲洞略過原文已刪與無連結的文。
- 標籤名稱、分面順序、改名合併規則都在 `_build/facets_def.py`,前端不要寫死標籤清單(`related.js` 的 `REL_FACETS` 與
  `render.js` 的狀態色對照 `STMAP` 是僅有的例外)。
