import csv, html, json, re
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
SOURCE = 'xn--12c1ezaww.com'
with (ROOT / 'post-index.csv').open(encoding='utf-8-sig') as file:
    POSTS = {urlsplit(row['post_url']).path.rstrip('/').rsplit('/', 1)[-1]: row['post_url']
             for row in csv.DictReader(file) if urlsplit(row['post_url']).hostname == SOURCE}

def read(url, host, method='GET'):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc != host:
        raise ValueError('Unexpected source')
    request = Request(url, method=method, headers={'User-Agent': 'curl/8.0'})
    if method == 'POST':
        request.add_header('Accept', 'application/json')
    with urlopen(request, timeout=9) as response:
        return response.read(2_000_000).decode('utf-8')

class OpenGraph(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        if tag == 'meta':
            attrs = dict(attrs)
            key = attrs.get('property')
            if key in ('og:title', 'og:image'):
                self.values.setdefault(key, attrs.get('content') or '')


@lru_cache(maxsize=2048)
def metadata(post):
    parser = OpenGraph()
    parser.feed(read(post, SOURCE))
    image = parser.values.get('og:image', '')
    return {'title': parser.values.get('og:title', ''),
            'image': image if urlsplit(image).scheme == 'https' else ''}


def resolve(post):
    page = read(post, SOURCE)
    frame = re.search(r'<iframe[^>]*\ssrc="(https://lumierecore\.com/[^"]+)"', page, re.I)
    player = read(html.unescape(frame[1]), 'lumierecore.com')
    config = re.search(r'src="(https://lumierecore\.com/player-config/[^"]+)"', player)
    script = read(html.unescape(config[1]), 'lumierecore.com')
    selection = re.search(r'PLAYER_PROXY_SELECTION_URL = "([^"]+)"', script)
    result = json.loads(read(selection[1], 'px.lumierecore.com', 'POST'))
    stream = urlsplit(result['masterUrl'])
    if stream.scheme != 'https' or stream.username or stream.password or '.m3u8' not in stream.path:
        raise ValueError('Unexpected stream')
    return stream.geturl()

# the only files served over HTTP; everything else in ROOT (.git, post-index.csv, this script, backups) is 404
STATIC_FILES = frozenset({
    '/clip-catalog.html',
    '/snake168-watch-banner.gif',
    '/snake168-floating-banner.webp',
    '/snake168-rail-baccarat.webp',
    '/snake168-rail-casino-roulette.webp',
    '/snake168-rail-slot.webp',
    '/banner-01.gif',
    '/banner-02.gif',
    '/banner-03.gif',
    '/banner-04.gif',
    '/banner-05.gif',
    '/banner-06.gif',
    '/logo.png',
})

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_HEAD(self):
        if urlsplit(self.path).path not in STATIC_FILES:
            self.send_error(404)
            return
        return super().do_HEAD()

    def do_GET(self):
        path = urlsplit(self.path).path
        match = re.fullmatch(r'/(stream|cover)/(\d+)', path)
        if not match:
            if path not in STATIC_FILES:
                self.send_error(404)
                return
            return super().do_GET()
        post = POSTS.get(match[2])
        if not post:
            self.send_error(404)
            return
        try:
            data = metadata(post) if match[1] == 'cover' else {'url': resolve(post)}
            payload = json.dumps(data).encode()
        except (OSError, ValueError, TypeError, KeyError) as error:
            self.log_error('Stream resolution failed: %s', type(error).__name__)
            self.send_error(502)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

if __name__ == '__main__':
    with ThreadingHTTPServer(('127.0.0.1', 8876), Handler) as server:
        print('http://127.0.0.1:8876/clip-catalog.html', flush=True)
        server.serve_forever()
