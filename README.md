# Photo2Craft

건물 사진의 비율과 특징을 Minecraft 블록 건축물로 옮기는 프로젝트다.

- **웹 데모**에서는 동봉된 건축 계획을 블록으로 변환하고 3D로 비교할 수 있다.
- **사진 생성 CLI**는 공식 TRELLIS.2 Space에서 GLB와 Clay 미리보기를 요청한다. 새 사진의 512 생성은 실제 테스트에서 서비스 오류로 중단됐다.
- **Minecraft 배치 실험**에서는 저장된 고딕 GLB에서 만든 6,372블록을 Java Edition 26.3에 배치했다. GLB 변환의 웹 연결, 편집, 게임 파일 자동 내보내기는 다음 구현 범위다. [검증 결과](EXPERIMENTS.md)

## 키 없이 웹 데모 실행

Windows와 Python 3.12 기준으로 저장소 루트에서 실행한다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m photo2craft.cli serve
```

[로컬 뷰어](http://127.0.0.1:8000)에서 고딕 주택 기본·부품 추가 결과와 슈뢰더 주택을 사진과 함께 볼 수 있다. 드래그로 회전하고 휠로 확대한다. 정면·오른쪽·뒷면 버튼으로 시점을 바꿀 수 있다. 초기 설치 후 실행에는 API 키와 인터넷 연결이 필요 없다. 종료는 `Ctrl+C`, 포트 지정은 `--port 8001`이다.

![로컬 3D 뷰어](docs/validation/viewer-20261123.jpg)

같은 블록을 CLI에서 재생성하려면 아래 명령을 실행한다. 출력 폴더의 `blocks.json`에는 좌표와 재질이 들어간다. [동봉 예제 검증](docs/validation/viewer-20261123.md)

```powershell
.\.venv\Scripts\python.exe -m photo2craft.cli build examples\gothic\run-04\plan.json --photo examples\gothic\run-04\input.jpg --out outputs\gothic-demo
```

## 사진으로 GLB와 Clay 요청

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[trellis]"
.\.venv\Scripts\python.exe -m photo2craft.cli trellis-auth
.\.venv\Scripts\python.exe -m photo2craft.cli generate-mesh examples\gothic\photo.jpg --out .local\trellis\gothic-cli
```

`HF token:`에 무료 계정 토큰을 하나씩 붙여넣고 마지막에 빈 Enter를 누른다. 토큰은 프로젝트 밖의 `%USERPROFILE%\.photo2craft\hf-tokens.txt`에 저장된다. 저장 개수는 `trellis-auth --list`로 확인한다. 세분화 토큰에는 ZeroGPU 잔량을 조회할 권한이 필요하다. [Hugging Face 잔량 조회 안내](https://huggingface.co/docs/huggingface_hub/main/guides/manage-spaces#track-your-zerogpu-quota)

CLI는 입력 사진을 공식 TRELLIS.2 Space에 전송한다. 기본값은 **해상도 512, 목표 100,000면, 텍스처 1024, 시드 0**이다. `--resolution 1024`로 비교할 수 있다. 등록 순서대로 무료 GPU 잔량이 60초 이상인 토큰에서 시작하며 Space의 실행 횟수 제한도 적용된다.

완료하면 `model.glb`, `clay/view-00.jpg`~`view-07.jpg`, `generation.json`을 저장한다. GLB 추출에 실패해도 이미 받은 Clay와 오류 기록은 남긴다. 같은 사진과 설정으로 같은 출력 경로를 사용하면 완료된 결과를 재사용한다.

[실험 기록](EXPERIMENTS.md) · [출처와 라이선스](REFERENCES.md)
