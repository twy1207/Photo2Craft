# 출처와 라이선스

최초 확인 2026-11-22. 웹 뷰어 출처는 2026-11-23, 메시·배경 제거 실험 출처는 2026-11-25에 추가했다. Three.js 배포 파일 일부를 라이선스와 함께 동봉한다.

## 직접 사용

| 항목 | 역할 | 출처·라이선스 |
|---|---|---|
| Pillow 13.0.0 | 사진 처리와 비교 PNG | [Pillow](https://github.com/python-pillow/Pillow), [MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| Pydantic 2.14.3 | 계획 구조와 관계 검증 | [Pydantic](https://github.com/pydantic/pydantic), [MIT](https://github.com/pydantic/pydantic/blob/main/LICENSE) |
| pytest 9.2.0 | 최소 회귀 검증, 개발 의존성 | [pytest](https://github.com/pytest-dev/pytest), MIT |
| Three.js 0.187.0 | 브라우저의 블록 3D 렌더링·OrbitControls | [공식 저장소](https://github.com/mrdoob/three.js), MIT. 원문 [LICENSE](photo2craft/web/vendor/three/LICENSE) 동봉 |
| Gemini API | 사진에서 계획 생성 | [구조화 출력](https://aistudio.google.com/docs/structured-output), [모델](https://aistudio.google.com/docs/models/gemini-3.8-flash), [한도](https://aistudio.google.com/docs/rate-limits), [약관](https://ai.google.dev/gemini-api/terms) |

Three.js는 [npm 배포본](https://registry.npmjs.org/three/-/three-0.187.0.tgz)의 SHA-512 무결성을 확인한 뒤 `three.module.js`, `three.core.js`, `OrbitControls.js`, `LICENSE`만 변경 없이 복사했다. 버전·URL·파일별 SHA-256은 [provenance.json](photo2craft/web/vendor/three/provenance.json)에 있다. 실행 중 CDN에 접속하지 않는다. 구현 참고: [공식 문서](https://threejs.org/docs/), InstancedMesh와 OrbitControls. Python 서버는 표준 라이브러리를 사용하며 새 Python 의존성은 추가하지 않았다.

## 별도 실험에서 사용

| 항목 | 역할 | 출처·라이선스 |
|---|---|---|
| TRELLIS.2 | 공식 Space에서 입력 전처리, 3D 생성과 GLB 추출 | [Space](https://huggingface.co/spaces/microsoft/TRELLIS.2), [코드 라이선스 MIT](https://github.com/microsoft/TRELLIS.2/blob/main/LICENSE), [모델 카드 MIT](https://huggingface.co/microsoft/TRELLIS.2-4B) |
| trimesh 5.2.2 | 로컬 실험의 GLB 삼각형 읽기 | [공식 저장소와 MIT 라이선스](https://github.com/mikedh/trimesh) |
| rembg 2.0.88 | 슈뢰더 사진의 로컬 배경 제거 비교 | [rembg MIT](https://github.com/danielgatis/rembg/blob/main/LICENSE.txt), [U²-Net 원본 코드 Apache-2.0](https://github.com/xuebinqin/U-2-Net/blob/master/LICENSE), [BiRefNet Lite 모델 카드 MIT](https://huggingface.co/ZhengPeng7/BiRefNet_lite) |

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
