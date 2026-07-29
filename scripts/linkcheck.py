# -*- coding: utf-8 -*-
"""일회용 검증: 휴먼 브리핑(naver.me 단축링크)을 실제로 따라가 최종 기사를 확인하고,
자동 생성된 data/links.json의 정치 픽과 '같은 기사인지' 대조한다.
GitHub Actions(네트워크 열림)에서만 실행. 결과는 로그로만 출력."""
import json
import re
import sys

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}


def resolve(url):
    """단축/원본 링크를 따라가 (최종URL, 정규화 기사키, og:title)를 반환."""
    try:
        r = requests.get(url, headers=UA, timeout=15, allow_redirects=True)
        final = r.url
        m = re.search(r'<meta property="og:title" content="([^"]*)"', r.text)
        title = m.group(1) if m else ""
        # 네이버 기사 정규키: article/{oid}/{aid}
        km = re.search(r"/article/(?:mnews/)?(\d+)/(\d+)", final)
        key = f"naver:{km.group(1)}/{km.group(2)}" if km else final.split("?")[0]
        return final, key, title
    except Exception as e:
        return f"(실패: {e})", None, ""


def parse_briefing(path):
    """example/briefings/*.txt 정치 섹터의 (제목, 링크) 목록."""
    out = []
    section = None
    lines = open(path, encoding="utf-8").read().splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("■"):
            section = ln
            continue
        if section and "정치 관련 주요기사" in section and ln.startswith("http"):
            title = lines[i - 1].strip()
            out.append((title, ln.strip()))
    return out


def main():
    human = parse_briefing("example/briefings/2026-07-29.txt")
    data = json.load(open("data/links.json", encoding="utf-8"))
    auto = [s for s in data["sectors"] if s["key"] == "politics_main"][0]["articles"]

    print("=" * 70)
    print("휴먼 정치 픽 → 실제 기사 (naver.me 따라가기)")
    print("=" * 70)
    human_keys = {}
    for title, link in human:
        final, key, og = resolve(link)
        human_keys[key] = (title, og)
        print(f"\n· {title}")
        print(f"  short: {link}")
        print(f"  final: {final}")
        print(f"  key  : {key}")
        print(f"  og   : {og}")

    print("\n" + "=" * 70)
    print("자동 정치 픽 → 실제 기사 (원문 링크 따라가기)")
    print("=" * 70)
    auto_keys = {}
    for a in auto:
        final, key, og = resolve(a["link"])
        auto_keys[key] = a["title"]
        print(f"\n· {a['title']}")
        print(f"  link : {a['link']}")
        print(f"  final: {final}")
        print(f"  key  : {key}")
        print(f"  og   : {og}")

    print("\n" + "=" * 70)
    print("정규화 기사키(oid/aid) 교집합 = 링크까지 완전히 같은 기사")
    print("=" * 70)
    common = set(human_keys) & set(auto_keys)
    common = {k for k in common if k}
    if common:
        for k in common:
            print(f"  ✅ {k}  |  {human_keys[k][0]}")
    else:
        print("  (기사키 완전 일치 0건 — 같은 이슈라도 다른 언론사/기사)")
    print(f"\n요약: 휴먼 {len(human_keys)}건 · 자동 {len(auto_keys)}건 · 완전일치 {len(common)}건")


if __name__ == "__main__":
    main()
