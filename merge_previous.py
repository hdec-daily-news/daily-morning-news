# -*- coding: utf-8 -*-
"""직전 배포본(data/prev_links.json)의 기사를 보존하고, 이번 실행에서 새로 잡힌 기사만 추가한다.

같은 윈도우(window_start 동일)에서 업데이트 버튼 등으로 재실행했을 때, 낮 시간 실행은 네이버 검색 API
1,000건 한도 때문에 아침 윈도우 기사를 못 잡아 섹터가 비어버리는 문제를 막는다.
새 윈도우(다음 날 06:03 자동 실행)에서는 병합하지 않고 새로 수집한 결과를 그대로 쓴다.
섹터별 개수는 기존 기준(8/5/5/5)을 넘지 않는다.
"""
import json
import os

PREV_PATH = "data/prev_links.json"
LINKS_PATH = "data/links.json"
LIMITS = {"politics_main": 8, "dp": 5, "ppp": 5, "economy": 5}


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def keys_of(article):
    return {k for k in (article.get("link"), article.get("long_link")) if k}


def main():
    new = load(LINKS_PATH)
    prev = load(PREV_PATH)
    if not new:
        print("[WARN] data/links.json 없음 — 병합 생략")
        return
    if not prev:
        print("[INFO] 직전 배포본 없음 — 병합 생략")
        return
    if prev.get("window_start") != new.get("window_start"):
        print("[INFO] 윈도우가 달라 병합 생략 (새 날짜 첫 실행)")
        return

    prev_by_key = {s["key"]: s for s in prev.get("sectors", [])}
    for sector in new.get("sectors", []):
        old = prev_by_key.get(sector["key"])
        if not old:
            continue
        limit = LIMITS.get(sector["key"], max(len(old["articles"]), len(sector["articles"])))
        merged = list(old["articles"])
        seen = set()
        for a in merged:
            seen |= keys_of(a)
        added = 0
        for a in sector["articles"]:
            if len(merged) >= limit:
                break
            if keys_of(a) & seen:
                continue
            merged.append(a)
            seen |= keys_of(a)
            added += 1
        print(f"[MERGE] {sector['key']}: 기존 {len(old['articles'])}건 유지 + 신규 {added}건 추가 = {len(merged)}건")
        sector["articles"] = merged
        # 기존 기사가 유지됐는데 출처 표기가 새 실행 기준으로 바뀌지 않도록 이전 값 보존
        if "source_note" in old:
            sector["source_note"] = old["source_note"]

    if prev.get("politics_main_source"):
        new["politics_main_source"] = prev["politics_main_source"]

    with open(LINKS_PATH, "w", encoding="utf-8") as f:
        json.dump(new, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
