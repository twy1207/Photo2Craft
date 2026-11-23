"""Read-only, loopback-only example viewer; no AI requests or file writes."""
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .compile import COLORS
from .model import parse_plan_json
from .pipeline import compile_document


def warning_labels(warnings):
    labels = []
    for warning in warnings:
        if 'roof lost' in warning:
            label = '얇은 지붕 일부가 블록 크기 때문에 생략됐습니다.'
        elif 'face cells painted' in warning:
            label = '창·패널 일부가 다른 구조와 겹칩니다.'
        elif 'clipped' in warning:
            label = '추가 부품의 크기를 기본 건물 범위에 맞췄습니다.'
        elif 'hidden' in warning or 'overwritten' in warning:
            label = '일부 부품이 가려지거나 다른 부품에 덮였습니다.'
        else:
            label = '일부 구조가 단순화됐습니다. 원본 사진과 비교해 주세요.'
        if label not in labels:
            labels.append(label)
    return labels


class ExampleCatalog:
    def __init__(self, examples: Path):
        root = examples.resolve()
        definitions = [
            ('gothic-base', 'gothic', '박공지붕 주택', '기본 결과',
             'gothic/run-04/plan.json', 'gothic/run-04/input.jpg', 'gothic/source.json'),
            ('gothic-attached', 'gothic', '박공지붕 주택', '부품 추가',
             'frozen-baseline-20261123/run/plan.json', 'gothic/run-04/input.jpg', 'gothic/source.json'),
            ('schroder-base', 'schroder', '비대칭 평지붕 건물', '기본 결과',
             'schroder/replay-01/plan.json', 'schroder/run-01/input.jpg', 'schroder/source.json'),
        ]
        self.entries, self.photos = {}, {}
        for key, building, title, variant, plan_file, photo_file, credit_file in definitions:
            plan, result, _ = compile_document(parse_plan_json((root/plan_file).read_text(encoding='utf-8')))
            credit = json.loads((root/credit_file).read_text(encoding='utf-8'))
            self.photos[key] = (root/photo_file).read_bytes()
            self.entries[key] = {
                'id': key, 'building': building, 'title': title, 'variant': variant,
                'view': plan.view, 'photo': f'/api/photos/{key}.jpg',
                'credit': {k: credit[k] for k in ('author', 'license', 'page')},
                'size': [max(p[i] for p in result.blocks)+1 for i in range(3)],
                'block_count': len(result.blocks), 'warning_count': len(result.warnings),
                'notes': warning_labels(result.warnings),
                'scene': result.as_dict(),
                'colors': {f'minecraft:{name}': value for name, value in COLORS.items()},
            }

    def listing(self):
        return {'examples': [{k: entry[k] for k in ('id', 'building', 'title', 'variant')}
                             for entry in self.entries.values()]}


def make_server(examples: Path, port=8000):
    if not 0 <= port <= 65535:
        raise ValueError('port must be between 0 and 65535')
    catalog = ExampleCatalog(examples)
    web_root = Path(__file__).with_name('web').resolve()

    class Handler(BaseHTTPRequestHandler):
        def send_bytes(self, status, content, content_type):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(content)

        def send_json(self, status, value):
            self.send_bytes(status, json.dumps(value, ensure_ascii=False).encode(), 'application/json; charset=utf-8')

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == '/api/examples':
                self.send_json(200, catalog.listing())
            elif path.startswith('/api/examples/'):
                entry = catalog.entries.get(path.removeprefix('/api/examples/'))
                self.send_json(200 if entry else 404, entry or {'error': '예제를 찾을 수 없습니다.'})
            elif path.startswith('/api/photos/'):
                photo = catalog.photos.get(path.removeprefix('/api/photos/').removesuffix('.jpg'))
                if photo:
                    self.send_bytes(200, photo, 'image/jpeg')
                else:
                    self.send_json(404, {'error': '사진을 찾을 수 없습니다.'})
            else:
                asset = (web_root/('index.html' if path == '/' else path.lstrip('/'))).resolve()
                if not asset.is_relative_to(web_root) or not asset.is_file():
                    self.send_json(404, {'error': '페이지를 찾을 수 없습니다.'})
                    return
                content_type = 'text/javascript' if asset.suffix == '.js' else mimetypes.guess_type(asset.name)[0] or 'application/octet-stream'
                if content_type.startswith('text/'):
                    content_type += '; charset=utf-8'
                self.send_bytes(200, asset.read_bytes(), content_type)

        def log_message(self, fmt, *args):
            pass

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def serve(examples: Path, port=8000):
    try:
        server = make_server(examples, port)
    except FileNotFoundError:
        raise ValueError('동봉 예제를 찾지 못했습니다. 저장소 루트에서 실행하거나 --examples 경로를 지정하세요.') from None
    with server:
        print(f'Photo2Craft: http://127.0.0.1:{server.server_port}  (Ctrl+C to stop)', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\nViewer stopped.', flush=True)
