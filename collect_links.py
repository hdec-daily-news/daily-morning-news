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
    {"key": "politics_main", "label": "정치 관련 주요기사", "queries": ["정치", "국회", "여야"], "count": 6},
    {"key": "dp", "label": "더불어민주당 동정", "queries": ["더불어민주당"], "count": 3},
    {"key": "ppp", "label": "국민의힘 동정", "queries": ["국민의힘"], "count": 3},
    {"key": "economy", "label": "경제 동정", "queries": ["경제"], "count": 3},
]

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
    for sector in SECTORS:
        articles = []
        for q in sector["queries"]:
            items = search_naver_window(q, start)
            print(f"[INFO] '{q}' 검색 결과 {len(items)}건 조회(윈도우 조기종료 포함)")
            for item in items:
                link = item.get("link") or item.get("originallink")
                if not link or link in seen_links:
                    continue
                if not in_window(item["pubDate"], start, end):
                    continue
                articles.append(
                    {
                        "title": clean_html(item["title"]),
                        "link": link,
                        "pubDate": item["pubDate"],
                    }
                )
                seen_links.add(link)
        articles.sort(key=lambda a: a["pubDate"], reverse=True)
        result[sector["key"]] = articles[: sector["count"]]
    return start, end, result


def date_label(dt):
    return f"{dt.month}/{dt.day}({WEEKDAY_KR[dt.weekday()]})"


def main():
    start, end, data = collect()
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
