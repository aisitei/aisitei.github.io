"""Verify published navigation and historical body preservation without network access."""
import json
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from site_ui import ArticleLayoutParser
ROOT=Path(__file__).resolve().parents[1]

class References(HTMLParser):
    def __init__(self,text):
        super().__init__()
        self.base=''
        self.urls=[]
        self.cards=0
        self.feed(text)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='base':self.base=attrs.get('href','')
        if tag in ('a','link','script','img'):
            self.urls.append(attrs.get('href') or attrs.get('src') or '')
        if tag=='article' and 'news-card' in attrs.get('class','').split():self.cards+=1

pages=[ROOT/'index.html',*sorted((ROOT/'news').glob('page-*.html'))]
errors=[]
card_count=0
for path in pages:
    doc=References(path.read_text())
    card_count+=doc.cards
    if doc.cards>24:errors.append(f'Unbounded page: {path}')
    base=(path.parent/doc.base).resolve() if doc.base else path.parent
    for url in doc.urls:
        parsed=urlsplit(url)
        if not parsed.path or parsed.scheme or parsed.netloc:continue
        target=(ROOT/parsed.path.lstrip('/')) if parsed.path.startswith('/') else base/unquote(parsed.path)
        if not target.exists():errors.append(f'Missing local reference: {path.name}: {url}')
records=json.loads((ROOT/'assets/data/articles.json').read_text())
if card_count!=len(records):errors.append(f'Article coverage: {card_count}/{len(records)}')
for item in records:
    if not (ROOT/item['url']).is_file():errors.append('Missing article: '+item['url'])
files=sorted((ROOT/'articles').rglob('index.html'))
# Compare exact UTF-8 body markup, including embedded CR characters, with the base commit.
process=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
for file in files:
    relative=file.relative_to(ROOT)
    process.stdin.write(('HEAD:'+str(relative)+'\n').encode());process.stdin.flush()
    header=process.stdout.readline().decode().split()
    if header[-1]=='missing':continue
    original=process.stdout.read(int(header[-1])).decode();process.stdout.read(1)
    updated=file.read_bytes().decode()
    body=original.split('<div class="article-body">',1)[-1].split('<!-- All images',1)[0]
    if body not in updated:errors.append('Changed article body: '+str(relative))
    layout=ArticleLayoutParser(updated).blocks
    if layout.get('hero-image-wrap',(sys.maxsize,))[0]<layout.get('article-meta',(0,))[0]:errors.append('Image before title: '+str(relative))
    doc=References(updated)
    for url in doc.urls:
        if '/assets/site.' in url or '/assets/news.js' in url or '/assets/article.js' in url:
            if not (file.parent/urlsplit(url).path).resolve().is_file():errors.append('Missing shared asset: '+str(relative))
process.stdin.close();process.wait()
if errors:
    print('\n'.join(errors[:30]));raise SystemExit(f'{len(errors)} validation errors')
print(f'PASS: {len(pages)} pages, {card_count} card links, {len(records)} searchable articles, {len(files)} preserved article bodies and valid title order.')
print(f'Home: {(ROOT/"index.html").stat().st_size:,} bytes; search index loaded on demand: {(ROOT/"assets/data/articles.json").stat().st_size:,} bytes.')
