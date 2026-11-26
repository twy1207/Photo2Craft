"""Keep local TRELLIS.2 tokens in one file outside the project."""
from getpass import getpass
import json
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile

HUB_URL = "https://huggingface.co"
LEGACY_CONFIG = Path(".local/trellis/tokens.json")
TOKEN_FILE = Path.home() / ".photo2craft" / "hf-tokens.txt"
_TOKEN = re.compile(r"hf_[A-Za-z0-9]+")


def legacy_tokens(config):
    from huggingface_hub.utils import get_stored_tokens

    try:
        settings = json.loads(config.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise ValueError(f"이전 토큰 설정을 찾지 못했습니다 ({config}).") from None
    except ValueError:
        raise ValueError("이전 토큰 설정을 JSON으로 읽지 못했습니다.") from None
    names = settings.get("tokens") if isinstance(settings, dict) else None
    if not isinstance(names, list) or not names or not all(
        isinstance(name, str) and name.strip() == name and name.isprintable()
        and not name.startswith("hf_") for name in names
    ):
        raise ValueError("이전 설정의 tokens에는 토큰 이름 목록이 필요합니다.")
    stored = get_stored_tokens()
    return {name: stored.get(name) for name in names}


def load_tokens(config=None):
    if config is not None:
        return legacy_tokens(config)
    if not TOKEN_FILE.is_file():
        return legacy_tokens(LEGACY_CONFIG) if LEGACY_CONFIG.is_file() else {}
    lines = TOKEN_FILE.read_text(encoding="utf-8-sig").splitlines()
    tokens = list(dict.fromkeys(line.strip() for line in lines if line.strip()))
    if not all(_TOKEN.fullmatch(token) for token in tokens):
        raise ValueError("토큰 파일에는 Hugging Face 토큰을 한 줄에 하나씩 넣어 주세요.")
    return {f"토큰 {index}": token for index, token in enumerate(tokens, 1)}


def save_tokens(tokens):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=TOKEN_FILE.parent, delete=False) as output:
        pending = Path(output.name)
        try:
            output.write("\n".join(tokens) + "\n")
        except OSError:
            output.close()
            pending.unlink(missing_ok=True)
            raise
    try:
        pending.replace(TOKEN_FILE)
    finally:
        pending.unlink(missing_ok=True)


def manage_tokens(*, list_only=False):
    tokens = list(dict.fromkeys(token for token in load_tokens().values() if token))
    if list_only:
        print(f"저장된 토큰 {len(tokens)}개")
        return
    if not sys.stdin.isatty():
        raise ValueError("토큰 등록은 PowerShell에서 대화형으로 실행해 주세요.")
    if tokens and not TOKEN_FILE.is_file():
        save_tokens(tokens)

    print("토큰을 하나씩 붙여넣으세요. 빈 Enter로 저장을 마칩니다.")
    while token := getpass("HF token: ").strip():
        if not _TOKEN.fullmatch(token):
            print("Hugging Face 토큰을 한 번에 하나만 입력해 주세요.")
        elif token in tokens:
            print("이미 저장된 토큰입니다.")
        else:
            tokens.append(token)
            save_tokens(tokens)
            print("저장했습니다.")
    print(f"저장된 토큰 {len(tokens)}개")
