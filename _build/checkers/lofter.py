# -*- coding: utf-8 -*-
"""Lofter(xxx.lofter.com)— ⚠️ 2026-10-30 probe.py 實測:雲端 / 海外 IP 不論正常、已刪、不存在,
   全部 302 → https://www.lofter.com/front/login(登入牆,連 /rss 也回空),所以在 GitHub Actions 上
   這個平台等於「略過」:一律回 login_required(blocked),不會把任何 Lofter 連結標成已刪。
   以下規則依已知行為寫成、尚未實測,站長在能看到 Lofter 的網路環境執行時才會用到:
   - 404 → deleted
   - 原網址是 /post/…,最終網址被導回該部落格首頁(路徑 /)或 www.lofter.com 首頁 → deleted(刪文常見導向)
   - 200 且內文含「页面不存在」「该页面不存在」「博客不存在」「内容已删除」「页面走丢了」等 → deleted(真的 404 頁標題是「404 Not Found」,2026-11-04 瀏覽器實測)
   - 最終網址是 www.lofter.com/front/login 或頁面是登入表單 → login_required
   - 其餘 200 → ok;author_name 見 blog_name()
   - **合集分享頁**(www.lofter.com/front/blog/collection/share?collectionId=…,is_collection)規則跟文章頁不同:
     這是 www.lofter.com 上的 JS 單頁,2026-11-05 站長本機實測 6 筆合集有 2 筆回 HTTP 404、但合集本身還在
     → **狀態碼 404 不算已刪**(unknown,reason collection_404);只有頁面明講「合集不存在 / 已被删除」(COLLECTION_GONE)才算 deleted。
     合集頁的 <title> 是合集名稱、不是作者,author_name 一律 None(不拿來判斷改名)。

   author_name(blog_name)— 2026-11-05 實測誤判:Lofter 文章頁 <title> 是「文章標題-博客名」(連字號**沒有空白**),
   舊版先找「 - 」(有空白),文章標題本身是「某文 - 上」時就切成「上-一只大鹅」,作者被當成改名。現在依序取:
     ① 頁面 header 裡連回部落格首頁(//xxx.lofter.com/)的連結文字,且 <title> 以「-該名字」結尾(兩個來源互相印證)→ source header_title
     ② 只有 header 連結文字 → header
     ③ <title> 最後一個「-」之後那段(不再優先切「 - 」)→ title
     ④ og:site_name → og
   都沒有 → None。瀏覽器巡檢(browser_checker)在 ③④ 時會再看部落格首頁取名字(blog_home),見該檔。"""
import re
from . import _http as H

GONE_TEXT = ('该页面不存在', '頁面不存在', '页面不存在', '博客不存在', '内容已删除', '该内容已被删除', '抱歉，你访问的页面',
             '页面走丢了', '页面已被移除', '链接可能已损毁')     # 後三個:2026-11-04 瀏覽器實測的 404 頁「哎呀，页面走丢了...」「你查找的链接可能已损毁，或页面已被移除」
LOGIN_PATH = '/front/login'

COLLECTION_GONE = ('合集不存在', '该合集不存在', '該合集不存在', '合集已被删除', '合集已删除', '该合集已被删除',
                   '合集已被刪除', '合集已刪除', '合集已失效')
# header 連回首頁的連結文字若是這些,是導覽列而不是博客名
NAV_WORDS = {'首页', '首頁', '主页', '主頁', 'home', 'index', '归档', '歸檔', 'archive', 'archives', '关于', '關於', 'about',
             'lofter', '登录', '登錄', '注册', '註冊', '私信', '提问', '提問', '留言', '标签', 'tags', 'tag', 'rss', '订阅', '訂閱',
             '返回首页', '返回首頁', '回到首页', '回到首頁', 'back', '上一篇', '下一篇', 'prev', 'next', '更多', 'more'}
DASHES = '-－—–'

def is_collection(url):
    """合集分享頁(www.lofter.com/front/blog/collection/share?collectionId=…)或其他 www.lofter.com 上的合集網址。"""
    h, p = H.host_of(url), H.path_of(url)
    return h in ('www.lofter.com', 'lofter.com') and ('/collection' in p or 'collectionId=' in (url or ''))

def _strip_tags(s):
    return re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()

def header_names(html, host):
    """頁面上連回部落格首頁的 <a> 的文字(依出現順序、去重;導覽字、空白、過長的略過)。host 是 xxx.lofter.com。"""
    if not host or host in ('www.lofter.com', 'lofter.com'):
        return []
    href = r'(?:(?:https?:)?//%s)?/?(?:index\.html?)?' % re.escape(host)
    pat = r'<a\b[^>]*\bhref\s*=\s*["\'](%s)["\'][^>]*>(.*?)</a>' % href
    out = []
    for m in re.finditer(pat, html or '', re.S | re.I):
        if not m.group(1):          # href="" 不算
            continue
        t = _strip_tags(m.group(2))
        if not t or len(t) > 40 or t.casefold() in NAV_WORDS or t in out:
            continue
        out.append(t)
    return out

def title_suffix(title):
    """<title>「文章標題-博客名」→ 最後一個連字號之後那段;沒有連字號回 ''。"""
    t = (title or '').strip()
    i = max(t.rfind(d) for d in DASHES)
    return t[i + 1:].strip() if i >= 0 else ''

def blog_name(html, host=''):
    """→ (博客名, 來源);來源 header_title / header / title / og,找不到 (None, '')。規則見檔頭。"""
    title = H.title_of(html)
    heads = header_names(html, host)
    for n in heads:
        if title == n or any(title.endswith(d + n) for d in DASHES) or title.endswith(' ' + n):
            return n, 'header_title'
    if heads:
        return heads[0], 'header'
    n = title_suffix(title)
    if n:
        return n, 'title'
    n = H.meta(html, 'og:site_name')
    if n:
        return n, 'og'
    return None, ''

def _blog_name(html, host=''):
    return blog_name(html, host)[0]

def classify_collection(code, final, html, url=''):
    """合集頁:只有頁面明講合集不存在才算 deleted;404 狀態碼本身不算(實測還在的合集也會回 404)。"""
    txt = H.text_of((html or '')[:200000])
    if any(k in txt for k in COLLECTION_GONE):
        return H.result('deleted', reason='collection_gone', code=code, final=final)
    if code == 404:
        return H.result('unknown', reason='collection_404', code=code, final=final)
    if code is not None and code != 200:
        return H.result('unknown', reason='http_%s' % code, code=code, final=final)
    if not txt.strip():
        return H.result('unknown', reason='empty', code=code, final=final)
    return H.result('ok', None, reason='collection', code=code, final=final)

def parse(code, final, html, url=''):
    fh, fp = H.host_of(final), H.path_of(final)
    if fh == 'www.lofter.com' and fp.startswith(LOGIN_PATH):
        return H.result('login_required', reason='login_wall', blocked=True, code=code, final=final)
    if is_collection(url):
        if code in (403, 429):
            return H.result('unknown', reason='blocked', blocked=True, code=code, final=final)
        return classify_collection(code, final, html, url)
    if code == 404:
        return H.result('deleted', reason='404', code=code, final=final)
    if code in (403, 429):
        return H.result('unknown', reason='blocked', blocked=True, code=code, final=final)
    if code != 200:
        return H.result('unknown', reason='http_%s' % code, code=code, final=final)
    if '/post/' in H.path_of(url) and (fp in ('', '/') or fh in ('www.lofter.com', 'lofter.com')):
        return H.result('deleted', reason='redirect_home', code=code, final=final)
    txt = H.text_of(html[:200000])
    if any(k in txt for k in GONE_TEXT):
        return H.result('deleted', reason='gone_text', code=code, final=final)
    if re.search(r'(登录|登錄)\s*LOFTER', txt) and 'post' not in H.path_of(final):
        return H.result('login_required', reason='login_form', code=code, final=final)
    name, src = blog_name(html, fh)
    return H.result('ok', name, reason='200', code=code, final=final, author_url=fh, author_source=src)

def check(url):
    code, final, html = H.fetch(url)
    return parse(code, final, html, url)
