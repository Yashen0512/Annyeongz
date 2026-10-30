# -*- coding: utf-8 -*-
"""一鍵更新 ③:讀 build_site.py 產出的 <輸出>/data.json(精簡格式,用 build_site.expand_data 還原),為每篇作品產生
   - <輸出>/p/<No>/index.html  分享頁(社群預覽卡用的 meta,開啟後導回首頁 ?p=<No> 自動打開詳情)
   - <輸出>/p/<No>/og.png      1200×630 的預覽圖(Pillow 畫;字型在 _build/fonts/:Noto Sans TC,諺文回退 Noto Sans KR)
   並輸出 sitemap.xml、feed.xml(最新收錄 50 篇)、feed-updated.xml(最近編輯 50 篇)、robots.txt。
   每頁 / 每圖都帶內容 hash(HTML 的 <meta name="az-hash">、PNG 的 tEXt 區塊),重跑時只重產有變動的。
   除了 Pillow 之外只用標準庫;所有步驟都是函式,pytest 可以直接呼叫 build_pages()。
   輸出資料夾與 build_site.py 相同:環境變數 SITE_OUT,沒設就是 ../site。"""
import hashlib, html, io, json, os, random, re, shutil, sys
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from xml.sax.saxutils import escape

SITE_URL = os.environ.get('SITE_URL', 'https://yashen0512.github.io/Annyeongz/')   # 站台正式網址(結尾有 /)
SITE_NAME = 'Annyeongz 平行宇宙'
BRAND_TEXT = 'Annyeongz 平行宇宙'          # OG 圖左上角文字(前面接 og_brand.png 的 🐶❤️🐰)
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, 'fonts')
BRAND_IMG = os.path.join(HERE, 'og_brand.png')   # 🐶❤️🐰 預先畫好的小圖(Actions 不用裝 emoji 字型)
PAGE_VERSION = 1    # 改了分享頁樣板就 +1 → 全部重產
OG_VERSION = 1      # 改了 OG 圖版面就 +1 → 全部重畫
FEED_N = 50
TZ8 = timezone(timedelta(hours=8))
HASH_RE = re.compile(r'<meta name="az-hash" content="([0-9a-f]{40})">')
NO_RE = re.compile(r'^[0-9A-Za-z_-]+$')   # 能當資料夾名的編號

# OG 圖配色(對應 styles/base.css 深色主題)
C_BG, C_INK, C_MUTED, C_ACCENT = '#15161b', '#ece9e3', '#9b948a', '#e58aa0'
C_CHIP, C_CHIPTXT, C_DEAD, C_DEADBG, C_NO = '#2c2d37', '#c9c3b7', '#e08363', '#3a2622', '#55505b'

# ---------- 讀資料 ----------

def load_data(out_dir):
    """讀 <輸出>/data.json(build_site.compact_data 的精簡格式)→ 完整 DATA dict(expand_data 還原;舊的完整格式也接受)。"""
    with io.open(os.path.join(out_dir, 'data.json'), encoding='utf-8') as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict) or 'articles' not in raw:
        raise ValueError('data.json 不是 build_site.py 產出的格式')
    import build_site
    return build_site.expand_data(raw)

# ---------- 純函式:文字 ----------

def multi_tags(a, facets):
    """多選分面的標籤,依分面順序攤平(與 render.js 的 multiTags 相同)。"""
    out = []
    for f in facets:
        if f['type'] == 'multi':
            for v in a['tags'].get(f['key']) or []:
                if v not in out:
                    out.append(v)
    return out

def single_tags(a, facets):
    out = []
    for f in facets:
        if f['type'] == 'single':
            out += [v for v in (a['tags'].get(f['key']) or [])[:1] if v]
    return out

def top_tags(a, facets, n=3):
    """前 n 個標籤:先多選分面(CP 配對、氛圍…),不夠再用單選(類型、篇幅、結局、狀態)補。"""
    return (multi_tags(a, facets) + single_tags(a, facets))[:n]

def people_line(a):
    """『作者』或『作者 · 譯 譯者』;沒作者回空字串。"""
    s = a.get('author') or ''
    if a.get('translator'):
        s = (s + ' · ' if s else '') + '譯 ' + a['translator']
    return s

def page_title(a):
    t = a.get('name') or '(無標題)'
    p = people_line(a)
    return (t + ' — ' + p if p else t) + ' | ' + SITE_NAME

def truncate(s, n):
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'

def description(a, facets, limit=160):
    """社群卡片的描述:收錄篇名(多行以「、」接起來),沒有就前三個標籤;原文已刪的前面加「(原文已刪)」。"""
    lines = [l.strip() for l in (a.get('alias') or '').split('\n') if l.strip()]
    if lines:
        body = '、'.join(lines)
    else:
        tags = top_tags(a, facets)
        body = ' · '.join(tags) if tags else (SITE_NAME + ' 收錄作品 #' + a['no'])
    if a.get('dead'):
        body = '(原文已刪)' + body
    return truncate(body, limit)

def share_url(no):
    return SITE_URL + 'p/' + str(no) + '/'

def content_hash(*parts):
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()

# ---------- 分享頁 ----------

def page_hash(a, facets):
    return content_hash(PAGE_VERSION, SITE_URL, a['no'], a.get('name'), a.get('author'), a.get('translator'),
                        a.get('alias'), a.get('tags'), bool(a.get('dead')), a.get('edited'))

def page_html(a, facets):
    """分享頁:head 給爬蟲看的 meta,body 列出作品名 / 作者 / 標籤,script 導回首頁並打開該篇詳情。
    導向用相對路徑 ../../?p=<No>,在正式站就是 /Annyeongz/?p=<No>,本機 site/ 用 http 伺服器開也通。"""
    no = a['no']
    e = html.escape
    title, desc, url = page_title(a), description(a, facets), share_url(no)
    og_img = url + 'og.png'
    tags = multi_tags(a, facets) + single_tags(a, facets)
    home = '../../?p=' + no
    alias = [l.strip() for l in (a.get('alias') or '').split('\n') if l.strip()]
    body = ['<h1>%s <small>#%s</small></h1>' % (e(a.get('name') or '(無標題)'), e(no))]
    if a.get('dead'):
        body.append('<p class="dead">原文已刪</p>')
    if a.get('author'):
        body.append('<p>作者:%s</p>' % e(a['author']))
    if a.get('translator'):
        body.append('<p>譯者:%s</p>' % e(a['translator']))
    if tags:
        body.append('<p>標籤:%s</p>' % ' · '.join(e(t) for t in tags))
    if alias:
        body.append('<p>收錄篇名:%s</p>' % '、'.join(e(l) for l in alias))
    body.append('<p><a href="%s">在 %s 開啟這篇的詳情 →</a></p>' % (e(home), e(SITE_NAME)))
    return ('<!DOCTYPE html>\n<html lang="zh-Hant">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<meta name="az-hash" content="%s">\n' % page_hash(a, facets)
            + '<title>%s</title>\n' % e(title)
            + '<meta name="description" content="%s">\n' % e(desc)
            + '<link rel="canonical" href="%s">\n' % e(url)
            + '<meta property="og:type" content="article">\n'
            + '<meta property="og:site_name" content="%s">\n' % e(SITE_NAME)
            + '<meta property="og:locale" content="zh_TW">\n'
            + '<meta property="og:title" content="%s">\n' % e(title)
            + '<meta property="og:description" content="%s">\n' % e(desc)
            + '<meta property="og:image" content="%s">\n' % e(og_img)
            + '<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n'
            + '<meta property="og:url" content="%s">\n' % e(url)
            + '<meta name="twitter:card" content="summary_large_image">\n'
            + '<meta name="twitter:title" content="%s">\n' % e(title)
            + '<meta name="twitter:description" content="%s">\n' % e(desc)
            + '<meta name="twitter:image" content="%s">\n' % e(og_img)
            + '<meta name="theme-color" content="%s">\n' % C_BG
            + '<style>body{margin:0;padding:32px 20px;font-family:"Microsoft JhengHei","PingFang TC",system-ui,sans-serif;'
              'background:%s;color:%s;line-height:1.6}h1{font-size:22px}small{color:%s;font-weight:400}'
              'a{color:%s}.dead{color:%s}</style>\n' % (C_BG, C_INK, C_MUTED, C_ACCENT, C_DEAD)
            + '<script>location.replace(%s);</script>\n' % json.dumps(home, ensure_ascii=False)
            + '</head>\n<body>\n<main>\n' + '\n'.join(body) + '\n</main>\n</body>\n</html>\n')

def read_page_hash(path):
    try:
        m = HASH_RE.search(io.open(path, encoding='utf-8').read(4000))
        return m.group(1) if m else None
    except OSError:
        return None

# ---------- OG 圖 ----------

def og_hash(a, facets):
    return content_hash(OG_VERSION, a['no'], a.get('name'), people_line(a), top_tags(a, facets), bool(a.get('dead')))

def read_png_hash(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return (im.text or {}).get('az-hash')
    except Exception:
        return None

_CJK = re.compile(r'[ᄀ-ᇿ⺀-鿿ꥠ-꥿가-퟿豈-﫿＀-￯\U00020000-\U0003ffff]')

def _units(text):
    """斷行單位:中日韓每個字可斷、拉丁字母以空白分字;空白本身也是單位(行首會被去掉)。"""
    units, buf = [], ''
    for ch in text:
        if ch.isspace():
            if buf: units.append(buf); buf = ''
            units.append(' ')
        elif _CJK.match(ch):
            if buf: units.append(buf); buf = ''
            units.append(ch)
        else:
            buf += ch
    if buf: units.append(buf)
    return units

def wrap_text(text, width_of, max_w, max_lines=2):
    """把 text 折成最多 max_lines 行(每行寬度 ≤ max_w,width_of(str) 回傳像素寬);
    超過的最後一行截斷加「…」。回傳 (行清單, 有沒有截斷)。"""
    lines, cur = [], ''
    for u in _units(text):
        cand = cur + u
        if cur and width_of(cand) > max_w:
            lines.append(cur.rstrip())
            cur = '' if u == ' ' else u
        else:
            cur = cand if (cur or u != ' ') else ''
    if cur.strip():
        lines.append(cur.rstrip())
    if len(lines) <= max_lines:
        return lines, False
    last = ''.join(lines[max_lines - 1:]) if max_lines > 0 else ''
    last = last.strip()
    while last and width_of(last + '…') > max_w:
        last = last[:-1].rstrip()
    return lines[:max_lines - 1] + [last + '…'], True

class Fonts:
    """字型與回退:中文 / 拉丁字母用 Noto Sans TC,TC 沒有的字(諺文等)用 Noto Sans KR;
    兩者都沒有的簡體字用 stmap.txt 轉成繁體字再畫,數學粗體字母等以 NFKC 折成一般字母,emoji 之類沒字的直接略過。
    有沒有字是用「畫出來跟 .notdef(豆腐)一不一樣」判斷,不用解析 cmap(只用標準庫 + Pillow)。"""
    FAMILIES = ('TC', 'KR')
    PROBE = 40

    def __init__(self, font_dir=FONT_DIR, stmap_path=os.path.join(HERE, 'stmap.txt')):
        self.paths = {(fam, w): os.path.join(font_dir, 'NotoSans%s-%s.woff' % (fam, 'Bold' if w == 'b' else 'Regular'))
                      for fam in self.FAMILIES for w in ('r', 'b')}
        self._c, self._cov, self._clean = {}, {}, {}
        self._notdef = {}
        self.s2t = {}
        try:
            t, s_ = (io.open(stmap_path, encoding='utf-8').read().splitlines() + ['', ''])[:2]
            self.s2t = {sc: tc for tc, sc in zip(t, s_) if sc != tc}
        except OSError:
            pass

    def get(self, fam, weight, size):
        from PIL import ImageFont
        k = (fam, weight, size)
        if k not in self._c:
            self._c[k] = ImageFont.truetype(self.paths[(fam, weight)], size)
        return self._c[k]

    def _mask(self, fam, ch):
        from PIL import Image, ImageDraw
        im = Image.new('L', (self.PROBE * 2, self.PROBE * 2))
        ImageDraw.Draw(im).text((4, self.PROBE // 2), ch, font=self.get(fam, 'r', self.PROBE), fill=255)
        return im.tobytes()

    def covers(self, fam, ch):
        k = (fam, ch)
        if k not in self._cov:
            if fam not in self._notdef:
                self._notdef[fam] = self._mask(fam, '\U0010fffd')
            self._cov[k] = ch.isspace() or self._mask(fam, ch) != self._notdef[fam]
        return self._cov[k]

    def family_of(self, ch):
        for fam in self.FAMILIES:
            if self.covers(fam, ch):
                return fam
        return None

    def clean(self, text):
        """把畫不出來的字換成畫得出來的(簡→繁、NFKC),還是沒有的就拿掉。"""
        out = []
        for ch in text:
            if ch not in self._clean:
                rep = ''
                if self.family_of(ch):
                    rep = ch
                elif ch in self.s2t and self.family_of(self.s2t[ch]):
                    rep = self.s2t[ch]
                else:
                    import unicodedata
                    alt = unicodedata.normalize('NFKC', ch)
                    if alt != ch and all(self.family_of(c) for c in alt):
                        rep = alt
                self._clean[ch] = rep
            out.append(self._clean[ch])
        return ''.join(out)

    def runs(self, text, weight, size):
        """已 clean 的字串 → [(片段, 字型)],相鄰同字型的字併成一段。"""
        out = []
        for ch in text:
            fam = self.family_of(ch) or 'TC'
            if out and out[-1][0] == fam:
                out[-1][1] += ch
            else:
                out.append([fam, ch])
        return [(seg, self.get(fam, weight, size)) for fam, seg in out]

    def length(self, d, text, weight, size):
        return sum(d.textlength(seg, font=f) for seg, f in self.runs(text, weight, size))

    def draw(self, d, xy, text, weight, size, fill, anchor='lm'):
        """畫一行混合字型的字。anchor 只支援 l?/r?(左或右對齊)+ m/s(中線或基線)。"""
        x, y = xy
        if anchor[0] == 'r':
            x -= self.length(d, text, weight, size)
        for seg, f in self.runs(text, weight, size):
            d.text((x, y), seg, font=f, fill=fill, anchor='l' + anchor[1])
            x += d.textlength(seg, font=f)

_BRAND_CACHE = {}

def brand_image(height):
    from PIL import Image
    if height not in _BRAND_CACHE:
        im = Image.open(BRAND_IMG).convert('RGBA')
        w = round(im.width * height / im.height)
        _BRAND_CACHE[height] = im.resize((w, height), Image.LANCZOS)
    return _BRAND_CACHE[height]

def og_image(a, facets, fonts):
    """畫一張 1200×630 的預覽圖:深色底、左上品牌、中間大字標題(最多兩行)、下方作者與前三個標籤、右下 #編號。"""
    from PIL import Image, ImageDraw
    W, H, M = 1200, 630, 70
    im = Image.new('RGB', (W, H), C_BG)
    d = ImageDraw.Draw(im, 'RGBA')
    # 星空(以編號當種子,每篇固定)
    rng = random.Random('az' + a['no'])
    for _ in range(70):
        x, y, r = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0.6, 2.2)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rng.randint(25, 110)))
    # 左上品牌
    b = brand_image(44)
    im.paste(b, (M, 54), b)
    fonts.draw(d, (M + b.width + 16, 54 + 22), BRAND_TEXT, 'r', 34, C_ACCENT)
    # 標題:先試 68,折不進兩行就 56,再不行截斷
    title = fonts.clean(a.get('name') or '') or '(無標題)'
    for size in (68, 56):
        lines, cut = wrap_text(title, lambda s, _sz=size: fonts.length(d, s, 'b', _sz), W - 2 * M - 26, 2)
        if not cut:
            break
    lh = round(size * 1.3)
    block = lh * len(lines)
    ty = 300 - block // 2 - 10
    d.rectangle((M, ty + 6, M + 6, ty + block - 6), fill=C_DEAD if a.get('dead') else C_ACCENT)
    for i, ln in enumerate(lines):
        fonts.draw(d, (M + 26, ty + i * lh + lh // 2), ln, 'b', size, C_INK)
    # 作者 / 譯者
    y = ty + block + 28
    who = fonts.clean(people_line(a))
    if who:
        fonts.draw(d, (M + 26, y), truncate(who, 40), 'r', 32, C_MUTED)
        y += 56
    # 標籤小籤(原文已刪排最前面,紅色)
    chips = ([('原文已刪', True)] if a.get('dead') else []) + [(fonts.clean(t).strip(), False) for t in top_tags(a, facets)]
    x = M + 26
    for txt, red in chips:
        if not txt:
            continue
        w = fonts.length(d, txt, 'r', 26) + 36
        if x + w > W - M - 160:
            break
        d.rounded_rectangle((x, y - 22, x + w, y + 22), radius=22, fill=C_DEADBG if red else C_CHIP)
        fonts.draw(d, (x + 18, y), txt, 'r', 26, C_DEAD if red else C_CHIPTXT)
        x += w + 12
    # 右下編號、左下網址
    fonts.draw(d, (W - M, H - M + 10), '#' + a['no'], 'b', 44, C_NO, anchor='rs')
    fonts.draw(d, (M, H - M + 10), SITE_URL.replace('https://', '').rstrip('/'), 'r', 22, C_NO, anchor='ls')
    return im

def save_png(im, path, h):
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
    meta = PngInfo(); meta.add_text('az-hash', h)
    im.convert('P', palette=Image.ADAPTIVE, colors=256).save(path, optimize=True, pnginfo=meta)

# ---------- sitemap / RSS ----------

def iso_date(disp):
    """'2026/6/26' → '2026-06-26';空字串回 None。"""
    m = re.match(r'(\d{4})/(\d{1,2})/(\d{1,2})', disp or '')
    return '%s-%02d-%02d' % (m.group(1), int(m.group(2)), int(m.group(3))) if m else None

def key_to_dt(k):
    """YYYYMMDDHHMM(台北)→ datetime;0 回 None。"""
    try:
        s = '%012d' % int(k)
        return datetime(int(s[0:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]), int(s[10:12]), tzinfo=TZ8)
    except (ValueError, TypeError):
        return None

def sitemap_xml(articles):
    home_mod = max((iso_date(a.get('edited')) or '' for a in articles), default='') or None
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
           '  <url><loc>%s</loc>%s</url>' % (escape(SITE_URL), '<lastmod>%s</lastmod>' % home_mod if home_mod else '')]
    for a in articles:
        mod = iso_date(a.get('edited')) or iso_date(a.get('created'))
        out.append('  <url><loc>%s</loc>%s</url>' % (escape(share_url(a['no'])), '<lastmod>%s</lastmod>' % mod if mod else ''))
    out.append('</urlset>\n')
    return '\n'.join(out)

def rss_xml(articles, facets, *, title, desc, filename, date_key):
    """RSS 2.0。date_key = 'ck'(收錄)或 'ek'(編輯);lastBuildDate 用最新一則的日期(不用建置時間,輸出才不會每次都變)。"""
    items, newest = [], None
    for a in articles:
        dt = key_to_dt(a.get(date_key))
        if dt and (newest is None or dt > newest):
            newest = dt
        url = share_url(a['no'])
        guid = url if date_key == 'ck' else url + '?e=' + str(a.get('ek') or '')
        parts = []
        if a.get('author'): parts.append('作者:' + a['author'])
        if a.get('translator'): parts.append('譯者:' + a['translator'])
        tags = multi_tags(a, facets) + single_tags(a, facets)
        if tags: parts.append('標籤:' + ' · '.join(tags))
        if a.get('alias'): parts.append('收錄篇名:' + '、'.join(l.strip() for l in a['alias'].split('\n') if l.strip()))
        if a.get('dead'): parts.insert(0, '(原文已刪)')
        if date_key == 'ek' and a.get('edited'): parts.append('最近編輯:' + a['edited'])
        items.append('    <item>\n      <title>%s</title>\n      <link>%s</link>\n      <guid isPermaLink="false">%s</guid>\n'
                     % (escape(page_title(a).rsplit(' | ', 1)[0]), escape(url), escape(guid))
                     + ('      <pubDate>%s</pubDate>\n' % format_datetime(dt) if dt else '')
                     + ''.join('      <category>%s</category>\n' % escape(t) for t in tags)
                     + ('      <dc:creator>%s</dc:creator>\n' % escape(a['author']) if a.get('author') else '')
                     + '      <description>%s</description>\n    </item>' % escape('|'.join(parts)))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            '  <channel>\n    <title>%s</title>\n    <link>%s</link>\n    <description>%s</description>\n'
            '    <language>zh-Hant</language>\n    <atom:link href="%s" rel="self" type="application/rss+xml"/>\n'
            % (escape(title), escape(SITE_URL), escape(desc), escape(SITE_URL + filename))
            + ('    <lastBuildDate>%s</lastBuildDate>\n' % format_datetime(newest) if newest else '')
            + '\n'.join(items) + '\n  </channel>\n</rss>\n')

def feed_latest(articles, facets):
    arts = sorted([a for a in articles if a.get('ck')], key=lambda a: (-a['ck'], -(int(a['no']) if a['no'].isdigit() else 0)))[:FEED_N]
    return rss_xml(arts, facets, title=SITE_NAME + ' ✨ 新星誕生', desc='安員同人文索引站:最新收錄的 %d 篇' % FEED_N,
                   filename='feed.xml', date_key='ck')

def feed_updated(articles, facets):
    arts = sorted([a for a in articles if a.get('ek')], key=lambda a: (-a['ek'], -(int(a['no']) if a['no'].isdigit() else 0)))[:FEED_N]
    return rss_xml(arts, facets, title=SITE_NAME + ' 🛰️ 軌道更新', desc='安員同人文索引站:最近編輯的 %d 篇' % FEED_N,
                   filename='feed-updated.xml', date_key='ek')

def robots_txt():
    return 'User-agent: *\nAllow: /\nSitemap: %ssitemap.xml\n' % SITE_URL

# ---------- 主流程 ----------

def write_if_changed(path, text):
    try:
        if io.open(path, encoding='utf-8').read() == text:
            return False
    except OSError:
        pass
    io.open(path, 'w', encoding='utf-8', newline='\n').write(text)
    return True

def build_pages(DATA, out_dir, images=True, fonts=None, log=None):
    """產生 p/<No>/{index.html, og.png}、sitemap.xml、feed.xml、feed-updated.xml、robots.txt。
    回傳統計 {'pages', 'images', 'skipped', 'removed', 'feeds', 'bad_no'}。"""
    log = log or (lambda *a: None)
    facets, articles = DATA['facets'], DATA['articles']
    pdir = os.path.join(out_dir, 'p')
    os.makedirs(pdir, exist_ok=True)
    st = {'pages': 0, 'images': 0, 'skipped': 0, 'removed': 0, 'feeds': [], 'bad_no': []}
    fonts = fonts or (Fonts() if images else None)
    keep = set()
    for a in articles:
        no = a['no']
        if not NO_RE.match(no or ''):
            st['bad_no'].append(no); continue
        keep.add(no)
        adir = os.path.join(pdir, no)
        os.makedirs(adir, exist_ok=True)
        hp = page_hash(a, facets)
        ppath = os.path.join(adir, 'index.html')
        if read_page_hash(ppath) != hp:
            io.open(ppath, 'w', encoding='utf-8', newline='\n').write(page_html(a, facets))
            st['pages'] += 1
        else:
            st['skipped'] += 1
        if images:
            ho = og_hash(a, facets)
            ipath = os.path.join(adir, 'og.png')
            if read_png_hash(ipath) != ho:
                save_png(og_image(a, facets, fonts), ipath, ho)
                st['images'] += 1
    # 資料裡已經沒有的編號 → 移除舊頁(只動我們自己產的:資料夾裡的 index.html 帶 az-hash)
    for name in os.listdir(pdir):
        d = os.path.join(pdir, name)
        if name not in keep and os.path.isdir(d) and read_page_hash(os.path.join(d, 'index.html')):
            shutil.rmtree(d); st['removed'] += 1
    for fn, text in (('sitemap.xml', sitemap_xml(articles)), ('feed.xml', feed_latest(articles, facets)),
                     ('feed-updated.xml', feed_updated(articles, facets)), ('robots.txt', robots_txt())):
        if write_if_changed(os.path.join(out_dir, fn), text):
            st['feeds'].append(fn)
    log(st)
    return st

def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    OUT = os.environ.get('SITE_OUT', '../site')
    images = '--no-images' not in argv
    DATA = load_data(OUT)
    st = build_pages(DATA, OUT, images=images)
    print('pages built: %d 篇 → %s/p/(重產 %d 頁、%d 圖,未變動 %d 頁,移除 %d 個舊資料夾)'
          % (len(DATA['articles']), OUT, st['pages'], st['images'], st['skipped'], st['removed']))
    print('sitemap / feed:', ('更新 ' + '、'.join(st['feeds'])) if st['feeds'] else '沒有變動')
    if st['bad_no']:
        print('⚠️ 編號不能當資料夾名稱,略過 %d 篇:%s' % (len(st['bad_no']), ', '.join(repr(x) for x in st['bad_no'])))


if __name__ == '__main__':
    main()
