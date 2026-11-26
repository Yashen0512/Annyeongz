#!/usr/bin/env bash
# Cloudflare Pages 的建置指令:只把「網站需要的檔」複製到 dist/ 發佈(白名單)。
#
# 為什麼要白名單:倉庫要改成私人,但 Cloudflare 若直接發佈整個倉庫,CLAUDE.md、_build/ 的腳本、
# article_links.json、link_status.json、tests/、docs/ 都會從網址打得開,等於私人倉庫的內容從網站漏出去。
#
# Cloudflare 後台設定:Build command = bash _build/cf_build.sh;Build output directory = dist
# 本機測試:bash cf_build.sh <倉庫根目錄> [輸出資料夾](不給就是本檔上一層與 <倉庫根>/dist)
#
# 新增網站要用的根目錄檔或資料夾 → 加進下面的 FILES / DIRS;前端改抓 _build/ 裡的檔 → 加進 BUILD_FILES。
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
OUT="${2:-$ROOT/dist}"

FILES=(index.html data.json sw.js manifest.webmanifest stats.html 404.html
       banner.png banner-mobile.png sitemap.xml feed.xml feed-updated.xml robots.txt)
DIRS=(p src styles vendor assets)
BUILD_FILES=(reactions_backup.json)     # stats.html 在 Worker 連不上時的退路(src/stats_page.js)
REQUIRED=(index.html data.json sw.js)  # 少了任何一個就讓建置失敗,Cloudflare 會保留上一版,不會發佈壞掉的站

for f in "${REQUIRED[@]}"; do
  if [ ! -f "$ROOT/$f" ]; then echo "cf_build: 缺少必要檔案 $f,中止(線上維持上一版)" >&2; exit 1; fi
done

rm -rf "$OUT"
mkdir -p "$OUT/_build"

n=0
for f in "${FILES[@]}"; do
  if [ -f "$ROOT/$f" ]; then cp "$ROOT/$f" "$OUT/"; n=$((n + 1)); else echo "cf_build: 略過(不存在)$f"; fi
done
for d in "${DIRS[@]}"; do
  if [ -d "$ROOT/$d" ]; then cp -R "$ROOT/$d" "$OUT/"; n=$((n + 1)); else echo "cf_build: 略過(不存在)$d/"; fi
done
for f in "${BUILD_FILES[@]}"; do
  if [ -f "$ROOT/_build/$f" ]; then cp "$ROOT/_build/$f" "$OUT/_build/"; n=$((n + 1)); fi
done

# 資料夾裡不該出現的雜檔(本機殘留)一律清掉
find "$OUT" \( -name '__pycache__' -o -name '.DS_Store' -o -name 'Thumbs.db' -o -name '*.py' -o -name '*.md' \) -prune -exec rm -rf {} +

total=$(find "$OUT" -type f | wc -l | tr -d ' ')
echo "cf_build: 完成,複製 $n 項、共 $total 個檔 → $OUT"
