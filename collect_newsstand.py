# -*- coding: utf-8 -*-
"""
프로젝트1 보강: 네이버 뉴스스탠드에서 각 언론사가 "오늘의 메인"으로 직접 편집해 올린
기사 중 정치 기사를 추출해 data/links.json의 politics_main 섹터를 대체한다.

배경(2026-07-28): 검색 API("정치"/"국회"/"여야" 키워드) 기반 politics_main은
역사 칼럼·해외 단신·오피니언이 섞여 들어와 휴먼픽과 겹침이 0건이었다.
뉴스스탠드는 언론사 편집자가 고른 대표 기사라서 이런 오탐이 구조적으로 적다.

수집 방식(1차 실행 디버그 덤프 분석으로 확정, 2026-07-28):
뉴스스탠드 메인(?list=ct2)은 언론사 카드를 iframe으로 렌더링하는데, 각 카드는
  https://newsstand.naver.com/include/page/{언론사코드}.html
라는 독립 정적 HTML이다 (코드는 네이버뉴스 oid와 동일: 조선=023, 동아=020 등).
따라서 브라우저(Playwright) 없이 requests로 주요 언론사 코드별 카드 페이지를 직접
가져와 헤드라인 앵커를 파싱한다. 메인 페이지의 로테이션/모드(언론사보기·기사보기)와
무관하게 전체 언론사를 안정적으로 커버한다.

동작 원칙 (안전 폴백):
- collect_links.py 실행 *후*에 돌려서 politics_main만 갱신한다.
- 수집 실패하거나 정치 기사가 MIN_REQUIRED건 미만이면 기존(검색 API) 결과를 유지한다.
- NEWSSTAND=0 환경변수로 즉시 비활성화 가능(코드 되돌릴 필요 없음).
- 후보 0건이면 첫 카드 페이지 HTML을 data/newsstand_debug.html 로 저장해 보정에 쓴다.
"""
import json
import os
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from collect_links import (
    KST,
    NAMED_FIGURES,
    PARTY_EXCLUDE_KEYWORDS,
    score_article,
    shorten_url,
    SHORTEN_LINKS,
    _now_override,
)

CARD_URL = "https://newsstand.naver.com/include/page/{oid}.html"
DEBUG_HTML_PATH = "data/newsstand_debug.html"
CANDIDATES_PATH = "data/newsstand_candidates.json"  # 클러스터링 튜닝용 후보 전체 로그
# 뉴스스탠드 픽이 이 건수 미만이면 교체하지 않고 기존 검색 API 결과 유지
MIN_REQUIRED = 4
# 한 언론사가 politics_main을 잠식하지 않도록 언론사당 최대 채택 수 제한
MAX_PER_PRESS = 2

# politics_main 소스로 쓸 언론사와 뉴스스탠드 카드 코드(=네이버뉴스 oid).
# 휴먼 브리핑(example/briefings/) 정치 섹터에 실제 인용된 언론사 기준으로 구성
# (이데일리/디지털타임스/머니투데이는 경제지지만 휴먼 정치픽에 자주 등장해 포함).
PRESS_OIDS = {
    "023": "조선일보",
    "025": "중앙일보",
    "020": "동아일보",
    "028": "한겨레",
    "032": "경향신문",
    "005": "국민일보",
    "022": "세계일보",
    "021": "문화일보",
    "081": "서울신문",
    "469": "한국일보",
    "001": "연합뉴스",
    "003": "뉴시스",
    "421": "뉴스1",
    "079": "노컷뉴스",
    "119": "데일리안",
    "629": "더팩트",
    "018": "이데일리",
    "029": "디지털타임스",
    "008": "머니투데이",
    "052": "YTN",
    "055": "SBS",
    "056": "KBS",
    "214": "MBC",
}

# 휴먼 브리핑 4일치(example/briefings/)의 언론사 인용 빈도 순위(2026-07-28 집계).
# 같은 이슈(클러스터)를 여러 언론사가 다뤘을 때 이 순서 앞쪽 언론사 기사를 대표로 뽑는다.
# 목록에 없는 언론사는 맨 뒤 취급.
PREFERRED_PRESS_ORDER = [
    "중앙일보", "동아일보", "이데일리", "서울신문", "세계일보", "조선일보",
    "뉴스1", "한국일보", "더팩트", "뉴시스", "데일리안", "노컷뉴스",
    "디지털타임스", "국민일보", "문화일보", "머니투데이",
]
_PRESS_RANK = {p: i for i, p in enumerate(PREFERRED_PRESS_ORDER)}

# 링크에서 제거해도 기사 식별에 지장 없는 추적용 파라미터 (utm_* 는 접두사 매칭)
TRACKING_PARAM_KEYS = {"wlog_sub", "cp", "ref", "source", "sc_src", "OutUrl"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://newsstand.naver.com/",
}

# "정치 기사" 판별 키워드. 언론사 메인 카드에는 정치 외 기사도 섞여 있으므로
# 제목에 아래 키워드(또는 NAMED_FIGURES 실명)가 있어야 politics_main 후보로 삼는다.
POLITICS_KEYWORDS = [
    "대통령", "국회", "여야", "여당", "야당", "정당", "총리", "장관", "청와대", "靑", "與", "野",
    "특검", "선관위", "선거", "재검표", "개헌", "국정", "탄핵", "계엄", "전당대회",
    "당대표", "원내", "의원", "북한", "北", "한미", "안보", "외교", "국방", "파병",
    "국무회의", "필리버스터", "개각", "여의도",
    "민주당", "국민의힘",  # 후보에는 올리되 pick 단계에서 정당 섹터 중복 규칙 적용
]

UI_TEXT_PATTERNS = [
    "구독", "전체보기", "뉴스스탠드", "로그인", "바로가기", "이전", "다음",
    "펼쳐보기", "설정", "도움말", "공지", "언론사 편집", "기사보기", "언론사보기",
    "동영상", "날씨", "TV편성표",
]


def looks_like_headline(text):
    t = " ".join(text.split())
    if len(t) < 10:
        return False
    if any(p in t for p in UI_TEXT_PATTERNS):
        return False
    if not re.search(r"[가-힣]", t):
        return False
    return True


def fetch_press_card(oid):
    """언론사 카드 페이지 HTML을 가져온다. 실패 시 None."""
    url = CARD_URL.format(oid=oid)
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"[WARN] 카드 페이지 로드 실패({PRESS_OIDS.get(oid, oid)}): {e}")
        return None


def extract_card_headlines(html, oid, press):
    """카드 HTML에서 (press, title, link) 후보를 추출한다."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        if not looks_like_headline(text):
            continue
        if href.startswith("#") or href.lower().startswith("javascript"):
            continue
        link = urljoin(CARD_URL.format(oid=oid), href)
        title = " ".join(text.split())
        key = (link.split("?")[0], title)
        if key in seen:
            continue
        seen.add(key)
        out.append({"press": press, "title": title, "link": link})
    return out


def collect_headlines():
    """전 언론사 카드에서 헤드라인 후보를 모은다. (후보 목록, 첫 성공 HTML) 반환."""
    candidates = []
    first_html = None
    ok_cards = 0
    for oid, press in PRESS_OIDS.items():
        html = fetch_press_card(oid)
        if html is None:
            continue
        if first_html is None:
            first_html = html
        ok_cards += 1
        found = extract_card_headlines(html, oid, press)
        candidates.extend(found)
    print(f"[INFO] 카드 {ok_cards}/{len(PRESS_OIDS)}개 로드, 헤드라인 후보 {len(candidates)}건")
    return candidates, first_html


def strip_tracking(url):
    """utm_* 등 추적용 쿼리 파라미터만 제거한다 (기사 식별 파라미터는 보존)."""
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.startswith("utm_") and k not in TRACKING_PARAM_KEYS
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_STOPWORDS = {"기자", "단독", "속보", "종합", "영상", "포토", "인터뷰", "오늘", "내일"}


def title_tokens(title):
    t = re.sub(r"\[[^\]]*\]", " ", title)  # [단독] 등 태그 제거
    return {w for w in _TOKEN_RE.findall(t) if w not in _STOPWORDS}


def cluster_candidates(items):
    """제목 토큰이 2개 이상 겹치면 같은 이슈로 묶는다(그리디).
    반환: 클러스터 리스트(각각 기사 dict 리스트)."""
    clusters = []
    for it in items:
        toks = it["_tokens"]
        for cl in clusters:
            if any(len(toks & other["_tokens"]) >= 2 for other in cl):
                cl.append(it)
                break
        else:
            clusters.append([it])
    return clusters


def press_rank(press):
    return _PRESS_RANK.get(press, len(PREFERRED_PRESS_ORDER))


def pick_politics(candidates, links_data, count):
    """정치 기사만 골라 이슈 클러스터 단위로 추려낸다.

    선정 원리(2026-07-28, 휴먼픽 방식 반영):
    1) 같은 이슈를 메인에 건 언론사 수가 많은 클러스터 우선 ("종합해서 추려내기")
    2) 클러스터 대표 기사는 휴먼 브리핑 인용 빈도 순위(PREFERRED_PRESS_ORDER) 앞 언론사로
    3) 키워드 스코어는 동순위 타이브레이커로만 사용
    """
    existing_links = set()
    existing_titles = set()
    for s in links_data["sectors"]:
        for art in s["articles"]:
            existing_links.add(art.get("long_link") or art["link"])
            existing_links.add(art["link"])
            existing_titles.add(re.sub(r"^\[[^\]]+\]\s*", "", art["title"]))

    filtered = []
    seen_titles = set()
    for c in candidates:
        title = c["title"]
        if not any(kw in title for kw in POLITICS_KEYWORDS) and not any(f in title for f in NAMED_FIGURES):
            continue
        # 정당 브랜드가 뚜렷한 기사는 dp/ppp 섹터 소관 (collect_links.py와 동일 규칙)
        if any(kw in title for kw in PARTY_EXCLUDE_KEYWORDS):
            continue
        if c["link"] in existing_links or title in existing_titles or title in seen_titles:
            continue
        seen_titles.add(title)
        filtered.append(
            {
                "press": c["press"],
                "title": title,
                "link": strip_tracking(c["link"]),
                "_score": score_article(title),
                "_tokens": title_tokens(title),
            }
        )

    clusters = cluster_candidates(filtered)
    # 클러스터 정렬: (커버 언론사 수 ↓, 최고 키워드 스코어 ↓) — 등장 순서는 stable로 유지
    clusters.sort(
        key=lambda cl: (len({a["press"] for a in cl}), max(a["_score"] for a in cl)),
        reverse=True,
    )

    picked, per_press = [], {}
    for cl in clusters:
        # 대표 기사: 선호 언론사 순위 → 키워드 스코어 순
        reps = sorted(cl, key=lambda a: (press_rank(a["press"]), -a["_score"]))
        rep = next((a for a in reps if per_press.get(a["press"], 0) < MAX_PER_PRESS), None)
        if rep is None:
            continue
        per_press[rep["press"]] = per_press.get(rep["press"], 0) + 1
        picked.append(
            {
                "title": f"[{rep['press']}] {rep['title']}",
                "link": rep["link"],
                "pubDate": "",  # 카드에는 발행 시각이 없음 (언론사가 '지금' 걸어둔 메인)
                "coverage": len({a["press"] for a in cl}),
            }
        )
        if len(picked) >= count:
            break
    return picked, clusters


def dump_candidates(clusters, path=CANDIDATES_PATH):
    """클러스터링 결과 전체를 저장한다 (휴먼픽과 대조해 기준을 보정하기 위한 로그)."""
    out = [
        {
            "presses": sorted({a["press"] for a in cl}),
            "articles": [{"press": a["press"], "title": a["title"], "link": a["link"], "score": a["_score"]} for a in cl],
        }
        for cl in clusters
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def merge_into_links(links_data, picked):
    """politics_main 섹터를 뉴스스탠드 픽으로 교체한다.
    픽이 count보다 적으면 기존(검색 API) 기사로 나머지 슬롯을 채운다."""
    for sector in links_data["sectors"]:
        if sector["key"] != "politics_main":
            continue
        count = len(sector["articles"]) or 8
        picked_links = {a["link"] for a in picked}
        leftover = [a for a in sector["articles"] if a["link"] not in picked_links]
        merged = picked + leftover[: max(0, count - len(picked))]
        for a in merged:
            a.pop("_score", None)
            if "long_link" not in a:
                a["long_link"] = a["link"]
                # 네이버뉴스 링크만 단축 시도. 언론사 원문 링크는 쿼리스트링이
                # 기사 식별에 필요할 수 있으므로 건드리지 않는다.
                if SHORTEN_LINKS and "n.news.naver.com" in a["link"]:
                    a["link"] = shorten_url(a["link"])
        sector["articles"] = merged
        sector["source_note"] = "newsstand 언론사 편집 메인 기반, 부족분은 검색 API 보충"
        return len(picked), len(merged)
    return 0, 0


def main():
    if os.environ.get("NEWSSTAND", "1") == "0":
        print("[INFO] NEWSSTAND=0 → 뉴스스탠드 수집 비활성화, 기존 결과 유지")
        return

    with open("data/links.json", encoding="utf-8") as f:
        links_data = json.load(f)

    candidates, first_html = collect_headlines()

    politics_count = next(
        (len(s["articles"]) or 8 for s in links_data["sectors"] if s["key"] == "politics_main"), 8
    )
    picked, clusters = pick_politics(candidates, links_data, politics_count)
    os.makedirs("data", exist_ok=True)
    dump_candidates(clusters)
    print(f"[INFO] 정치 이슈 클러스터 {len(clusters)}개 (전체 후보 로그: {CANDIDATES_PATH})")

    if len(picked) < MIN_REQUIRED:
        if first_html:
            os.makedirs("data", exist_ok=True)
            with open(DEBUG_HTML_PATH, "w", encoding="utf-8") as f:
                f.write(first_html)
        print(
            f"[WARN] 정치 기사 {len(picked)}건(<{MIN_REQUIRED}) — 교체하지 않고 기존 결과 유지. "
            f"카드 구조 확인용 덤프: {DEBUG_HTML_PATH if first_html else '(로드 실패로 없음)'}"
        )
        return

    n_picked, n_total = merge_into_links(links_data, picked)
    if os.path.exists(DEBUG_HTML_PATH):
        os.remove(DEBUG_HTML_PATH)

    now = _now_override() or datetime.now(KST)
    links_data["politics_main_source"] = {
        "method": "newsstand_cards",
        "picked": n_picked,
        "merged_total": n_total,
        "updated_at": now.isoformat(),
    }
    with open("data/links.json", "w", encoding="utf-8") as f:
        json.dump(links_data, f, ensure_ascii=False, indent=2)
    for a in [s for s in links_data["sectors"] if s["key"] == "politics_main"][0]["articles"]:
        print(f"  - {a['title']}")
    print(f"[OK] politics_main을 뉴스스탠드 픽 {n_picked}건(+보충 {n_total - n_picked}건)으로 갱신")


if __name__ == "__main__":
    main()
