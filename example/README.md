# 참고용 실제 예시 (수동 수집)

자동 파이프라인 로직을 실제 사례와 대조해서 튜닝하기 위한 참고 자료.
자동 파이프라인 산출물이 아니라 사람이 직접 캡쳐/작성해서 공유한 예시이며,
라이브 사이트(GitHub Pages)에는 게시되지 않는다.

- `articles/`, `infographics/` — (2026-07-08~07-14 수집분, 유형별 분류) 일반 기사형/순수
  인포그래픽형 캡쳐. 이후 `captures/`로 방식이 바뀌었으므로 새로 받는 캡쳐는 여기 추가하지 않는다.
- `captures/{날짜}/` — (2026-07-21~ 수집분) **받은 순서 그대로** `01_`, `02_`... 번호를 매겨 저장.
  같은 이슈/주제의 기사와 인포그래픽이 함께 묶여서 순서대로 오기 때문에, 유형별로 나누지 않고
  원래 순서를 그대로 보존한다 (예: 기사 → 그 기사와 관련된 인포그래픽 → 다음 이슈로 넘어감).
- `briefings/` — 날짜별 정치/정당/경제 헤드라인+링크 텍스트 브리핑 (사람이 직접 고른 "정답" 기사 목록)

각 이미지 파일명 형식: `{순번}_{언론사(있으면)}_{내용요약}.{ext}` (captures/), 또는
`{날짜}_{언론사(있으면)}_{내용요약}.{ext}` (articles/, infographics/, 구버전)

## 용도

- `articles/`, `infographics/`, `captures/`: `capture_images.py`의 `INFOGRAPHIC_TEXT_THRESHOLD`,
  `INFOGRAPHIC_RATIO_THRESHOLD` 등 판별 기준값이나 `HEADER_SELECTORS`/`BODY_SELECTORS`를
  보정할 때, "실제로 사람이 인포그래픽/기사로 분류한 사례가 이렇게 생겼다"는 정답 세트로 참고한다.
  `captures/`는 추가로 원래 순서(이슈별 묶음)까지 보존하고 있어 정렬/그룹핑 로직에도 참고할 수 있다.
- `briefings/`: `collect_links.py`의 기사 선정 스코어링(`NAMED_FIGURES`, `QUOTE_CHARS`,
  `PRIORITY_TAGS`, `PRESS_DOMAINS` 등)을 보정할 때, "사람이 직접 고르면 어떤 기사가
  뽑히는지"를 보여주는 정답 세트로 참고한다.
