import sys
from types import SimpleNamespace

from photo2craft import trellis_auth


def test_token_file_keeps_existing_tokens_and_appends_without_duplicates(monkeypatch, tmp_path, capsys):
    storage = tmp_path / "hf-tokens.txt"
    legacy = tmp_path / "tokens.json"
    legacy.write_text('{"tokens": ["old-name"]}', encoding="utf-8")
    replies = iter(["hf_second", "hf_second", "hf_third", ""])
    monkeypatch.setattr(trellis_auth, "TOKEN_FILE", storage)
    monkeypatch.setattr(trellis_auth, "LEGACY_CONFIG", legacy)
    monkeypatch.setattr(trellis_auth, "getpass", lambda _: next(replies))
    monkeypatch.setattr(trellis_auth.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setitem(sys.modules, "huggingface_hub.utils", SimpleNamespace(
        get_stored_tokens=lambda: {"old-name": "hf_first", "unselected": "hf_other"},
    ))

    trellis_auth.manage_tokens()
    assert list(trellis_auth.load_tokens().values()) == ["hf_first", "hf_second", "hf_third"]
    output = capsys.readouterr().out
    assert output.endswith("저장된 토큰 3개\n")
    assert "hf_" not in output
    trellis_auth.manage_tokens(list_only=True)
    assert capsys.readouterr().out == "저장된 토큰 3개\n"
