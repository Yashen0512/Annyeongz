# vendor/

第三方程式庫的本機副本(不走 CDN,離線 / PWA 也能用)。

| 檔案 | 版本 | 來源 | 用途 |
|---|---|---|---|
| `chart.umd.js` | Chart.js 4.6.1(MIT,見 `chart.js-LICENSE.md`) | npm `chart.js` 套件的 `dist/chart.umd.js` | `stats.html` 統計星圖的圖表 |

升級方式:`npm pack chart.js@4`,解開後把 `package/dist/chart.umd.js` 覆蓋過來,並更新上表版本與 `sw.js` 的 `CACHE` 版號。
