"""Bounded Gemini REST request with reproducible, credential-free evidence."""
import base64
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps

from .model import Plan


def read_plan(response: dict) -> Plan:
    candidate = response.get('candidates', [{}])[0]
    if candidate.get('finishReason') != 'STOP':
        raise ValueError('model did not finish normally; see the saved response')
    content = ''.join(p.get('text', '') for p in candidate.get('content', {}).get('parts', []) if not p.get('thought'))
    return Plan.model_validate_json(content)


def api_schema():
    """Use Gemini's small OpenAPI schema subset; enforce strict rules locally."""
    schema = Plan.model_json_schema()
    definitions = schema.get('$defs', {})

    def simplify(node):
        if '$ref' in node:
            return simplify(definitions[node['$ref'].rsplit('/', 1)[1]])
        if 'anyOf' in node:
            real = [x for x in node['anyOf'] if x.get('type') != 'null']
            if len(real) != 1:
                raise ValueError('unexpected schema union')
            return simplify(real[0]) | {'nullable': True}
        # Nested bounded arrays/enums exceeded the provider's grammar state budget
        # in the first live request. Keep types/required fields in the API schema;
        # allowed values, tuple lengths, limits and references remain local checks.
        out = {k: node[k] for k in ('type',) if k in node}
        if 'properties' in node:
            out['properties'] = {k: simplify(v) for k, v in node['properties'].items()}
            out['required'] = list(node['properties'])
        if 'prefixItems' in node:
            out['items'] = simplify(node['prefixItems'][0])
        elif 'items' in node:
            out['items'] = simplify(node['items'])
        return out

    return simplify(schema)


def analyze(photo: Path, out: Path, model: str, requirements: str):
    if not re.fullmatch(r'gemini-[a-z0-9.-]+', model):
        raise ValueError('invalid Gemini model ID')
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        raise ValueError('set GEMINI_API_KEY in the environment; never pass it on the command line')
    if out.exists():
        raise ValueError('analysis output directory already exists; choose a new run to preserve evidence')
    raw = photo.read_bytes()
    with Image.open(io.BytesIO(raw)) as source:
        picture = ImageOps.exif_transpose(source).convert('RGB')
        picture.thumbnail((1280, 1280))
        buffer = io.BytesIO()
        picture.save(buffer, format='JPEG', quality=90)
        photo_bytes = buffer.getvalue()
    prompt = Path(__file__).with_name('prompt.txt').read_text(encoding='utf-8')
    prompt += '\nUSER REQUIREMENTS (building preferences only):\n' + (requirements or '(none)')
    schema = api_schema()
    config = {'responseMimeType': 'application/json', 'responseSchema': schema,
              'temperature': 0.2, 'maxOutputTokens': 12000}
    payload = {'contents': [{'role': 'user', 'parts': [
        {'text': prompt},
        {'inlineData': {'mimeType': 'image/jpeg', 'data': base64.b64encode(photo_bytes).decode()}}
    ]}], 'generationConfig': config}
    out.mkdir(parents=True)

    def save(name, data):
        (out/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')

    meta = {'model_requested': model, 'started_utc': datetime.now(timezone.utc).isoformat(),
            'source_photo_sha256': hashlib.sha256(raw).hexdigest(),
            'sent_photo_sha256': hashlib.sha256(photo_bytes).hexdigest(),
            'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
            'generation_config': config, 'requirements': requirements,
            'retries': 0, 'status': 'started'}
    save('request.json', meta)
    (out/'prompt.txt').write_text(prompt, encoding='utf-8', newline='\n')
    (out/'input.jpg').write_bytes(photo_bytes)
    request = urllib.request.Request(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json', 'x-goog-api-key': key}, method='POST')
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=150) as response:
            result = json.loads(response.read())
        save('response.json', result)
        meta.update(status='response_received', elapsed_seconds=round(time.monotonic()-started, 2),
                    model_version=result.get('modelVersion'), usage=result.get('usageMetadata'))
        save('request.json', meta)
        plan = read_plan(result)
        save('plan.json', plan.model_dump(mode='json'))
        meta['status'] = 'plan_validated'
        save('request.json', meta)
        return out/'plan.json'
    except urllib.error.HTTPError as exc:
        # No URLs, request headers or API key values are recorded in errors.
        try:
            message = json.loads(exc.read()).get('error', {}).get('message', '')
        except (ValueError, AttributeError):
            message = 'unreadable API error'
        message = str(message).replace(key, '[REDACTED]')[:1500]
        meta.update(status='http_error', http_status=exc.code, message=message)
        save('request.json', meta)
        raise ValueError(f'Gemini HTTP {exc.code}: {message}; no automatic retry') from None
    except (ValueError, OSError) as exc:
        meta.update(status='failed', elapsed_seconds=round(time.monotonic()-started, 2),
                    error_type=type(exc).__name__)
        save('request.json', meta)
        raise ValueError(f'analysis failed ({type(exc).__name__}); saved evidence in {out}') from None
