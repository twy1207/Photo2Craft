# Photo2Craft

건물 사진의 특징을 마인크래프트 블록 건축물로 옮기는 개인 텀프로젝트.
현재는 새 설계의 작은 생성 실험 단계이며, 웹 편집·게임 내보내기는 아직 구현하지 않았다.

## 현재 구현

- 부모 본체의 크기를 기준으로 부품 크기와 위치를 계산한다.
- 평지붕·박공지붕과 벽면에 붙는 창/문/색상 패널을 블록으로 만든다.
- 저장된 계획으로 블록 JSON과 사진 비교 PNG를 생성한다. Minecraft 텍스처는 사용하지 않는다.
- 자동 검증은 부품 부착, 잘못된 참조, 지붕 위 빈 공간에 생기는 세부 블록 방지의 3개 항목만 있다. 사진 유사도 검증과는 별개다.

## 실행 준비 (Windows / Python 3.12)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

저장된 계획이 있으면 API 없이 다시 생성할 수 있다.

```powershell
.\.venv\Scripts\python.exe -m photo2craft.cli build path\to\plan.json --photo path\to\photo.jpg --out outputs\sample
```

현재 공통 블록 데이터는 좌표·팔레트·생성 부품 ID를 담은 `blocks.json`이다. 게임 파일 형식은 아직 아니다. 비교 PNG는 투영법·유리 표현이 실제 게임과 다르며 입력 사진의 카메라를 복원하지 않는다.

작업 지침은 [AGENTS.md](AGENTS.md), 자료·사진·라이선스는 [REFERENCES.md](REFERENCES.md)를 참고한다. 이전 프로토타입은 `codex/prototype-v0`에 보존되어 있으며 그 테스트와 실험은 새 구현의 검증 결과가 아니다.
