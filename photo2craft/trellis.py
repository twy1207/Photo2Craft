"""Generate a GLB and Clay previews using the official TRELLIS.2 Space."""
from base64 import b64decode
from binascii import Error as Base64Error
from contextlib import closing
from datetime import timedelta, timezone
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import Path
import re
from shutil import copyfile
from struct import unpack
from tempfile import TemporaryDirectory

from PIL import Image

from .trellis_auth import HUB_URL, load_tokens

SPACE_ID = "microsoft/TRELLIS.2"
SPACE_URL = "https://microsoft-trellis-2.hf.space"
FREE_GPU_SECONDS = 300
START_GPU_SECONDS = 60
DEFAULT_RESOLUTION = "512"
RESOLUTIONS = (DEFAULT_RESOLUTION, "1024")
CLAY_VIEW_COUNT = 8
SEED = 0
SAMPLER = (
    7.5, 0.7, 12, 5.0,  # Sparse structure
    7.5, 0.5, 12, 3.0,  # Shape
    1.0, 0.0, 12, 3.0,  # Material
)
DECIMATION_TARGET = 100_000
TEXTURE_SIZE = 1024
ENDPOINTS = ("/preprocess_image", "/image_to_3d", "/extract_glb")


class QuotaRejected(ValueError):
    """The Space explicitly rejected a request before model generation."""


class ClayImages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.mode = None
        self.images = {}

    def handle_starttag(self, tag, attrs):
        if tag != "img":
            return
        attributes = dict(attrs)
        title = attributes.get("title") or ""
        if title.casefold() in {"clay", "clay render"}:
            mode = re.fullmatch(r"selectMode\((\d+)\)", attributes.get("onclick") or "")
            if mode:
                self.mode = int(mode[1])
        view = re.fullmatch(r"view-m(\d+)-s(\d+)", attributes.get("id") or "")
        if view:
            self.images[tuple(map(int, view.groups()))] = attributes.get("src") or ""


def save_clay(html, out):
    gallery = ClayImages()
    if isinstance(html, str):
        gallery.feed(html)
        gallery.close()
    views = []
    for index in range(CLAY_VIEW_COUNT):
        source = gallery.images.get((gallery.mode, index), "")
        prefix = "data:image/jpeg;base64,"
        if not source.startswith(prefix):
            continue
        try:
            data = b64decode(source[len(prefix):], validate=True)
            with Image.open(BytesIO(data), formats=["JPEG"]) as image:
                image.load()
        except (Base64Error, OSError, ValueError, Image.DecompressionBombError):
            continue
        path = out / "clay" / f"view-{index:02d}.jpg"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        views.append({"index": index, "path": path.relative_to(out).as_posix()})
    return views


def verify_glb(path):
    with path.open("rb") as model:
        header = model.read(20)
        if len(header) != 20:
            raise ValueError("완전한 GLB 파일을 받지 못했습니다.")
        magic, version, size, json_size, chunk = unpack("<4sIII4s", header)
        if (magic, version, chunk) != (b"glTF", 2, b"JSON") or (
            size != path.stat().st_size or not 0 < json_size <= size - 20
        ):
            raise ValueError("GLB 파일의 형식이나 크기가 올바르지 않습니다.")
        try:
            document = json.loads(model.read(json_size))
        except (UnicodeError, ValueError):
            raise ValueError("GLB 형상 정보를 읽지 못했습니다.") from None
        if not isinstance(document, dict) or not document.get("meshes"):
            raise ValueError("GLB에 메시가 없습니다.")


def read_quota(api, token, name):
    try:
        return api.get_zero_gpu_quota(token=token)
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        reason = {
            401: "토큰이 만료되었거나 유효하지 않습니다.",
            403: "ZeroGPU 잔량 조회 권한을 확인해 주세요.",
            429: "잔량 조회 요청이 제한됐습니다.",
        }.get(status, f"ZeroGPU 잔량을 읽지 못했습니다 ({type(exc).__name__}).")
        print(f"{name} - {reason}", flush=True)
        return None


def next_result(photo, stage, names, tokens, api, client_type, handle_file, *, resolution=DEFAULT_RESOLUTION):
    resets = []
    for name in names:
        token = tokens.get(name)
        if not token:
            print(f"{name} - 저장소에 계정 토큰이 없습니다.", flush=True)
            continue
        quota = read_quota(api, token, name)
        if quota is None:
            continue
        if quota.base != FREE_GPU_SECONDS or quota.overquota_used not in (0, None):
            print(f"{name} - ZeroGPU 무료 계정으로 확인되지 않았습니다.", flush=True)
            continue
        if quota.resets_at is not None:
            resets.append(quota.resets_at)
        if quota.remaining < START_GPU_SECONDS:
            print(f"{name} - {int(quota.remaining)}초 남아 건너뜁니다.", flush=True)
            continue
        print(f"{name} - {quota.remaining:.0f}초 남아 생성을 시작합니다.", flush=True)
        try:
            return run_space(
                photo, stage, name, token, quota.remaining, api, client_type, handle_file,
                resolution=resolution,
            )
        except QuotaRejected as exc:
            print(f"{name} - {exc}로 생성이 거절됐습니다.", flush=True)
    hint = ""
    if resets:
        kst = timezone(timedelta(hours=9))
        hint = f" 확인된 가장 이른 리셋 시각은 {min(resets).astimezone(kst):%Y-%m-%d %H:%M KST}입니다."
    raise ValueError(f"지금 사용할 수 있는 무료 ZeroGPU 계정이 없습니다.{hint}")


def checked_call(stage, function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Exception as exc:
        message = str(exc).casefold()
        limit = None
        if "zerogpu runs limit" in message:
            limit = "ZeroGPU 실행 횟수 한도"
        elif "you have exceeded your gpu quota" in message:
            limit = "ZeroGPU 잔량 부족"
        if limit is not None:
            if stage in ("전처리", "메시 생성"):
                raise QuotaRejected(limit) from None
            reason = limit
        elif "gpu task timeout" in message or "gpu task timed out" in message:
            reason = "ZeroGPU 실행 시간 초과"
        elif "not enabled verbose error reporting" in message:
            reason = "Space가 세부 오류를 제공하지 않음"
        else:
            reason = type(exc).__name__
        raise ValueError(f"TRELLIS.2 {stage} 단계에서 실패했습니다 ({reason}).") from None


def run_space(photo, stage, name, token, before, api, client_type, handle_file, *, resolution):
    downloads = stage.parent / "downloads"
    downloads.mkdir(exist_ok=True)
    client = checked_call(
        "연결", client_type, SPACE_URL, token=token, verbose=False, analytics_enabled=False,
        download_files=downloads, max_workers=1,
    )
    with closing(client):
        schema = checked_call("API 확인", client.view_api, print_info=False, return_format="dict")
        if not all(endpoint in schema.get("named_endpoints", {}) for endpoint in ENDPOINTS):
            raise ValueError("공식 TRELLIS.2 API에서 전처리·생성·추출 경로를 확인하지 못했습니다.")

        print("사진 전처리 중", flush=True)
        prepared = checked_call(
            "전처리", client.predict, handle_file(str(photo)), api_name=ENDPOINTS[0]
        )
        prepared = downloaded_file(prepared, downloads)

        print(f"{resolution} 메시 생성 중", flush=True)
        preview = checked_call(
            "메시 생성", client.predict, handle_file(str(prepared)), SEED, resolution,
            *SAMPLER, api_name=ENDPOINTS[1],
        )
        after_generation = read_quota(api, token, name)
        views = save_clay(preview, stage)

        print("GLB 추출 중", flush=True)
        extraction_error = None
        try:
            extracted = checked_call(
                "GLB 추출", client.predict, DECIMATION_TARGET, TEXTURE_SIZE, api_name=ENDPOINTS[2]
            )
            if isinstance(extracted, (tuple, list)) and extracted:
                extracted = extracted[0]
            model = downloaded_file(extracted, downloads)
            verify_glb(model)
            copyfile(model, stage / "model.glb")
        except ValueError as exc:
            extraction_error = str(exc)

    after_extraction = read_quota(api, token, name)
    return {
        "model": "model.glb" if extraction_error is None else None,
        "extraction_error": extraction_error,
        "clay_views": views,
        "quota_remaining_seconds": {
            "before_generation": before,
            "after_generation": None if after_generation is None else after_generation.remaining,
            "after_extraction": None if after_extraction is None else after_extraction.remaining,
        },
    }


def downloaded_file(result, downloads):
    if isinstance(result, (str, Path)):
        path = Path(result).resolve()
        if path.is_relative_to(downloads) and path.is_file():
            return path
    raise ValueError("TRELLIS.2 응답에서 내려받은 파일을 찾지 못했습니다.")


def generate_mesh(photo: Path, out: Path, config: Path | None = None, *, resolution: str = DEFAULT_RESOLUTION):
    if resolution not in RESOLUTIONS:
        raise ValueError("해상도는 512 또는 1024를 지정해 주세요.")
    photo, out = photo.resolve(), out.resolve()
    with Image.open(photo) as image:
        image.verify()
    request = {
        "space": SPACE_ID,
        "photo_sha256": sha256(photo.read_bytes()).hexdigest(),
        "resolution": resolution,
        "seed": SEED,
        "sampler": list(SAMPLER),
        "decimation_target": DECIMATION_TARGET,
        "texture_size": TEXTURE_SIZE,
    }
    if out.exists():
        manifest = out / "generation.json"
        cached = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else None
        if not isinstance(cached, dict) or cached.get("request") != request:
            raise ValueError("출력 폴더를 사용 중입니다. 새 --out 경로를 지정해 주세요.")
        if cached.get("model") is None:
            raise ValueError("이 폴더에는 Clay와 실패 기록이 있습니다. 다시 생성하려면 새 --out 경로를 사용하세요.")
        verify_glb(out / "model.glb")
        print(f"저장된 GLB 재사용 - {out}", flush=True)
        print_clay_count(out)
        return

    try:
        from gradio_client import Client, handle_file
        from huggingface_hub import HfApi
    except ImportError:
        raise ValueError('TRELLIS.2 선택 의존성을 설치해 주세요 (pip install -e ".[trellis]").') from None
    tokens = load_tokens(config)
    if not any(tokens.values()):
        raise ValueError("저장된 토큰이 없습니다. trellis-auth로 토큰을 등록해 주세요.")

    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".trellis-", dir=out.parent) as temporary:
        stage = Path(temporary) / "result"
        stage.mkdir()
        result = next_result(
            photo, stage, list(tokens), tokens, HfApi(endpoint=HUB_URL), Client, handle_file,
            resolution=resolution,
        )
        (stage / "generation.json").write_text(
            json.dumps({"request": request, **result}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        stage.rename(out)
    print_clay_count(out)
    if result["extraction_error"] is not None:
        raise ValueError(f"{result['extraction_error']} 결과 기록은 {out}에 저장했습니다.")
    print(f"GLB 저장 - {out / 'model.glb'}", flush=True)


def print_clay_count(out):
    count = sum((out / "clay" / f"view-{index:02d}.jpg").is_file() for index in range(CLAY_VIEW_COUNT))
    if count < CLAY_VIEW_COUNT:
        print(f"Clay 일부 누락 - {count}/{CLAY_VIEW_COUNT}장", flush=True)
    else:
        print(f"Clay {count}장 - {out / 'clay'}", flush=True)
