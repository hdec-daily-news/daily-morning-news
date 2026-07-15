# -*- coding: utf-8 -*-
"""data/links.json + data/images.json → index.html (GitHub Pages 게시용)"""
import json
import os
import zipfile

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
  <p class="download">
    <a href="output/latest.xlsx">엑셀 다운로드</a>
  </p>
</header>

<section class="infographics">
  <h2>📊 인포그래픽·차트 ({infographic_count}건)</h2>
  <p class="hint">"이미지 다운로드"를 누르거나, 이미지를 길게 눌러 저장한 뒤 카톡으로 보내세요.</p>
  <div class="gallery">
    {infographics_html}
  </div>
</section>

<section class="project1">
  <h2>프로젝트1 — 정치·정당·경제 주요기사</h2>
  <button class="copy-btn copy-all" data-copy-target="copy-all-text" type="button">📋 전체 복사 (카톡용)</button>
  {sectors_html}
</section>

<section class="project2">
  <div class="section-head">
    <h2>프로젝트2 — 네이버 메인 뉴스 캡쳐 ({image_count}건)</h2>
    <a class="zip-btn" href="output/images.zip">📦 이미지 전체 일괄 다운로드 ({total_image_count}장)</a>
  </div>
  <p class="hint">"이미지 다운로드"를 누르거나, 이미지를 길게 눌러 저장한 뒤 카톡으로 보내세요.</p>
  <div class="gallery">
    {gallery_html}
  </div>
</section>

<footer>
  <p>자동 생성 · Daily Morning News · 매일 GitHub Actions로 갱신</p>
</footer>

<div id="copy-toast" class="toast" hidden>복사됨!</div>
<script id="copy-data" type="application/json">{copy_data_json}</script>
<script>
(function () {{
  var data = JSON.parse(document.getElementById("copy-data").textContent);
  var toast = document.getElementById("copy-toast");
  function showToast() {{
    toast.hidden = false;
    clearTimeout(showToast._t);
    showToast._t = setTimeout(function () {{ toast.hidden = true; }}, 1500);
  }}
  function fallbackCopy(text) {{
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    var ok = false;
    try {{ ok = document.execCommand("copy"); }} catch (e) {{ ok = false; }}
    document.body.removeChild(ta);
    return ok;
  }}
  document.querySelectorAll(".copy-btn").forEach(function (btn) {{
    btn.addEventListener("click", function () {{
      var key = btn.getAttribute("data-copy-target");
      var text = data[key] || "";
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(text).then(showToast, function () {{
          if (fallbackCopy(text)) {{
            showToast();
          }} else {{
            alert("복사에 실패했습니다. 아래 텍스트를 직접 선택해 복사해주세요:\\n\\n" + text);
          }}
        }});
      }} else if (fallbackCopy(text)) {{
        showToast();
      }} else {{
        alert("복사에 실패했습니다. 아래 텍스트를 직접 선택해 복사해주세요:\\n\\n" + text);
      }}
    }});
  }});
}})();
</script>
</body>
</html>
"""

SECTOR_ICON = {"politics_main": "①", "dp": "②", "ppp": "③", "economy": "④"}


def sector_copy_text(sector):
    icon = SECTOR_ICON.get(sector["key"], "")
    lines = [f"{icon} {sector['label']}"]
    if sector["articles"]:
        for a in sector["articles"]:
            lines.append(f"- {a['title']}")
            lines.append(f"  {a['link']}")
    else:
        lines.append("(해당 시간대 기사 없음)")
    return "\n".join(lines)


def render_sector(sector):
    items = sector["articles"]
    lis = "\n".join(
        f'    <li><a href="{a["link"]}" target="_blank" rel="noopener">{a["title"]}</a></li>' for a in items
    ) or '    <li class="empty">(해당 시간대 기사 없음)</li>'
    icon = SECTOR_ICON.get(sector["key"], "")
    key = sector["key"]
    return f"""  <div class="sector">
    <div class="sector-head">
      <h3>{icon} {sector['label']}</h3>
      <button class="copy-btn" data-copy-target="sector-{key}" type="button">복사</button>
    </div>
    <ul>
{lis}
    </ul>
  </div>"""


def _image_card(img, link, label, extra_class=""):
    img_name = os.path.basename(img)
    cls = f"card {extra_class}".strip()
    return (
        f'    <div class="{cls}">\n'
        f'      <a class="card-thumb" href="{link}" target="_blank" rel="noopener">'
        f'<img src="{img}" alt="{label}" loading="lazy"></a>\n'
        f'      <span>{label}</span>\n'
        f'      <a class="dl-btn" href="{img}" download="{img_name}">⬇ 이미지 다운로드</a>\n'
        f'    </div>'
    )


def render_gallery(images):
    cards = []
    for item in images:
        img = item.get("image")
        if not img or not item.get("ok", True):
            continue
        cards.append(_image_card(img, item["link"], item["title"]))
    return "\n".join(cards) or "    <p>캡쳐된 이미지가 없습니다.</p>"


def render_infographics(images, graphics_items):
    cards = []
    for item in images:
        for info in item.get("infographics", []):
            img = info.get("image")
            if not img:
                continue
            label = info.get("caption") or item.get("title", "")
            cards.append(_image_card(img, item["link"], label, extra_class="infographic-card"))
    for g in graphics_items:
        img = g.get("image")
        if not img:
            continue
        label = f"[{g.get('source', '')}] {g.get('title', '')}".strip()
        cards.append(_image_card(img, g.get("link", "#"), label, extra_class="infographic-card"))
    return "\n".join(cards) or "    <p>오늘은 인포그래픽/차트가 발견되지 않았습니다.</p>", len(cards)


def build_images_zip(articles, graphics_items, out_path):
    """캡쳐 이미지 + 인포그래픽(기사 내 발견분 + 통신사 그래픽 코너 수집분)을 모두 모아
    ZIP 하나로 묶는다 (모바일에서 원탭 일괄 다운로드용)."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in articles:
            img = item.get("image")
            if img and item.get("ok", True) and os.path.exists(img):
                zf.write(img, arcname=os.path.basename(img))
                count += 1
            for info in item.get("infographics", []):
                info_img = info.get("image")
                if info_img and os.path.exists(info_img):
                    zf.write(info_img, arcname=f"infographics/{os.path.basename(info_img)}")
                    count += 1
        for g in graphics_items:
            g_img = g.get("image")
            if g_img and os.path.exists(g_img):
                zf.write(g_img, arcname=f"graphics/{os.path.basename(g_img)}")
                count += 1
    return count


def main():
    with open("data/links.json", encoding="utf-8") as f:
        links_data = json.load(f)

    images_data = {"articles": []}
    if os.path.exists("data/images.json"):
        with open("data/images.json", encoding="utf-8") as f:
            images_data = json.load(f)

    graphics_data = {"items": []}
    if os.path.exists("data/graphics.json"):
        with open("data/graphics.json", encoding="utf-8") as f:
            graphics_data = json.load(f)

    sectors_html = "\n".join(render_sector(s) for s in links_data["sectors"])
    gallery_html = render_gallery(images_data.get("articles", []))
    ok_images = [a for a in images_data.get("articles", []) if a.get("ok", True) and a.get("image")]
    infographics_html, infographic_count = render_infographics(
        images_data.get("articles", []), graphics_data.get("items", [])
    )
    total_image_count = build_images_zip(
        images_data.get("articles", []), graphics_data.get("items", []), "output/images.zip"
    )

    sector_texts = {f"sector-{s['key']}": sector_copy_text(s) for s in links_data["sectors"]}
    all_text = f"{links_data['date_label']} 일일 정치 주요뉴스\n\n" + "\n\n".join(
        sector_copy_text(s) for s in links_data["sectors"]
    )
    copy_data = dict(sector_texts, **{"copy-all-text": all_text})

    html = TEMPLATE.format(
        date_label=links_data["date_label"],
        window_start=links_data["window_start"][:16].replace("T", " "),
        window_end=links_data["window_end"][:16].replace("T", " "),
        sectors_html=sectors_html,
        gallery_html=gallery_html,
        image_count=len(ok_images),
        infographics_html=infographics_html,
        infographic_count=infographic_count,
        total_image_count=total_image_count,
        copy_data_json=json.dumps(copy_data, ensure_ascii=False).replace("</", "<\\/"),
    )
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("[OK] index.html 생성 완료")


if __name__ == "__main__":
    main()
