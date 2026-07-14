# 참고용 실제 캡쳐 예시 (수동 수집)

`capture_images.py`의 캡쳐/인포그래픽 판별 로직을 실제 네이버 기사와 대조해서
튜닝하기 위한 참고 자료. 자동 파이프라인 산출물이 아니라 사람이 직접 캡쳐해서
공유한 예시이며, 라이브 사이트(GitHub Pages)에는 게시되지 않는다.

- `articles/` — 일반 기사형(언론사명·헤드라인·날짜(+리드 요약) + 대표사진)
- `infographics/` — 순수 인포그래픽형(헤더 없이 차트/표 이미지 자체가 핵심 정보)

각 파일명 형식: `{날짜}_{언론사(있으면)}_{내용요약}.{ext}`

## 용도

`capture_images.py`의 `INFOGRAPHIC_TEXT_THRESHOLD`, `INFOGRAPHIC_RATIO_THRESHOLD`
등 판별 기준값이나 `HEADER_SELECTORS`/`BODY_SELECTORS`를 보정할 때,
"실제로 사람이 인포그래픽/기사로 분류한 사례가 이렇게 생겼다"는 정답 세트로 참고한다.
