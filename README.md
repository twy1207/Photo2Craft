# Photo2Craft

건물 사진의 특징을 마인크래프트 블록 건축물로 옮기는 개인 텀프로젝트.
현재는 새 설계의 작은 생성 실험 단계이며, 웹 편집·게임 내보내기는 아직 구현하지 않았다. **두 사진에서 서로 다른 지붕과 일부 특징이 나왔지만, 충분한 사진 유사도를 확보하지 못했다.**

| 사진 | 입력과 생성 결과 | 확인한 한계 |
|---|---|---|
| 박공지붕 주택 | [비교 이미지](examples/gothic/run-04/comparison.png) | 현관 기둥·굴뚝·옆면 창 누락, 현관 지붕 높이 오류 |
| 비대칭 평지붕 건물 | [비교 이미지](examples/schroder/replay-01/comparison.png) | 상자 형태로 단순화, 면의 후퇴·돌출과 창 비율 오류, 빨간 부재 매몰 |

실행 과정과 실패 기록은 [EXPERIMENTS.md](EXPERIMENTS.md)에 있다. 동봉 결과는 사진에서 얻은 AI 응답이며 계획을 사진별로 수작업 수정하지 않았다.

## 현재 구현

- 부모 본체의 크기를 기준으로 부품 크기와 위치를 계산한다.
- 평지붕·박공지붕과 벽면에 붙는 창/문/색상 패널을 블록으로 만든다.
- 저장된 계획으로 블록 JSON과 사진 비교 PNG를 생성한다. Minecraft 텍스처는 사용하지 않는다.
- Gemini 이미지 분석과 실제 응답 저장, 응답 재검증·재생성을 지원한다. 분석의 관찰/추정 표시는 모델의 진술이며 사실 확인을 보장하지 않는다.
- 자동 검증은 부품 부착, 잘못된 참조, 지붕 위 빈 공간에 생기는 세부 블록 방지의 3개 항목만 있다. 사진 유사도 검증과는 별개다.

## 실행 준비 (Windows / Python 3.12)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

설치가 끝나면 아래 두 명령은 **API 키와 네트워크 없이** 동봉 결과를 다시 생성한다. 설치에는 패키지 다운로드가 필요하다.

```powershell
.\.venv\Scripts\python.exe -m photo2craft.cli build examples\gothic\run-04\plan.json --photo examples\gothic\run-04\input.jpg --out outputs\gothic-demo
.\.venv\Scripts\python.exe -m photo2craft.cli build examples\schroder\replay-01\plan.json --photo examples\schroder\run-01\input.jpg --out outputs\schroder-demo
```

출력 폴더의 `comparison.png`를 열어 사진/입력 쪽 시점/정면/반대쪽을 확인한다. `blocks.json`은 좌표·팔레트·생성 부품 ID를 담는 자체 형식으로, 게임 파일 형식은 아직 아니다. `summary.json`은 구조 경고, `build.json`은 입력·소스 해시와 실행 의존성을 담는다.

## 새 사진 분석

환경 변수 `GEMINI_API_KEY`를 준비한 뒤 실행한다. 키를 명령 인자나 저장소에 넣지 않는다. `.env` 자동 로딩은 없다. 사진과 요구사항은 Google API로 전송된다. 무료 티어 데이터 취급은 [Google 약관](https://ai.google.dev/gemini-api/terms)을 따른다.

```powershell
.\.venv\Scripts\python.exe -m photo2craft.cli analyze path\to\photo.jpg --out outputs\new-run
# 선택적 요구사항: --requirements "Use a warm stone palette"
# 모델 명시: --model gemini-3.8-flash
```

기본 모델은 첫 실험에서 요청이 성공한 `gemini-3.5-flash-lite`다. `gemini-3.8-flash`는 당시 503 오류가 두 번 발생했으며 품질 비교는 못 했다. 계정별 무료 티어와 한도는 AI Studio에서 확인해야 한다. 자동 재시도·유료 모델 전환은 없다. 분석은 기존 출력 폴더를 덮어쓰지 않는다.

`request.json`, `prompt.txt`, 실제 전송된 `input.jpg`, 응답을 받은 경우 `response.json`이 보존된다. 로컬 검증을 통과하면 `plan.json`과 비교 결과가 추가된다. API에는 간단한 타입 구조만 전달하고, 재질·배열 길이·관계 등은 로컬에서 검증한다. 검사 실패를 성공으로 숨기지 않는다.

저장된 원본 응답을 현재 검증 규칙으로 다시 읽을 수도 있다. 아래 명령은 새 출력 폴더를 요구하며 API를 호출하지 않는다.

```powershell
.\.venv\Scripts\python.exe -m photo2craft.cli replay examples\schroder\run-01\response.json --photo examples\schroder\run-01\input.jpg --out outputs\schroder-replay
```

## 현재 표현의 한계

직선 부품, 평지붕, 박공지붕과 벽면 패치만 표현한다. 회전된 매스, 곡면, 박공의 뾰족한 창, 경사진 현관 지붕, 실제 작동하는 문, 내부 공간의 연결은 구현하지 않았다. 보이지 않는 면은 AI의 추정이며, 이번 결과에서는 대부분 빈 벽으로 남았다. 세부 부품이 같은 자리를 차지하면 잘리거나 묻힐 수 있으며 경고만 제공한다.

비교 PNG는 투영법·유리 표현이 실제 게임과 다르고 입력 카메라를 복원하지 않는다. 평평한 단색 면은 개별 블록 경계가 생략되어 보이지만 실제 출력은 정수 좌표의 블록 목록이다. 3개 자동 테스트와 두 사례의 재생성은 일반적인 사진 유사도·실제 게임 호환성의 검증이 아니다.

작업 지침은 [AGENTS.md](AGENTS.md), 자료·사진·라이선스는 [REFERENCES.md](REFERENCES.md)를 참고한다. 이전 프로토타입은 `codex/prototype-v0`에 보존되어 있으며 그 테스트와 실험은 새 구현의 검증 결과가 아니다.
