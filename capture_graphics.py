# -*- coding: utf-8 -*-
"""
프로젝트2 보강: 통신사(연합뉴스/뉴스1/뉴시스) 그래픽 전용 코너에서
전일 22:00~당일 06:00(KST) 윈도우에 올라온 인포그래픽을 원본 화질로 직접 수집한다.

배경(2026-07-15, 사용자 제보): 기사 본문 안에서 인포그래픽을 찾는 capture_images.py의
이미지 분류 로직과 별개로, 이 통신사들은 인포그래픽만 모아두는 전용 코너를 운영한다.
당일 아침(06:00 이전)에는 그날 그래픽이 아직 많이 안 올라오므로, 전일 것까지 긁어온다.
- 연합뉴스 https://www.yna.co.kr/graphic/index
- 뉴스1   https://www.news1.kr/photos/graphic
- 뉴시스  https://www.newsis.com/pho/gralist/?cid=pho

주의: requests+BeautifulSoup으로 정적 HTML을 파싱한다(Playwright 없이 가벼운 스크래핑).
셀렉터는 Claude Browser로 실제 페이지 DOM을 직접 확인해서 작성했지만, 사이트 개편 시
CANDIDATE 함수들(collect_yna/collect_newsis/collect_news1)을 다시 확인해야 한다.
뉴스1은 상대시간("N시간 전")만 제공해 정밀도가 떨어지고, 절대 날짜("YYYY-MM-DD")로
표시된 항목은 시각 정보가 없어 판단하지 않고 건너뛴다(윈도우 밖일 가능성이 높음).
"""
import json
import os
import re
from datetime import datetime, timedelta
from urllib.parse import unquote, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

from collect_links import get_window, KST, _now_override

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_soup(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def collect_yna(start, end):
    """연합뉴스 그래픽. 목록에 정확한 'YYYY-MM-DD HH:MM' 타임스탬프가 있어 정밀 필터 가능."""
    items = []
    try:
        soup = fetch_soup("https://www.yna.co.kr/graphic/index")
    except Exception as e:
        print(f"[WARN] 연합뉴스 그래픽 목록 로드 실패: {e}")
        return items
    for a in soup.select("a.img"):
        href = a.get("href")
        img = a.select_one("img")
        if not href or not img or not img.get("src"):
            continue
        box = a.find_parent("li") or a.parent
        time_el = box.select_one(".txt-time") if box else None
        title_el = box.select_one(".title01") if box else None
        if not time_el:
            continue
        try:
            dt = datetime.strptime(time_el.get_text(strip=True), "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        except Exception:
            continue
        if not (start <= dt <= end):
            continue
        items.append(
            {
                "source": "연합뉴스",
                "title": (title_el.get_text(strip=True) if title_el else "").strip(),
                "link": href,
                "image_url": img["src"],
                "pubdate": dt.isoformat(),
            }
        )
    return items


def collect_newsis(start, end):
    """뉴시스 그래픽. 이미지 URL의 rnd= 파라미터(YYYYMMDDHHMMSS)로 정밀 필터 가능."""
    items = []
    try:
        soup = fetch_soup("https://www.newsis.com/pho/gralist/?cid=pho")
    except Exception as e:
        print(f"[WARN] 뉴시스 그래픽 목록 로드 실패: {e}")
        return items
    for li in soup.select("li"):
        a = li.select_one(".thumCont a")
        img = li.select_one(".thumCont img")
        title_el = li.select_one(".txtCont a")
        if not a or not img or not img.get("src"):
            continue
        src = img["src"]
        m = re.search(r"rnd=(\d{14})", src)
        if not m:
            continue
        try:
            dt = datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=KST)
        except Exception:
            continue
        if not (start <= dt <= end):
            continue
        href = a.get("href", "")
        if href.startswith("/"):
            href = "https://www.newsis.com" + href
        img_url = src if src.startswith("http") else "https:" + src
        items.append(
            {
                "source": "뉴시스",
                "title": (title_el.get_text(strip=True) if title_el else "").strip(),
                "link": href,
                "image_url": img_url,
                "pubdate": dt.isoformat(),
            }
        )
    return items


def _parse_relative_time(text, now):
    text = text.strip()
    m = re.match(r"(\d+)분\s*전", text)
    if m:
        return now - timedelta(minutes=int(m.group(1)))
    m = re.match(r"(\d+)시간\s*전", text)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = re.match(r"(\d+)일\s*전", text)
    if m:
        return now - timedelta(days=int(m.group(1)))
    return None  # 절대 날짜("YYYY-MM-DD")는 시각 정보가 없어 판단하지 않고 건너뜀


def collect_news1(start, end, now):
    """뉴스1 그래픽뉴스. 상대시간만 제공되어 정밀도가 낮음(참고: 목록 순서상 최신이 위)."""
    items = []
    try:
        soup = fetch_soup("https://www.news1.kr/photos/graphic")
    except Exception as e:
        print(f"[WARN] 뉴스1 그래픽 목록 로드 실패: {e}")
        return items
    for a in soup.select('a[href^="/photos/"]'):
        img = a.select_one("img")
        if not img:
            continue
        card = a.find_parent(class_=re.compile(r"col-"))
        if not card:
            continue
        time_el = card.select_one(".entry-meta span")
        title_el = card.select_one("h2 a")
        if not time_el:
            continue
        dt = _parse_relative_time(time_el.get_text(strip=True), now)
        if not dt or not (start <= dt <= end):
            continue
        src = img.get("src", "")
        real_url = src
        if "url=" in src:
            qs = parse_qs(urlparse(src).query)
            if "url" in qs:
                real_url = unquote(qs["url"][0])
                real_url = re.sub(r"(\.jpe?g|\.png).*$", r"\1", real_url, flags=re.IGNORECASE)
        if real_url.startswith("/"):
            real_url = "https://www.news1.kr" + real_url
        href = a.get("href", "")
        if href.startswith("/"):
            href = "https://www.news1.kr" + href
        items.append(
            {
                "source": "뉴스1",
                "title": (title_el.get_text(strip=True) if title_el else "").strip(),
                "link": href,
                "image_url": real_url,
                "pubdate": dt.isoformat(),
            }
        )
    return items


def download_image(url, out_path):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(r.content)


def main():
    now = _now_override() or datetime.now(KST)
    start, end = get_window(now)
    os.makedirs("images/graphics", exist_ok=True)

    all_items = []
    all_items += collect_yna(start, end)
    all_items += collect_newsis(start, end)
    all_items += collect_news1(start, end, now)
    print(f"[INFO] 윈도우({start}~{end}) 내 통신사 그래픽 후보 {len(all_items)}건 발견")

    saved = []
    for idx, item in enumerate(all_items, start=1):
        ext = os.path.splitext(urlparse(item["image_url"]).path)[1] or ".jpg"
        out_path = f"images/graphics/{item['source']}_{idx:02d}{ext}"
        try:
            download_image(item["image_url"], out_path)
        except Exception as e:
            print(f"[WARN] 다운로드 실패 ({item['source']} {item['title'][:20]}): {e}")
            continue
        saved.append({**item, "image": out_path})
        print(f"[OK] [{item['source']}] {item['title'][:30]} -> {out_path}")

    with open("data/graphics.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": now.isoformat(),
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                "items": saved,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"[OK] 통신사 그래픽 {len(saved)}건 수집 완료")


if __name__ == "__main__":
    main()
