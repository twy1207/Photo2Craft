# 출처와 라이선스

확인일: 2026-11-22. 외부 프로젝트 코드를 복사하지 않고 표현 방식과 실험 설계의 참고 자료로 읽었다. 이 파일은 법률적 판단이나 전체 의존성 감사가 아니다.

## 직접 사용

| 항목 | 역할 | 출처·라이선스 |
|---|---|---|
| Pillow 13.0.0 | 사진 처리와 비교 PNG | [Pillow](https://github.com/python-pillow/Pillow), [MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| Pydantic 2.14.3 | 계획 구조와 관계 검증 | [Pydantic](https://github.com/pydantic/pydantic), [MIT](https://github.com/pydantic/pydantic/blob/main/LICENSE) |
| pytest 9.2.0 | 최소 회귀 검증, 개발 의존성 | [pytest](https://github.com/pytest-dev/pytest), MIT |
| Gemini API | 사진에서 계획 생성 | [구조화 출력](https://aistudio.google.com/docs/structured-output), [모델](https://aistudio.google.com/docs/models/gemini-3.8-flash), [한도](https://aistudio.google.com/docs/rate-limits), [약관](https://ai.google.dev/gemini-api/terms) |

## 사진

| 사례 | 촬영자 | 출처·라이선스 |
|---|---|---|
| American Gothic House | Ser Amantio di Nicolao | [원본 페이지](https://commons.wikimedia.org/wiki/File:American_Gothic_House_-_front_of_house.jpg), CC0-1.0 |
| Rietveld-Schröderhuis | Luctor | [원본 페이지](https://commons.wikimedia.org/wiki/File:Rietveld-Schr%C3%B6derhuis.jpg), Public domain / PD-self |

각 `examples/<사례>/source.json`에 URL, 변경 사항, 해시가 있다. 사진은 보존 브랜치 `codex/prototype-v0`의 축소본을 그대로 가져왔고 원본 페이지의 라이선스를 다시 확인했다. 사진과 출처 정보만 재사용했으며 이전 계획·코드·결과는 가져오지 않았다. 축소본은 최대 1280px JPEG이며 EXIF가 제거되어 있다. [CC0 설명](https://creativecommons.org/publicdomain/zero/1.0/).

## 접근법 참고

- [AIConstructor](https://github.com/alanlapid/AIConstructor): 도형을 포함한 JSON 계획. GitHub 표시 GPL-3.0.
- [mcbuild](https://github.com/harrynull/mcbuild): 여러 시점 렌더와 피드백. GitHub 표시 MIT.
- [APT 코드](https://github.com/spearsheep/APT-Architectural-Planning-LLM-Agent), [논문](https://arxiv.org/html/2411.17255v2): 계획과 평가, 시각적 충실도 한계. 저장소 라이선스는 GitHub 메타데이터에서 식별되지 않았고 코드 도입 없음. 논문 페이지는 CC BY 4.0 표시.
- [BlockShot](https://github.com/VecetyP/BlockShot): 깊이·점군에서 복셀로 변환. GitHub 표시 MIT.
- [Make the Schem](https://github.com/riqqu/maketheschem): 복셀 미리보기·편집·내보내기. GitHub 표시 MIT.

위 프로그램들을 직접 실행해 비교 검증하지 않았다. 앞으로 코드를 도입한다면 해당 커밋의 실제 라이선스와 파일별 조건을 확인해야 한다. Minecraft 텍스처나 게임 파일은 동봉하지 않는다. 이 프로젝트 자체의 공개 배포 라이선스는 제출 준비 때 별도로 정한다.
