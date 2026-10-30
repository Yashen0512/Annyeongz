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
stats.html                 📊 統計星圖(靜態頁,不經樣板;用 <script src="data.js"> 讀同一份資料,圖表用 Chart.js)
p/<No>/index.html, og.png  每篇作品的靜態分享頁與 1200×630 預覽圖(build_pages.py 產物;.gitattributes 標 linguist-generated)
sitemap.xml feed.xml feed-updated.xml robots.txt   同上(build_pages.py 產物)
src/                       前端程式(ES modules,無框架)
  main.js                  組裝:狀態、DOM 事件、呼叫各模組、啟動順序
  data.js                  載入與正規化 window.DATA、簡繁折算、資料存取小工具
  filter.js                篩選(純函式,不碰 DOM)
  sort.js                  排序(純函式,六種)
  storage.js               localStorage / sessionStorage 的 key 與讀寫(集中管理);書架 / 已讀的匯出匯入(exportState / importState)
  url.js                   篩選狀態 ⇄ 網址 #f= 參數
  render.js                書卡、輪播小卡、分類面板、條件列、分頁、詳情 / 公告彈窗、統計卡的 DOM 產生
  related.js               「類似的文」相似度(純函式)
  reactions.js             公開愛心數 / 觀測數的本機狀態與同步
  api.js                   站外服務(Val Town)的 fetch 包裝
  intro.js                 開場動畫(傳統 script,非 module;需同步執行)
  stats.js                 統計星圖:統計純函式(每月分組 / 排行 / 比例 / 年度已刪)+ Chart.js 設定物件 + createCharts
  stats_page.js            統計星圖的組裝:讀 CSS 變數當圖表顏色、主題切換重畫、「全部 / 排除已刪」、計數讀取與備份退路
styles/                    樣式,依原本的 cascade 順序切成六個檔(index.html 依序載入)+ stats.css(統計星圖專用)
  base.css panel.css main.css modal.css responsive.css intro.css stats.css
vendor/                    第三方單檔(Chart.js 統計星圖;lz-string 壓縮與 qrcode-generator 產 QR 給書架匯出),傳統 <script> 載入,不走 npm;版本與授權見 vendor/README.md
tests/                     測試
  *.test.js                Vitest(filter / sort / url / stats / storage 純函式)+ fixtures.js
  py/                      pytest(build_site / fetch_data / build_pages 純函式 + 用 30 篇 fixture 跑完整建置與產頁;
                           checkers HTML 樣本;check_links 狀態機與改名判斷;notion_writeback 的 rich_text 純函式)
  fixtures/build_input/    30 篇的建置輸入(主表 / 作者 / 公告 CSV、article_links.json、expected.json),由 make_fixture.py 從 data.js 反推
  fixtures/html/           各平台頁面的最小 HTML 樣本(正常 / 已刪 / 登入牆 / Cloudflare 挑戰頁),給 checkers 測試用
_build/                    建置工具(Python,只用標準庫)
  fetch_data.py            從 Notion API 抓主表 / 作者 / 公告 / 每篇連結 → CSV + article_links.json(主流程在 main())
  build_site.py            CSV → data.js + index.html(樣板注入資料與簡繁對照表)+ 複製 src/、styles/、vendor/、stats.html;含編號重複 / 架構自檢(build_data / write_site 可被 import)
  build_pages.py           data.js → p/<No>/{index.html, og.png} + sitemap.xml + feed.xml / feed-updated.xml + robots.txt;只重產內容 hash 有變的(build_pages 可被 import)
  fonts/                   OG 圖字型:Noto Sans TC / KR 的 Regular、Bold(Google Fonts,OFL);諺文用 KR 回退、TC 沒有的簡體字用 stmap 轉繁、emoji 略過
  og_brand.png             OG 圖左上的 🐶❤️🐰(預先畫好,Actions 不用裝 emoji 字型)
  site_template.html       首頁樣板(真正要改的 HTML 在這裡)
  facets_def.py            分面定義、標籤改名 / 合併規則、逐篇人工校正(單一事實來源)
  stmap.txt                簡繁對照表(兩行:繁字串 / 簡字串,逐字對應)
  article_links.json       每篇閱讀連結(fetch_data.py 產生;保留鍵 __edited__ / __blocks__ 見「原文巡檢」)
  reactions_backup.json    愛心 / 觀測計數的備份({編號: [愛心, 觀測]})
  probe.py                 可行性測試:四個平台各抓正常 / 已刪 / 不存在三個連結,印狀態碼、最終網址、HTML 前 2000 字
  checkers/                各平台「還在不在」檢查器(postype / lofter / ao3 / aff;共用介面 check(url))
  check_links.py           每日巡檢:所有原文連結 + 作者庫平台網址 → link_status.json、check_report.json(不寫 Notion)
  notion_writeback.py      把巡檢結果寫回 Notion(❌ 標記 / 作者改名 + 曾用名);預設 dry-run,--go 才寫
  link_status.json         每個連結的上次狀態、連續天數、上次檢查時間(commit 進 repo;巡檢排程每天更新)
                           check_links.yml(每天 03:00 巡檢原文連結 + 寫回 Notion + 開 Issue)
sw.js                      PWA service worker(network-first;預先快取 src/、styles/、vendor/ 與 stats.html)
manifest.webmanifest       PWA 設定
.github/workflows/         sync.yml(同步 Notion + 建置 + 部署)、static.yml(push main → 部署)、test.yml(PR → Vitest + pytest)、
                           check_links.yml(每天 03:00 巡檢原文連結 + 寫回 Notion + 開 Issue)
requirements.txt           建置相依:只有 Pillow(build_pages.py 畫 OG 圖);sync.yml 與站長電腦都要裝
package.json / pytest.ini / requirements-dev.txt   只為了測試,部署用不到
```

## 資料流(整個 repo 的骨幹)

```
Notion 三個資料庫(主表、作者/譯者資料庫、公告)
  │  _build/fetch_data.py   Notion API → Annyeongz_<主表ID>_all.csv、_authors/authors_all.csv、_announce/announce_all.csv、
  │                         article_links.json(每篇內文的閱讀連結,增量:新 No 或頁面編輯過才重抓)、
  │                         stats.json(有 GOATCOUNTER_TOKEN 才抓)、reactions_backup.json(愛心 / 觀測備份)
  ▼
  │  _build/build_site.py   套 facets_def.py(分面定義、改名合併、逐篇校正)→ DATA
  │                         → <輸出>/data.js、<輸出>/index.html(site_template.html 注入 /*__DATA__*/ 與簡繁表)
  │                         → 複製 src/、styles/、vendor/ 到 <輸出>(輸出就是倉庫根目錄時不動)
  ▼
  │  _build/build_pages.py  讀 <輸出>/data.js → <輸出>/p/<No>/index.html + og.png(每篇分享頁與預覽圖,內容 hash 沒變就跳過)
  │                         → <輸出>/sitemap.xml、feed.xml(最新收錄 50)、feed-updated.xml(最近編輯 50)、robots.txt
  ▼
GitHub Pages(static.yml:整個倉庫原樣上傳)
```

- **兩條路徑,同一組腳本**:
  - GitHub Actions `sync.yml`:只有 `workflow_dispatch`(檔案裡**沒有 cron**),每天台灣時間 **08:31 與 21:01** 的自動執行是由外部
    觸發這個 dispatch;`build_site.py` 會把這兩個時段後 8 分鐘內的建置時間貼齊顯示成 08:31 / 21:01(頁尾「訊號同步」)。
    環境變數 `SITE_OUT=..` → 直接輸出到倉庫根目錄,
    然後 `git add index.html data.js p sitemap.xml feed.xml feed-updated.xml robots.txt _build/article_links.json _build/reactions_backup.json`
    commit 回 `main` 再部署。Actions 會先 `pip install -r requirements.txt`(Pillow)。
  - 本機 `更新網站.bat`(不在 repo 裡,在站長電腦上)跑同一組 `fetch_data.py` → `build_site.py` → `build_pages.py`,沒設 `SITE_OUT` 時輸出到 `../site`
    (也就是 `_build/` 旁的 `site/` 資料夾,已 gitignore);`deploy.py`(同樣不在 repo 裡)負責把本機腳本同步進 `_build/`,
    也要把 `site/p/`、`sitemap.xml`、`feed*.xml`、`robots.txt` 一併部署。站長電腦要 `pip install -r requirements.txt` 一次。
    `build_site.py` 會把 `src/`、`styles/`、`vendor/` 與 `stats.html` 一起複製進輸出資料夾(`STATIC_DIRS` / `STATIC_FILES`),
    所以本機產出的 `site/` 用 http 伺服器開就能用(含統計星圖)。
- **第三條路徑:原文巡檢(`check_links.yml`,每天台灣時間 03:00)**:`fetch_data.py` → `check_links.py` → `notion_writeback.py --go`
  → commit `_build/link_status.json`;有變更就開 Issue「原文狀態變更 YYYY-MM-DD」。巡檢結果**只寫回 Notion**(❌ 與作者庫),
  不碰 data.js / CSV,08:31 的 sync 再把它建進網站。細節見下方「原文巡檢與寫回」。
- **結論:`index.html`、`data.js`、`p/`、`sitemap.xml`、`feed*.xml` 都是產物,不要直接改。** 要改前端一律改 `_build/site_template.html` 與它引用的 `src/`、`styles/`,
  再由 `build_site.py` 產出;要改分享頁 / OG 圖 / sitemap / RSS 改 `_build/build_pages.py`(改了版面記得把 `PAGE_VERSION` / `OG_VERSION` +1,才會全部重產)。
- Token:`fetch_data.py` 先看 `NOTION_TOKEN` 環境變數(Actions 的 secret)、再看 `_build/notion_token.txt`(本機,不進版控)、
  都沒有就**不帶 Authorization header** 直接送,交給雲端開發環境的網路代理注入。本機與 Actions 行為不變。
- 沒有 Notion 時,`tests/fixtures/build_input/` 的 30 篇 fixture 可以跑完整個 `build_site.py`(見「測試」)。

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
| `people` | 作者 / 譯者資料庫,**以 Notion 作者頁 ID(32 碼)為鍵**:`{id: {name 目前顯示名, urls:{平台: 網址}, aliases:[曾用名,來自作者庫「曾用名」multi_select,由巡檢改名時填], dead 已刪帳號}}`。作者庫每一位都在(沒填平台的 `urls` 是 `{}`);主表關聯到但作者庫讀不到的,會用名字補一筆 |
| `announcements` | 公告 `[{content, date:'2026/10/18', dk:20261018, pin:true}]` |
| `updated` | 資料庫更新時間(所有文章最新的編輯時間,頁尾「星圖更新」) |
| `synced` | 本次建置時間(頁尾「訊號同步」) |
| `dead_authors` | 已刪帳號的作者**名字**陣列(= people 裡 dead 的 name;相容舊前端,新前端以 people[id].dead 為準) |
| `stats` | 建置時抓到的瀏覽人次 `{today, week, month, lastmonth, year, total, asof}`;可能是 null |

- **每篇文章(`articles[]`)**:

| 欄位 | 意義 |
|---|---|
| `no` | 編號(字串;10000 以上是活動系列)。排序、書架、計數都用它當 key |
| `name` | 標題 |
| `alias` | 收錄篇名(多行,以 `\n` 分隔;書卡只顯示第一筆 +「等 N 篇」,詳情顯示全部) |
| `author` / `translator` | 作者 / 譯者顯示字串,多人用「、」分隔。譯文(形式/性質含「譯文」)且兩人以上時第一人是作者、其餘是譯者 |
| `author_ids` / `translator_ids` | 與上面以「、」拆開後**一一對應**的 Notion 作者頁 ID(穩定鍵;關聯只有名字沒有網址時為空字串) |
| `persona` | 人設(安、員),多行 |
| `tags` | `{分面: [標籤, ...]}`,鍵與 `facets[].key` 相同;單選分面也是陣列(取第一個) |
| `links` | 閱讀連結 `[[名稱, 網址]]` 或 `[[名稱, 網址, 1]]`;第三格 1 = **該連結已失效**(Notion 連結名稱裡的 ❌)。網址 `annyeongz:<編號>` 是站內互連(前傳 / 續寫),不算有效或失效連結 |
| `dead` | **原文已刪旗標**:Notion 紅標,或超過一半的站外連結已失效。書卡淡化 + 紅左邊 +「原文已刪」徽章;不計愛心 / 觀測;穿越蟲洞不會抽到 |
| `created` / `ck` | **收錄日期**(Notion 建立時間)顯示字串 `2026/7/13` 與可排序整數 `YYYYMMDDHHMM`;「最新收錄」排序與「新星誕生」用 `ck` |
| `edited` / `ek` | **最近編輯日** 與整數;「軌道更新」用 `ek` |
| `_s` | (執行期才有)標題 + 作者 + 譯者 + 人設 + 收錄篇名經簡繁折算、小寫後的搜尋字串,由 `src/data.js` 補上 |

- **各欄位對應的 Notion 欄**(`fetch_data.py` 讀 → CSV 欄名 → `build_site.py`):

| data.js | Notion(主表) | 說明 |
|---|---|---|
| `name` | `文章名稱`(title) | |
| `no` | `No`(number / unique_id / title 或 rich_text 三種型別都接受,`read_no`) | 轉成字串 |
| `edited` / `ek` | 頁面 `last_edited_time` → CSV `上次編輯時間`(台北時間中文格式) | `parse_dt` |
| `created` / `ck` | 頁面 `created_time` → CSV `建立時間` | 同上 |
| `persona` | `人設(安、員)`(rich_text) | |
| `author` / `translator` / `*_ids` | `作者/譯者資料庫`(relation)→ CSV 寫成 `名字 (https://www.notion.so/<頁面ID>), …` | `author_parts` 用網址邊界拆,保留 ID |
| `tags` 單選 | `文章狀態` / `文章篇幅` / `文章類型` / `結局`(select) | |
| `tags` 多選 | `文章標籤`(舊的 multi_select,經 REMAP / DROP / ADD 拆進各分面)+ 11 個分面欄(`CP配對`…`1st鳳梨汁推薦`,multi_select) | `facets_def.bucketize` + `merge_facet_cols` |
| `links` | 頁面**內文**區塊裡的連結(`article_links.json`);`@` 提及站內另一篇 → `annyeongz:<No>` | 名稱含 ❌ → 第三格 1 |
| `dead` | 頁面圖示紅色(CSV `紅標` = Y)或 ❌ 連結過半 | `is_dead` |
| `alias` | `收錄篇名`(rich_text) | |
| `people[id]` | 作者庫:`作者名稱`(title)、`作者平台(AF/AO3/LFT/LFT2/PT/WB/X/其他)`(url)、頁面圖示紅色 → `紅標`、頁面 ID → `頁面ID`、`曾用名`(multi_select,', ' 分隔)→ `aliases` | 舊版作者 CSV 沒有 `頁面ID` 欄時,ID 由主表作者欄的網址回填;沒有 `曾用名` 欄 → aliases 空 |
| `announcements` | 公告庫:`內容`、`日期`、`置頂`(checkbox) | |

- **鐵則:作品 `No` 永不重編。** 站內跳轉(`annyeongz:<No>`)、書架與已讀的 localStorage、分享網址、`article_links.json` 的鍵、
  愛心 / 觀測計數(Val Town)全都以 `No` 為鍵;改了編號等於把讀者的書架與所有計數弄丟。**10000 以上是活動系列專用號段**,
  一般文的下一個編號由 `build_site.py` 建置時印出(優先回填空號)。重複編號會在建置時印警告,要回 Notion 修。
- **`dead`(原文已刪)的判定**(`build_site.is_dead`):Notion 頁面圖示是紅色(紅標),**或**頁面內文的閱讀連結名稱含 ❌ 的
  比例超過一半(站內互連 `annyeongz:編號` 不計入分子分母)。紅標 = Y 但還有沒標 ❌ 的連結,建置時會列出待人工確認。
- **愛心數與觀測數不在資料檔裡**。它們是即時計數,存在 Val Town(`REACT_API`),格式 `{編號: [愛心, 觀測]}`,
  由 `src/reactions.js` 在開站時 GET 回來;收藏 / 取消收藏 / 打開詳情時 POST `{no, type:'like'|'unlike'|'view'}`。
  `REACT_API` 留空或讀取失敗時只是不顯示數字(愛心 / 觀測排序會退回編號大→小),書架照常。
  `_build/reactions_backup.json` 是這份計數的備份。

## 原文巡檢與寫回(`_build/check_links.py` → `_build/notion_writeback.py`)

目標:每天自動檢查所有原文連結是否還存在、同步作者改名,**結果寫回 Notion**(資料唯一源頭),網站下次 sync 自然更新。
所有腳本只用標準庫,放在 `_build/`,由站長電腦的 deploy.py 一併同步。

- **檢查器 `_build/checkers/`**:依網域分派 `postype.py` / `lofter.py` / `ao3.py` / `aff.py`,共用介面
  `check(url) → {status: 'ok'|'deleted'|'login_required'|'unknown', author_name: str|None, …}`;每個平台的判斷規則寫在檔頭,
  核心是純函式 `parse(code, final_url, html, url)`,pytest 用 `tests/fixtures/html/` 的樣本直接測。`author_name` 是頁面上解析到的
  作者**目前顯示名**(Postype 取 ld+json author.name;Lofter 取 og:site_name / `<title>` 博客名;AO3 取 byline 的 pseud;
  AFF 取作者連結文字),解析不到就 None,不猜。
- **2026-10-30 用 `probe.py` 實測(雲端 / GitHub Actions 這類海外 IP)**:Postype 正常 200 + ld+json、已刪 / 不存在都 404,可靠;
  **Lofter 一律 302 → www.lofter.com/front/login(登入牆)、AO3 一律 418 Cloudflare「Request temporarily denied」、
  AFF 一律 403 Cloudflare「Just a moment」** → 這三個平台的 checker 會回 `login_required` / `unknown`(`blocked=True`),
  `check_links.py` 看到某平台前 3 筆全被擋就略過該平台其餘連結,**不會把任何連結標成已刪**。它們的 deleted 規則依已知行為寫成、
  尚未實測,站長在看得到這些平台的網路跑才會生效。
- **`check_links.py`**(不寫 Notion):來源 = `article_links.json` 的每篇連結 + 作者庫 CSV 的平台網址(沒有 CSV 時退回 `../data.js`);
  四個平台各一條執行緒交錯,同平台間隔 1.5~3 秒隨機;逾時 / 5xx / 429 重試 2 次,仍失敗 = `unknown`(不算已刪)。
  狀態機(`advance`):只有**連續兩天**都 `deleted` 才算真的死(`dead`),同一天重跑不重複計,`unknown` 不改任何計數;
  已死的每 30 天複查一次(`is_due`),複查看到 `ok` 就復活。狀態存 `_build/link_status.json`(以網址為鍵:
  `{status, streak, last, counted, dead, dead_since, author_name, platform, …}`),commit 進 repo。
  輸出 `check_report.json`(新死 / 復活 / 改名 / 改名候選 / 作者頁失效 / 各平台統計)與有變更時的 `check_report.md`(Issue 內文)。
  報告以「該是什麼狀態」為準:**新死 = dead 且 Notion 連結名稱還沒有 ❌;復活 = Notion 有 ❌ 但今天看到 ok**,所以寫回失敗隔天會再列。
- **`notion_writeback.py`**:預設 dry-run 只印清單,`--go` 才寫。
  - 死連結:用 `article_links.json` 的 `__blocks__`(`{No: {page: 頁面ID, links: {網址: [blockID, rich_text 位置]}}}`,
    `fetch_data.py` 記錄)找到該連結的 block,在連結文字**前**插入一段純文字「❌」;復活就把連結段落與緊鄰前後純文字段裡的 ❌
    都清掉(相容站長以前手動加在連結後面的寫法)。`build_site.py` 既有的 dead 判定(❌ 過半)自動接手。block 對不上就重掃頁面
    子 block 找 href,連頁面 ID 都沒有就用 No 查主表。
  - 作者改名:同一作者(Notion 作者頁 ID)在同一平台有**兩篇以上**單一作者作品解析到同一個新名字、該名字不是目前名稱 / 括號內別名 /
    曾用名、該名字 / 帳號沒出現在別的作者名下(合集帳號)、**且作者庫該平台網址的帳號與頁面作者帳號相符** → 把作者庫「作者名稱」
    改成新名字,並把舊名加進「曾用名」multi_select(不存在就用 database update API 建立;不刪、不重複;半形逗號換全形)。
    作者庫沒有該平台網址、無法核對的只列為「候選」,不寫回。寫之前再讀一次作者頁,title 已不是報告的舊名就跳過。
- **排程 `check_links.yml`**:每天 UTC 19:00(台灣 03:00)與 `workflow_dispatch`(可選 dry-run、平台);讀 secret `NOTION_TOKEN`;
  commit `_build/link_status.json`;`check_report.md` 存在(有新死 / 復活 / 改名)就用 `gh issue create` 開 Issue。
- **本機**:`更新網站.bat` 預設不巡檢;帶參數(`更新網站.bat 巡檢`)才在 fetch 之後跑 `check_links.py` + `notion_writeback.py --go`,
  片段在 `_build/更新網站_巡檢片段.bat.txt`。
- 手動測試:`python check_links.py --platforms postype --no 1352,1255`(只查這幾篇)→ `python notion_writeback.py --no 1352`(dry-run)
  → 加 `--go`。`article_links.json` 的保留鍵一律以 `__` 開頭,迭代時要跳過。

## 篩選邏輯(`src/filter.js`)

共 **15 個面**:4 個單選(文章類型、文章篇幅、結局、文章狀態)、8 個多選分面(CP配對、氛圍、情感梗、背景設定、類型世界觀、
題材梗、分級、形式/性質)、3 個合集面(命定站賀文合集、계간윶녕 : 𝐋𝐎𝐕𝐄 𝐆𝐀𝐌𝐄、1st鳳梨汁推薦)。清單與順序在 `_build/facets_def.py`。

篩選狀態的形狀:`sel = {分面: {標籤: 'on' | 'exc'}}`、`modes = {分面: 'and'}`,加上作者、搜尋字、書架、隱藏已讀 / 原文已刪。

- **同區多選 = OR(任一)**:同一分面選多個標籤,文章有其中任一個就通過。
- **跨區 = AND**:不同分面之間是「同時」,每個有條件的分面都要通過。
- **點擊循環**:未選 → 第一次點 = 包含(`on`,粉底)→ 第二次點 = **排除**(`exc`,紅字刪除線)→ 第三次點 = 取消。
  排除是硬條件:文章只要有任一個被排除的標籤就不顯示,不管包含怎麼設。
- **區標題可切「任一 / 全部」**:多選分面的標題右邊有個 `任一` 小標,點一下變 `全部`(`modes[分面]='and'`),
  該區的包含標籤就變成 AND(全部都要有);只影響該區,其他區照舊。單選分面沒有這個切換。
- 其他疊加條件(都是 AND):搜尋字(比對 `_s`,簡繁皆可,`_s` 含作者 / 譯者的曾用名)、
  作者 / 譯者專頁(`matchesAuthor`:顯示名字相同,**或**名字 / 曾用名經 `makePersonLookup` 對到的作者頁 ID 出現在該篇的
  `author_ids` / `translator_ids`;分享網址的 `a` 仍是名字)、
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
- **帶到另一台裝置(匯出 / 匯入,`storage.js` 檔尾)**:書架區「📤 匯出」「📥 匯入」「🗑 清除所有紀錄」三個按鈕(`render.js` 的
  `shelfToolsHTML`,視窗與詳情共用 `#modal`,`main.js` 的 `_mode = 'tool'`)。
  - 格式 `{ v: 1, shelf: [收藏編號], read: [已讀編號], todo: [待閱讀編號], exportedAt: ISO }`,用 `vendor/lz-string.min.js` 的
    `compressToEncodedURIComponent` 壓成只含 `A-Z a-z 0-9 + - $` 的字串。`todo` 是後加的**可選欄位**(版本仍是 1):
    舊字串沒有這欄照樣能匯入,且不動這台的待閱讀;要再加欄位也比照辦理,不要升版本。
  - 匯出提供「複製字串」「複製匯入連結」(`<網址>?s=<字串>`)與 QR code(`vendor/qrcode.js`,內容是匯入連結;字串超過
    `QR_MAX` = 2000 字就不畫、提示改用複製)。
  - 匯入:貼上字串或連結、或「掃描 QR」(只有 `BarcodeDetector` 可用的瀏覽器才有這顆按鈕)→ `decodeState` 驗證 `v` 與欄位型別
    (不合法丟 Error、顯示訊息、原資料完全不動)→ 預覽「將加入 X 本書架、Y 篇已讀、Z 篇待閱讀」→ 選「合併」(預設,聯集)或「覆蓋」→ 確認才寫入。
    匯入的已讀會自動移出待閱讀(`mergeState` 最後一步);匯入的收藏會標進 `annyeongz_favs_sent`(原裝置已算過公開愛心,不再 +1)。
  - 另一台裝置打開 `?s=<字串>` 會自動跳出匯入預覽(不自動寫入);匯入完成後 `history.replaceState` 移除 `?s=`(`#f=` 保留)。
    解析 `?s=` **不能用 `URLSearchParams`**(會把 `+` 當空白),用 `extractPayload`。
  - 清除所有紀錄:要輸入「清除」才能按;清掉收藏 / 待閱讀 / 已讀 / `favs_sent` / 書架分頁,並像逐篇取消收藏一樣把已計入的公開愛心扣回。

## 複製篩選連結(`src/url.js`)

- 格式:`<origin + pathname>#f=<encodeURIComponent(JSON.stringify(o))>`,`o` 只放有設定的欄位:
  - `s` 標籤三態 `{分面: {標籤: 'on'|'exc'}}`
  - `m` 任一 / 全部 `{分面: 'and'}`
  - `a` 作者 / 譯者專頁名字
  - `q` 搜尋字(原始輸入去頭尾空白)
  - `sort` 排序(預設 `old` 不寫)
- 沒有任何條件時就是純網址。範例:`#f=%7B%22s%22%3A%7B%22CP%E9%85%8D%E5%B0%8D%22%3A%7B%22%E5%AE%89%2F%E5%93%A1%22%3A%22on%22%7D%7D%7D`
- 只在**開站時**讀一次 hash(`applyShareHash`),之後改 hash 不會重新套用;hash 壞掉就當沒有。
- 複製用 `navigator.clipboard.writeText`,不支援時退回 `prompt()`(`main.js` 的 `copyText`)。

## 作品分享頁(`_build/build_pages.py` + `src/url.js`)

- 每篇有獨立網址 `https://yashen0512.github.io/Annyeongz/p/<No>/`(`url.js` 的 `articleShareURL`;詳情彈窗的「🔗 分享」按鈕複製這個)。
  貼到社群會顯示該篇專屬預覽卡:`p/<No>/index.html` 的 `<head>` 有 title「{標題} — {作者} | Annyeongz 平行宇宙」、description
  (收錄篇名,沒有就前三個標籤;原文已刪前面加「(原文已刪)」)、og:*、twitter:card=summary_large_image,og:image 指向同資料夾的 `og.png`。
  `<body>` 列出作品名 / 作者 / 標籤給爬蟲看,`<script>` 用相對路徑導回 `../../?p=<No>`(正式站就是 `/Annyeongz/?p=<No>`)。
- 首頁開站時讀到 `?p=<No>`(`parseArticleParam`)→ `openSharedArticle()` 打開該篇詳情,並 `history.replaceState` 把 p 拿掉(其他參數與 `#f=` 保留);
  `intro.js` 看到 `?p=` 就不播開場動畫。編號不存在就什麼都不做。
- **OG 圖**:Pillow 畫 1200×630,深色底 `#15161b`、左上 🐶❤️🐰 Annyeongz 平行宇宙、中間粗體標題(最多兩行,超過截斷加 …)、
  下方作者(譯文加「譯 譯者」)與前三個標籤小籤(原文已刪多一顆紅籤)、右下 #編號、以編號為種子的星點。字型見 `_build/fonts/`。
- **只重產有變動的**:HTML 帶 `<meta name="az-hash">`、PNG 帶 tEXt `az-hash`(內容欄位 + `PAGE_VERSION` / `OG_VERSION` 的 sha1),
  重跑時逐篇比對;1486 篇首跑約 3 分鐘,之後沒變動約 3 秒。資料裡已經沒有的編號會移除舊資料夾(只動帶 az-hash 的)。
- `sitemap.xml`:首頁 + 所有 `/p/<No>/`,lastmod 用 `edited`。`feed.xml` 依 `ck` 最新收錄 50 篇、`feed-updated.xml` 依 `ek` 最近編輯 50 篇
  (RSS 2.0,每則含標題、作者、標籤 category、分享連結、日期);`lastBuildDate` 用最新一則的日期而不是建置時間,所以沒變動就不會產生 diff。
  `site_template.html` 的 `<head>` 有兩個 `<link rel="alternate" type="application/rss+xml">`。

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
- 改了 `src/`、`styles/` 或 `vendor/` 的檔名,記得同步 `sw.js` 的預先快取清單並把 `CACHE` 版本號 +1。

## 統計星圖(`stats.html`)

- 首頁頁尾「🌌 宇宙誕生於 2023/08/07」旁的「📊 統計星圖」連過來。**靜態頁、不經樣板注入**:`<script src="data.js">` 讀同一份 `window.DATA`,
  所以資料跟首頁一樣在每次同步後更新;`build_site.py` 會把它與 `vendor/` 複製進輸出資料夾,`sync.yml` / `static.yml` 原樣上傳整個倉庫就部署了。
- 圖表用 **Chart.js 4 的 UMD 本機副本**(`vendor/chart.umd.js`,不走 CDN),六塊:總覽數字卡、每月收錄趨勢(從匯入月 2025/01 的下一個月畫起,新收錄 + 累積右軸;匯入批次只進累積起始值,圖下有說明)、
  標籤篇數排行(前 20,可切「全部 / 排除已刪」,只算多選分面、與熱門星系一致)、作者篇數排行(前 20,作者 + 譯者都算、以作者頁 ID 歸戶;
  點長條 → 首頁 `#f={"a":名字}`)、愛心 × 觀測散佈(每點一篇,hover 顯示標題,點了開 `./?p=<編號>`;分享頁 `/p/<編號>/` 上線後改 `stats_page.js` 的 `articleURL`)、
  已刪趨勢(依收錄年份堆疊:仍可閱讀 / 原文已刪)。
- 愛心 / 觀測計數先 GET `REACT_API`(`stats.html` 內的 `window.AZ_CONFIG`,與樣板同一個端點),失敗退回 `_build/reactions_backup.json`;原文已刪不計。
- **圖表顏色全部從 CSS 變數讀**(`--accent`、`--be`、`--he`、`--exc`、`--purp`、`--ink`、`--muted`、`--line`、`--card`),切主題就 destroy 重畫;
  手機(≤560px)每張圖單欄、圖本身保留最小寬度在卡片內橫向捲動。
- 統計計算是純函式(`src/stats.js` 前半,`tests/stats.test.js` 測每月分組、排行、比例、年度、散佈點與圖表設定);`stats_page.js` 才碰 DOM。

## 測試

```bash
npm install                       # 只需一次(vitest 是 devDependency)
npm test                          # vitest run:tests/filter.test.js、sort.test.js、url.test.js、stats.test.js、storage.test.js
pip install -r requirements-dev.txt   # 只需一次(pytest)
python3 -m pytest -q              # tests/py:build_site(dead 判定、作者拆分與 ID、日期、30 篇 fixture 完整建置比對)、fetch_data(No 三種型別、token 來源)、
                                  #          build_pages(描述 / 標題折行 / 字型回退 / sitemap / RSS、30 篇產頁與 hash 跳過重產)
                                  #          checkers(各平台 HTML 樣本)、check_links(連續兩天狀態機、到期、改名判斷、平台被擋短路、重試)、notion_writeback(❌ 加 / 移除、PATCH 格式、曾用名合併)、build_site 曾用名、fetch_data block 位置
```

- `.github/workflows/test.yml` 在 PR 時兩組都自動跑,不需要 Notion token。
- fixture 由 `python3 tests/fixtures/make_fixture.py` 從 `data.js` 反推(30 篇:含空作者、多作者、譯文、站內互連、兩種 dead、收錄篇名);
  `expected.json` 是這 30 篇在 `data.js` 的原樣,測試斷言「從 CSV 重建 == 原本」。資料格式改了就重產 fixture。
- `storage.test.js` 把 `vendor/lz-string.min.js` 當傳統 script 執行後掛到 `globalThis.LZString`(與瀏覽器同一份),並用假的 `localStorage`。
- 純函式模組(filter / sort / url / related / stats)不可 import DOM 或 `window`,這樣才能在 Node 直接測;
  `build_site.py` / `fetch_data.py` / `build_pages.py` / `check_links.py` / `notion_writeback.py` 的 import 不能有副作用(網路、讀 CSV、載字型),主流程放 `main()`;
  `checkers/*.py` 的判斷邏輯放在 `parse()` 純函式,`check()` 才碰網路。
- 改畫面或行為前後,建議用 Playwright 把舊版與新版同時跑一遍比對 DOM 與截圖(這次拆模組就是這樣驗的)。

## 程式慣例

- **繁體中文註解**(台灣用語),檔頭先寫這個模組負責什麼。
- **不用框架、不引入大型相依套件**;前端只有原生 ES module,開發相依只有 Vitest 與 pytest。瀏覽器端沒有 bundler、沒有 transpile。
  需要的第三方小工具以單檔放 `vendor/`(傳統 script 掛全域),`src/` 裡用 `globalThis.X` 取用並處理沒載到的情況。
- **Python 腳本只用標準庫**(`csv`、`json`、`urllib`…,現況如此,維持);唯一例外是 `build_pages.py` 畫 OG 圖用的 Pillow(`requirements.txt`),
  而且只在畫圖的函式裡 import,`--no-images` 或只產頁 / sitemap / RSS 時不需要它。
- 作者一律用 Notion 作者頁 ID 對應(`author_ids` / `people[id]`),顯示名只是顯示;改名同步之後會填 `aliases`。
- 純函式與 DOM 分開:`filter.js`、`sort.js`、`url.js`、`related.js` 不碰 DOM;`render.js` 只產生 DOM,狀態與事件接線都在 `main.js`。
- 詳情彈窗與書卡的 HTML 字串用 inline `onclick` 呼叫 `toggleFav`、`filterByTag`、`navDetail` 等函式,
  這些函式在 `main.js` 結尾用 `Object.assign(window, {...})` 掛到全域;新增這類函式要一起掛上去。
- 本機儲存的 key 只能從 `storage.js` 的 `KEYS` 拿,**key 名稱不可改**(改了讀者的書架就不見了)。
- `index.html` 的文案、emoji、全形標點(「：」「（）」)是刻意的,不要「順手」改成半形。
- 原站的幾個既有行為是刻意保留的,改之前先確認:搜尋 / 排序 / 勾選框觸發重繪時**不會跳回第 1 頁**(只會夾到最後一頁);
  分面標籤三態循環是 包含 → 排除 → 取消;穿越蟲洞略過原文已刪與無連結的文。
- 標籤名稱、分面順序、改名合併規則都在 `_build/facets_def.py`,前端不要寫死標籤清單(`related.js` 的 `REL_FACETS` 與
  `render.js` 的狀態色對照 `STMAP` 是僅有的例外)。
