"""IFEED Policy Update: one entry per week (Monday to Sunday), the largest entrepreneurial ecosystem
announcement of that week from the 14 bodies. Data lives in data/policy.json; this module fetches
candidates from korea.kr, adds an entry with its first-page image, and rewrites the published pages."""
import datetime as dt, html, json, os, re, subprocess, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data', 'policy.json')
# korea.kr press release codes for 13 of the 14 bodies. The National Assembly committee is not on korea.kr.
CODES = {'A00032': ('정부부처', '중소벤처기업부'), 'A00015': ('정부부처', '산업통상부'), 'C00003': ('위원회', '금융위원회'),
         'A00033': ('정부부처', '과학기술정보통신부'), 'A00001': ('정부부처', '고용노동부'), 'A00002': ('정부부처', '교육부'),
         'A00039': ('정부부처', '지식재산처'), 'A00008': ('정부부처', '농림축산식품부'), 'A00023': ('정부부처', '해양수산부'),
         'A00009': ('정부부처', '문화체육관광부'), 'A00012': ('정부부처', '보건복지부'), 'A00006': ('정부부처', '국토교통부'),
         'A00004': ('정부부처', '국무조정실')}
BODY_EN = {'중소벤처기업부': 'Ministry of SMEs and Startups', '산업통상부': 'Ministry of Trade, Industry and Resources',
           '금융위원회': 'Financial Services Commission', '과학기술정보통신부': 'Ministry of Science and ICT',
           '고용노동부': 'Ministry of Employment and Labor', '교육부': 'Ministry of Education', '지식재산처': 'Ministry of Intellectual Property',
           '농림축산식품부': 'Ministry of Agriculture, Food and Rural Affairs', '해양수산부': 'Ministry of Oceans and Fisheries',
           '문화체육관광부': 'Ministry of Culture, Sports and Tourism', '보건복지부': 'Ministry of Health and Welfare',
           '국토교통부': 'Ministry of Land, Infrastructure and Transport', '국무조정실': 'Office for Government Policy Coordination',
           '국회 산업통상자원중소벤처기업위원회': 'National Assembly Trade, Industry, Energy, SMEs and Startups Committee'}
REL = ['창업', '스타트업', '벤처', '중소기업', '중소벤처', '소상공인', '기업가', '액셀러레이터', '창업기획자', '모태펀드', '유니콘', '딥테크', '스케일업',
       '기술사업화', '사업화', '팁스', 'TIPS', '혁신기업', '규제샌드박스', '규제특례', '기술창업', '재창업', '엔젤', '크라우드펀딩', '코스닥', '기업공개', 'IPO',
       '인수합병', 'M&A', '회수시장', '벤처투자', '투자펀드', '성장펀드', '펀드', '정책금융', '보증', '혁신성장', '지역혁신', '창업중심대학', '실험실', '학생창업',
       '청년창업', '신산업', '지식재산', '특허', '기술금융', '자본시장', '첨단산업', 'R&D', '연구개발']
BIG = {'종합대책': 6, '대책': 4, '전략': 4, '기본계획': 6, '종합계획': 6, '계획': 2, '방안': 3, '로드맵': 4, '국무회의': 4, '의결': 3, '국회': 3, '통과': 3,
       '법': 2, '개정': 2, '시행': 2, '출범': 4, '신설': 3, '조성': 3, '조원': 5, '억원': 2, '발표': 2, '경제관계장관회의': 5, '업무계획': 4, '확정': 3,
       '본격': 2, '대통령': 3, '국정과제': 4, '예산': 3}
SMALL = {'개최': -3, '간담회': -3, '방문': -3, '시상': -3, '모집': -2, '공모': -1, '선정': -1, '설명자료': -6, '보도참고': -2, '해명': -6, '인사': -4,
         '포럼': -2, '세미나': -2, '현장': -2, '캠페인': -3, '홍보': -2, '참가': -2, '축제': -3}
CORE = {'중소벤처기업부': 3, '금융위원회': 1, '과학기술정보통신부': 1, '산업통상부': 1, '지식재산처': 1}
MONTHS = 'January February March April May June July August September October November December'.split()

def curl(args, out=None, tries=6):
    for i in range(tries):
        r = subprocess.run(['curl', '-sS', '-L', '-m', '60', '-A', 'Mozilla/5.0'] + (['-o', out] if out else []) + args, capture_output=True)
        if r.returncode == 0 and (out is None or (os.path.exists(out) and os.path.getsize(out) > 500)):
            return r.stdout.decode('utf-8', 'ignore') if out is None else out
        time.sleep(2 + 2 * i)
    raise RuntimeError('download failed: ' + ' '.join(args[-1:]))

def fetch_list(code, start, end):
    typ, name = CODES[code]; out, page = [], 1
    while True:
        h = curl(['-X', 'POST', 'https://www.korea.kr/briefing/pressReleaseList.do', '--data-urlencode', f'pageIndex={page}',
                  '--data-urlencode', f'repCodeType={typ}', '--data-urlencode', f'repCode={code}', '--data-urlencode', f'startDate={start}',
                  '--data-urlencode', f'endDate={end}', '--data-urlencode', 'srchWord=', '--data-urlencode', 'period=direct'])
        m = re.search(r'총 <strong>(\d+)</strong>건', h); total = int(m.group(1)) if m else 0
        items = re.findall(r'pressReleaseView\.do\?newsId=(\d+)[^"]*">\s*<span class="text">\s*<strong>(.*?)</strong>.*?<span class="source">\s*<span>([\d-]+)</span>', h, re.S)
        for nid, t, d in items:
            out.append(dict(newsId=nid, body_ko=name, title_ko=html.unescape(re.sub(r'<.*?>', '', t)).strip(), date=d))
        if page * 10 >= total or not items: return out
        page += 1

def score(x):
    t = x['title_ko']; rel = sum(1 for k in REL if k in t)
    if not rel: return None
    s = rel * 2 + CORE.get(x['body_ko'], 0) + sum(v for k, v in BIG.items() if k in t) + sum(v for k, v in SMALL.items() if k in t)
    m = re.search(r'(\d[\d,\.]*)\s*(조|억)\s*원', t)
    if m: s += 4 if m.group(2) == '조' else (3 if float(m.group(1).replace(',', '')) >= 1000 else 1)
    return s

def candidates(monday, top=12):
    start, end = monday, monday + dt.timedelta(days=6); seen, out = set(), []
    for code in CODES:
        for x in fetch_list(code, start.isoformat(), end.isoformat()):
            if x['newsId'] in seen: continue
            seen.add(x['newsId']); s = score(x)
            if s is not None: out.append(dict(score=s, **x))
    return sorted(out, key=lambda x: -x['score'])[:top]

def nice_date(d):
    d = dt.date.fromisoformat(d); return f'{d.day} {MONTHS[d.month - 1]} {d.year}'

def first_page(news_id, out_jpg):
    """First page of the release: its PDF if attached, otherwise korea.kr's own document viewer
    (LibreOffice conversions of ODT/HWP show tracked changes, so they are the last resort)."""
    h = curl([f'https://www.korea.kr/briefing/pressReleaseView.do?newsId={news_id}'])
    atts = [(f, html.unescape(n).strip()) for f, n in re.findall(r'<a href="/common/download\.do\?fileId=(\d+)&amp;tblKey=GMN">\s*<img[^>]*>(.*?)\s*</a>', h, re.S)]
    kogl = re.search(r'open_type_0(\d)\.png', h)
    viewer = re.search(r'<iframe[^>]+id="content_press"[^>]+src="([^"]+)"', h)
    from PIL import Image
    with tempfile.TemporaryDirectory() as td:
        png, how = os.path.join(td, 'p.png'), None
        pdfs = [a for a in atts if a[1].lower().endswith('.pdf')]
        # the release itself, not an agenda paper or annex attached beside it
        pdfs = [a for a in pdfs if '보도' in a[1]] or [a for a in pdfs if not re.search(r'안건|붙임|별첨|첨부|참고자료|설명자료', a[1])]
        if pdfs:
            f = os.path.join(td, 'a.pdf'); curl([f'https://www.korea.kr/common/download.do?fileId={pdfs[0][0]}&tblKey=GMN'], f)
            subprocess.run(['pdftoppm', '-r', '110', '-f', '1', '-l', '1', '-png', '-singlefile', f, png[:-4]], check=True); how = 'pdf'
        elif viewer:
            from playwright.sync_api import sync_playwright
            from PIL import ImageStat
            with sync_playwright() as p:
                b = p.chromium.launch()
                for attempt in range(4):   # the viewer sometimes answers "upstream request failed"; retry until a page is drawn
                    pg = b.new_page(viewport={'width': 800, 'height': 1130})
                    pg.goto('https://www.korea.kr' + html.unescape(viewer.group(1))); pg.wait_for_load_state('networkidle'); pg.wait_for_timeout(2500 + 1500 * attempt)
                    pg.screenshot(path=png); pg.close()
                    st = ImageStat.Stat(Image.open(png).convert('L').crop((0, 60, 800, 1130)))
                    if st.mean[0] > 180 and st.stddev[0] > 20: break   # a white page with text, not a grey loading screen
                    time.sleep(3)
                b.close()
            im = Image.open(png).convert('L'); w, hh = im.size; top = 0
            while top < 120 and sum(im.getpixel((x, top)) for x in range(0, w, 8)) / len(range(0, w, 8)) < 200: top += 1
            Image.open(png).crop((0, top + 4, w, hh)).save(png); how = 'viewer'
        else:
            conv = [a for ext in ('.odt', '.docx', '.hwp') for a in atts if a[1].lower().endswith(ext)]
            for fid, name in conv[:2]:
                ext = os.path.splitext(name)[1].lower(); f = os.path.join(td, 'a' + ext)
                curl([f'https://www.korea.kr/common/download.do?fileId={fid}&tblKey=GMN'], f)
                subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', td, f], capture_output=True, timeout=240)
                if os.path.exists(os.path.join(td, 'a.pdf')):
                    subprocess.run(['pdftoppm', '-r', '110', '-f', '1', '-l', '1', '-png', '-singlefile', os.path.join(td, 'a.pdf'), png[:-4]], check=True); how = 'converted'; break
        if not how: raise RuntimeError(f'no first page for {news_id}')
        im = Image.open(png).convert('RGB')
        if im.width > im.height * 1.2: im = im.crop((0, 0, im.width // 2, im.height))   # two pages side by side: keep the first
        w = 640; im = im.resize((w, int(im.height * w / im.width)))
        im.crop((0, 0, w, min(im.height, 480))).save(out_jpg, quality=80, optimize=True, progressive=True)
    return dict(kogl=kogl.group(1) if kogl else None, source=how)

def load():
    return json.load(open(DATA, encoding='utf-8')) if os.path.exists(DATA) else []

def save(entries):
    entries.sort(key=lambda e: (e['week'], e['date']), reverse=True)
    json.dump(entries, open(DATA, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

def add_entry(week, news_id, body_ko, date, title_en, title_ko):
    entries = [e for e in load() if e['week'] != week]
    img = f'assets/policy/{news_id}.jpg'
    os.makedirs(os.path.join(ROOT, 'assets', 'policy'), exist_ok=True)
    meta = first_page(news_id, os.path.join(ROOT, img))
    entries.append(dict(week=week, date=date, body_ko=body_ko, body=BODY_EN[body_ko], title=title_en, title_ko=title_ko, newsId=news_id,
                        url=f'https://www.korea.kr/briefing/pressReleaseView.do?newsId={news_id}', img='/' + img, kogl=meta['kogl']))
    save(entries); return entries

def esc(s): return html.escape(s, quote=True)

def card(e):
    u = esc(e['url'])
    return (f'<li class="prow">\n          <a class="pthumb" href="{u}" rel="noopener noreferrer" target="_blank" tabindex="-1" aria-hidden="true">'
            f'<img src="{esc(e["img"])}" alt="" loading="lazy"></a>\n          <p class="d">{nice_date(e["date"])}</p>\n          <p class="c">{esc(e["body"])}</p>\n'
            f'          <div class="pb"><h3><a href="{u}" rel="noopener noreferrer" target="_blank">{esc(e["title"])}</a></h3></div>\n        </li>')

def render():
    """Rewrite the Policy Update list on /policy and the latest three on the home page, and the search index entry."""
    entries = load()
    for fname, cls, n in [('policy.html', 'plist', None), ('index.html', 'plist hp', 3)]:
        p = os.path.join(ROOT, fname); h = open(p, encoding='utf-8').read()
        rows = '\n'.join(card(e) for e in (entries[:n] if n else entries))
        h2, k = re.subn(r'(<ul class="' + re.escape(cls) + r'">).*?(</ul>)', lambda m: m.group(1) + rows + m.group(2), h, count=1, flags=re.S)
        assert k == 1, fname
        open(p, 'w', encoding='utf-8').write(h2)
    js = os.path.join(ROOT, 'site.js'); s = open(js, encoding='utf-8').read()
    text = 'Policy Update ' + ' '.join(f'{nice_date(e["date"])} {e["body"]} {e["title"]}' for e in entries)
    s2, k = re.subn(r'(\{"title": ?"Policy(?: Update)?", ?"url": ?"/policy", ?"text": ?)"(?:[^"\\]|\\.)*"', lambda m: m.group(1) + json.dumps(text, ensure_ascii=False), s, count=1)
    if k: open(js, 'w', encoding='utf-8').write(s2)
    return len(entries)

if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'candidates':   # python3 tools/policy_lib.py candidates [YYYY-MM-DD monday]; default: last week
        today = dt.date.today(); mon = dt.date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else today - dt.timedelta(days=today.weekday() + 7)
        print(f'week of {mon}')
        for x in candidates(mon): print(f"{x['score']:>3}  {x['date']}  {x['body_ko']}  {x['newsId']}  {x['title_ko']}")
    elif cmd == 'add':        # python3 tools/policy_lib.py add WEEK_MONDAY NEWS_ID BODY_KO DATE "English title" "Korean title"
        add_entry(*sys.argv[2:8]); print('entries', render())
    elif cmd == 'render':
        print('entries', render())
