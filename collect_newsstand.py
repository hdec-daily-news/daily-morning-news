# -*- coding: utf-8 -*-
"""
프로젝트1 보강: 네이버 뉴스스탠드(https://newsstand.naver.com/?list=ct2)에서
각 언론사가 "오늘의 메인"으로 직접 편집해 올린 기사 중 정치 기사를 추출해
data/links.json의 politics_main 섹터를 대체한다.

배경(2026-07-28): 검색 API("정치"/"국회"/"여야" 키워드) 기반 politics_main은
역사 칼럼·해외 단신·오피니언이 섞여 들어와 휴먼픽과 겹침이 0건이었다.
뉴스스탠드는 언론사 편집자가 고른 대표 기사라서 이런 오탐이 구조적으로 적다.

동작 원칙 (안전 폴백):
- collect_links.py 실행 *후*에 돌려서 politics_main만 갱신한다.
- 뉴스스탠드 수집이 실패하거나 정치 기사가 MIN_REQUIRED건 미만이면
  기존(검색 API) 결과를 그대로 두고 종료한다. 실행 순서만 지키면 절대 데이터를 깨지 않는다.
- NEWSSTAND=0 환경변수로 즉시 비활성화 가능(코드 되돌릴 필요 없음).

주의: 이 코드는 네트워크 차단 환경에서 실제 뉴스스탠드 DOM을 보지 못한 채 작성됐다.
추출 결과가 부족하면 data/newsstand_debug.html 에 페이지 전체를 저장하므로,
첫 Actions 실행 후 그 파일을 보고 추출 휴리스틱을 보정할 것 (README '알려진 한계' 참고).
"""
import asyncio
import json
import os
import re

from playwright.async_api import async_playwright

from collect_links import (
    KST,
    NAMED_FIGURES,
    PARTY_EXCLUDE_KEYWORDS,
    press_name,
    score_article,
    shorten_url,
    SHORTEN_LINKS,
    _now_override,
)
from datetime import datetime

NEWSSTAND_URL = "https://newsstand.naver.com/?list=ct2"
DEBUG_HTML_PATH = "data/newsstand_debug.html"
# 뉴스스탠드 픽이 이 건수 미만이면 교체하지 않고 기존 검색 API 결과 유지
MIN_REQUIRED = 4

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# "정치 기사" 판별 키워드. 뉴스스탠드 카드에는 정치 외 기사도 섞여 있으므로
# 제목에 아래 키워드(또는 NAMED_FIGURES 실명)가 있어야 politics_main 후보로 삼는다.
POLITICS_KEYWORDS = [
    "대통령", "국회", "여야", "정당", "총리", "장관", "청와대", "靑", "與", "野",
    "특검", "선관위", "선거", "재검표", "개헌", "국정", "탄핵", "계엄", "전당대회",
    "당대표", "원내", "의원", "북한", "北", "한미", "안보", "외교", "국방", "파병",
    "민주당", "국민의힘",  # 정당 브랜드 기사도 일단 후보에 올린 뒤 아래에서 정당 섹터 중복만 제거
]

# 기사 제목이 아닌 UI 텍스트를 걸러내기 위한 패턴
UI_TEXT_PATTERNS = [
    "구독", "전체언론사", "뉴스스탠드", "로그인", "바로가기", "이전", "다음",
    "펼쳐보기", "설정", "도움말", "공지", "언론사 편집", "기사보기", "언론사보기",
]


def looks_like_headline(text):
    """앵커 텍스트가 실제 기사 헤드라인처럼 보이는지 판별한다."""
    t = " ".join(text.split())
    if len(t) < 10:
        return False
    if any(p in t for p in UI_TEXT_PATTERNS):
        return False
    if not re.search(r"[가-힣]", t):
        return False
    return True


async def fetch_anchors(url):
    """뉴스스탠드 페이지의 모든 앵커(href, text)와 전체 HTML을 가져온다.
    '기사보기' 모드 토글이 있으면 눌러서 각 언론사 카드에 헤드라인이 노출되게 한다."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900})
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(2000)
        # 뉴스스탠드는 '언론사보기'(로고만)와 '기사보기'(헤드라인 노출) 모드가 있다.
        # 기사보기 모드여야 헤드라인 앵커가 DOM에 실린다. 실패해도 치명적이지 않으니 무시.
        try:
            toggle = page.locator("text=기사보기").first
            await toggle.click(timeout=3000)
            await page.wait_for_timeout(1500)
        except Exception:
            pass
        anchors = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(a => ({href: a.href, text: (a.innerText || '').trim()}))",
        )
        html = await page.content()
        await browser.close()
        return anchors, html


def extract_candidates(anchors):
    """앵커 목록에서 '주요 언론사 기사 링크 + 헤드라인' 후보를 추출한다."""
    seen = set()
    out = []
    for a in anchors:
        href, text = a.get("href", ""), a.get("text", "")
        if not href.startswith("http") or not looks_like_headline(text):
            continue
        title = " ".join(text.split())
        # 뉴스스탠드 헤드라인은 대개 언론사 원문 사이트로 연결된다.
        # 네이버뉴스 링크(n.news.naver.com)는 언론사 판별이 안 되므로 프리픽스 없이 통과시킨다.
        press = press_name(href)
        is_naver_article = "n.news.naver.com" in href
        if not press and not is_naver_article:
            continue
        key = (href.split("?")[0], title)
        if key in seen or title in {t for _, t in seen}:
            continue
        seen.add(key)
        out.append({"press": press, "title": title, "link": href})
    return out


def pick_politics(candidates, links_data, count):
    """정치 기사만 골라 스코어순 상위 count건을 반환한다. 다른 섹터에 이미 있는
    링크/제목과 겹치면 제외한다(정당 섹터 기사가 politics_main에 중복 노출되는 것 방지)."""
    existing_links = set()
    existing_titles = set()
    for s in links_data["sectors"]:
        for art in s["articles"]:
            existing_links.add(art.get("long_link") or art["link"])
            existing_links.add(art["link"])
            # "[언론사] 제목" 프리픽스 제거 후 비교
            existing_titles.add(re.sub(r"^\[[^\]]+\]\s*", "", art["title"]))

    picked = []
    for c in candidates:
        title = c["title"]
        if not any(kw in title for kw in POLITICS_KEYWORDS) and not any(f in title for f in NAMED_FIGURES):
            continue
        # 정당 브랜드가 뚜렷한 기사는 dp/ppp 섹터 소관 (collect_links.py와 동일 규칙)
        if any(kw in title for kw in PARTY_EXCLUDE_KEYWORDS):
            continue
        if c["link"] in existing_links or title in existing_titles:
            continue
        display_title = f"[{c['press']}] {title}" if c["press"] else title
        picked.append(
            {
                "title": display_title,
                "link": c["link"],
                "pubDate": "",  # 뉴스스탠드 목록에는 발행 시각이 없음 (언론사가 '지금' 걸어둔 메인)
                "_score": score_article(display_title),
            }
        )
    # 동점이면 후보 등장 순서(뉴스스탠드 노출 순서) 유지 — sorted는 stable
    picked.sort(key=lambda a: a["_score"], reverse=True)
    return picked[:count]


def merge_into_links(links_data, picked):
    """politics_main 섹터의 기사 목록을 뉴스스탠드 픽으로 교체한다.
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
                # 네이버뉴스 링크만 단축 시도. 언론사 원문 링크는 쿼리스트링이 기사 식별에
                # 필요할 수 있으므로 건드리지 않는다.
                if SHORTEN_LINKS and "n.news.naver.com" in a["link"]:
                    a["link"] = shorten_url(a["link"])
        sector["articles"] = merged
        sector["source_note"] = "newsstand(ct2) 언론사 편집 메인 기반, 부족분은 검색 API 보충"
        return len(picked), len(merged)
    return 0, 0


def main():
    if os.environ.get("NEWSSTAND", "1") == "0":
        print("[INFO] NEWSSTAND=0 → 뉴스스탠드 수집 비활성화, 기존 결과 유지")
        return

    with open("data/links.json", encoding="utf-8") as f:
        links_data = json.load(f)

    try:
        anchors, html = asyncio.run(fetch_anchors(NEWSSTAND_URL))
    except Exception as e:
        print(f"[WARN] 뉴스스탠드 로드 실패, 기존(검색 API) politics_main 유지: {e}")
        return

    candidates = extract_candidates(anchors)
    print(f"[INFO] 뉴스스탠드 앵커 {len(anchors)}개 중 기사 후보 {len(candidates)}건")

    politics_count = next(
        (len(s["articles"]) or 8 for s in links_data["sectors"] if s["key"] == "politics_main"), 8
    )
    picked = pick_politics(candidates, links_data, politics_count)

    if len(picked) < MIN_REQUIRED:
        os.makedirs("data", exist_ok=True)
        with open(DEBUG_HTML_PATH, "w", encoding="utf-8") as f:
            f.write(html)
        print(
            f"[WARN] 정치 기사 {len(picked)}건(<{MIN_REQUIRED}) — 교체하지 않고 기존 결과 유지. "
            f"페이지 구조 확인용 덤프 저장: {DEBUG_HTML_PATH}"
        )
        return

    n_picked, n_total = merge_into_links(links_data, picked)
    # 교체 성공 시 이전 디버그 덤프는 정리(레포 용량 관리)
    if os.path.exists(DEBUG_HTML_PATH):
        os.remove(DEBUG_HTML_PATH)

    now = _now_override() or datetime.now(KST)
    links_data["politics_main_source"] = {
        "method": "newsstand",
        "url": NEWSSTAND_URL,
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
