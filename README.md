# Photo2Craft

건물 사진의 비율과 특징을 Minecraft 블록 건축물로 옮기는 프로젝트다.

- **웹 데모**에서는 저장된 TRELLIS.2 블록 결과를 사진 및 Clay와 비교할 수 있다. 처음 내려받은 저장소에서는 동봉된 계획 예제를 바로 볼 수 있다.
- **사진 생성 CLI**는 공식 TRELLIS.2 Space에서 GLB와 Clay 미리보기를 받는다. 주택 렌더로 해상도 512 생성을 확인했다.
- **GLB 변환 CLI**는 메시를 블록으로 옮기고 Clay 윤곽과 GLB의 넓은 표면을 기준으로 다듬는다. 웹에서 같은 시점의 보정 전후를 비교할 수 있다.
- **Minecraft 배치 실험**에서는 저장된 고딕 GLB에서 만든 6,372블록을 Java Edition 26.3에 배치했다. [검증 결과](EXPERIMENTS.md)

## 키 없이 웹 데모 실행

Windows와 Python 3.12 기준으로 저장소 루트에서 실행한다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m photo2craft.cli serve
```

[로컬 뷰어](http://127.0.0.1:8000)에서 드래그로 회전하고 휠로 확대한다. 정면·오른쪽·뒷면 버튼으로 시점을 바꿀 수 있다. 초기 설치 후 실행에는 API 키와 인터넷 연결이 필요 없다. 종료는 `Ctrl+C`, 포트 지정은 `--port 8001`이다.

개발 환경의 `.local/trellis/`에 저장된 결과를 기본으로 표시한다. **박공지붕 주택**은 512로 재생성한 결과와 Clay 8장을 최장변 48블록에서 볼 수 있다. **비대칭 평지붕 건물**은 64블록으로 열리며 **최장변**에서 48·56·64를 바꿀 수 있다. 폴더가 없는 건물은 동봉된 Gemini 계획 예제로 열린다.

동봉된 계획 예제를 CLI에서 재생성하려면 아래 명령을 실행한다. 출력 폴더의 `blocks.json`에는 좌표와 재질이 들어간다. [동봉 예제 검증](docs/validation/viewer-20261123.md)

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

## 저장된 GLB를 블록으로 변환하고 비교

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[mesh]"
.\.venv\Scripts\python.exe -m photo2craft.cli voxelize .local\trellis\gothic-cli\model.glb --photo examples\gothic\photo.jpg --clay .local\trellis\gothic-cli\clay --out outputs\gothic-mesh
.\.venv\Scripts\python.exe -m photo2craft.cli serve --mesh-result outputs\gothic-mesh
```

위 명령은 앞 단계에서 받은 GLB를 사용한다. 다른 GLB로 실행하려면 입력과 출력 경로를 바꾼다. 출력 경로는 새 폴더로 지정한다. `--photo`와 `--clay`는 선택 사항이며, `--clay`에는 같은 GLB와 함께 받은 Clay 폴더를 지정한다. 기본 최장변은 48블록이며 `--extent`로 16~64블록을 설정할 수 있다. `--front-yaw`는 모델을 수평으로 회전하는 각도다.

메시 표면을 흰색 콘크리트 블록으로 변환하고 자동 보정을 적용한다. Clay로 외곽 잡음을 정리할 때 GLB에서 이어진 지붕과 벽의 같은 높이의 줄을 보호한다. 이후에는 GLB의 깊이·경사와 블록 연결성을 기준으로 표면을 정리하고, 지면 높이가 확인된 벽 아래 틈을 메운다. `blocks.json`은 최종 결과이며 `blocks-before.json`은 보정 전 변환본이다. [로컬 뷰어](http://127.0.0.1:8000)에서 **보정 전**과 **보정 후**를 같은 Clay 시점으로 비교할 수 있다. 변환과 비교는 API 키 없이 로컬에서 실행한다.

GLB 결과의 **블록 편집**에서 **영역 선택** 또는 **블록 하나**를 고른다. 영역 선택은 3D 화면에서 서로 마주 보는 두 모서리 블록을 클릭한다. 선택된 직육면체의 블록을 주황색으로 확인하고 **선택 제거**로 적용한다. **되돌리기**는 직전 제거를 취소한다. **블록 JSON 저장**으로 편집본을 내려받을 수 있다. 편집 상태는 탭을 새로고침하면 초기화된다.

[실험 기록](EXPERIMENTS.md) · [출처와 라이선스](REFERENCES.md)
