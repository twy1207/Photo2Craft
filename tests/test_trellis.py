import base64
from datetime import datetime, timezone
from io import BytesIO
import json
from struct import pack
import sys
from types import SimpleNamespace

from PIL import Image
import pytest

from photo2craft import trellis


@pytest.mark.parametrize("extraction_fails, first_quota", [(False, 59), (True, 59), (False, 90)])
def test_generate_mesh_preserves_results(tmp_path, monkeypatch, extraction_fails, first_quota):
    photo = tmp_path / "input.png"
    Image.new("RGB", (2, 2)).save(photo)
    output = tmp_path / "result"
    config = tmp_path / "tokens.json"
    config.write_text('{"tokens": ["first", "second", "third"]}', encoding="utf-8")
    jobs, quota_requests = [], []
    expected_jobs = list(trellis.ENDPOINTS)
    if first_quota >= 60:
        expected_jobs.insert(1, "/image_to_3d")
    image_file = BytesIO()
    Image.new("RGB", (2, 2), "gray").save(image_file, format="JPEG")
    jpeg = image_file.getvalue()
    data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    gallery = '<img title="Clay render" onclick="selectMode(2)">'
    gallery += "".join(f'<img id="view-m2-s{i}" src="{data_url}">' for i in range(8))
    gallery += '<img id="view-m1-s0" src="data:image/jpeg;base64,wrong-mode">'
    model_json = b'{"asset":{"version":"2.0"},"meshes":[{"primitives":[{}]}]}'
    model_json += b" " * (-len(model_json) % 4)
    glb = pack("<4sIII4s", b"glTF", 2, 20 + len(model_json), len(model_json), b"JSON") + model_json

    class FakeHub:
        def __init__(self, *, endpoint):
            assert endpoint == "https://huggingface.co"

        def get_zero_gpu_quota(self, *, token):
            quota_requests.append(token)
            remaining = first_quota if token == "token-1" else 80 - 20 * quota_requests.count(token)
            return SimpleNamespace(base=300, remaining=remaining, resets_at=None, overquota_used=None)

    class FakeSpace:
        def __init__(self, url, *, token, download_files, **_):
            assert url == trellis.SPACE_URL
            assert token in ("token-1", "token-2")
            self.token = token
            self.downloads = download_files

        def view_api(self, **_):
            return {"named_endpoints": dict.fromkeys(trellis.ENDPOINTS)}

        def close(self):
            assert self.downloads.is_dir()

        def predict(self, *args, api_name):
            jobs.append(api_name)
            if api_name == "/preprocess_image":
                assert args == (str(photo),)
                prepared = self.downloads / "prepared.png"
                prepared.write_bytes(photo.read_bytes())
                return str(prepared)
            if api_name == "/image_to_3d":
                assert args[:3] == (str(self.downloads.parent / "prepared.png"), 0, "512")
                if self.token == "token-1":
                    raise RuntimeError("You have exceeded your free ZeroGPU quota (120s requested vs. 90s left)")
                return gallery
            assert jobs == expected_jobs
            assert args == (100_000, 1024)
            if extraction_fails:
                raise RuntimeError("The upstream Gradio app has not enabled verbose error reporting")
            asset = self.downloads / "asset.glb"
            asset.write_bytes(glb)
            return str(asset), str(asset)

    monkeypatch.setitem(sys.modules, "gradio_client", SimpleNamespace(Client=FakeSpace, handle_file=lambda path: path))
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(HfApi=FakeHub))
    monkeypatch.setitem(sys.modules, "huggingface_hub.utils", SimpleNamespace(
        get_stored_tokens=lambda: {"first": "token-1", "second": "token-2", "third": "token-3"},
    ))

    if extraction_fails:
        with pytest.raises(ValueError, match="Space가 세부 오류를 제공하지 않음"):
            trellis.generate_mesh(photo, output, config)
    else:
        trellis.generate_mesh(photo, output, config)
    manifest = json.loads((output / "generation.json").read_text(encoding="utf-8"))
    assert manifest["request"]["resolution"] == "512"
    assert manifest["request"]["seed"] == 0
    assert quota_requests == ["token-1", "token-2", "token-2", "token-2"]
    assert manifest["quota_remaining_seconds"] == {
        "before_generation": 60, "after_generation": 40, "after_extraction": 20,
    }
    assert [entry["index"] for entry in manifest["clay_views"]] == list(range(8))
    assert all((output / entry["path"]).read_bytes() == jpeg for entry in manifest["clay_views"])
    assert not any(secret in str(manifest) for secret in ("token-1", "token-2", "token-3"))

    if extraction_fails:
        assert manifest["model"] is None
        assert not (output / "model.glb").exists()
        with pytest.raises(ValueError, match="실패 기록"):
            trellis.generate_mesh(photo, output, output / "no-config.json")
    else:
        assert (output / "model.glb").read_bytes() == glb
        trellis.generate_mesh(photo, output, output / "no-config.json")
    with pytest.raises(ValueError, match="새 --out 경로"):
        trellis.generate_mesh(photo, output, config, resolution="1024")
    assert jobs == expected_jobs
    assert quota_requests == ["token-1", "token-2", "token-2", "token-2"]


def test_all_accounts_exhausted_does_not_call_space(capsys):
    def get_quota(*, token):
        day = {"a": 28, "b": 27, "c": 29, "paid": 26}[token]
        return SimpleNamespace(
            base=2400 if token == "paid" else 300,
            remaining=2400 if token == "paid" else 10,
            overquota_used=None,
            resets_at=datetime(2026, 11, day, tzinfo=timezone.utc),
        )

    def unexpected_client(*_, **__):
        pytest.fail("접근 가능한 무료 잔량이 없어 Space를 호출하면 안 됩니다.")

    with pytest.raises(ValueError, match="2026-11-27 09:00 KST"):
        trellis.next_result(
            None, None, ["a", "b", "c", "paid"], {"a": "a", "b": "b", "c": "c", "paid": "paid"},
            SimpleNamespace(get_zero_gpu_quota=get_quota), unexpected_client, None,
        )
    notices = capsys.readouterr().out
    assert notices.count("건너뜁니다") == 3
    assert "무료 계정으로 확인되지 않았습니다" in notices


@pytest.mark.parametrize("message, reason", [
    ("You have exceeded your GPU quota (0s left vs. 120s requested)", "ZeroGPU 잔량 부족"),
    ("You have exceeded your free ZeroGPU quota (120s requested vs. 90s left)", "ZeroGPU 잔량 부족"),
    ("You have exceeded your ZeroGPU runs limit.", "ZeroGPU 실행 횟수 한도"),
])
def test_quota_rejection_only_allows_switching_before_generation(message, reason):
    def rejected():
        raise RuntimeError(message)

    with pytest.raises(trellis.QuotaRejected, match=reason):
        trellis.checked_call("전처리", rejected)
    with pytest.raises(trellis.QuotaRejected, match=reason):
        trellis.checked_call("메시 생성", rejected)
    with pytest.raises(ValueError, match="GLB 추출 단계") as error:
        trellis.checked_call("GLB 추출", rejected)
    assert not isinstance(error.value, trellis.QuotaRejected)
