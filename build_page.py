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
  <button class="copy-btn copy-all" data-copy-target="copy-all-text" type="button">📋 전체 복사 (카톡용)</button>
  {sectors_html}
</section>

<section class="project2">
  <h2>프로젝트2 — 네이버 메인 뉴스 캡쳐 ({image_count}건)</h2>
  <p class="hint">이미지를 길게 눌러 저장한 뒤 카톡으로 보내세요.</p>
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
        copy_data_json=json.dumps(copy_data, ensure_ascii=False).replace("</", "<\\/"),
    )
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("[OK] index.html 생성 완료")


if __name__ == "__main__":
    main()
