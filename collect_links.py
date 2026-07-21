# -*- coding: utf-8 -*-
"""
프로젝트1: 링크+헤드라인 수집
네이버 뉴스 검색 API로 4개 섹터 기사를 수집하고, 전일 22:00~당일 06:00(KST) 시간필터를 적용한다.
출력: data/links.json (build_page.py / build_excel.py에서 사용)
"""
import json
import os
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")

# 네이버 뉴스 검색 API 키
# 보안을 위해 코드에 직접 하드코딩하지 않는다. GitHub repo Settings > Secrets and variables > Actions 에
# NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 를 등록해서 사용한다 (README 참고).
# 로컬 테스트 시에는 환경변수로 export 하거나 .env 파일(git 추적 제외)을 사용할 것.
def _sanitize_key(raw):
    """헤더 값으로 쓸 수 없는 개행/제어문자를 전부 제거한다(양끝뿐 아니라 중간에 섞여 있어도 제거)."""
    return re.sub(r"[\r\n\t\x00-\x1f\x7f]", "", raw).strip()


def _diagnose(name, raw, cleaned):
    """실제 값은 절대 출력하지 않고, 문제 원인만 안전하게 로그로 남긴다."""
    flags = []
    if len(raw) != len(cleaned):
        flags.append(f"제어문자/개행 {len(raw) - len(cleaned)}자 제거됨")
    if raw != raw.strip():
        flags.append("앞뒤 공백 있음")
    if "\n" in raw or "\r" in raw:
        flags.append("개행문자 포함")
    print(f"[INFO] {name} 길이(정제전/후)={len(raw)}/{len(cleaned)} 문제={flags or '없음'}")


_RAW_ID = os.environ.get("NAVER_CLIENT_ID", "")
_RAW_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
NAVER_CLIENT_ID = _sanitize_key(_RAW_ID)
NAVER_CLIENT_SECRET = _sanitize_key(_RAW_SECRET)

_diagnose("NAVER_CLIENT_ID", _RAW_ID, NAVER_CLIENT_ID)
_diagnose("NAVER_CLIENT_SECRET", _RAW_SECRET, NAVER_CLIENT_SECRET)
if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
    print("[WARN] NAVER_CLIENT_ID/SECRET 환경변수가 설정되지 않았습니다. API 호출이 실패할 수 있습니다.")

SECTORS = [
    {"key": "politics_main", "label": "정치 관련 주요기사", "queries": ["정치", "국회", "여야"], "count": 8},
    {"key": "dp", "label": "더불어민주당 동정", "queries": ["더불어민주당"], "count": 5},
    {"key": "ppp", "label": "국민의힘 동정", "queries": ["국민의힘"], "count": 5},
    {
        "key": "economy",
        "label": "경제 동정",
        "queries": ["경제", "증권", "환율", "AI", "빅테크"],
        "count": 5,
    },
]

# 처리(수집) 순서: 정당 특화 섹터(dp/ppp)와 경제를 먼저 채워서 관련 기사를 선점하게 하고,
# 가장 포괄적인 politics_main을 마지막에 채운다 (2026-07-15, 정치 섹터에 정당 뉴스가
# 섞여 들어가는 문제 수정 — "정치"/"국회"/"여야" 쿼리가 너무 넓어서 먼저 처리하면
# 정당/경제 관련 기사까지 다 politics_main이 선점해버렸음).
PROCESS_ORDER = ["dp", "ppp", "economy", "politics_main"]

# politics_main에는 정당 브랜드가 뚜렷한 기사를 넣지 않는다 (해당 정당 섹터로 가야 함)
PARTY_EXCLUDE_KEYWORDS = ["더불어민주당", "국민의힘"]

# 선정 기준 스코어링 (과거 사람이 직접 고른 220여 일치 기사 분석 결과 반영, 2026-07-15):
# - 주요 정치인 실명 발언/충돌 중심 기사 선호
# - 따옴표 인용구가 제목에 있는 기사 선호 (발언·갈등 프레이밍)
# - [단독]/[속보]/[종합] 태그 기사 선호
# - [사설]/[신간]/[오늘의 주요일정] 등 단신·칼럼·안내성 기사는 감점
NAMED_FIGURES = [
    "이재명", "오세훈", "정청래", "장동혁", "한동훈", "김민석", "송영길",
    "안철수", "추경호", "이준석", "우원식", "정점식", "나경원", "한덕수",
]
# IT/빅테크/증권/환율/금융/AI 관련 기사는 "econony 5건 중 최소 1건은 보장"하는 방식으로 다룬다
# (경제 동정에 별도 스코어 가점을 줬더니 4일치 사람이 직접 고른 예시(example/briefings/)와
# 대조해보니 AI/빅테크 뉴스가 5건을 통째로 잠식해버렸다 — 실제 사람 선택은 부동산/금리/코스피/
# 환율이 핵심이고 AI는 "가끔 있으면 좋은" 보조 주제였다. 2026-07-21 예시로 확인 후 가점 제거,
# 아래 rank_with_topic_quota()로 "최소 1건 보장"만 남김.)
TECH_FINANCE_KEYWORDS = [
    "AI", "인공지능", "빅테크", "반도체", "증권", "환율", "금융", "통화",
    "코스피", "코스닥", "엔비디아", "삼성전자", "SK하이닉스",
]
QUOTE_CHARS = ['"', "'", "“", "”", "‘", "’"]
PRIORITY_TAGS = ["[단독]", "[속보]", "[종합]"]
LOW_PRIORITY_TAGS = ["[사설]", "[신간]", "[오늘의 주요일정]", "[알림]", "[부고]", "[포토]", "[칼럼]"]
# 정치 섹터에 섞여 들어온 오탐 사례(2026-07-21 실제 결과로 확인): 날씨/교통 특보, 지역
# 의회(시·군·구·도의회) 단신은 "정치" 키워드에 걸리지만 실질적 국가 정치 뉴스가 아니다.
# 주의: "태풍"/"장맛비"/"호우" 단독으로는 안 쓴다 — "태풍의 눈"처럼 정치 기사에서 비유로도
# 흔히 쓰이기 때문(사람이 고른 example/briefings/로 검증 중 발견, 2026-07-21).
# "주의보"/"특보"는 실제 기상특보 기사 제목에만 붙는 정형화된 표현이라 오탐 위험이 낮다.
NEGATIVE_KEYWORDS = [
    "주의보", "폭염특보", "AI PICK",
    "시의회", "군의회", "구의회", "도의회",
]
# 네이버뉴스에 정식 편입된 기사만 채택 (지역/업계 소규모 매체 자동 배제)
NAVER_NEWS_HOST = "n.news.naver.com"

# 원문 링크(originallink) 도메인 → 언론사명. 과거 사람이 직접 고른 기사에서 실제로
# 많이 쓰인 주요 언론사만 화이트리스트로 채택한다(2026-07-15). 이 목록에 없는 도메인은
# (지역/업계 소규모 매체로 간주해) 자동으로 제외된다.
# 주의: 도메인은 기억을 바탕으로 정리한 것이라 오탈자/누락 가능성 있음 — 실제 실행 결과에서
# 좋은 기사가 빠진다면 여기 도메인을 보정할 것.
PRESS_DOMAINS = {
    "chosun.com": "조선일보",
    "biz.chosun.com": "조선비즈",
    "joongang.co.kr": "중앙일보",
    "joins.com": "중앙일보",
    "donga.com": "동아일보",
    "hani.co.kr": "한겨레",
    "khan.co.kr": "경향신문",
    "hankookilbo.com": "한국일보",
    "segye.com": "세계일보",
    "munhwa.com": "문화일보",
    "seoul.co.kr": "서울신문",
    "edaily.co.kr": "이데일리",
    "mt.co.kr": "머니투데이",
    "mk.co.kr": "매일경제",
    "sedaily.com": "서울경제",
    "fnnews.com": "파이낸셜뉴스",
    "dt.co.kr": "디지털타임스",
    "yna.co.kr": "연합뉴스",
    "yonhapnewstv.co.kr": "연합뉴스TV",
    "newsis.com": "뉴시스",
    "news1.kr": "뉴스1",
    "kmib.co.kr": "국민일보",
    "asiae.co.kr": "아시아경제",
    "hankyung.com": "한국경제",
    "heraldcorp.com": "헤럴드경제",
    "biz.heraldcorp.com": "헤럴드경제",
    "nocutnews.co.kr": "노컷뉴스",
    "dailian.co.kr": "데일리안",
    "news.tf.co.kr": "더팩트",
    "sbs.co.kr": "SBS",
    "news.sbs.co.kr": "SBS",
    "biz.sbs.co.kr": "SBS Biz",
    "imbc.com": "MBC",
    "imnews.imbc.com": "MBC",
    "ytn.co.kr": "YTN",
    "jibs.co.kr": "JIBS",
    "tvchosun.com": "TV조선",
    "kbs.co.kr": "KBS",
    "news.kbs.co.kr": "KBS",
}


def press_name(originallink):
    """originallink 도메인으로 언론사를 판별한다. 화이트리스트에 없으면 None."""
    m = re.search(r"https?://(?:www\.)?([^/]+)", originallink or "")
    if not m:
        return None
    host = m.group(1).lower()
    for domain, name in PRESS_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return None


def score_article(title):
    score = 0
    if any(fig in title for fig in NAMED_FIGURES):
        score += 3
    if any(ch in title for ch in QUOTE_CHARS):
        score += 2
    if any(tag in title for tag in PRIORITY_TAGS):
        score += 2
    if any(tag in title for tag in LOW_PRIORITY_TAGS):
        score -= 3
    return score


def rank_with_topic_quota(articles, count, topic_keywords=None, min_topic_slots=0):
    """점수순 상위 count건을 뽑되, topic_keywords에 해당하는 기사가 min_topic_slots건
    미만이면 최고점 topic 기사로 최하위 비-topic 슬롯 하나를 교체해 최소 보장한다.
    (economy 섹터: AI/빅테크가 "가끔 있으면 좋은" 보조 주제이지 전체를 잠식하면 안 됨.)"""
    ranked = sorted(articles, key=lambda a: (a["_score"], parse_pubdate(a["pubDate"])), reverse=True)
    top = ranked[:count]
    if not topic_keywords or min_topic_slots <= 0:
        return top
    is_topic = lambda a: any(kw in a["title"] for kw in topic_keywords)
    if sum(1 for a in top if is_topic(a)) >= min_topic_slots:
        return top
    top_links = {a["link"] for a in top}
    topic_candidates = [a for a in ranked if is_topic(a) and a["link"] not in top_links]
    if not topic_candidates:
        return top
    for i in range(len(top) - 1, -1, -1):
        if not is_topic(top[i]):
            top[i] = topic_candidates[0]
            break
    return top


WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def get_window(now=None):
    """전일 22:00 ~ 당일 06:00 (KST) 윈도우 계산.
    실행 시각이 06:00 이전이면(당일 06:00이 아직 안 왔으면) 그냥 현재 시각까지로 잘라준다.
    """
    now = now or datetime.now(KST)
    end = now.replace(hour=6, minute=0, second=0, microsecond=0)
    if now < end:
        end = now
    start = (end - timedelta(days=1)).replace(hour=22, minute=0, second=0, microsecond=0)
    return start, end


def clean_html(text):
    text = re.sub(r"<.*?>", "", text)
    return (
        text.replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#39;", "'")
    )


def search_naver_page(query, start_idx, display=100):
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": display, "start": start_idx, "sort": "date"}
    r = requests.get(url, headers=headers, params=params, timeout=15)
    r.raise_for_status()
    return r.json().get("items", [])


def parse_pubdate(pubdate_str):
    try:
        return parsedate_to_datetime(pubdate_str).astimezone(KST)
    except Exception:
        return None


def search_naver_window(query, window_start, max_start=1000, page_size=100):
    """검색 결과를 sort=date로 페이지네이션하며, pubDate가 window_start보다
    오래된 기사가 나오면 더 뒤져봐야 소용없으므로 조기 종료한다.
    (실행 시각이 늦어져 윈도우 기사가 최신 100건 밖으로 밀려도 안전하게 수집한다.)
    """
    items = []
    start_idx = 1
    while start_idx <= max_start:
        try:
            page = search_naver_page(query, start_idx, page_size)
        except Exception as e:
            print(f"[WARN] '{query}' 검색 실패(start={start_idx}): {e}")
            break
        if not page:
            break
        items.extend(page)
        oldest_in_page = parse_pubdate(page[-1]["pubDate"])
        if oldest_in_page and oldest_in_page < window_start:
            break
        start_idx += page_size
    return items


def in_window(pubdate_str, start, end):
    dt = parse_pubdate(pubdate_str)
    if dt is None:
        return False
    return start <= dt <= end


def collect(now=None):
    start, end = get_window(now)
    result = {}
    seen_links = set()
    sectors_by_key = {s["key"]: s for s in SECTORS}
    for key in PROCESS_ORDER:
        sector = sectors_by_key[key]
        articles = []
        for q in sector["queries"]:
            items = search_naver_window(q, start)
            print(f"[INFO] '{q}' 검색 결과 {len(items)}건 조회(윈도우 조기종료 포함)")
            for item in items:
                link = item.get("link") or item.get("originallink")
                if not link or link in seen_links:
                    continue
                if NAVER_NEWS_HOST not in link:
                    continue
                press = press_name(item.get("originallink", ""))
                if not press:
                    continue
                if not in_window(item["pubDate"], start, end):
                    continue
                raw_title = clean_html(item["title"])
                # 날씨/교통 특보, 지역 의회 단신은 어느 섹터에서도 유효하지 않으므로 하드 제외.
                if any(kw in raw_title for kw in NEGATIVE_KEYWORDS):
                    continue
                # politics_main은 가장 포괄적인 쿼리라서 정당 브랜드가 뚜렷한 기사는
                # 각 정당 섹터로 보내고 여기서는 제외한다.
                if key == "politics_main" and any(kw in raw_title for kw in PARTY_EXCLUDE_KEYWORDS):
                    continue
                title = f"[{press}] {raw_title}"
                articles.append(
                    {
                        "title": title,
                        "link": link,
                        "pubDate": item["pubDate"],
                        "_score": score_article(title),
                    }
                )
                seen_links.add(link)
        topic_kw = TECH_FINANCE_KEYWORDS if key == "economy" else None
        top = rank_with_topic_quota(articles, sector["count"], topic_keywords=topic_kw, min_topic_slots=1)
        result[key] = [{k: v for k, v in a.items() if k != "_score"} for a in top]
    return start, end, result


def date_label(dt):
    return f"{dt.month}/{dt.day}({WEEKDAY_KR[dt.weekday()]})"


def _now_override():
    """테스트/검증용: NOW_OVERRIDE 환경변수(ISO 8601, 예: 2026-07-09T06:05:00+09:00)가 설정되면
    실제 시각 대신 그 시각 기준으로 윈도우를 계산한다. 실제 스케줄 실행 시에는 설정하지 않는다."""
    raw = os.environ.get("NOW_OVERRIDE", "").strip()
    if not raw:
        return None
    dt = datetime.fromisoformat(raw)
    return dt if dt.tzinfo else dt.replace(tzinfo=KST)


def main():
    now = _now_override()
    if now:
        print(f"[INFO] NOW_OVERRIDE 적용: {now.isoformat()}")
    start, end, data = collect(now)
    os.makedirs("data", exist_ok=True)

    out = {
        "generated_at": datetime.now(KST).isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "date_label": date_label(end),
        "sectors": [
            {"key": s["key"], "label": s["label"], "queries": s["queries"], "articles": data[s["key"]]}
            for s in SECTORS
        ],
    }
    with open("data/links.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 일별 실행 로그 (선정 근거)
    log_path = f"data/log_{end.strftime('%Y%m%d')}.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    total = sum(len(s["articles"]) for s in out["sectors"])
    print(f"[OK] {date_label(end)} 기사 {total}건 수집 완료 (윈도우 {start} ~ {end})")


if __name__ == "__main__":
    main()
