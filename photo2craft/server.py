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
        local_meshes = root.parent / '.local' / 'trellis'
        # The first available result for a building is its default size.
        mesh_directories = {
            'gothic': (('gothic', 'gothic-block-check'),),
            'schroder': (
                ('schroder-64', 'schroder-block-review-64'),
                ('schroder', 'schroder-block-review'),
                ('schroder-56', 'schroder-block-review-56'),
            ),
        }
        definitions = [
            ('gothic-base', 'gothic', '박공지붕 주택', '기본 결과',
             'gothic/run-04/plan.json', 'gothic/run-04/input.jpg', 'gothic/source.json'),
            ('gothic-attached', 'gothic', '박공지붕 주택', '부품 추가',
             'frozen-baseline-20261123/run/plan.json', 'gothic/run-04/input.jpg', 'gothic/source.json'),
            ('schroder-base', 'schroder', '비대칭 평지붕 건물', '기본 결과',
             'schroder/replay-01/plan.json', 'schroder/run-01/input.jpg', 'schroder/source.json'),
        ]
        self.entries, self.photos, self.mesh_assets = {}, {}, {}
        loaded_meshes = set()
        for key, building, title, variant, plan_file, photo_file, credit_file in definitions:
            if building in loaded_meshes:
                continue
            photo_credit = json.loads((root/credit_file).read_text(encoding='utf-8'))
            credit = {k: photo_credit[k] for k in ('author', 'license', 'page')}
            for result_id, folder in mesh_directories[building]:
                mesh_directory = local_meshes / folder
                if (mesh_directory / 'mesh-review.json').is_file():
                    self.add_mesh_result(mesh_directory, building=building, result_id=result_id,
                                         title=title, credit=credit)
                    loaded_meshes.add(building)
            if building in loaded_meshes:
                continue

            plan, result, _ = compile_document(parse_plan_json((root/plan_file).read_text(encoding='utf-8')))
            self.photos[key] = (root/photo_file).read_bytes()
            self.entries[key] = {
                'id': key, 'building': building, 'title': title, 'variant': variant,
                'view': plan.view, 'photo': f'/api/photos/{key}.jpg',
                'credit': credit,
                'size': [max(p[i] for p in result.blocks)+1 for i in range(3)],
                'block_count': len(result.blocks), 'warning_count': len(result.warnings),
                'notes': ['저장된 Gemini 계획으로 만든 예제입니다.', *warning_labels(result.warnings)],
                'scene': result.as_dict(),
                'colors': {f'minecraft:{name}': value for name, value in COLORS.items()},
            }

    def listing(self):
        return {'examples': [{k: entry.get(k) for k in ('id', 'building', 'title', 'variant', 'extent')}
                             for entry in self.entries.values()]}

    def add_mesh_result(self, directory: Path, *, building='mesh', title='GLB 변환 결과',
                        credit=None, result_id=None, first=False):
        root = directory.resolve()
        result_id = result_id or building

        def read(name):
            file = (root / name).resolve()
            if not file.is_relative_to(root):
                raise ValueError('비교 이미지가 변환 결과 폴더를 벗어납니다.')
            return file.read_bytes()

        def asset(name, content_type):
            url = f'/api/mesh/{result_id}/{name}'
            self.mesh_assets[url] = (read(name), content_type)
            return url

        report = json.loads(read('mesh-review.json'))
        if not isinstance(report, dict) or report.get('format') != 'photo2craft-mesh-review-v1':
            raise ValueError('지원되는 GLB 변환 결과를 지정해 주세요.')
        size = report.get('size')
        if not isinstance(size, list) or len(size) != 3 or not all(type(v) is int and 1 <= v <= 64 for v in size):
            raise ValueError('블록 격자 크기를 확인할 수 없습니다.')

        photo_names = {'photo.jpg': 'image/jpeg', 'photo.png': 'image/png', 'photo.webp': 'image/webp'}
        photo_name = report.get('photo')
        if photo_name is not None and photo_name not in photo_names:
            raise ValueError('지원되는 원본 사진 형식을 지정해 주세요.')
        photo = None if photo_name is None else asset(photo_name, photo_names[photo_name])

        views = []
        for view in report['views']:
            index = view['index']
            if type(index) is not int or not 0 <= index < 8:
                raise ValueError('Clay 시점 번호가 올바르지 않습니다.')
            views.append({**view, 'url': asset(f'clay/view-{index:02d}.jpg', 'image/jpeg')})

        variants = [('after', 'blocks.json', '보정 후' if views else '기본 변환')]
        if views:
            variants.insert(0, ('before', 'blocks-before.json', '보정 전'))
        entries = {}
        for version, filename, variant in variants:
            key = f'{result_id}-{version}'
            scene = json.loads(read(filename))
            if not isinstance(scene, dict) or scene.get('format') != 'photo2craft-blocks-v1' or not scene.get('blocks'):
                raise ValueError('블록 데이터 형식을 확인할 수 없습니다.')
            source = 'TRELLIS.2 GLB' if credit else 'GLB'
            notes = [f'{source}의 표면을 흰색 콘크리트 블록으로 옮겼습니다.']
            if version == 'after' and views:
                notes.append(f"Clay {report['aligned_views']}개 시점과 비교해 바깥쪽 블록 {report['removed']}개를 정리했습니다.")
            entries[key] = {
                'id': key, 'building': building, 'title': title, 'variant': variant,
                'view': 'front_right', 'photo': photo, 'credit': credit, 'size': size, 'extent': max(size),
                'block_count': len(scene['blocks']), 'warning_count': len(scene.get('warnings', [])),
                'notes': notes, 'scene': scene,
                'colors': {f'minecraft:{name}': value for name, value in COLORS.items()},
                'clay': views, 'clay_camera': report.get('camera'),
            }
        if first:
            self.entries = {**entries, **self.entries}
        else:
            self.entries.update(entries)


def make_server(examples: Path, port=8000, *, mesh_result=None):
    if not 0 <= port <= 65535:
        raise ValueError('port must be between 0 and 65535')
    catalog = ExampleCatalog(examples)
    if mesh_result is not None:
        try:
            catalog.add_mesh_result(mesh_result, first=True)
        except FileNotFoundError:
            raise ValueError('지정한 GLB 변환 결과 파일을 찾지 못했습니다.') from None
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
            elif path in catalog.mesh_assets:
                self.send_bytes(200, *catalog.mesh_assets[path])
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


def serve(examples: Path, port=8000, *, mesh_result=None):
    try:
        server = make_server(examples, port, mesh_result=mesh_result)
    except FileNotFoundError:
        raise ValueError('동봉 예제를 찾지 못했습니다. 저장소 루트에서 실행하거나 --examples 경로를 지정하세요.') from None
    with server:
        print(f'Photo2Craft: http://127.0.0.1:{server.server_port}  (Ctrl+C to stop)', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\nViewer stopped.', flush=True)
