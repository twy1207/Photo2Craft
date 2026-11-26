# 출처와 라이선스

## 실행 의존성과 서비스

| 항목 | 역할 | 출처·라이선스 |
|---|---|---|
| Pillow 13.0.0 | 사진 처리와 비교 PNG | [Pillow](https://github.com/python-pillow/Pillow), [MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| Pydantic 2.14.3 | 계획 구조와 관계 검증 | [Pydantic](https://github.com/pydantic/pydantic), [MIT](https://github.com/pydantic/pydantic/blob/main/LICENSE) |
| pytest 9.2.0 | 최소 회귀 검증, 개발 의존성 | [pytest](https://github.com/pytest-dev/pytest), MIT |
| Three.js 0.187.0 | 브라우저의 블록 3D 렌더링·OrbitControls | [공식 저장소](https://github.com/mrdoob/three.js), MIT. 원문 [LICENSE](photo2craft/web/vendor/three/LICENSE) 동봉 |
| Gradio Client 2.7.2 | TRELLIS.2 전처리·생성·추출 세션과 파일 다운로드 | [Gradio Python Client](https://www.gradio.app/docs/python-client/client), Apache-2.0 |
| Hugging Face Hub 2.4.0 | 로컬 토큰과 ZeroGPU 무료 잔량 조회 | [공식 Python 클라이언트](https://github.com/huggingface/huggingface_hub), Apache-2.0 |
| TRELLIS.2 Space | 사진 전처리, 메시 생성, Clay 미리보기와 GLB 추출 | [Space 소스](https://huggingface.co/spaces/microsoft/TRELLIS.2/blob/main/app.py), [코드 라이선스 MIT](https://github.com/microsoft/TRELLIS.2/blob/main/LICENSE), [모델 카드 MIT](https://huggingface.co/microsoft/TRELLIS.2-4B) |
| NumPy 2.5.5 | 삼각형과 블록의 교차 계산, Clay 실루엣 비교 | [공식 저장소](https://github.com/numpy/numpy), [BSD-3-Clause](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| trimesh 5.2.2 | GLB 삼각형과 장면 좌표 읽기 | [공식 저장소와 MIT 라이선스](https://github.com/mikedh/trimesh) |

Three.js 파일과 MIT 라이선스는 npm 배포본에서 가져왔다. 버전, 원본 URL과 파일별 해시는 동봉된 기록에서 확인할 수 있다. [Three.js 출처 기록](photo2craft/web/vendor/three/provenance.json)

Clay 시점을 맞출 때 공식 TRELLIS.2 코드의 카메라 배치와 GLB 축 변환을 참고했다. [카메라 배치](https://github.com/microsoft/TRELLIS.2/blob/main/trellis2/utils/render_utils.py#L93-L99) · [GLB 축 변환](https://github.com/microsoft/TRELLIS.2/blob/main/o-voxel/o_voxel/postprocess.py#L297-L306)

## 실험 도구

| 항목 | 역할 | 출처·라이선스 |
|---|---|---|
| Gemini API | 동봉 예제의 건축 계획을 만든 초기 실험 | [구조화 출력](https://aistudio.google.com/docs/structured-output), [약관](https://ai.google.dev/gemini-api/terms) |
| rembg 2.0.88 | 슈뢰더 사진의 로컬 배경 제거 비교 | [rembg MIT](https://github.com/danielgatis/rembg/blob/main/LICENSE.txt), [U²-Net 원본 코드 Apache-2.0](https://github.com/xuebinqin/U-2-Net/blob/master/LICENSE), [BiRefNet Lite 모델 카드 MIT](https://huggingface.co/ZhengPeng7/BiRefNet_lite) |

## 사진

| 사례 | 촬영자 | 출처·라이선스 |
|---|---|---|
| American Gothic House | Ser Amantio di Nicolao | [원본 페이지](https://commons.wikimedia.org/wiki/File:American_Gothic_House_-_front_of_house.jpg), CC0-1.0 |
| Rietveld-Schröderhuis | Luctor | [원본 페이지](https://commons.wikimedia.org/wiki/File:Rietveld-Schr%C3%B6derhuis.jpg), Public domain / PD-self |

각 `examples/<사례>/source.json`에 URL, 변경 사항, 해시가 있다. 사진은 보존 브랜치 `codex/prototype-v0`의 축소본을 그대로 가져왔고 원본 페이지의 라이선스를 다시 확인했다. 사진과 출처 정보만 재사용했으며 이전 계획·코드·결과는 가져오지 않았다. 축소본은 최대 1280px JPEG이며 EXIF가 제거되어 있다. [CC0 설명](https://creativecommons.org/publicdomain/zero/1.0/).

초기 조사 자료는 Git 이력에 있다. [과거 출처와 참고 목록](https://github.com/twy1207/Photo2Craft/blob/2760722cdd59c4be2fe0a3cd1a469eb73f9bb2ec/REFERENCES.md)
