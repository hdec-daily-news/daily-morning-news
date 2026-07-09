# -*- coding: utf-8 -*-
"""
프로젝트2: 네이버 메인 뉴스 전반 "기사 메인화면" 캡쳐
- 정치/경제/사회/세계/IT과학 등 섹션에서 최신 기사 후보를 모아 시간필터 적용
- Playwright(headless Chromium)로 각 기사 페이지의 제목~대표이미지 영역만 크롭 캡쳐
- 기사 본문 내 인포그래픽/차트로 보이는 이미지는 별도로 원본 화질 그대로 저장 (images/infographics/)
  → 경영층이 인포그래픽/차트 이미지를 선호하므로 개별 파일로 분리 제공

주의: 이 스크립트는 개발 환경(네트워크 차단 샌드박스)에서 실사 테스트를 하지 못한 상태로 작성됨.
네이버 뉴스 페이지 DOM 구조(선택자)가 실제와 다를 수 있으니, 첫 GitHub Actions 실행 결과 이미지를
확인하고 CANDIDATE_SELECTORS / 캡쳐 로직을 보정해야 한다.

인포그래픽 판별 휴리스틱 보정 이력:
- 2026-07-09 최초 실행에서 세로형 비율만으로 판별 → 아파트 항공사진(부동산 기사)이 오탐됨
  (실제 캡쳐 파일로 검증: flat_color_ratio ≈ 0.0009, 배경색이 거의 없어 사진임이 명확)
  → 캡션 키워드가 없을 때는 세로형 비율 + 단색 배경 비중(_flat_color_ratio)을 함께 요구하도록 보정.
  합성 인포그래픽 샘플로는 flat_color_ratio ≈ 0.81로 임계값(0.22)을 여유 있게 통과함을 확인.
- 여전히 실제 네이버 인포그래픽 이미지로는 검증 못한 상태이므로, 앞으로 오탐/누락 사례가
  보이면 INFOGRAPHIC_FLAT_COLOR_RATIO / INFOGRAPHIC_ASPECT_RATIO를 조정할 것.
"""
import asyncio
import json
import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from PIL import Image
from playwright.async_api import async_playwright

from collect_links import get_window, in_window, date_label

KST = ZoneInfo("Asia/Seoul")

# 네이버 뉴스 섹션: 100 정치, 101 경제, 102 사회, 104 세계, 105 IT/과학
SECTIONS = ["100", "101", "102", "104", "105"]
TARGET_TOTAL = 20
PER_SECTION = 5

VIEWPORT = {"width": 800, "height": 1400}

# 기사 목록 페이지에서 헤드라인 링크를 찾기 위한 후보 선택자 (네이버 개편 시 수정 필요)
LIST_LINK_SELECTORS = [
    "a.sa_text_title",
    "div.sa_text a.sa_text_title",
    "a.cluster_text_headline",
    ".section_article a",
]

# 기사 본문 페이지에서 헤더(제목/기자/시각)와 대표이미지를 찾기 위한 후보 선택자
HEADER_SELECTORS = ["#ct .media_end_head", "#title_area", ".media_end_head"]
BODY_SELECTORS = ["#dic_area", "#articleBodyContents", "#newsct_article"]

# 인포그래픽/차트 판별용: 캡션(이미지 설명)에 이 키워드가 있으면 인포그래픽으로 간주 (단독으로도 확정 신호)
INFOGRAPHIC_CAPTION_KEYWORDS = ["인포그래픽", "그래픽", "자료:", "자료=", "차트", "표=", "©그래픽", "일러스트"]
# 캡션에 키워드가 없을 때 보조로 쓰는 조건: 세로로 긴 이미지 + 단색 배경 비중이 높음
# (일반 사진은 색이 다양해서 최빈색 비중이 낮고, 인포그래픽/차트는 흰색·회색 배경이 넓게 깔려 최빈색 비중이 높다)
INFOGRAPHIC_ASPECT_RATIO = 1.15
INFOGRAPHIC_FLAT_COLOR_RATIO = 0.22
INFOGRAPHIC_MIN_WIDTH = 300


async def collect_candidate_links(context):
    page = await context.new_page()
    links = []
    seen = set()
    for sid in SECTIONS:
        try:
            await page.goto(f"https://news.naver.com/section/{sid}", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(800)
        except Exception as e:
            print(f"[WARN] 섹션 {sid} 로드 실패: {e}")
            continue
        found = []
        for sel in LIST_LINK_SELECTORS:
            els = await page.query_selector_all(sel)
            if els:
                found = els
                break
        count = 0
        for el in found:
            if count >= PER_SECTION:
                break
            href = await el.get_attribute("href")
            title = (await el.inner_text() or "").strip()
            if not href or not title or href in seen:
                continue
            if "n.news.naver.com" not in href and "news.naver.com" not in href:
                continue
            seen.add(href)
            links.append({"title": title, "link": href, "section": sid})
            count += 1
    await page.close()
    return links[:TARGET_TOTAL]


async def get_article_pubdate(page):
    """기사 페이지에서 입력시각 텍스트를 찾아 datetime으로 변환 시도. 실패 시 None."""
    try:
        el = await page.query_selector("span.media_end_head_info_datestamp_time") or await page.query_selector(
            ".media_end_head_info_datestamp_time"
        )
        if el:
            attr = await el.get_attribute("data-date-time")
            if attr:
                return datetime.fromisoformat(attr).replace(tzinfo=KST)
    except Exception:
        pass
    return None


async def capture_article(page, url, out_path):
    await page.goto(url, wait_until="domcontentloaded", timeout=25000)
    await page.wait_for_timeout(1200)

    header = None
    for sel in HEADER_SELECTORS:
        header = await page.query_selector(sel)
        if header:
            break
    body = None
    for sel in BODY_SELECTORS:
        body = await page.query_selector(sel)
        if body:
            break

    if not header:
        # 헤더를 못 찾으면 상단 뷰포트만 캡쳐 (fallback)
        await page.screenshot(path=out_path)
        return False, body

    header_box = await header.bounding_box()
    bottom_y = header_box["y"] + header_box["height"] + 500  # fallback 높이

    if body:
        img = await body.query_selector("img")
        if img:
            img_box = await img.bounding_box()
            if img_box:
                bottom_y = img_box["y"] + img_box["height"] + 80  # 캡션 여유분 포함

    clip = {
        "x": 0,
        "y": max(header_box["y"] - 10, 0),
        "width": VIEWPORT["width"],
        "height": min(bottom_y - max(header_box["y"] - 10, 0), 1600),
    }
    await page.screenshot(path=out_path, clip=clip)
    return True, body


async def _image_caption(img):
    """이미지 근처(형제/부모의 형제)에서 캡션 텍스트를 찾는다. 네이버는 보통
    <em class="img_desc"> 또는 <span class="end_photo_org"> 형태로 캡션을 둔다."""
    try:
        caption = await img.evaluate(
            """(el) => {
                const fig = el.closest('figure') || el.parentElement;
                if (!fig) return '';
                const capEl = fig.querySelector('em, .img_desc, figcaption, .end_photo_org');
                return capEl ? capEl.innerText : '';
            }"""
        )
        return (caption or "").strip()
    except Exception:
        return ""


def _flat_color_ratio(path, max_dim=80):
    """이미지 축소본에서 가장 흔한 색이 차지하는 비율. 인포그래픽/차트는 단색 배경이
    넓게 깔려 이 값이 높고, 일반 사진(인물/풍경/건물 등)은 색이 다양해 낮다."""
    try:
        im = Image.open(path).convert("RGB")
        im.thumbnail((max_dim, max_dim))
        colors = im.getcolors(maxcolors=1_000_000)
        if not colors:
            return 0.0
        total = im.width * im.height
        most_common = max(colors, key=lambda c: c[0])[0]
        return most_common / total
    except Exception:
        return 0.0


def _caption_says_infographic(caption):
    return bool(caption) and any(kw in caption for kw in INFOGRAPHIC_CAPTION_KEYWORDS)


def _shape_says_infographic(width, height):
    return width >= INFOGRAPHIC_MIN_WIDTH and height / max(width, 1) >= INFOGRAPHIC_ASPECT_RATIO


async def capture_infographics(body, out_prefix):
    """기사 본문 내 이미지들을 훑어 인포그래픽/차트로 보이는 것만 별도 파일로 저장한다.
    실제 <img> 엘리먼트를 그대로 스크린샷하므로 원본 화질을 그대로 유지한다.
    캡션에 인포그래픽 키워드가 있으면 확정, 없으면 세로형 비율 + 단색 배경 비중을 함께 봐서
    일반 사진(부동산/인물 항공샷 등)이 오탐되는 것을 줄인다."""
    if not body:
        return []
    saved = []
    imgs = await body.query_selector_all("img")
    for i, img in enumerate(imgs, start=1):
        box = await img.bounding_box()
        if not box or box["width"] < 1 or box["height"] < 1:
            continue
        caption = await _image_caption(img)
        by_caption = _caption_says_infographic(caption)
        if not by_caption and not _shape_says_infographic(box["width"], box["height"]):
            continue
        out_path = f"{out_prefix}_{i}.png"
        try:
            await img.screenshot(path=out_path)
        except Exception:
            continue
        if not by_caption and _flat_color_ratio(out_path) < INFOGRAPHIC_FLAT_COLOR_RATIO:
            os.remove(out_path)
            continue
        saved.append({"image": out_path, "caption": caption})
    return saved


async def main():
    start, end = get_window()
    os.makedirs("images", exist_ok=True)
    os.makedirs("images/infographics", exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport=VIEWPORT)

        candidates = await collect_candidate_links(context)
        print(f"[INFO] 후보 기사 {len(candidates)}건 수집")

        page = await context.new_page()
        captured = []
        for idx, c in enumerate(candidates, start=1):
            out_name = f"images/article_{idx:02d}.png"
            try:
                ok, body = await capture_article(page, c["link"], out_name)
                infographics = await capture_infographics(body, f"images/infographics/article_{idx:02d}")
                captured.append({**c, "image": out_name, "ok": ok, "infographics": infographics})
                info_note = f", 인포그래픽 {len(infographics)}건" if infographics else ""
                print(f"[{'OK' if ok else 'FALLBACK'}] {idx:02d} {c['title'][:30]} -> {out_name}{info_note}")
            except Exception as e:
                print(f"[FAIL] {idx:02d} {c['title'][:30]}: {e}")

        await browser.close()

    with open("data/images.json", "w", encoding="utf-8") as f:
        json.dump(
            {"generated_at": datetime.now(KST).isoformat(), "date_label": date_label(end), "articles": captured},
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"[OK] 이미지 캡쳐 {len(captured)}건 완료")


if __name__ == "__main__":
    asyncio.run(main())
