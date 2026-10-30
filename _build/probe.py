# -*- coding: utf-8 -*-
"""可行性測試:對四個原文平台(Postype / Lofter / AO3 / Asianfanfics)各抓三個連結
   (正常作品、已知已刪、明顯不存在),印出 HTTP 狀態碼、最終網址、HTML 前 2000 字,
   用來逐平台找「已刪除」的可靠判斷依據。只用標準庫;帶一般瀏覽器 User-Agent。
   用法:python probe.py [平台名…]   (不帶參數 = 四個平台都跑;可加 --full 印整頁)

   2026-10-30 從雲端(海外 IP)實測結果 → 規則寫進 checkers/{platform}.py 檔頭:
   - Postype:正常 200 + <head> ld+json BlogPosting(author.name = 作者暱稱);已刪與不存在都 404 → 可靠
   - Lofter:正常 / 已刪 / 不存在全部 302 → https://www.lofter.com/front/login(登入牆;/rss 也回空)→ 略過(login_required)
   - AO3:全部 418「Request temporarily denied」Cloudflare 挑戰頁 → 略過(unknown / blocked)
   - Asianfanfics:全部 403「Just a moment…」Cloudflare 受管挑戰頁 → 略過(unknown / blocked)
   被擋的平台不做繞過;站長在看得到該平台的網路環境重跑 probe.py 即可補驗。"""
import sys, urllib.request, urllib.error, urllib.parse, gzip, io, ssl, http.cookiejar

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
HEADERS = {'User-Agent': UA,
           'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
           'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8,ko;q=0.7',
           'Accept-Encoding': 'gzip'}

# 平台 → [(說明, 網址)];已刪的取自 data.js 裡 dead=true 且 links 第三格為 1 的篇目
SAMPLES = {
    'postype': [('正常', 'https://www.postype.com/@ynseasonrps/post/17540326'),
                ('已刪', 'https://www.postype.com/@rps-rrr/post/5273805'),
                ('不存在', 'https://www.postype.com/@ynseasonrps/post/99999999999')],
    'lofter': [('正常', 'https://liaoshann.lofter.com/post/75a5b5cf_34e873064'),
               ('已刪', 'https://null837932.lofter.com/post/3150adbe_34d4dc338'),
               ('不存在', 'https://liaoshann.lofter.com/post/75a5b5cf_ffffffffff')],
    'ao3': [('正常', 'https://archiveofourown.org/works/79669351'),
            ('已刪(data.js 無 AO3 已刪樣本,改用舊編號)', 'https://archiveofourown.org/works/1'),
            ('不存在', 'https://archiveofourown.org/works/999999999999')],
    'aff': [('正常', 'https://www.asianfanfics.com/story/view/1596369/n-a'),
            ('已刪', 'https://www.asianfanfics.com/story/view/1700779/kiss-me-more'),
            ('不存在', 'https://www.asianfanfics.com/story/view/9999999999/x')],
}

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """記錄每一跳的 Location,但仍交給 urllib 跟隨。"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        print('   ↪ %d → %s' % (code, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def fetch(url):
    """回傳 (狀態碼, 最終網址, 內文字串)。4xx/5xx 也讀內文。"""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(_NoRedirect(), urllib.request.HTTPCookieProcessor(cj),
                                         urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        resp = opener.open(req, timeout=30)
        code, final, raw, hdr = resp.status, resp.geturl(), resp.read(), resp.headers
    except urllib.error.HTTPError as e:
        code, final, raw, hdr = e.code, e.geturl() or url, e.read(), e.headers
    if (hdr.get('Content-Encoding') or '').lower() == 'gzip':
        try: raw = gzip.decompress(raw)
        except Exception: pass
    return code, final, raw.decode('utf-8', 'replace')

def main(argv):
    full = '--full' in argv
    plats = [a for a in argv if not a.startswith('--')] or list(SAMPLES)
    for p in plats:
        print('\n' + '=' * 30, p.upper(), '=' * 30)
        for label, url in SAMPLES[p]:
            print('\n--- [%s] %s' % (label, url))
            try:
                code, final, html = fetch(url)
            except Exception as e:
                print('   !! 例外:', repr(e)); continue
            print('   狀態碼:', code)
            print('   最終網址:', final)
            print('   長度:', len(html))
            body = html if full else html[:2000]
            print('   ---- HTML ----')
            print(body)
    print('\n(逐平台判斷規則整理在 checkers/*.py 檔頭)')

if __name__ == '__main__':
    main(sys.argv[1:])
