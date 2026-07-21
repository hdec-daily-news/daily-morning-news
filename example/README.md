# 참고용 실제 예시 (수동 수집)

자동 파이프라인 로직을 실제 사례와 대조해서 튜닝하기 위한 참고 자료.
자동 파이프라인 산출물이 아니라 사람이 직접 캡쳐/작성해서 공유한 예시이며,
라이브 사이트(GitHub Pages)에는 게시되지 않는다.

- `articles/` — 일반 기사형 캡쳐(언론사명·헤드라인·날짜(+리드 요약) + 대표사진)
- `infographics/` — 순수 인포그래픽형 캡쳐(헤더 없이 차트/표 이미지 자체가 핵심 정보)
- `briefings/` — 날짜별 정치/정당/경제 헤드라인+링크 텍스트 브리핑 (사람이 직접 고른 "정답" 기사 목록)

각 이미지 파일명 형식: `{날짜}_{언론사(있으면)}_{내용요약}.{ext}`

## 용도

- `articles/`, `infographics/`: `capture_images.py`의 `INFOGRAPHIC_TEXT_THRESHOLD`,
  `INFOGRAPHIC_RATIO_THRESHOLD` 등 판별 기준값이나 `HEADER_SELECTORS`/`BODY_SELECTORS`를
  보정할 때, "실제로 사람이 인포그래픽/기사로 분류한 사례가 이렇게 생겼다"는 정답 세트로 참고한다.
- `briefings/`: `collect_links.py`의 기사 선정 스코어링(`NAMED_FIGURES`, `QUOTE_CHARS`,
  `PRIORITY_TAGS`, `PRESS_DOMAINS` 등)을 보정할 때, "사람이 직접 고르면 어떤 기사가
  뽑히는지"를 보여주는 정답 세트로 참고한다.
