# -*- coding: utf-8 -*-
"""data/links.json + data/images.json → index.html (GitHub Pages 게시용)"""
import json
import os

TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>일일 정치 주요뉴스 {date_label}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header>
  <h1>일일 정치 주요뉴스</h1>
  <p class="date">{date_label} · 기준 {window_start} ~ {window_end}</p>
  <p class="download"><a href="output/latest.xlsx">엑셀 다운로드</a></p>
</header>

<section class="project1">
  <h2>프로젝트1 — 정치·정당·경제 주요기사</h2>
  {sectors_html}
</section>

<section class="project2">
  <h2>프로젝트2 — 네이버 메인 뉴스 캡쳐 ({image_count}건)</h2>
  <div class="gallery">
    {gallery_html}
  </div>
</section>

<footer>
  <p>자동 생성 · Daily Morning News · 매일 GitHub Actions로 갱신</p>
</footer>
</body>
</html>
"""

SECTOR_ICON = {"politics_main": "①", "dp": "②", "ppp": "③", "economy": "④"}


def render_sector(sector):
    items = sector["articles"]
    lis = "\n".join(
        f'    <li><a href="{a["link"]}" target="_blank" rel="noopener">{a["title"]}</a></li>' for a in items
    ) or '    <li class="empty">(해당 시간대 기사 없음)</li>'
    icon = SECTOR_ICON.get(sector["key"], "")
    return f"""  <div class="sector">
    <h3>{icon} {sector['label']}</h3>
    <ul>
{lis}
    </ul>
  </div>"""


def render_gallery(images):
    cards = []
    for item in images:
        img = item.get("image")
        if not img or not item.get("ok", True):
            continue
        cards.append(
            f'    <a class="card" href="{item["link"]}" target="_blank" rel="noopener">'
            f'<img src="{img}" alt="{item["title"]}" loading="lazy">'
            f'<span>{item["title"]}</span></a>'
        )
    return "\n".join(cards) or "    <p>캡쳐된 이미지가 없습니다.</p>"


def main():
    with open("data/links.json", encoding="utf-8") as f:
        links_data = json.load(f)

    images_data = {"articles": []}
    if os.path.exists("data/images.json"):
        with open("data/images.json", encoding="utf-8") as f:
            images_data = json.load(f)

    sectors_html = "\n".join(render_sector(s) for s in links_data["sectors"])
    gallery_html = render_gallery(images_data.get("articles", []))
    ok_images = [a for a in images_data.get("articles", []) if a.get("ok", True) and a.get("image")]

    html = TEMPLATE.format(
        date_label=links_data["date_label"],
        window_start=links_data["window_start"][:16].replace("T", " "),
        window_end=links_data["window_end"][:16].replace("T", " "),
        sectors_html=sectors_html,
        gallery_html=gallery_html,
        image_count=len(ok_images),
    )
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("[OK] index.html 생성 완료")


if __name__ == "__main__":
    main()
