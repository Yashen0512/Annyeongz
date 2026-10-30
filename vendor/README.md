# vendor/ — 前端第三方單檔

第三方程式庫的本機副本:不走 CDN、不走 npm 執行期相依,直接以傳統 `<script>` 載入(離線 / PWA 也能用)。
建置時由 `build_site.py` 與 `src/`、`styles/` 一起複製到輸出資料夾(`STATIC_DIRS`),`sw.js` 也會預先快取。

| 檔案 | 來源 | 版本 | 授權 | 用途 |
|---|---|---|---|---|
| `chart.umd.js` | npm `chart.js`(dist/chart.umd.js) | 4.6.1 | MIT(`chart.js-LICENSE.md`) | `stats.html` 統計星圖的圖表(`window.Chart`) |
| `lz-string.min.js` | npm `lz-string`(libs/lz-string.min.js) | 1.5.0 | MIT(`LICENSE.lz-string`) | 書架匯出字串壓縮(`window.LZString`,`src/storage.js` 用) |
| `qrcode.js` | npm `qrcode-generator`(dist/qrcode.js) | 2.0.4 | MIT(檔頭) | 匯出 QR code(`window.qrcode`,`src/main.js` 用) |

更新方式:`npm pack <套件>@<版本>` 解開後把對應檔案原樣覆蓋過來,改這張表的版本,並把 `sw.js` 的 `CACHE` 版本號 +1。
檔案內容不要手改。
